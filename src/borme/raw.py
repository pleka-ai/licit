"""Write the raw BORME layer: one Parquet set per year, parsed from the cache.

For each year directory of the XML cache (:mod:`borme.download`) this writes
``<out>/<año>/{filing,act,position}.parquet`` with natural keys: a filing is
``(doc_id, number)``, an act ``(doc_id, number, n)`` and a position
``(doc_id, number, act_n, n)``, ``n`` being the order in the text. A year is a
pure function of its cached XML, so re-parsing never needs the BOE.

Usage::

    PYTHONPATH=src uv run python -m borme.raw <cache_dir> <out_dir> [<año>...]
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from borme.parser import Document, read
from shared.logger import get_logger

logger = get_logger(__name__)

# Column order and DuckDB types of every raw table: also the schema of an
# empty year, so readers work before any BORME is ingested.
SCHEMA: dict[str, dict[str, str]] = {
    "filing": {
        "doc_id": "VARCHAR",
        "province": "VARCHAR",
        "published": "DATE",
        "number": "BIGINT",
        "company": "VARCHAR",
        "text": "VARCHAR",
        "volume": "VARCHAR",
        "page": "VARCHAR",
        "section": "VARCHAR",
        "sheet": "VARCHAR",
        "entry": "VARCHAR",
        "entry_date": "DATE",
    },
    "act": {
        "doc_id": "VARCHAR",
        "number": "BIGINT",
        "n": "INTEGER",
        "kind": "VARCHAR",
        "text": "VARCHAR",
        "capital": "DOUBLE",
        "resulting_capital": "DOUBLE",
        "address": "VARCHAR",
        "new_name": "VARCHAR",
        "purpose": "VARCHAR",
        "start_of_operations": "DATE",
    },
    "position": {
        "doc_id": "VARCHAR",
        "number": "BIGINT",
        "act_n": "INTEGER",
        "n": "INTEGER",
        "role": "VARCHAR",
        "name": "VARCHAR",
    },
}

_COPY_OPTS = "FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 250000"


def rows(docs: list[Document]) -> dict[str, list[dict[str, Any]]]:
    """Flatten parsed documents into the rows of every raw table."""
    out: dict[str, list[dict[str, Any]]] = {t: [] for t in SCHEMA}
    for d in docs:
        for f in d.filings:
            r = f.registry
            out["filing"].append(
                {
                    "doc_id": d.id,
                    "province": d.province,
                    "published": d.date,
                    "number": f.number,
                    "company": f.company,
                    "text": f.text,
                    "volume": r.volume,
                    "page": r.page,
                    "section": r.section,
                    "sheet": r.sheet,
                    "entry": r.entry,
                    "entry_date": r.entry_date,
                }
            )
            for i, a in enumerate(f.acts, start=1):
                out["act"].append(
                    {
                        "doc_id": d.id,
                        "number": f.number,
                        "n": i,
                        "kind": a.kind,
                        "text": a.text,
                        "capital": a.capital,
                        "resulting_capital": a.resulting_capital,
                        "address": a.address,
                        "new_name": a.new_name,
                        "purpose": a.purpose,
                        "start_of_operations": a.start_of_operations,
                    }
                )
                for j, p in enumerate(a.positions, start=1):
                    out["position"].append(
                        {
                            "doc_id": d.id,
                            "number": f.number,
                            "act_n": i,
                            "n": j,
                            "role": p.role,
                            "name": p.name,
                        }
                    )
    return out


def write(out_dir: Path, table_rows: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    """Write one raw set (possibly empty) to ``out_dir``; return row counts."""
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    counts = {}
    for table, columns in SCHEMA.items():
        cols = ", ".join(f'"{c}" {t}' for c, t in columns.items())
        con.execute(f"CREATE OR REPLACE TABLE t ({cols})")
        data = table_rows.get(table) or []
        if data:
            frame = pd.DataFrame(data, columns=list(columns))
            con.register("frame", frame)
            con.execute("INSERT INTO t SELECT * FROM frame")
            con.unregister("frame")
        path = str(out_dir / f"{table}.parquet").replace("'", "''")
        con.execute(f"COPY t TO '{path}' ({_COPY_OPTS})")
        counts[table] = len(data)
    return counts


EMPTY = "vacio"


def ensure(borme_dir: Path) -> Path:
    """``borme_dir``, with an empty raw set added if it has no year yet.

    Readers glob every year directory; the empty set keeps the schema there
    before any BORME is ingested (and in tests).
    """
    if not any(borme_dir.glob("*/filing.parquet")):
        write(borme_dir / EMPTY, rows([]))
    return borme_dir


def year(cache_dir: Path, out_dir: Path, yr: int) -> dict[str, int]:
    """Parse every cached document of ``yr`` into ``out_dir/<yr>``."""
    docs = [d for p in sorted((cache_dir / str(yr)).glob("*.xml")) if (d := read(p))]
    counts = write(out_dir / str(yr), rows(docs))
    logger.info("BORME raw year=%d documents=%d %s", yr, len(docs), counts)
    return counts


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    match args:
        case [cache_dir, out_dir, *years]:
            cache = Path(cache_dir)
            wanted = [int(y) for y in years] or sorted(
                int(p.name) for p in cache.iterdir() if p.is_dir() and p.name.isdigit()
            )
            for yr in wanted:
                year(cache, Path(out_dir), yr)
        case _:
            sys.exit("usage: borme.raw <cache_dir> <out_dir> [<año>...]")


if __name__ == "__main__":
    main()
