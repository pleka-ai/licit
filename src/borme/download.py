"""Download BORME Section A from the BOE open-data API into a local cache.

Each publication day has a summary (JSON) listing one item per province in
Section A; each item's XML holds that day's registered acts. Files are cached
as ``<cache>/<año>/<identificador>.xml`` and each day's summary as
``<cache>/<año>/dias/<aaaammdd>.json`` (an empty list when there was no BORME
that day), so reruns fetch only what is missing. Published days never change;
today's summary is not cached, since it may still be incomplete.

Usage::

    PYTHONPATH=src uv run python -m borme.download <cache_dir> <desde> [<hasta>]
"""

from __future__ import annotations

import asyncio
import json
import ssl
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from shared.config import Settings
from shared.logger import get_logger

logger = get_logger(__name__)

ACTS_SECTION = "A"
INDEX_SUFFIX = "-99"  # the daily alphabetical index of companies: no acts


@dataclass(frozen=True)
class Item:
    """One province's Section A document of one day."""

    id: str
    province: str
    day: date


@dataclass
class Result:
    days: int = 0
    days_without_borme: int = 0
    downloaded: int = 0
    cached: int = 0
    failed: list[str] = field(default_factory=list)


def summary_items(summary: dict[str, Any], day: date) -> list[Item]:
    """Section A documents listed in a summary (lists may come unwrapped)."""

    def as_list(x: Any) -> list[Any]:
        return x if isinstance(x, list) else [x] if x else []

    items: list[Item] = []
    for issue in as_list(summary["data"]["sumario"]["diario"]):
        for section in as_list(issue.get("seccion")):
            if section.get("codigo") != ACTS_SECTION:
                continue
            items.extend(
                Item(item["identificador"], item["titulo"], day)
                for item in as_list(section.get("item"))
                if not item["identificador"].endswith(INDEX_SUFFIX)
            )
    return items


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


class Downloader:
    """Polite, retried downloads with a bounded number of requests in flight."""

    def __init__(self, cache_dir: Path, settings: Settings) -> None:
        self.cache = cache_dir
        self.settings = settings
        self.sem = asyncio.Semaphore(settings.borme_max_concurrent)
        self.result = Result()

    async def _get(
        self, http: httpx.AsyncClient, url: str, **kw: Any
    ) -> httpx.Response | None:
        """GET with retries on 429/5xx/transport errors; None on 404.

        A TLS failure mid-response (``ssl.SSLError``) can surface unwrapped by
        httpx: it is retried like any other transport error.
        """
        delay = self.settings.http_retry_delay
        for attempt in range(1, self.settings.http_max_retries + 1):
            try:
                async with self.sem:
                    resp = await http.get(url, **kw)
                if resp.status_code == httpx.codes.NOT_FOUND:
                    return None
                retryable = (
                    resp.status_code == httpx.codes.TOO_MANY_REQUESTS
                    or resp.status_code >= httpx.codes.INTERNAL_SERVER_ERROR
                )
                if not retryable:
                    resp.raise_for_status()
                    return resp
                logger.warning(
                    "BOE status=%s url=%s attempt=%d", resp.status_code, url, attempt
                )
            except (httpx.TransportError, ssl.SSLError) as exc:
                logger.warning("BOE error=%s url=%s attempt=%d", exc, url, attempt)
            await asyncio.sleep(delay)
            delay *= 2
        msg = f"BOE unreachable: {url}"
        raise RuntimeError(msg)

    def _summary_path(self, day: date) -> Path:
        return self.cache / str(day.year) / "dias" / f"{day:%Y%m%d}.json"

    async def _summary(self, http: httpx.AsyncClient, day: date) -> list[Item]:
        path = self._summary_path(day)
        if path.exists():
            return [
                Item(i["id"], i["province"], day) for i in json.loads(path.read_text())
            ]
        url = self.settings.borme_sumario_url.format(fecha=f"{day:%Y%m%d}")
        resp = await self._get(http, url, headers={"Accept": "application/json"})
        items = summary_items(resp.json(), day) if resp is not None else []
        if day < datetime.now(UTC).date():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps([{"id": i.id, "province": i.province} for i in items])
            )
        return items

    async def _document(self, http: httpx.AsyncClient, item: Item) -> None:
        path = self.cache / str(item.day.year) / f"{item.id}.xml"
        if path.exists():
            self.result.cached += 1
            return
        try:
            resp = await self._get(http, self.settings.borme_xml_url.format(id=item.id))
        except RuntimeError:
            resp = None
        if resp is None:
            self.result.failed.append(item.id)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".part")
        partial.write_bytes(resp.content)
        partial.rename(path)
        self.result.downloaded += 1

    async def run(self, start: date, end: date) -> Result:
        timeout = httpx.Timeout(self.settings.http_timeout)
        headers = {"User-Agent": self.settings.borme_user_agent}
        async with httpx.AsyncClient(
            timeout=timeout, headers=headers, follow_redirects=True
        ) as http:
            summaries = await asyncio.gather(
                *(self._summary(http, d) for d in _days(start, end))
            )
            self.result.days = sum(1 for s in summaries if s)
            self.result.days_without_borme = sum(1 for s in summaries if not s)
            items = [i for s in summaries for i in s]
            await asyncio.gather(*(self._document(http, i) for i in items))
        return self.result


async def download(
    cache_dir: Path, start: date, end: date, settings: Settings
) -> Result:
    """Fill ``cache_dir`` with every Section A document published in [start, end]."""
    result = await Downloader(cache_dir, settings).run(start, end)
    logger.info(
        "BORME download days=%d without_borme=%d downloaded=%d cached=%d failed=%d",
        result.days,
        result.days_without_borme,
        result.downloaded,
        result.cached,
        len(result.failed),
    )
    return result


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    match args:
        case [cache_dir, start, *rest] if len(rest) <= 1:
            end = date.fromisoformat(rest[0]) if rest else datetime.now(UTC).date()
            result = asyncio.run(
                download(Path(cache_dir), date.fromisoformat(start), end, Settings())
            )
            if result.failed:
                missing = len(result.failed)
                sys.exit(f"{missing} documents not downloaded: {result.failed[:5]}")
        case _:
            sys.exit("usage: borme.download <cache_dir> <desde> [<hasta>]")


if __name__ == "__main__":
    main()
