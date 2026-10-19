"""Sync the basic licitacion rows to Cloudflare D1.

D1's free tier allows 100k rows written per day, so each run sends at
most ``d1_max_rows_per_run`` changed licitaciones (newest first) inside a
rolling window of ``d1_window_days``. The ``d1_sync`` table in Postgres
remembers what D1 already holds; it travels with the nightly pg_dump.

Usage::

    PYTHONPATH=src uv run python -m export.d1 build <out.sql> <pending.json>
    wrangler d1 execute licit --remote --file <out.sql>
    PYTHONPATH=src uv run python -m export.d1 commit <pending.json>
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg

from export.columns import LICITACION_COLS, licitacion_select
from shared.config import Settings
from shared.logger import get_logger

logger = get_logger(__name__)

_SYNC_DDL = """
CREATE TABLE IF NOT EXISTS d1_sync (
  id uuid PRIMARY KEY,
  fecha_actualizacion timestamptz NOT NULL
)
"""

_UPDATE_SET = ", ".join(f"{c}=excluded.{c}" for c in LICITACION_COLS if c != "id")


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
    """Build an idempotent INSERT ... ON CONFLICT for one licitacion."""
    cols = ", ".join(LICITACION_COLS)
    vals = ", ".join(sql_literal(row[c]) for c in LICITACION_COLS)
    return (
        f"INSERT INTO licitacion ({cols}) VALUES ({vals}) "
        f"ON CONFLICT(id) DO UPDATE SET {_UPDATE_SET};"
    )


async def build(sql_path: Path, pending_path: Path, settings: Settings) -> int:
    """Write the D1 SQL batch and the list of rows it contains."""
    cutoff = datetime.now(UTC) - timedelta(days=settings.d1_window_days)
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute(_SYNC_DDL)
        rows = await conn.fetch(
            f"""
            SELECT m.* FROM ({licitacion_select()}) m
            LEFT JOIN d1_sync s ON s.id = m.id::uuid
            WHERE m.fecha_publicacion >= $1
              AND (s.id IS NULL OR s.fecha_actualizacion < m.fecha_actualizacion)
            ORDER BY m.fecha_actualizacion DESC
            LIMIT $2
            """,
            cutoff,
            settings.d1_max_rows_per_run,
        )
    finally:
        await conn.close()

    lines = [f"DELETE FROM licitacion WHERE fecha_publicacion < {sql_literal(cutoff)};"]
    lines += [upsert_statement(dict(r)) for r in rows]
    lines.append(
        "INSERT INTO meta (clave, valor) VALUES "
        f"('ultima_sync', {sql_literal(datetime.now(UTC))}) "
        "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor;"
    )
    sql_path.write_text("\n".join(lines) + "\n")
    pending = {
        "cutoff": cutoff.isoformat(),
        "rows": [[r["id"], r["fecha_actualizacion"].isoformat()] for r in rows],
    }
    pending_path.write_text(json.dumps(pending))
    logger.info("D1 batch rows=%d cutoff=%s", len(rows), cutoff.date())
    return len(rows)


async def commit(pending_path: Path, settings: Settings) -> None:
    """Record a successfully applied batch in ``d1_sync``."""
    pending = json.loads(pending_path.read_text())
    cutoff = datetime.fromisoformat(pending["cutoff"])
    records = [(r[0], datetime.fromisoformat(r[1])) for r in pending["rows"]]
    conn = await asyncpg.connect(settings.database_url)
    try:
        async with conn.transaction():
            await conn.execute(_SYNC_DDL)
            await conn.executemany(
                """
                INSERT INTO d1_sync (id, fecha_actualizacion) VALUES ($1::uuid, $2)
                ON CONFLICT (id) DO UPDATE
                SET fecha_actualizacion = excluded.fecha_actualizacion
                """,
                records,
            )
            await conn.execute(
                """
                DELETE FROM d1_sync s USING mv_licitacion m
                WHERE s.id = m.id AND m.fecha_publicacion < $1
                """,
                cutoff,
            )
    finally:
        await conn.close()
    logger.info("D1 sync committed rows=%d", len(records))


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    settings = Settings()
    match args:
        case ["build", sql_path, pending_path]:
            asyncio.run(build(Path(sql_path), Path(pending_path), settings))
        case ["commit", pending_path]:
            asyncio.run(commit(Path(pending_path), settings))
        case _:
            sys.exit("usage: export.d1 build <out.sql> <pending.json> | commit <json>")


if __name__ == "__main__":
    main()
