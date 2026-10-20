"""Feed reader handler — CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import shutil
import tempfile
import urllib.parse
import zipfile
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
import httpx

from etl.parsers.page import PageParser
from etl.repositories.entry_repo import PgEntryRepository
from etl.repositories.failed_entry_repo import PgFailedEntryRepository
from etl.repositories.sync_state_repo import PgSyncStateRepository
from etl.services.feed_reader import FeedReaderService
from shared.config import Settings
from shared.enums import ROOT_FILENAMES, FeedType
from shared.logger import get_logger
from shared.models.etl import SyncResult

logger = get_logger(__name__)

_FEED_TYPES = [FeedType.OUTSIDERS, FeedType.INSIDERS]

_EMPTY_FEED = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
)

_SEED_BASE_URL = "https://contrataciondelsectorpublico.gob.es/sindicacion"
_SEED_FEED_PATHS: dict[str, str] = {
    FeedType.OUTSIDERS: "sindicacion_1044/PlataformasAgregadasSinMenores",
    FeedType.INSIDERS: "sindicacion_643/licitacionesPerfilesContratanteCompleto3",
}


# ------------------------------------------------------------------ Transport


class LocalFeedTransport(httpx.AsyncBaseTransport):
    """httpx transport that reads ATOM files from disk.

    Use with ``base_url`` set to the year directory as a file:// URI
    so that relative filenames from ``<link rel="next">`` resolve
    correctly.  Newer PLACSP zips use absolute URLs in next links;
    the *base_dir* fallback resolves those by filename.
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = Path(urllib.parse.unquote(request.url.path))
        if not path.exists():
            # Absolute URLs (https://contrataciondelestado.es/…) won't
            # resolve to a local path.  Fall back to filename-only lookup.
            alt = self._base_dir / path.name
            if alt.exists():
                path = alt
            else:
                logger.info("Local file not found (cross-zip boundary): %s", path)
                return httpx.Response(200, content=_EMPTY_FEED)
        content = path.read_bytes()
        logger.debug("File read path=%s size=%d bytes", path, len(content))
        return httpx.Response(200, content=content)


# ----------------------------------------------------------- Seed download


def archive_name(feed_type: str, year: int) -> str:
    """File name of a yearly archive in the zip cache."""
    return f"{feed_type}_{year}.zip"


async def _download_and_extract(
    feed_type: str,
    year: int,
    year_dir: Path,
    zip_dir: Path | None = None,
) -> None:
    """Extract a yearly zip archive into *year_dir*, downloading it if needed.

    With *zip_dir*, an archive already there is reused and a downloaded one is
    kept, so archived years are fetched from PLACSP only once.
    """
    base_name = _SEED_FEED_PATHS[feed_type]
    url = f"{_SEED_BASE_URL}/{base_name}_{year}.zip"
    zip_path = (zip_dir or year_dir.parent) / archive_name(feed_type, year)

    year_dir.mkdir(parents=True, exist_ok=True)

    if zip_dir is not None and zip_path.exists():
        logger.info("Cached archive feed_type=%s year=%d", feed_type, year)
    else:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading feed_type=%s year=%d url=%s", feed_type, year, url)
        timeout = httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0)
        partial = zip_path.with_suffix(".part")
        async with (
            httpx.AsyncClient(follow_redirects=True, timeout=timeout) as http,
            http.stream("GET", url) as resp,
        ):
            resp.raise_for_status()
            with open(partial, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)
        partial.rename(zip_path)

    logger.info("Extracting feed_type=%s year=%d", feed_type, year)
    await asyncio.to_thread(_extract_zip, zip_path, year_dir, keep=zip_dir is not None)


def _extract_zip(zip_path: Path, dest: Path, *, keep: bool = False) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    if not keep:
        zip_path.unlink()


# ---------------------------------------------------------- Pair resolution


def resolve_pairs(
    local_dir: str | None,
    years: list[int] | None,
    feed_types: list[str] | None = None,
) -> list[tuple[str, int]]:
    """Determine (feed_type, year) pairs to process."""
    feed_types = feed_types or list(_FEED_TYPES)
    if years and not local_dir:
        msg = "--years requires --local"
        raise ValueError(msg)

    if not local_dir:
        return [(ft, 0) for ft in feed_types]

    pairs = _discover_local_pairs(Path(local_dir), years, feed_types)
    logger.info("Local index built file_count=%d base_dir=%s", len(pairs), local_dir)
    return pairs


