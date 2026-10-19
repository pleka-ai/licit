"""Drop tenders older than the ETL window so the nightly dump stays small.

Older years live on as frozen Parquet under ``parquet/historico/``.

Usage::

    PYTHONPATH=src uv run python -m export.prune
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import asyncpg

from shared.config import Settings
from shared.logger import get_logger

logger = get_logger(__name__)


async def prune(settings: Settings) -> int:
    """Delete folders not updated within the window; return rows deleted."""
    cutoff = datetime.now(UTC) - timedelta(days=settings.etl_window_days)
    conn = await asyncpg.connect(settings.database_url)
    try:
        status = await conn.execute(
            "DELETE FROM contract_folder_status WHERE updated < $1", cutoff
        )
        await conn.execute("SELECT refresh_mv_licitacion()")
        await conn.execute("SELECT refresh_mv_landing_stats()")
    finally:
        await conn.close()
    deleted = int(status.split()[-1])
    logger.info("Pruned folders=%d cutoff=%s", deleted, cutoff.date())
    return deleted


def main() -> None:
    asyncio.run(prune(Settings()))


if __name__ == "__main__":
    main()
