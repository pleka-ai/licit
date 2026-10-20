"""Tests for the BORME downloader against a mocked BOE API."""

from __future__ import annotations

import json
import ssl
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from borme.download import download, summary_items
from shared.config import Settings

SUMMARY_URL = "https://www.boe.es/datosabiertos/api/borme/sumario/{}"
XML_URL = "https://www.boe.es/diario_borme/xml.php"


def _summary(*items: tuple[str, str], unwrap: bool = False) -> dict[str, object]:
    listed = [{"identificador": i, "titulo": t} for i, t in items]
    section = {
        "codigo": "A",
        "item": listed[0] if unwrap and len(listed) == 1 else listed,
    }
    other = {"codigo": "C", "item": [{"identificador": "BORME-C-1", "titulo": "x"}]}
    return {"data": {"sumario": {"diario": [{"seccion": [section, other]}]}}}


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="test", http_retry_delay=0, http_max_retries=2)


def test_summary_items_skip_index_and_other_sections() -> None:
    day = date(2026, 10, 16)
    items = summary_items(
        _summary(("BORME-A-2026-200-28", "MADRID"), ("BORME-A-2026-200-99", "ÍNDICE")),
        day,
    )
    assert [(i.id, i.province) for i in items] == [("BORME-A-2026-200-28", "MADRID")]
    # A single item may come as an object instead of a list.
    one = summary_items(_summary(("BORME-A-2026-200-02", "ALBACETE"), unwrap=True), day)
    assert [i.id for i in one] == ["BORME-A-2026-200-02"]


@pytest.mark.asyncio
@respx.mock
async def test_download_fills_the_cache_once(
    tmp_path: Path, settings: Settings
) -> None:
    respx.get(SUMMARY_URL.format("20261016")).mock(
        return_value=httpx.Response(
            200, json=_summary(("BORME-A-2026-200-28", "MADRID"))
        )
    )
    respx.get(SUMMARY_URL.format("20261017")).mock(return_value=httpx.Response(404))
    doc = respx.get(XML_URL, params={"id": "BORME-A-2026-200-28"}).mock(
        return_value=httpx.Response(200, content=b"<documento/>")
    )

    result = await download(tmp_path, date(2026, 10, 16), date(2026, 10, 17), settings)

    assert (result.days, result.days_without_borme, result.downloaded) == (1, 1, 1)
    assert (
        tmp_path / "2026" / "BORME-A-2026-200-28.xml"
    ).read_bytes() == b"<documento/>"
    saved = json.loads((tmp_path / "2026" / "dias" / "20261017.json").read_text())
    assert saved == []  # no BORME that day, remembered

    again = await download(tmp_path, date(2026, 10, 16), date(2026, 10, 17), settings)
    assert (again.downloaded, again.cached) == (0, 1)
    assert doc.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_unreachable_document_is_reported(
    tmp_path: Path, settings: Settings
) -> None:
    respx.get(SUMMARY_URL.format("20261016")).mock(
        return_value=httpx.Response(
            200, json=_summary(("BORME-A-2026-200-28", "MADRID"))
        )
    )
    respx.get(XML_URL).mock(return_value=httpx.Response(503))

    result = await download(tmp_path, date(2026, 10, 16), date(2026, 10, 16), settings)

    assert result.failed == ["BORME-A-2026-200-28"]
    assert not list((tmp_path / "2026").glob("*.xml"))


@pytest.mark.asyncio
@respx.mock
async def test_tls_failure_is_retried(tmp_path: Path, settings: Settings) -> None:
    respx.get(SUMMARY_URL.format("20261016")).mock(
        return_value=httpx.Response(
            200, json=_summary(("BORME-A-2026-200-28", "MADRID"))
        )
    )
    respx.get(XML_URL).mock(
        side_effect=[
            ssl.SSLError("record layer failure"),
            httpx.Response(200, content=b"<documento/>"),
        ]
    )

    result = await download(tmp_path, date(2026, 10, 16), date(2026, 10, 16), settings)

    assert (result.downloaded, result.failed) == (1, [])


@pytest.mark.asyncio
@respx.mock
async def test_refused_document_does_not_stop_the_rest(
    tmp_path: Path, settings: Settings
) -> None:
    respx.get(SUMMARY_URL.format("20261016")).mock(
        return_value=httpx.Response(
            200,
            json=_summary(
                ("BORME-A-2026-200-28", "MADRID"), ("BORME-A-2026-200-08", "BARCELONA")
            ),
        )
    )
    respx.get(XML_URL, params={"id": "BORME-A-2026-200-28"}).mock(
        return_value=httpx.Response(403)
    )
    respx.get(XML_URL, params={"id": "BORME-A-2026-200-08"}).mock(
        return_value=httpx.Response(200, content=b"<documento/>")
    )

    result = await download(tmp_path, date(2026, 10, 16), date(2026, 10, 16), settings)

    assert (result.downloaded, result.failed) == (1, ["BORME-A-2026-200-28"])
