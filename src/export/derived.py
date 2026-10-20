"""Build the API's derived D1 rows (catalogs and /salud stats) from the model.

Aggregating the whole model inside D1 hits its per-query time limit, so the
filter catalogs and the headline stats are computed here with DuckDB over the
model's Parquet (:mod:`export.modelo`) and shipped as SQL.

Usage::

    PYTHONPATH=src uv run python -m export.derived <out_dir> <modelo_dir>

Writes ``d1-9001.sql`` … so ``scripts/d1-load.sh <out_dir>`` applies them after
the table chunks written by :mod:`export.d1` in the same directory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

from export.d1 import sql_literal
from shared.config import Settings
from shared.logger import get_logger

logger = get_logger(__name__)

_FIRST_FILE = 9001

# Joined once: every licitacion with its labels.
_LIC = """
CREATE TEMP VIEW lic AS
SELECT f.*, l.tipo_contrato, l.tipo_contrato_codigo, l.procedimiento,
       l.procedimiento_codigo, l.tramitacion, e.codigo AS estado_codigo,
       e.descripcion AS estado, o.tipo AS organo_tipo, c.codigo AS cpv,
       c.descripcion AS cpv_descripcion
FROM ciclo_licitacion f
JOIN licitacion l USING (licitacion_key)
JOIN estado e USING (estado_key)
JOIN organo o USING (organo_key)
JOIN cpv c USING (cpv_key)
"""
_CATALOGO = """
SELECT 'tipo_contrato' AS tipo, tipo_contrato AS valor,
       max(tipo_contrato_codigo) AS codigo, NULL AS descripcion, count(*) AS n
FROM lic WHERE tipo_contrato IS NOT NULL GROUP BY 2
UNION ALL
SELECT 'estado', estado, max(estado_codigo), NULL, count(*)
FROM lic WHERE estado_key > 0 GROUP BY 2
UNION ALL
SELECT 'procedimiento', procedimiento, max(procedimiento_codigo), NULL, count(*)
FROM lic WHERE procedimiento IS NOT NULL GROUP BY 2
UNION ALL
SELECT 'tramitacion', tramitacion, NULL, NULL, count(*)
FROM lic WHERE tramitacion IS NOT NULL GROUP BY 2
UNION ALL
SELECT 'organo_tipo', organo_tipo, NULL, NULL, count(*)
FROM lic WHERE organo_tipo IS NOT NULL GROUP BY 2
UNION ALL
SELECT 'cpv', cpv, cpv, max(cpv_descripcion), count(*)
FROM lic WHERE cpv_key > 0 GROUP BY 2
"""
_STATS = """
SELECT count(*) AS total_licitaciones,
       count(DISTINCT organo_key) FILTER (WHERE organo_key > 0) AS total_organos,
       (SELECT count(*) FROM resumen_empresa) AS total_empresas,
       round(coalesce(sum(presupuesto_sin_iva), 0))::BIGINT AS importe_total,
       strftime(min(fecha_publicacion), '%Y-%m-%dT%H:%M:%S+00:00') AS desde,
       strftime(max(fecha_actualizacion), '%Y-%m-%dT%H:%M:%S+00:00')
         AS ultima_actualizacion
FROM ciclo_licitacion
"""


def build(out_dir: Path, modelo_dir: Path, settings: Settings) -> None:
    """Write the derived-row SQL files into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    for path in sorted(modelo_dir.glob("*.parquet")):
        quoted = str(path).replace("'", "''")
        con.execute(
            f"CREATE VIEW {path.stem} AS SELECT * FROM read_parquet('{quoted}')"
        )
    con.execute(_LIC)

    per_stmt = settings.d1_rows_per_insert * 5
    catalogo = con.execute(_CATALOGO).fetchall()
    cat_cols = "tipo, valor, codigo, descripcion, n"
    files: list[list[str]] = [
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
    ]
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
    logger.info("Derived catalogo=%d stats=%s", len(catalogo), stats)


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    match args:
        case [out_dir, modelo_dir]:
            build(Path(out_dir), Path(modelo_dir), Settings())
        case _:
            sys.exit("usage: export.derived <out_dir> <modelo_dir>")


if __name__ == "__main__":
    main()
