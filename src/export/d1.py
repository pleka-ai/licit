"""Sync the basic licitacion rows to Cloudflare D1 (full history).

Two modes:

* incremental (daily): rows of the Postgres window that changed since the
  last sync, tracked in ``d1_sync_v2`` (travels with the nightly pg_dump).
* ``--todo`` (historico): every row in the database, used when back-filling
  an archived year on a fresh Postgres.

Upserts never let an older snapshot overwrite a newer one, keep the earliest
``fecha_publicacion`` and merge ``historial_estados``, so archived years and
the live window can be loaded in any order.

Usage::

    PYTHONPATH=src uv run python -m export.d1 build <out_dir> [--todo]
    for f in <out_dir>/*.sql; do wrangler d1 execute licit --remote --file $f; done
    PYTHONPATH=src uv run python -m export.d1 commit <out_dir>/pending.json
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg

from export.columns import LICITACION_COLS, licitacion_select
from shared.config import Settings
from shared.logger import get_logger

logger = get_logger(__name__)

# PLACSP's "summary" is an auto-generated recap of other columns: not worth
# the D1 storage. It is still published in Parquet.
D1_COLS: tuple[str, ...] = tuple(c for c in LICITACION_COLS if c != "descripcion")

_SYNC_TABLE = "d1_sync_v2"
_SYNC_DDL = f"""
DROP TABLE IF EXISTS d1_sync;
CREATE TABLE IF NOT EXISTS {_SYNC_TABLE} (
  id uuid PRIMARY KEY,
  fecha_actualizacion timestamptz NOT NULL
)
"""

_MERGED_HISTORIAL = (
    "(SELECT json_group_array(json(value)) FROM (SELECT value FROM ("
    " SELECT value FROM json_each(licitacion.historial_estados)"
    " UNION SELECT value FROM json_each(excluded.historial_estados))"
    " ORDER BY json_extract(value, '$.fecha')))"
)
_SPECIAL_SET = {
    "fecha_publicacion": (
        "min(coalesce(licitacion.fecha_publicacion, excluded.fecha_publicacion),"
        " coalesce(excluded.fecha_publicacion, licitacion.fecha_publicacion))"
    ),
    "historial_estados": _MERGED_HISTORIAL,
}
_UPDATE_SET = ", ".join(
    f"{c}={_SPECIAL_SET.get(c, f'excluded.{c}')}" for c in D1_COLS if c != "id"
)


def sql_literal(value: Any) -> str:
    """Render a Python value as a SQLite literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int | float | Decimal):
        return str(value)
    if isinstance(value, datetime | date | time):
        return "'" + value.isoformat() + "'"
    return "'" + str(value).replace("'", "''") + "'"


def upsert_statement(row: dict[str, Any]) -> str:
    """Build an order-independent upsert for one licitacion."""
    cols = ", ".join(D1_COLS)
    vals = ", ".join(sql_literal(row[c]) for c in D1_COLS)
    return (
        f"INSERT INTO licitacion ({cols}) VALUES ({vals}) "
        f"ON CONFLICT(id) DO UPDATE SET {_UPDATE_SET} "
        "WHERE excluded.fecha_actualizacion >= licitacion.fecha_actualizacion;"
    )


def _meta_statement() -> str:
    return (
        "INSERT INTO meta (clave, valor) VALUES "
        f"('ultima_sync', {sql_literal(datetime.now(UTC))}) "
        "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor;"
    )


async def build(out_dir: Path, settings: Settings, *, todo: bool) -> int:
    """Write chunked D1 SQL files plus ``pending.json``; return row count."""
    out_dir.mkdir(parents=True, exist_ok=True)
    query = f"SELECT m.* FROM ({licitacion_select(with_pk=True)}) m"
    if not todo:
        query += (
            f" LEFT JOIN {_SYNC_TABLE} s ON s.id = m.pk"
            " WHERE s.id IS NULL OR s.fecha_actualizacion < m.fecha_actualizacion"
        )
    query += " ORDER BY m.fecha_actualizacion DESC"

    pending: list[list[str]] = []
    chunk: list[str] = []
    n_files = 0

    def flush() -> None:
        nonlocal chunk, n_files
        if not chunk:
            return
        n_files += 1
        (out_dir / f"d1-{n_files:04d}.sql").write_text("\n".join(chunk) + "\n")
        chunk = []

    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute(_SYNC_DDL)
        async with conn.transaction():
            async for record in conn.cursor(query, prefetch=2000):
                row = dict(record)
                chunk.append(upsert_statement(row))
                pending.append([str(row["pk"]), row["fecha_actualizacion"].isoformat()])
                if len(chunk) >= settings.d1_chunk_rows:
                    flush()
    finally:
        await conn.close()

    chunk.append(_meta_statement())
    flush()
    (out_dir / "pending.json").write_text(json.dumps({"rows": pending}))
    logger.info("D1 batch rows=%d files=%d todo=%s", len(pending), n_files, todo)
    return len(pending)


async def commit(pending_path: Path, settings: Settings) -> None:
    """Record a successfully applied batch in the sync table."""
    pending = json.loads(pending_path.read_text())
    records = [(r[0], datetime.fromisoformat(r[1])) for r in pending["rows"]]
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute(_SYNC_DDL)
        async with conn.transaction():
            await conn.executemany(
                f"""
                INSERT INTO {_SYNC_TABLE} (id, fecha_actualizacion)
                VALUES ($1::uuid, $2)
                ON CONFLICT (id) DO UPDATE
                SET fecha_actualizacion = excluded.fecha_actualizacion
                """,
                records,
            )
            # Forget folders pruned from the Postgres window.
            await conn.execute(
                f"""
                DELETE FROM {_SYNC_TABLE} s WHERE NOT EXISTS (
                  SELECT 1 FROM contract_folder_status c WHERE c.id = s.id)
                """
            )
    finally:
        await conn.close()
    logger.info("D1 sync committed rows=%d", len(records))


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    settings = Settings()
    match args:
        case ["build", out_dir, *flags] if set(flags) <= {"--todo"}:
            asyncio.run(build(Path(out_dir), settings, todo="--todo" in flags))
        case ["commit", pending_path]:
            asyncio.run(commit(Path(pending_path), settings))
        case _:
            sys.exit("usage: export.d1 build <out_dir> [--todo] | commit <json>")


if __name__ == "__main__":
    main()
