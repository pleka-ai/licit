"""Tests for the BORME Section A parser (synthetic fixtures, real structure)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from borme.parser import (
    Document,
    Position,
    acts,
    amount,
    positions,
    read,
    registry,
    short_date,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def doc() -> Document:
    parsed = read(FIXTURES / "BORME-A-2026-200-28.xml")
    assert parsed is not None
    return parsed


def test_document_metadata_and_filings(doc: Document) -> None:
    assert doc.id == "BORME-A-2026-200-28"
    assert doc.province == "MADRID"
    assert doc.date == date(2026, 10, 16)
    assert [f.number for f in doc.filings] == [460001, 460002, 460003, 460004]
    assert doc.filings[0].company == "OBRAS EJEMPLO DEL CENTRO SOCIEDAD LIMITADA"


def test_alphabetical_index_is_skipped() -> None:
    assert read(FIXTURES / "BORME-A-2026-200-99.xml") is None


def test_incorporation_fields(doc: Document) -> None:
    filing = doc.filings[0]
    kinds = [a.kind for a in filing.acts]
    assert kinds == ["Constitución", "Nombramientos"]
    const = filing.acts[0]
    assert const.start_of_operations == date(2026, 10, 1)
    assert const.purpose == "Construcción de edificios y obra civil"
    assert const.address == "C/ MAYOR 1 (MADRID)"
    assert const.capital == 3000.0
    assert filing.acts[1].positions == [Position("Adm. Unico", "PEREZ GOMEZ ANA MARIA")]
    assert filing.registry.sheet == "M 812345"
    assert filing.registry.entry == "1"
    assert filing.registry.entry_date == date(2026, 10, 8)


def test_positions_and_capital(doc: Document) -> None:
    filing = doc.filings[1]
    by_kind = {a.kind: a for a in filing.acts}
    assert [(p.role, p.name) for p in by_kind["Ceses/Dimisiones"].positions] == [
        ("Consejero", "LOPEZ RUIZ JUAN"),
        ("Consejero", "MARTIN SANZ LUIS"),
        ("Presidente", "LOPEZ RUIZ JUAN"),
    ]
    appointed = by_kind["Nombramientos"].positions
    assert ("Apo.Sol.", "OBRAS EJEMPLO DEL CENTRO SL") in [
        (p.role, p.name) for p in appointed
    ]
    # Two-piece labels keep their abbreviation.
    assert ("Cons. Deleg.", "GARCIA DIAZ EVA") in [(p.role, p.name) for p in appointed]
    increase = by_kind["Ampliación de capital"]
    assert (increase.capital, increase.resulting_capital) == (60000.0, 120000.0)
    assert (filing.registry.volume, filing.registry.page) == ("40001", "12")


def test_name_address_and_sole_member(doc: Document) -> None:
    by_kind = {a.kind: a for a in doc.filings[2].acts}
    assert by_kind["Cambio de denominación social"].new_name == (
        "NUEVO NOMBRE PRUEBA SOCIEDAD LIMITADA"
    )
    assert by_kind["Cambio de domicilio social"].address == (
        "AVDA DE LA PRUEBA 10 (ALCALA DE HENARES)"
    )
    assert by_kind["Declaración de unipersonalidad"].positions == [
        Position("Socio único", "SERVICIOS DE PRUEBA SOCIEDAD ANONIMA")
    ]


def test_dissolution_sequence(doc: Document) -> None:
    kinds = [a.kind for a in doc.filings[3].acts]
    assert kinds == ["Disolución", "Ceses/Dimisiones", "Nombramientos", "Extinción"]
    assert doc.filings[3].acts[0].text == "Voluntaria."


def test_old_format_separators_and_free_text() -> None:
    old = read(FIXTURES / "BORME-A-2009-1-01.xml")
    assert old is not None
    first = old.filings[0]
    assert [a.kind for a in first.acts] == [
        "Otros conceptos",
        "Ampliación del objeto social",
        "Nombramientos",
    ]
    assert first.acts[0].text == "Se modifica el artículo 9 de los Estatutos sociales."
    assert first.acts[2].positions == [Position("ADM.UNICO", "GOMEZ SANCHEZ PABLO")]
    # Headings match without their accents ("caracter").
    assert old.filings[1].acts[0].kind == "Pérdida del carácter de unipersonalidad"
    assert old.filings[1].acts[1].kind == "Fe de erratas"
    assert old.filings[1].registry.entry_date == date(2006, 1, 12)


def test_helpers() -> None:
    assert short_date("13.10.26") == date(2026, 10, 13)
    assert short_date("1.2.1999") == date(1999, 2, 1)
    assert short_date("31.02.26") is None
    assert amount("Capital: 1.234.567,89 Euros.", "Capital") == 1234567.89
    assert amount("Capital: 3000 Euros.", "Capital") == 3000.0
    assert registry("T 1 , F 2, S 8, H B 99, I/A 3 (1.1.10)").sheet == "B 99"
    assert positions("Adm. Mancom.: A UNO;B DOS. Dir. General: C TRES.") == [
        Position("Adm. Mancom.", "A UNO"),
        Position("Adm. Mancom.", "B DOS"),
        Position("Dir. General", "C TRES"),
    ]
    found, reg = acts("Extinción.  Datos registrales. S 8 , H M 1, I/A 2 (1.1.20).")
    assert [a.kind for a in found] == ["Extinción"]
    assert reg.sheet == "M 1"
