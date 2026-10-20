"""Build the data model with SQLMesh and publish it as Parquet.

Runs the ``warehouse/`` SQLMesh project on a fresh DuckDB file over a
compacted raw set (:mod:`export.compact`), then writes one Parquet file per
table of the ``modelo`` and ``resumen`` schemas, plus ``manifest.json``. The
BORME (:mod:`borme.raw`, one directory per year) is optional: without it the
model is built with its BORME tables empty.

Usage::

    PYTHONPATH=src uv run python -m export.modelo <out_dir> <raw_dir> [<borme_dir>]
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from sqlmesh import Context

from borme.raw import ensure
from shared.logger import get_logger

logger = get_logger(__name__)

WAREHOUSE_DIR = Path(__file__).resolve().parents[2] / "warehouse"
SCHEMAS: tuple[str, ...] = ("modelo", "resumen")

# Few, large row groups: the browser explorer fetches one HTTP range per
# column chunk, so fewer groups means far fewer round trips.
_COPY_OPTS = "FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 500000"

_STATS = """
SELECT
  count(*) AS total_licitaciones,
  (SELECT count(*) FROM modelo.organo WHERE organo_key > 0) AS total_organos,
  (SELECT count(*) FROM modelo.empresa WHERE empresa_key > 0) AS total_empresas,
  coalesce(sum(presupuesto_sin_iva), 0)::DOUBLE AS importe_total,
  min(fecha_publicacion)::VARCHAR AS desde,
  max(fecha_actualizacion)::VARCHAR AS ultima_actualizacion
FROM modelo.ciclo_licitacion
"""


def build(raw_dir: Path, database: Path, borme_dir: Path) -> dict[str, dict[str, str]]:
    """Run every warehouse model over ``raw_dir`` and ``borme_dir`` into ``database``.

    Returns each published table's group (the folder under warehouse/models:
    entidades, actividad, resumenes) and description, for the manifest.
    """
    # SQLMesh logs every statement at INFO: keep the CI logs readable.
    logging.getLogger("sqlmesh").setLevel(logging.WARNING)
    os.environ["RAW_PATH"] = str(raw_dir.resolve())
    os.environ["BORME_PATH"] = str(borme_dir.resolve())
    os.environ["WAREHOUSE_DB"] = str(database.resolve())
    context = Context(paths=str(WAREHOUSE_DIR))
    try:
        context.plan(auto_apply=True, no_prompts=True)
        docs = {}
        for model in context.models.values():
            schema, _, table = model.name.replace('"', "").rpartition(".")
            if schema.rpartition(".")[2] in SCHEMAS:
                docs[table] = {
                    "grupo": model._path.parent.name if model._path else "",
                    "descripcion": model.description or "",
                }
        return docs
    finally:
        context.close()


def _select(con: duckdb.DuckDBPyConnection, schema: str, table: str) -> str:
    """SELECT that writes TIMESTAMPTZ as naive UTC and sorts by date if possible.

    DuckDB-WASM (the explorer) ships without ICU and cannot read TIMESTAMPTZ.
    """
    cols = con.execute(
        "SELECT column_name, data_type FROM information_schema.columns"
        " WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
        [schema, table],
    ).fetchall()
    exprs = [
        f'"{c}"::TIMESTAMP AS "{c}"' if t == "TIMESTAMP WITH TIME ZONE" else f'"{c}"'
        for c, t in cols
    ]
    names = {c for c, _ in cols}
    order = [c for c in ("fecha_publicacion", "licitacion_key") if c in names]
    order_by = f" ORDER BY {', '.join(order)}" if order else ""
    return f"SELECT {', '.join(exprs)} FROM {schema}.{table}{order_by}"


def publish(
    database: Path, out_dir: Path, docs: dict[str, dict[str, str]] | None = None
) -> dict[str, object]:
    """Copy every model and aggregate table to Parquet; return the manifest.

    The manifest lists each table's role, description and columns, so the
    explorer can show the schema without opening every file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(database), read_only=True)
    con.execute("SET TimeZone = 'UTC'")

    tables: dict[str, dict[str, object]] = {}
    for schema in SCHEMAS:
        names = con.execute(
            "SELECT table_name FROM information_schema.tables"
            " WHERE table_schema = ? ORDER BY table_name",
            [schema],
        ).fetchall()
        for (table,) in names:
            path = out_dir / f"{table}.parquet"
            con.execute(
                f"COPY ({_select(con, schema, table)}) TO '{path}' ({_COPY_OPTS})"
            )
            row = con.execute(f"SELECT count(*) FROM '{path}'").fetchone()
            columns = con.execute(
                "SELECT column_name, column_type"
                f" FROM (DESCRIBE SELECT * FROM '{path}')"
            ).fetchall()
            tables[table] = {
                "file": path.name,
                **(docs or {}).get(table, {}),
                "columnas": [list(c) for c in columns],
                "rows": row[0] if row else 0,
                "bytes": path.stat().st_size,
            }
            logger.info(
                "Published table=%s.%s rows=%s", schema, table, tables[table]["rows"]
            )

    cur = con.execute(_STATS)
    stat_names = [d[0] for d in cur.description or []]
    manifest: dict[str, object] = {
        "generado": datetime.now(UTC).isoformat(),
        "tablas": tables,
        "stats": dict(zip(stat_names, cur.fetchone() or (), strict=True)),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    return manifest


def export(
    out_dir: Path, raw_dir: Path, borme_dir: Path | None = None
) -> dict[str, object]:
    """Build the model over ``raw_dir`` and the BORME; publish it to ``out_dir``."""
    with tempfile.TemporaryDirectory() as tmp:
        database = Path(tmp) / "warehouse.duckdb"
        borme = ensure(borme_dir or Path(tmp) / "borme")
        docs = build(raw_dir, database, borme)
        return publish(database, out_dir, docs)


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    match args:
        case [out_dir, raw_dir, *borme] if len(borme) <= 1:
            borme_dir = Path(borme[0]) if borme else None
            manifest = export(Path(out_dir), Path(raw_dir), borme_dir)
            logger.info("Manifest: %s", manifest["stats"])
        case _:
            sys.exit("usage: export.modelo <out_dir> <raw_dir> [<borme_dir>]")


if __name__ == "__main__":
    main()
