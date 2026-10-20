"""Integration test: parsed fixtures → Postgres → raw Parquet with natural keys."""

import os
from pathlib import Path

import asyncpg
import duckdb
import pytest
import pytest_asyncio

from etl.parsers.page import PageParser
from etl.repositories.entry_repo import PgEntryRepository
from export.raw import RAW_TABLES, export

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)
FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest_asyncio.fixture
async def loaded():
    pool = await asyncpg.create_pool(DATABASE_URL)
    repo = PgEntryRepository(pool)
    parser = PageParser()
    for name in ("full_entry.xml", "multi_lot_with_terms.xml"):
        page = parser.parse((FIXTURES / name).read_bytes(), "outsiders")
        for entry in page.entries:
            await repo.process_entry(entry)
    yield
    await pool.execute("TRUNCATE contract_folder_status, contracting_party CASCADE")
    await pool.close()


@pytest.mark.asyncio
@pytest.mark.usefixtures("loaded")
async def test_raw_export_uses_natural_keys(tmp_path: Path) -> None:
    manifest = export(tmp_path, DATABASE_URL)
    assert set(manifest["tablas"]) == set(RAW_TABLES)  # type: ignore[call-overload]

    con = duckdb.connect()

    def rows(sql: str) -> list[tuple[object, ...]]:
        return con.execute(sql.replace("$", str(tmp_path) + "/")).fetchall()

    folders = rows("SELECT entry_id, organo_ref FROM '$contract_folder_status.parquet'")
    assert len(folders) == 2
    assert all(entry_id and organo_ref for entry_id, organo_ref in folders)
    columns = {
        r[0] for r in rows("DESCRIBE SELECT * FROM '$contract_folder_status.parquet'")
    }
    assert "id" not in columns  # Postgres uuids never leave the database

    # Every child points at an exported folder.
    for table in ("procurement_project_lot", "tender_result", "document_reference"):
        orphans = rows(
            f"SELECT count(*) FROM '${table}.parquet' c WHERE c.entry_id NOT IN"
            " (SELECT entry_id FROM '$contract_folder_status.parquet')"
        )
        assert orphans == [(0,)], table

    # Winners resolve to a result of the same folder through the ordinal.
    unmatched = rows(
        "SELECT count(*) FROM '$winning_party.parquet' w"
        " LEFT JOIN '$tender_result.parquet' r"
        "   ON r.entry_id = w.entry_id AND r.n = w.result_n"
        " WHERE r.n IS NULL"
    )
    assert unmatched == [(0,)]

    # Ordinals are a dense 1..k sequence per folder.
    gaps = rows(
        "SELECT entry_id FROM '$cpv_classification.parquet'"
        " GROUP BY entry_id HAVING max(n) <> count(*)"
    )
    assert gaps == []

    lots = rows("SELECT count(*) FROM '$procurement_project_lot.parquet'")
    assert lots[0][0] > 0
    assert rows("SELECT count(*) FROM '$status_change.parquet'") == [(2,)]
