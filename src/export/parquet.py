"""Export the warehouse to Parquet files for the in-browser explorer.

Usage::

    PYTHONPATH=src uv run python -m export.parquet <out_dir>

Writes one zstd Parquet file per basic table plus ``manifest.json`` with
row counts and headline stats. CI uploads the rolling window to
``parquet/reciente/`` and archived years to ``parquet/historico/<year>/``;
the Worker serves them at ``/data/parquet/``.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from export.columns import (
    ADJUDICACION_SELECT,
    CPV_SELECT,
    LOTE_SELECT,
    licitacion_select,
)
from shared.config import Settings
from shared.logger import get_logger

logger = get_logger(__name__)

# Postgres-side queries (pushed down via postgres_query).
_PG_TABLES: dict[str, str] = {
    "licitacion": licitacion_select() + " ORDER BY m.fecha_publicacion",
    "lote": LOTE_SELECT,
    "adjudicacion": ADJUDICACION_SELECT,
    "cpv": CPV_SELECT,
    "empresa": "SELECT * FROM empresa",
}

_COPY_OPTS = "FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 100000"


def export(out_dir: Path, database_url: str) -> dict[str, object]:
    """Copy every table to ``out_dir`` and return the manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    dsn = database_url.replace("'", "''")
    con.execute(f"ATTACH '{dsn}' AS pg (TYPE postgres, READ_ONLY)")

    tables: dict[str, dict[str, int | str]] = {}
    for name, sql in _PG_TABLES.items():
        path = out_dir / f"{name}.parquet"
        escaped = sql.replace("'", "''")
        con.execute(
            f"COPY (SELECT * FROM postgres_query('pg', '{escaped}')) "
            f"TO '{path}' ({_COPY_OPTS})"
        )
        rows = con.execute(f"SELECT count(*) FROM '{path}'").fetchone()
        tables[name] = {
            "file": path.name,
            "rows": int(rows[0]) if rows else 0,
            "bytes": path.stat().st_size,
        }
        logger.info("Exported table=%s rows=%s", name, tables[name]["rows"])

    stats = con.execute(
        f"""
        SELECT count(*), count(DISTINCT organo_id),
               coalesce(sum(presupuesto_sin_iva), 0)::DOUBLE,
               max(fecha_actualizacion)::VARCHAR
        FROM '{out_dir / "licitacion.parquet"}'
        """
    ).fetchone()
    manifest: dict[str, object] = {
        "generado": datetime.now(UTC).isoformat(),
        "tablas": tables,
        "stats": {
            "total_licitaciones": stats[0] if stats else 0,
            "total_organos": stats[1] if stats else 0,
            "total_empresas": tables["empresa"]["rows"],
            "importe_total": stats[2] if stats else 0,
            "ultima_actualizacion": stats[3] if stats else None,
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    return manifest


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    out_dir = Path(args[0] if args else "out/parquet")
    manifest = export(out_dir, Settings().database_url)
    logger.info("Manifest: %s", manifest["stats"])


if __name__ == "__main__":
    main()
