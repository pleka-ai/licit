"""Merge several raw Parquet exports into one deduplicated history.

Each source directory holds the tables written by :mod:`export.raw` (an
archived year, the daily window, or a previous compaction). Sources are given
oldest first; on ties the later one wins. Merge rules:

* a folder keeps its newest snapshot (``updated``), and every child table keeps
  the rows of that same snapshot, so a folder never mixes two versions;
* ``status_change`` is the union of every observed status, which is how the
  model recovers the first publication date and the status timeline;
* ``contracting_party`` keeps the version stamped with the newest folder;
* ``codice_code`` keeps each code's latest description.

Usage::

    PYTHONPATH=src uv run python -m export.compact <out_dir> <src_dir> [<src_dir>...]
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from export.raw import RAW_TABLES
from shared.logger import get_logger

logger = get_logger(__name__)

_FOLDER = "contract_folder_status"
_SPECIAL = (_FOLDER, "contracting_party", "status_change", "codice_code")
FOLDER_CHILDREN: tuple[str, ...] = tuple(t for t in RAW_TABLES if t not in _SPECIAL)

_COPY_OPTS = "FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 250000"


def _read(con: duckdb.DuckDBPyConnection, sources: list[Path], table: str) -> str:
    """Register ``src_<table>``: every source's rows plus their ``_src`` rank."""
    selects = [
        f"SELECT *, {i} AS _src FROM read_parquet('{_quote(s / f'{table}.parquet')}')"
        for i, s in enumerate(sources)
        if (s / f"{table}.parquet").exists()
    ]
    if not selects:
        msg = f"No {table}.parquet in {sources}"
        raise FileNotFoundError(msg)
    view = f"src_{table}"
    con.execute(f"CREATE TEMP VIEW {view} AS " + " UNION ALL BY NAME ".join(selects))
    return view


def _quote(path: Path) -> str:
    return str(path).replace("'", "''")


def compact(out_dir: Path, sources: list[Path]) -> dict[str, object]:
    """Write the merged raw set to ``out_dir`` and return its manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")

    folders = _read(con, sources, _FOLDER)
    con.execute(
        f"""
        CREATE TEMP TABLE winner AS
        SELECT entry_id, arg_max(_src, (updated, _src)) AS _src
        FROM {folders} GROUP BY entry_id
        """
    )

    queries: dict[str, str] = {
        _FOLDER: f"""
            SELECT f.* EXCLUDE (_src) FROM {folders} f
            JOIN winner w USING (entry_id, _src)
            ORDER BY f.updated, f.entry_id
        """
    }
    for table in FOLDER_CHILDREN:
        view = _read(con, sources, table)
        queries[table] = f"""
            SELECT c.* EXCLUDE (_src) FROM {view} c
            JOIN winner w USING (entry_id, _src)
            ORDER BY c.entry_id
        """
    queries["status_change"] = f"""
        SELECT DISTINCT entry_id, status_code, updated
        FROM {_read(con, sources, "status_change")}
        WHERE entry_id IN (SELECT entry_id FROM winner)
        ORDER BY entry_id, updated
    """
    parties = _read(con, sources, "contracting_party")
    queries["contracting_party"] = f"""
        SELECT * EXCLUDE (_src, _rn) FROM (
          SELECT *, row_number() OVER (
            PARTITION BY organo_ref ORDER BY updated DESC, _src DESC) AS _rn
          FROM {parties})
        WHERE _rn = 1 ORDER BY organo_ref
    """
    codes = _read(con, sources, "codice_code")
    queries["codice_code"] = f"""
        SELECT list, code, arg_max(description, _src) AS description
        FROM {codes} GROUP BY list, code ORDER BY list, code
    """

    tables: dict[str, dict[str, int | str]] = {}
    for name, query in queries.items():
        path = out_dir / f"{name}.parquet"
        con.execute(f"COPY ({query}) TO '{_quote(path)}' ({_COPY_OPTS})")
        row = con.execute(f"SELECT count(*) FROM '{_quote(path)}'").fetchone()
        tables[name] = {
            "file": path.name,
            "rows": row[0] if row else 0,
            "bytes": path.stat().st_size,
        }
        logger.info("Compacted raw table=%s rows=%s", name, tables[name]["rows"])

    manifest: dict[str, object] = {
        "generado": datetime.now(UTC).isoformat(),
        "tablas": tables,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    return manifest


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    match args:
        case [out_dir, *sources] if sources:
            compact(Path(out_dir), [Path(s) for s in sources])
        case _:
            sys.exit("usage: export.compact <out_dir> <src_dir> [<src_dir>...]")


if __name__ == "__main__":
    main()