def _discover_local_pairs(
    base: Path,
    years: list[int] | None,
    feed_types: list[str],
) -> list[tuple[str, int]]:
    """Scan local feed directory for (feed_type, year) pairs."""
    pairs: list[tuple[str, int]] = []

    for ft in feed_types:
        ft_dir = base / ft
        if not ft_dir.is_dir():
            continue

        root_name = ROOT_FILENAMES[ft]
        found_years: list[int] = []

        for child in ft_dir.iterdir():
            if not child.is_dir() or not child.name.isdigit():
                continue
            yr = int(child.name)
            if years and yr not in years:
                continue
            if not (child / root_name).exists():
                continue
            found_years.append(yr)

        pairs.extend((ft, yr) for yr in sorted(found_years, reverse=True))

    return pairs


# ------------------------------------------------------- Parallel execution


async def run_feeds_parallel(
    pairs: list[tuple[str, int]],
    sync_fn: Callable[[str, int], Awaitable[SyncResult]],
    max_concurrent: int,
) -> dict[str, Any]:
    """Run all feed pairs concurrently, aggregate results, isolate errors."""
    sem = asyncio.Semaphore(max_concurrent)

    async def _guarded(ft: str, yr: int) -> SyncResult:
        async with sem:
            return await sync_fn(ft, yr)

    raw = await asyncio.gather(
        *[_guarded(ft, yr) for ft, yr in pairs],
        return_exceptions=True,
    )

    total_processed = 0
    total_stale = 0
    total_failed = 0
    total_pages = 0
    success = True

    for r in raw:
        if isinstance(r, BaseException):
            logger.exception("Feed failed: %s", r)
            success = False
        else:
            total_processed += r.processed
            total_stale += r.skipped_stale
            total_failed += r.failed
            total_pages += r.pages

    return {
        "success": success,
        "processed": total_processed,
        "skipped_stale": total_stale,
        "failed": total_failed,
        "pages": total_pages,
    }


# ----------------------------------------------------------- Sync one pair


def _make_http_client(
    feed_type: str,
    year: int,
    *,
    seed_dir: Path | None,
    local_dir: str | None,
) -> tuple[httpx.AsyncClient, str | None, Path | None]:
    """Build the httpx client and start URL for a single pair.

    Returns (http_client, start_url, cleanup_dir).
    """
    if seed_dir is not None:
        resolved = seed_dir.resolve()
        base_url = resolved.as_uri() + "/"
        return (
            httpx.AsyncClient(
                transport=LocalFeedTransport(resolved), base_url=base_url
            ),
            ROOT_FILENAMES[feed_type],
            seed_dir,
        )
    if local_dir:
        year_path = (Path(local_dir) / feed_type / str(year)).resolve()
        base_url = year_path.as_uri() + "/"
        return (
            httpx.AsyncClient(
                transport=LocalFeedTransport(year_path), base_url=base_url
            ),
            ROOT_FILENAMES[feed_type],
            None,
        )
    return httpx.AsyncClient(), None, None


async def _sync_one_pair(
    feed_type: str,
    year: int,
    *,
    pool: asyncpg.Pool,
    config: Settings,
    event: dict[str, Any],
) -> SyncResult:
    """Download (if seed), process, and clean up a single (feed_type, year)."""
    seed_dir: Path | None = None
    tmp_base: Path | None = event.get("_tmp_base")

    if event.get("seed") and tmp_base is not None:
        seed_dir = tmp_base / feed_type / str(year)
        try:
            await _download_and_extract(
                feed_type, year, seed_dir, zip_dir=event.get("zip_dir")
            )
        except (httpx.HTTPStatusError, httpx.TransportError):
            logger.exception(
                "Seed download FAILED feed_type=%s year=%d",
                feed_type,
                year,
            )
            raise

    http, start_url, cleanup_dir = _make_http_client(
        feed_type,
        year,
        seed_dir=seed_dir,
        local_dir=event.get("local_dir"),
    )

    try:
        async with http:
            svc = FeedReaderService(
                entry_repo=PgEntryRepository(pool),
                sync_repo=PgSyncStateRepository(pool),
                failed_repo=PgFailedEntryRepository(pool),
                parser=PageParser(),
                http_client=http,
                config=config,
            )
            is_local = seed_dir is not None or event.get("local_dir")
            return await svc.sync(
                feed_type=feed_type,
                year=year,
                start_url=start_url,
                end_date=event.get("end_date"),
                skip_stale_check=bool(is_local),
            )
    finally:
        if cleanup_dir is not None:
            shutil.rmtree(cleanup_dir, ignore_errors=True)
            logger.info("Cleaned up feed_type=%s year=%d", feed_type, year)


