"""End to end: parsed fixtures → Postgres → raw → compact → data model."""

import os
from pathlib import Path

import asyncpg
import duckdb
import pytest
import pytest_asyncio

from etl.parsers.page import PageParser
from etl.repositories.entry_repo import PgEntryRepository
from export import compact, modelo, raw

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)
FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest_asyncio.fixture
async def loaded():
    pool = await asyncpg.create_pool(DATABASE_URL)
    repo = PgEntryRepository(pool)
    parser = PageParser()
    for name in ("full_entry.xml", "multi_lot_with_terms.xml", "minimal_entry.xml"):
        page = parser.parse((FIXTURES / name).read_bytes(), "outsiders")
        for entry in page.entries:
            await repo.process_entry(entry)
    yield
    await pool.execute("TRUNCATE contract_folder_status, contracting_party CASCADE")
    await pool.close()


@pytest.mark.asyncio
@pytest.mark.usefixtures("loaded")
async def test_model_builds_from_raw(tmp_path: Path) -> None:
    raw.export(tmp_path / "raw", DATABASE_URL)
    compact.compact(tmp_path / "todo", [tmp_path / "raw"])
    # Blocking audits (grain, not-null keys, referential integrity) run here.
    manifest = modelo.export(tmp_path / "modelo", tmp_path / "todo")

    tablas = manifest["tablas"]
    assert isinstance(tablas, dict)
    for table in (
        "licitacion",
        "ciclo_licitacion",
        "presupuesto_lote",
        "adjudicacion",
        "lote",
        "organo",
        "empresa",
        "cpv",
        "documento",
    ):
        assert (tmp_path / "modelo" / f"{table}.parquet").exists(), table
    # The manifest documents each table for the explorer.
    assert tablas["licitacion"]["grupo"] == "entidades"
    assert tablas["ciclo_licitacion"]["grupo"] == "actividad"
    assert ["licitacion_key", "BIGINT"] in tablas["licitacion"]["columnas"]

    out = str(tmp_path / "modelo") + "/"
    con = duckdb.connect()
    # Public ids keep the formula of the previous flat export.
    entry_ids = con.execute(
        f"SELECT placsp_id, id FROM '{out}licitacion.parquet'"
    ).fetchall()
    assert len(entry_ids) == 3
    for placsp_id, public_id in entry_ids:
        expected = con.execute(
            "SELECT md5('licitacion:' || ?)::UUID::VARCHAR", [placsp_id]
        )
        assert public_id == expected.fetchone()[0]  # type: ignore[index]

    # Every licitacion has at least one budget row (real lots or the whole object).
    missing = con.execute(
        f"SELECT count(*) FROM '{out}licitacion.parquet' l WHERE NOT EXISTS ("
        f" SELECT 1 FROM '{out}presupuesto_lote.parquet' o"
        " WHERE o.licitacion_key = l.licitacion_key)"
    ).fetchone()
    assert missing == (0,)
