"""Sync the API's tables of the data model to Cloudflare D1.

D1 mirrors a few tables of the model (worker/schema.sql). Each run compares
today's model Parquet (:mod:`export.modelo`) with the previous one and writes
SQL that applies only the difference: upserts for new or changed rows,
deletes for rows that disappeared. Without a previous model it writes a full
load for an empty database, licitaciones in ``fecha_publicacion`` order so
that rowids are chronological (the API reads "newest first" as a reverse
rowid scan).

Lookup tables (organo, empresa, cpv…) are written before the tables that
reference them (the full-text triggers on licitacion read names from organo
and empresa) and deleted after them.

Usage::

    PYTHONPATH=src uv run python -m export.d1 <out_dir> <modelo_dir> [<prev_modelo_dir>]
    scripts/d1-load.sh <out_dir>
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from shared.config import Settings
from shared.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class D1Table:
    """A D1 table fed from the model: its key and the query that builds it.

    ``query`` runs in DuckDB with the model's tables as views in the current
    schema; its columns are the D1 columns.
    """

    key: tuple[str, ...]
    query: str
    order: str = ""


# Load order: lookup tables first. Placeholder rows (keys <= 0) stay out of D1
# so the API's LEFT JOINs return NULL for them.
D1_TABLES: dict[str, D1Table] = {
    "estado": D1Table(
        ("estado_key",),
        "SELECT estado_key, codigo, descripcion FROM estado WHERE estado_key > 0",
    ),
    "resultado": D1Table(
        ("resultado_key",),
        "SELECT resultado_key, codigo, descripcion FROM resultado"
        " WHERE resultado_key > 0",
    ),
    "cpv": D1Table(
        ("cpv_key",),
        "SELECT cpv_key, codigo, descripcion FROM cpv WHERE cpv_key > 0",
    ),
    "lugar": D1Table(
        ("lugar_key",),
        "SELECT lugar_key, codigo, nombre, nombre_placsp, nuts2 AS comunidad"
        " FROM lugar WHERE lugar_key > 0",
    ),
    "organo": D1Table(
        ("organo_key",),
        "SELECT o.organo_key, o.id, o.nombre, o.nif, o.tipo,"
        " coalesce(r.licitaciones, 0) AS licitaciones"
        " FROM organo o LEFT JOIN resumen_organo r USING (organo_key)"
        " WHERE o.organo_key > 0",
    ),
    "empresa": D1Table(
        ("empresa_key",),
        "SELECT e.empresa_key, e.nif, e.nombre,"
        " coalesce(r.contratos, 0) AS contratos"
        " FROM empresa e LEFT JOIN resumen_empresa r USING (empresa_key)"
        " WHERE e.empresa_key > 0",
    ),
    "licitacion": D1Table(
        ("licitacion_key",),
        # The API's row: licitacion joined to its ciclo_licitacion row.
        "SELECT l.licitacion_key, l.id, l.expediente, l.titulo, l.url_place,"
        " c.organo_key, c.estado_key, c.cpv_key, c.lugar_key,"
        " c.adjudicatario_key, c.resultado_key, l.tipo_contrato_codigo,"
        " l.tipo_contrato, l.procedimiento_codigo, l.procedimiento,"
        " l.tramitacion, l.sistema_contratacion, l.financiacion_codigo,"
        " l.financiacion, c.fecha_publicacion, c.fecha_actualizacion,"
        " c.fecha_limite, c.hora_limite, c.fecha_adjudicacion,"
        " c.fecha_formalizacion, c.presupuesto_sin_iva, c.presupuesto_con_iva,"
        " c.valor_estimado, l.duracion, l.duracion_unidad, c.num_lotes,"
        " c.num_ofertas, c.importe_adjudicado_sin_iva, c.num_documentos,"
        " l.tasa_subcontratacion_maxima"
        " FROM licitacion l JOIN ciclo_licitacion c USING (licitacion_key)",
        order="fecha_publicacion, licitacion_key",
    ),
    "adjudicacion": D1Table(
        ("licitacion_key", "resultado_n", "adjudicatario_n"),
        "SELECT licitacion_key, resultado_n, adjudicatario_n, empresa_key,"
        " organo_key, fecha_adjudicacion, importe_sin_iva, presupuesto_sin_iva"
        " FROM adjudicacion",
    ),
    "cambio_estado": D1Table(
        ("licitacion_key", "momento", "estado_key"),
        "SELECT licitacion_key, momento, estado_key FROM cambio_estado",
    ),
}

_LOOKUPS = ("estado", "resultado", "cpv", "lugar", "organo", "empresa")


def sql_literal(value: Any) -> str:
    """Render a Python value as a SQLite literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int | float | Decimal):
        return str(value)
    if isinstance(value, datetime) and value.tzinfo is None:
        value = value.replace(tzinfo=UTC)  # the model's Parquet stores naive UTC
    if isinstance(value, datetime | date | time):
        return "'" + value.isoformat() + "'"
    return "'" + str(value).replace("'", "''") + "'"


def _values(rows: list[tuple[Any, ...]]) -> str:
    return ",\n".join("(" + ", ".join(sql_literal(v) for v in r) + ")" for r in rows)


def insert_statement(table: str, cols: list[str], rows: list[tuple[Any, ...]]) -> str:
    """Plain multi-row INSERT (full loads into an empty database)."""
    return f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n{_values(rows)};"


