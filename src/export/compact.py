"""Merge several Parquet snapshots into one deduplicated set.

Each source directory holds ``licitacion/lote/adjudicacion/cpv/empresa``
Parquet files exported by :mod:`export.parquet` (an archived year, the daily
window, or a previous compaction). A licitacion seen in several sources keeps
the newest snapshot's fields and children, the earliest ``fecha_publicacion``
and the union of ``historial_estados`` — the same rules as the D1 upsert.

Output is sorted by ``fecha_publicacion`` so readers (the in-browser explorer,
the D1 rebuild) can prune row groups by date.

Usage::

    PYTHONPATH=src uv run python -m export.compact <out_dir> <src_dir> [<src_dir>...]
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from export.columns import LICITACION_COLS
from shared.logger import get_logger

logger = get_logger(__name__)

_CHILDREN = ("lote", "adjudicacion", "cpv")
# Few, large row groups: the browser explorer fetches one HTTP range per
# column chunk, so fewer groups means far fewer round trips.
_COPY_OPTS = "FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 500000"
_HISTORIAL_TYPE = '[{"fecha": "VARCHAR", "estado": "VARCHAR"}]'
_TIMESTAMPTZ = ("fecha_publicacion", "fecha_actualizacion")

# Small pre-aggregated tables so the explorer's first queries are instant.
_SUMMARIES = {
    "resumen_mensual": """
        SELECT date_trunc('month', fecha_publicacion)::DATE AS mes, tipo_contrato,
               count(*) AS licitaciones,
               round(sum(presupuesto_sin_iva)) AS importe_licitado
        FROM licitacion GROUP BY ALL ORDER BY mes, tipo_contrato
    """,
    "resumen_organo": """
        SELECT organo_id, arg_max(organo, fecha_actualizacion) AS organo,
               arg_max(organo_nif, fecha_actualizacion) AS organo_nif,
               count(*) AS licitaciones,
               round(sum(presupuesto_sin_iva)) AS importe_licitado
        FROM licitacion WHERE organo_id IS NOT NULL
        GROUP BY organo_id ORDER BY licitaciones DESC
    """,
    "licitacion_abierta": """
        SELECT id, fecha_publicacion::DATE AS fecha_publicacion, fecha_limite,
               titulo, organo, tipo_contrato, estado, presupuesto_sin_iva,
               cpv_principal, lugar_subentidad, url_place
        FROM licitacion WHERE fecha_limite >= current_date
        ORDER BY fecha_limite, presupuesto_sin_iva DESC
    """,
    "resumen_empresa": """
        SELECT adjudicatario_nif, arg_max(adjudicatario, length(adjudicatario))
                 AS adjudicatario,
               count(*) AS contratos,
               round(sum(importe_adjudicacion)) AS importe_adjudicado
        FROM adjudicacion WHERE adjudicatario_nif IS NOT NULL
        GROUP BY adjudicatario_nif ORDER BY contratos DESC
    """,
}


def _files(sources: list[Path], table: str) -> str:
    paths = [
        str(s / f"{table}.parquet")
        for s in sources
        if (s / f"{table}.parquet").exists()
    ]
    if not paths:
        msg = f"No {table}.parquet in {sources}"
        raise FileNotFoundError(msg)
    return "[" + ", ".join("'" + p.replace("'", "''") + "'" for p in paths) + "]"


def compact(out_dir: Path, sources: list[Path]) -> dict[str, object]:
    """Write the merged Parquet set to ``out_dir`` and return its manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")

    con.execute(
        f"""
        CREATE TEMP TABLE src AS
        SELECT *, parse_dirpath(filename) AS _src
        FROM read_parquet({_files(sources, "licitacion")},
                          union_by_name = true, filename = true)
        """
    )
    other_cols = ", ".join(
        f"w.{c}"
        for c in LICITACION_COLS
        if c not in ("fecha_publicacion", "historial_estados")
    )
    con.execute(
        f"""
        CREATE TEMP TABLE licitacion AS
        WITH ranked AS (
          SELECT *, row_number() OVER (
            PARTITION BY id ORDER BY fecha_actualizacion DESC, _src DESC) AS _rn
          FROM src
        ),
        agg AS (
          SELECT id,
                 min(fecha_publicacion) AS fecha_publicacion,
                 to_json(list_sort(list_distinct(flatten(list(
                   from_json(historial_estados, '{_HISTORIAL_TYPE}'))))))::VARCHAR
                   AS historial_estados
          FROM src GROUP BY id
        )
        SELECT {other_cols}, agg.fecha_publicacion, agg.historial_estados, w._src
        FROM ranked w JOIN agg USING (id)
        WHERE w._rn = 1
        """
    )

    tables: dict[str, dict[str, int | str]] = {}

    def write(name: str, query: str) -> None:
        path = out_dir / f"{name}.parquet"
        con.execute(f"COPY ({query}) TO '{path}' ({_COPY_OPTS})")
        rows = con.execute(f"SELECT count(*) FROM '{path}'").fetchone()
        tables[name] = {
            "file": path.name,
            "rows": rows[0] if rows else 0,
            "bytes": path.stat().st_size,
        }
        logger.info("Compacted table=%s rows=%s", name, tables[name]["rows"])

    # Timestamps are written as naive UTC: DuckDB-WASM ships without ICU and
    # cannot cast TIMESTAMPTZ.
    lic_cols = ", ".join(
        f"{c}::TIMESTAMP AS {c}" if c in _TIMESTAMPTZ else c for c in LICITACION_COLS
    )
    write(
        "licitacion",
        f"SELECT {lic_cols} FROM licitacion ORDER BY fecha_publicacion, id",
    )
    for child in _CHILDREN:
        write(
            child,
            f"""
            SELECT c.* EXCLUDE (filename)
            FROM read_parquet({_files(sources, child)},
                              union_by_name = true, filename = true) c
            JOIN licitacion w
              ON w.id = c.licitacion_id AND w._src = parse_dirpath(c.filename)
            ORDER BY w.fecha_publicacion, c.licitacion_id
            """,
        )
    write(
        "empresa",
        f"""
        SELECT nif, arg_max(nombre, length(nombre)) AS nombre,
               any_value(ciudad) AS ciudad, any_value(tipo) AS tipo
        FROM read_parquet({_files(sources, "empresa")}, union_by_name = true)
        GROUP BY nif ORDER BY nif
        """,
    )

    adj = out_dir / "adjudicacion.parquet"
    con.execute(f"CREATE TEMP VIEW adjudicacion AS SELECT * FROM '{adj}'")
    for name, query in _SUMMARIES.items():
        write(name, query)

    stats = con.execute(
        """
        SELECT count(*), count(DISTINCT organo_id), count(DISTINCT adjudicatario_nif),
               coalesce(sum(presupuesto_sin_iva), 0)::DOUBLE,
               min(fecha_publicacion)::VARCHAR, max(fecha_actualizacion)::VARCHAR
        FROM licitacion
        """
    ).fetchone()
    manifest: dict[str, object] = {
        "generado": datetime.now(UTC).isoformat(),
        "tablas": tables,
        "stats": dict(
            zip(
                (
                    "total_licitaciones",
                    "total_organos",
                    "total_empresas",
                    "importe_total",
                    "desde",
                    "ultima_actualizacion",
                ),
                stats or (),
                strict=False,
            )
        ),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    return manifest


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    match args:
        case [out_dir, *sources] if sources:
            manifest = compact(Path(out_dir), [Path(s) for s in sources])
            logger.info("Manifest: %s", manifest["stats"])
        case _:
            sys.exit("usage: export.compact <out_dir> <src_dir> [<src_dir>...]")


if __name__ == "__main__":
    main()