# ------------------------------------------------------------------ Handler


async def _handle(event: dict[str, Any]) -> dict[str, Any]:
    config = Settings()
    local_dir = event.get("local_dir")
    years = event.get("years")
    feed_type = event.get("feed_type")
    feed_types = [feed_type] if feed_type else None
    seed = event.get("seed", False)

    if seed:
        fts = feed_types or list(_FEED_TYPES)
        yrs = years or list(range(2017, datetime.now(UTC).year + 1))
        pairs = [(ft, yr) for ft in fts for yr in sorted(yrs, reverse=True)]
        event["_tmp_base"] = Path(tempfile.mkdtemp(prefix="licit-seed-"))
    else:
        pairs = resolve_pairs(local_dir=local_dir, years=years, feed_types=feed_types)

    mode = "seed" if seed else ("local" if local_dir else "remote")
    logger.info("Invocation start mode=%s pairs=%s", mode, pairs)

    pool = await asyncpg.create_pool(config.database_url)
    try:

        async def _sync_one(ft: str, yr: int) -> SyncResult:
            return await _sync_one_pair(ft, yr, pool=pool, config=config, event=event)

        agg = await run_feeds_parallel(
            pairs,
            _sync_one,
            max_concurrent=config.feed_reader_max_concurrent_feeds,
        )

    finally:
        await pool.close()
        tmp_base = event.get("_tmp_base")
        if tmp_base is not None:
            shutil.rmtree(tmp_base, ignore_errors=True)

    logger.info(
        "Invocation end processed=%d failed=%d skipped_stale=%d pages=%d success=%s",
        agg["processed"],
        agg["failed"],
        agg["skipped_stale"],
        agg["pages"],
        agg["success"],
    )

    return {
        "statusCode": 200 if agg["success"] else 500,
        "body": {
            "processed": agg["processed"],
            "skipped_stale": agg["skipped_stale"],
            "failed": agg["failed"],
            "pages": agg["pages"],
        },
    }


# ---------------------------------------------------------------------- CLI


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Feed reader CLI")
    parser.add_argument(
        "--seed",
        action="store_true",
        default=False,
        help="Download archives from PLACSP, ingest, and clean up.",
    )
    parser.add_argument(
        "--local",
        type=str,
        default=None,
        help="Path to local feed directory. Enables local seeding mode.",
    )
    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=None,
        help="Year filter (e.g. 2020 2021). Requires --seed or --local.",
    )
    parser.add_argument(
        "--feed-type",
        type=str,
        default=None,
        choices=[ft.value for ft in FeedType],
        help="Process a single feed type (e.g. insiders). Optional.",
    )
    parser.add_argument(
        "--zip-dir",
        type=Path,
        default=None,
        help="With --seed: reuse yearly archives found here and keep downloads.",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Processing cutoff (ISO8601). Optional.",
    )
    return parser.parse_args(argv)


def _build_event(args: argparse.Namespace) -> dict[str, Any]:
    event: dict[str, Any] = {}
    if args.seed:
        event["seed"] = True
    if args.local:
        event["local_dir"] = args.local
    if args.years:
        event["years"] = args.years
    if args.feed_type:
        event["feed_type"] = args.feed_type
    if args.zip_dir:
        event["zip_dir"] = args.zip_dir
    if args.end_date:
        dt = datetime.fromisoformat(args.end_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        event["end_date"] = dt
    return event


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    event = _build_event(args)
    try:
        result = asyncio.run(_handle(event))
        logger.info("Result: %s", result)
    except KeyboardInterrupt:
        logger.info("Interrupted")


if __name__ == "__main__":
    main()
