"""Tests for the raw BORME Parquet layer."""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb

from borme.parser import read
from borme.raw import SCHEMA, rows, write, year

FIXTURES = Path(__file__).parent / "fixtures"


def test_year_from_cache(tmp_path: Path) -> None:
    cache = tmp_path / "cache" / "2026"
    cache.mkdir(parents=True)
    for name in ("BORME-A-2026-200-28.xml", "BORME-A-2026-200-99.xml"):
        shutil.copy(FIXTURES / name, cache / name)

    counts = year(tmp_path / "cache", tmp_path / "raw", 2026)

    assert counts == {"filing": 4, "act": 12, "position": 13}
    out = tmp_path / "raw" / "2026"
    keys = duckdb.sql(
        f"SELECT count(*), count(DISTINCT (doc_id, number, n)) FROM '{out}/act.parquet'"
    ).fetchone()
    assert keys == (12, 12)
    sheet = duckdb.sql(
        f"SELECT sheet FROM '{out}/filing.parquet' WHERE number = 460001"
    ).fetchone()
    assert sheet == ("M 812345",)


def test_empty_year_keeps_the_schema(tmp_path: Path) -> None:
    write(tmp_path, rows([]))
    for table, columns in SCHEMA.items():
        described = duckdb.sql(
            f"DESCRIBE SELECT * FROM '{tmp_path}/{table}.parquet'"
        ).fetchall()
        assert [c[0] for c in described] == list(columns), table


def test_rows_link_positions_to_their_act() -> None:
    doc = read(FIXTURES / "BORME-A-2026-200-28.xml")
    assert doc is not None
    out = rows([doc])
    acts = {(a["number"], a["n"]): a["kind"] for a in out["act"]}
    for p in out["position"]:
        assert (p["number"], p["act_n"]) in acts
