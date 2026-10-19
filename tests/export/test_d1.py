"""Tests for the D1 SQL batch builder."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, time
from decimal import Decimal

from export.columns import LICITACION_COLS
from export.d1 import sql_literal, upsert_statement


def test_sql_literal_escapes_and_types() -> None:
    assert sql_literal(None) == "NULL"
    assert sql_literal(True) == "1"
    assert sql_literal(Decimal("12.50")) == "12.50"
    assert sql_literal("O'Donnell") == "'O''Donnell'"
    assert sql_literal(date(2026, 1, 2)) == "'2026-01-02'"
    assert sql_literal(time(9, 30)) == "'09:30:00'"


def test_upsert_round_trips_through_sqlite() -> None:
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE licitacion (rid INTEGER PRIMARY KEY, id TEXT UNIQUE, "
        + ", ".join(c for c in LICITACION_COLS if c != "id")
        + ")"
    )
    row = dict.fromkeys(LICITACION_COLS)
    row |= {
        "id": "abc",
        "titulo": "Obra 'urgente'; DROP TABLE licitacion; --",
        "presupuesto_sin_iva": Decimal("1000.5"),
        "fecha_actualizacion": datetime(2026, 1, 1, tzinfo=UTC),
    }
    db.executescript(upsert_statement(row))
    row["titulo"] = "Actualizada"
    db.executescript(upsert_statement(row))

    query = "SELECT rid, titulo, presupuesto_sin_iva FROM licitacion"
    rows = db.execute(query).fetchall()
    assert rows == [(1, "Actualizada", 1000.5)]