def upsert_statement(
    table: str, spec: D1Table, cols: list[str], rows: list[tuple[Any, ...]]
) -> str:
    """Multi-row upsert keyed on the table's natural key (keeps licitacion rid)."""
    sets = ", ".join(f"{c} = excluded.{c}" for c in cols if c not in spec.key)
    # Tables whose columns are all key (cambio_estado) have nothing to update.
    action = f"DO UPDATE SET {sets}" if sets else "DO NOTHING"
    return (
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n{_values(rows)}\n"
        f"ON CONFLICT({', '.join(spec.key)}) {action};"
    )


def delete_statement(table: str, spec: D1Table, keys: list[tuple[Any, ...]]) -> str:
    """Delete rows by key (row-value IN list for composite keys)."""
    if len(spec.key) == 1:
        listed = ", ".join(sql_literal(k[0]) for k in keys)
        return f"DELETE FROM {table} WHERE {spec.key[0]} IN ({listed});"
    rows = ", ".join("(" + ", ".join(sql_literal(v) for v in k) + ")" for k in keys)
    return f"DELETE FROM {table} WHERE ({', '.join(spec.key)}) IN (VALUES {rows});"


def meta_statement() -> str:
    """Record the sync time shown by /salud."""
    return (
        "INSERT INTO meta (clave, valor) VALUES "
        f"('ultima_sync', {sql_literal(datetime.now(UTC))}) "
        "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor;"
    )


def _attach(con: duckdb.DuckDBPyConnection, schema: str, model_dir: Path) -> None:
    """Expose every Parquet file of a model directory as views in ``schema``."""
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    for path in sorted(model_dir.glob("*.parquet")):
        quoted = str(path).replace("'", "''")
        con.execute(
            f"CREATE VIEW {schema}.{path.stem} AS"
            f" SELECT * FROM read_parquet('{quoted}')"
        )


def _batches(
    cur: duckdb.DuckDBPyConnection, size: int
) -> Iterator[list[tuple[Any, ...]]]:
    while batch := cur.fetchmany(size):
        yield batch


class _Writer:
    """Numbered SQL files of at most ``chunk_rows`` rows each."""

    def __init__(self, out_dir: Path, chunk_rows: int) -> None:
        self.out_dir = out_dir
        self.chunk_rows = chunk_rows
        self.files = 0
        self._lines: list[str] = []
        self._rows = 0

    def add(self, statement: str, rows: int) -> None:
        self._lines.append(statement)
        self._rows += rows
        if self._rows >= self.chunk_rows:
            self.flush()

    def flush(self) -> None:
        if not self._lines:
            return
        self.files += 1
        path = self.out_dir / f"d1-{self.files:04d}.sql"
        path.write_text("\n".join(self._lines) + "\n")
        self._lines, self._rows = [], 0


def build(
    out_dir: Path, modelo_dir: Path, prev_dir: Path | None, settings: Settings
) -> dict[str, dict[str, int]]:
    """Write the D1 SQL files; return upserted and deleted rows per table."""
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    _attach(con, "nuevo", modelo_dir)
    if prev_dir is not None:
        _attach(con, "previo", prev_dir)

    writer = _Writer(out_dir, settings.d1_chunk_rows)
    per_stmt = settings.d1_rows_per_insert
    summary: dict[str, dict[str, int]] = {}

    sides = ("nuevo", "previo") if prev_dir is not None else ("nuevo",)
    for side in sides:
        con.execute(f"SET schema = '{side}'")
        for table, spec in D1_TABLES.items():
            con.execute(f"CREATE TABLE main.{side}_{table} AS {spec.query}")
    con.execute("SET schema = 'main'")

    def deletes(table: str) -> None:
        if prev_dir is None:
            return
        spec = D1_TABLES[table]
        keys = ", ".join(spec.key)
        cur = con.execute(
            f"SELECT {keys} FROM previo_{table} EXCEPT SELECT {keys} FROM nuevo_{table}"
        )
        n = 0
        for batch in _batches(cur, per_stmt * 5):
            writer.add(delete_statement(table, spec, batch), len(batch))
            n += len(batch)
        summary.setdefault(table, {})["borradas"] = n

    def upserts(table: str) -> None:
        spec = D1_TABLES[table]
        # Set difference treats NULLs as equal, so unchanged rows drop out.
        query = (
            f"SELECT * FROM nuevo_{table}"
            if prev_dir is None
            else f"SELECT * FROM (FROM nuevo_{table} EXCEPT FROM previo_{table})"
        )
        order = f" ORDER BY {spec.order}" if spec.order else ""
        cur = con.execute(query + order)
        cols = [d[0] for d in cur.description or []]
        n = 0
        for batch in _batches(cur, per_stmt):
            statement = (
                insert_statement(table, cols, batch)
                if prev_dir is None
                else upsert_statement(table, spec, cols, batch)
            )
            writer.add(statement, len(batch))
            n += len(batch)
        summary.setdefault(table, {})["escritas"] = n

    referencing = [t for t in D1_TABLES if t not in _LOOKUPS]
    for table in reversed(referencing):
        deletes(table)
    for table in D1_TABLES:
        upserts(table)
    for table in reversed(_LOOKUPS):
        deletes(table)

    writer.add(meta_statement(), 1)
    writer.flush()
    logger.info("D1 batch files=%d full=%s %s", writer.files, prev_dir is None, summary)
    return summary


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    match args:
        case [out_dir, modelo_dir]:
            build(Path(out_dir), Path(modelo_dir), None, Settings())
        case [out_dir, modelo_dir, prev_dir]:
            prev = Path(prev_dir)
            # A missing previous model (first run) means a full load.
            build(
                Path(out_dir),
                Path(modelo_dir),
                prev if (prev / "licitacion.parquet").exists() else None,
                Settings(),
            )
        case _:
            sys.exit("usage: export.d1 <out_dir> <modelo_dir> [<prev_modelo_dir>]")


if __name__ == "__main__":
    main()
