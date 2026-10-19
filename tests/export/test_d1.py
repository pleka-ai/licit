"""Tests for the D1 SQL batch builder, run against the real D1 schema."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from export.d1 import D1_COLS, sql_literal, upsert_statement

_SCHEMA = Path(__file__).parents[2] / "worker" / "schema.sql"


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA.read_text())
    return conn


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = dict.fromkeys(D1_COLS)
    row |= {
        "id": "abc",
        "titulo": "Mantenimiento de ascensores",
        "fecha_publicacion": datetime(2024, 1, 1, tzinfo=UTC),
        "fecha_actualizacion": datetime(2024, 1, 1, tzinfo=UTC),
        "historial_estados": json.dumps(
            [{"estado": "Publicada", "fecha": "2024-01-01T00:00:00+00:00"}]
        ),
    }
    return row | overrides


def test_sql_literal_escapes_and_types() -> None:
    assert sql_literal(None) == "NULL"
    assert sql_literal(True) == "1"
    assert sql_literal(Decimal("12.50")) == "12.50"
    assert sql_literal("O'Donnell") == "'O''Donnell'"
    assert sql_literal(date(2026, 1, 2)) == "'2026-01-02'"
    assert sql_literal(time(9, 30)) == "'09:30:00'"


def test_descripcion_is_not_sent_to_d1() -> None:
    assert "descripcion" not in D1_COLS


def test_injection_is_stored_as_text(db: sqlite3.Connection) -> None:
    db.executescript(upsert_statement(_row(titulo="x'); DROP TABLE licitacion; --")))
    assert db.execute("SELECT titulo FROM licitacion").fetchone() == (
        "x'); DROP TABLE licitacion; --",
    )


def test_newer_snapshot_wins_and_history_merges(db: sqlite3.Connection) -> None:
    db.executescript(upsert_statement(_row()))
    newer = _row(
        titulo="Mantenimiento de ascensores (adjudicada)",
        fecha_publicacion=datetime(2025, 6, 1, tzinfo=UTC),
        fecha_actualizacion=datetime(2025, 6, 1, tzinfo=UTC),
        historial_estados=json.dumps(
            [{"estado": "Adjudicada", "fecha": "2025-06-01T00:00:00+00:00"}]
        ),
    )
    db.executescript(upsert_statement(newer))

    titulo, publicada, historial = db.execute(
        "SELECT titulo, fecha_publicacion, historial_estados FROM licitacion"
    ).fetchone()
    assert titulo == "Mantenimiento de ascensores (adjudicada)"
    assert publicada.startswith("2024-01-01")
    assert [h["estado"] for h in json.loads(historial)] == ["Publicada", "Adjudicada"]


def test_older_snapshot_does_not_overwrite(db: sqlite3.Connection) -> None:
    db.executescript(
        upsert_statement(
            _row(titulo="Nuevo", fecha_actualizacion=datetime(2025, 1, 1, tzinfo=UTC))
        )
    )
    db.executescript(upsert_statement(_row(titulo="Viejo")))
    assert db.execute("SELECT count(*), titulo FROM licitacion").fetchone() == (
        1,
        "Nuevo",
    )


def test_fts_follows_updates(db: sqlite3.Connection) -> None:
    db.executescript(upsert_statement(_row()))
    db.executescript(
        upsert_statement(
            _row(
                titulo="Limpieza viaria",
                fecha_actualizacion=datetime(2025, 1, 1, tzinfo=UTC),
            )
        )
    )
    match = "SELECT count(*) FROM licitacion_fts WHERE licitacion_fts MATCH ?"
    assert db.execute(match, ("ascensores",)).fetchone() == (0,)
    assert db.execute(match, ("limpieza",)).fetchone() == (1,)
