"""Build the API's derived D1 tables from the compacted Parquet.

Aggregating 1.6M rows inside D1 hits its per-query time limit, so empresa,
organo, catalogo and the /salud stats are computed here with DuckDB and
shipped as SQL. Upserts only rewrite rows whose values changed, so the daily
run writes few rows.

Usage::

    PYTHONPATH=src uv run python -m export.derived <out_dir> <licitacion.parquet>

Writes ``d1-9001.sql`` … so ``scripts/d1-load.sh <out_dir>`` applies them after
any licitacion chunks in the same directory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import duckdb

from export.d1 import sql_literal
from shared.config import Settings
from shared.logger import get_logger

logger = get_logger(__name__)

_FIRST_FILE = 9001

_EMPRESA = """
SELECT adjudicatario_nif AS nif,
       arg_max(adjudicatario, fecha_actualizacion) AS nombre,
       count(*) AS contratos
FROM lic WHERE adjudicatario_nif IS NOT NULL GROUP BY 1 ORDER BY 1
"""
_ORGANO = """
SELECT organo_id AS id,
       arg_max(organo, fecha_actualizacion) AS nombre,
       arg_max(organo_nif, fecha_actualizacion) AS nif,
       count(*) AS licitaciones
FROM lic WHERE organo_id IS NOT NULL GROUP BY 1 ORDER BY 1
"""
_CATALOGO = """
SELECT 'tipo_contrato' AS tipo, tipo_contrato AS valor, max(type_code) AS codigo,
       NULL AS descripcion, count(*) AS n
FROM lic WHERE tipo_contrato IS NOT NULL GROUP BY 2
UNION ALL
SELECT 'estado', estado, max(status_code), NULL, count(*)
FROM lic WHERE estado IS NOT NULL GROUP BY 2
UNION ALL
SELECT 'procedimiento', procedimiento, max(procedure_code), NULL, count(*)
FROM lic WHERE procedimiento IS NOT NULL GROUP BY 2
UNION ALL
SELECT 'tramitacion', tramitacion, NULL, NULL, count(*)
FROM lic WHERE tramitacion IS NOT NULL GROUP BY 2
UNION ALL
SELECT 'organo_tipo', organo_tipo, NULL, NULL, count(*)
FROM lic WHERE organo_tipo IS NOT NULL GROUP BY 2
UNION ALL
SELECT 'cpv', cpv_principal, cpv_principal, max(cpv_principal_desc), count(*)
FROM lic WHERE cpv_principal IS NOT NULL GROUP BY 2
"""
_STATS = """
SELECT count(*) AS total_licitaciones,
       count(DISTINCT organo_id) AS total_organos,
       count(DISTINCT adjudicatario_nif) AS total_empresas,
       round(coalesce(sum(presupuesto_sin_iva), 0))::BIGINT AS importe_total,
       strftime(min(fecha_publicacion), '%Y-%m-%dT%H:%M:%S+00:00') AS desde,
       strftime(max(fecha_actualizacion), '%Y-%m-%dT%H:%M:%S+00:00')
         AS ultima_actualizacion
FROM lic
"""


def _upserts(
    table: str,
    key: str,
    cols: list[str],
    rows: list[tuple[Any, ...]],
    rows_per_stmt: int,
) -> list[str]:
    """Multi-row upserts that skip rows whose values did not change."""
    sets = ", ".join(f"{c} = excluded.{c}" for c in cols if c != key)
    changed = " OR ".join(f"{table}.{c} IS NOT excluded.{c}" for c in cols if c != key)
    out = []
    for i in range(0, len(rows), rows_per_stmt):
        values = ",\n".join(
            "(" + ", ".join(sql_literal(v) for v in r) + ")"
            for r in rows[i : i + rows_per_stmt]
        )
        out.append(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n{values}\n"
            f"ON CONFLICT({key}) DO UPDATE SET {sets} WHERE {changed};"
        )
    return out


def build(out_dir: Path, parquet: Path, settings: Settings) -> None:
    """Write the derived-table SQL files into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    path = str(parquet).replace("'", "''")
    con.execute(f"CREATE TEMP VIEW lic AS SELECT * FROM read_parquet('{path}')")

    per_stmt = settings.d1_rows_per_insert * 5
    files: list[list[str]] = []
    empresa = con.execute(_EMPRESA).fetchall()
    files.append(
        _upserts("empresa", "nif", ["nif", "nombre", "contratos"], empresa, per_stmt)
    )
    organo = con.execute(_ORGANO).fetchall()
    files.append(
        _upserts(
            "organo", "id", ["id", "nombre", "nif", "licitaciones"], organo, per_stmt
        )
    )
    catalogo = con.execute(_CATALOGO).fetchall()
    cat_cols = "tipo, valor, codigo, descripcion, n"
    files.append(
        ["DELETE FROM catalogo;"]
        + [
            f"INSERT INTO catalogo ({cat_cols}) VALUES\n"
            + ",\n".join(
                "(" + ", ".join(sql_literal(v) for v in r) + ")"
                for r in catalogo[i : i + per_stmt]
            )
            + ";"
            for i in range(0, len(catalogo), per_stmt)
        ]
    )
    cur = con.execute(_STATS)
    names = [d[0] for d in cur.description or []]
    stats = dict(zip(names, cur.fetchone() or (), strict=True))
    files.append(
        [
            "INSERT INTO meta (clave, valor) VALUES "
            f"('stats', {sql_literal(json.dumps(stats))}) "
            "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;"
        ]
    )

    for n, statements in enumerate(files, start=_FIRST_FILE):
        (out_dir / f"d1-{n}.sql").write_text("\n".join(statements) + "\n")
    logger.info(
        "Derived empresa=%d organo=%d catalogo=%d stats=%s",
        len(empresa),
        len(organo),
        len(catalogo),
        stats,
    )


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    match args:
        case [out_dir, parquet]:
            build(Path(out_dir), Path(parquet), Settings())
        case _:
            sys.exit("usage: export.derived <out_dir> <licitacion.parquet>")


if __name__ == "__main__":
    main()
