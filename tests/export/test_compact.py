"""Tests for merging raw Parquet exports (export.compact)."""

from __future__ import annotations

from pathlib import Path

import duckdb

from export.compact import FOLDER_CHILDREN, compact

_EMPTY = {
    "contracting_party": "SELECT 'o' AS organo_ref, NULL::TIMESTAMPTZ AS updated,"
    " NULL::VARCHAR AS name WHERE false",
    "status_change": "SELECT NULL::VARCHAR AS entry_id, NULL::VARCHAR AS status_code,"
    " NULL::TIMESTAMPTZ AS updated WHERE false",
    "codice_code": "SELECT NULL::VARCHAR AS list, NULL::VARCHAR AS code,"
    " NULL::VARCHAR AS description WHERE false",
}


def _source(path: Path, tables: dict[str, str]) -> Path:
    """Write a raw export whose tables are the given queries (others empty)."""
    path.mkdir(parents=True)
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    defaults = dict.fromkeys(
        FOLDER_CHILDREN,
        "SELECT NULL::VARCHAR AS entry_id, NULL::BIGINT AS n WHERE false",
    )
    for name, query in (defaults | _EMPTY | tables).items():
        con.execute(f"COPY ({query}) TO '{path / name}.parquet' (FORMAT parquet)")
    return path


def _folder(entry_id: str, updated: str, name: str) -> str:
    return (
        f"SELECT '{entry_id}' AS entry_id, TIMESTAMPTZ '{updated}' AS updated,"
        f" '{name}' AS name, 'PUB' AS status_code"
    )


def _rows(out: Path, query: str) -> list[tuple[object, ...]]:
    return duckdb.sql(query.replace("$", f"{out}/")).fetchall()


def test_newest_snapshot_keeps_its_own_children(tmp_path: Path) -> None:
    old = _source(
        tmp_path / "2024",
        {
            "contract_folder_status": _folder("a", "2024-01-01", "Viejo"),
            "procurement_project_lot": "SELECT 'a' AS entry_id, unnest(['1', '2'])"
            " AS lot_number",
            "status_change": "SELECT 'a' AS entry_id, 'PUB' AS status_code,"
            " TIMESTAMPTZ '2024-01-01' AS updated",
        },
    )
    new = _source(
        tmp_path / "reciente",
        {
            "contract_folder_status": _folder("a", "2025-03-01", "Nuevo"),
            "procurement_project_lot": "SELECT 'a' AS entry_id, '9' AS lot_number",
            "status_change": "SELECT 'a' AS entry_id, 'ADJ' AS status_code,"
            " TIMESTAMPTZ '2025-03-01' AS updated",
        },
    )
    out = tmp_path / "todo"
    # Argument order does not matter when timestamps differ.
    compact(out, [new, old])

    assert _rows(out, "SELECT name FROM '$contract_folder_status.parquet'") == [
        ("Nuevo",)
    ]
    assert _rows(out, "SELECT lot_number FROM '$procurement_project_lot.parquet'") == [
        ("9",)
    ]
    # The status timeline is the union of every snapshot.
    assert _rows(
        out, "SELECT status_code FROM '$status_change.parquet' ORDER BY updated"
    ) == [("PUB",), ("ADJ",)]


def test_later_source_wins_ties(tmp_path: Path) -> None:
    first = _source(
        tmp_path / "a", {"contract_folder_status": _folder("x", "2025-01-01", "A")}
    )
    second = _source(
        tmp_path / "b", {"contract_folder_status": _folder("x", "2025-01-01", "B")}
    )
    out = tmp_path / "todo"
    compact(out, [first, second])
    assert _rows(out, "SELECT name FROM '$contract_folder_status.parquet'") == [("B",)]


def test_party_and_codes_keep_latest_version(tmp_path: Path) -> None:
    party = "SELECT 'P1' AS organo_ref, TIMESTAMPTZ '{ts}' AS updated, '{name}' AS name"
    code = "SELECT 'cpv' AS list, '45000000' AS code, '{d}' AS description"
    old = _source(
        tmp_path / "old",
        {
            "contract_folder_status": _folder("a", "2024-01-01", "x"),
            "contracting_party": party.format(ts="2024-01-01", name="Ayto. viejo"),
            "codice_code": code.format(d="Obras (v1)"),
        },
    )
    new = _source(
        tmp_path / "new",
        {
            "contract_folder_status": _folder("b", "2025-01-01", "y"),
            "contracting_party": party.format(ts="2025-01-01", name="Ayto. nuevo"),
            "codice_code": code.format(d="Obras"),
        },
    )
    out = tmp_path / "todo"
    manifest = compact(out, [old, new])

    assert _rows(out, "SELECT name FROM '$contracting_party.parquet'") == [
        ("Ayto. nuevo",)
    ]
    assert _rows(out, "SELECT description FROM '$codice_code.parquet'") == [("Obras",)]
    assert manifest["tablas"]["contract_folder_status"]["rows"] == 2  # type: ignore[index]
