"""Tests for the yearly archive cache of the seed download."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
import pytest
import respx

from etl.handlers.feed_reader import _download_and_extract, archive_name


def _zip_bytes(name: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, content)
    return buf.getvalue()


@pytest.mark.asyncio
@respx.mock
async def test_cached_archive_is_not_downloaded(tmp_path: Path) -> None:
    zips = tmp_path / "zips"
    zips.mkdir()
    (zips / archive_name("insiders", 2019)).write_bytes(_zip_bytes("a.atom", b"x"))
    route = respx.get(url__regex=r".*").mock(return_value=httpx.Response(500))

    await _download_and_extract("insiders", 2019, tmp_path / "y", zip_dir=zips)

    assert not route.called
    assert (tmp_path / "y" / "a.atom").read_bytes() == b"x"
    assert (zips / archive_name("insiders", 2019)).exists()


@pytest.mark.asyncio
@respx.mock
async def test_downloaded_archive_is_kept_in_cache(tmp_path: Path) -> None:
    zips = tmp_path / "zips"
    respx.get(url__regex=r".*_2020\.zip$").mock(
        return_value=httpx.Response(200, content=_zip_bytes("b.atom", b"y"))
    )

    await _download_and_extract("outsiders", 2020, tmp_path / "y", zip_dir=zips)

    assert (tmp_path / "y" / "b.atom").read_bytes() == b"y"
    assert (zips / archive_name("outsiders", 2020)).exists()
    assert not list(zips.glob("*.part"))


@pytest.mark.asyncio
@respx.mock
async def test_without_cache_the_archive_is_removed(tmp_path: Path) -> None:
    respx.get(url__regex=r".*_2021\.zip$").mock(
        return_value=httpx.Response(200, content=_zip_bytes("c.atom", b"z"))
    )
    year_dir = tmp_path / "seed" / "insiders" / "2021"

    await _download_and_extract("insiders", 2021, year_dir)

    assert (year_dir / "c.atom").exists()
    assert not list((tmp_path / "seed" / "insiders").glob("*.zip"))
