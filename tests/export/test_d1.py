"""Tests for the D1 sync (export.d1), run against the real D1 schema in SQLite."""

from __future__ import annotations

import sqlite3
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import pytest

from export.d1 import D1_TABLES, build, sql_literal
from shared.config import Settings

_SCHEMA = Path(__file__).parents[2] / "worker" / "schema.sql"

# Minimal model: the columns each D1 query reads, typed like export.modelo.
_MODEL_COLUMNS: dict[str, str] = {
    "estado": "estado_key BIGINT, codigo VARCHAR, descripcion VARCHAR",
    "resultado": "resultado_key BIGINT, codigo VARCHAR, descripcion VARCHAR",
    "modalidad": (
        "modalidad_key BIGINT, tipo_contrato_codigo VARCHAR, tipo_contrato VARCHAR,"
        " procedimiento_codigo VARCHAR, procedimiento VARCHAR, tramitacion VARCHAR,"
        " sistema_contratacion VARCHAR, financiacion_codigo VARCHAR,"
        " financiacion VARCHAR"
    ),
    "cpv": "cpv_key BIGINT, codigo VARCHAR, descripcion VARCHAR",
    "lugar": (
        "lugar_key BIGINT, codigo VARCHAR, nombre VARCHAR, nombre_placsp VARCHAR,"
        " nuts2 VARCHAR"
    ),
    "organo": (
        "organo_key BIGINT, id VARCHAR, nombre VARCHAR, nif VARCHAR, tipo VARCHAR"
    ),
    "resumen_organo": "organo_key BIGINT, licitaciones BIGINT",
    "empresa": "empresa_key BIGINT, nif VARCHAR, nombre VARCHAR",
    "resumen_empresa": "empresa_key BIGINT, contratos BIGINT",
    "licitacion": (
        "licitacion_key BIGINT, id VARCHAR, expediente VARCHAR, titulo VARCHAR,"
        " url_place VARCHAR, organo_key BIGINT, modalidad_key BIGINT,"
        " estado_key BIGINT, cpv_key BIGINT, lugar_key BIGINT,"
        " adjudicatario_key BIGINT, resultado_key BIGINT,"
        " fecha_publicacion TIMESTAMP, fecha_actualizacion TIMESTAMP,"
        " fecha_limite DATE, hora_limite VARCHAR, fecha_adjudicacion DATE,"
        " fecha_formalizacion DATE, presupuesto_sin_iva DOUBLE,"
        " presupuesto_con_iva DOUBLE, valor_estimado DOUBLE, duracion DOUBLE,"
        " duracion_unidad VARCHAR, num_lotes INT, num_ofertas INT,"
        " importe_adjudicado_sin_iva DOUBLE, num_documentos INT,"
        " tasa_subcontratacion_maxima DOUBLE"
    ),
    "adjudicacion": (
        "licitacion_key BIGINT, resultado_n INT, adjudicatario_n INT,"
        " empresa_key BIGINT, organo_key BIGINT, fecha_adjudicacion DATE,"
        " importe_sin_iva DOUBLE, presupuesto_sin_iva DOUBLE"
    ),
    "cambio_estado": "licitacion_key BIGINT, momento TIMESTAMP, estado_key BIGINT",
}

_BASE: dict[str, list[dict[str, Any]]] = {
    "estado": [
        {"estado_key": 0, "codigo": "?", "descripcion": "Desconocido"},
        {"estado_key": 1, "codigo": "PUB", "descripcion": "En plazo"},
        {"estado_key": 2, "codigo": "ADJ", "descripcion": "Adjudicada"},
    ],
    "resultado": [{"resultado_key": 5, "codigo": "8", "descripcion": "Adjudicado"}],
    "modalidad": [
        {"modalidad_key": 3, "tipo_contrato_codigo": "2", "tipo_contrato": "Servicios"}
    ],
    "cpv": [{"cpv_key": 4, "codigo": "72000000", "descripcion": "Servicios TI"}],
    "lugar": [{"lugar_key": 6, "codigo": "ES300", "nombre": "Madrid"}],
    "organo": [
        {"organo_key": 0, "id": None, "nombre": "Órgano desconocido"},
        {"organo_key": 7, "id": "o-1", "nombre": "Ayuntamiento de Ávila"},
    ],
    "resumen_organo": [{"organo_key": 7, "licitaciones": 2}],
    "empresa": [
        {"empresa_key": -1, "nombre": "Sin adjudicatario"},
        {"empresa_key": 8, "nif": "B1", "nombre": "Datos SL"},
    ],
    "resumen_empresa": [{"empresa_key": 8, "contratos": 1}],
    "licitacion": [
        {
            "licitacion_key": 10,
            "id": "l-10",
            "titulo": "Mantenimiento de ascensores",
            "organo_key": 7,
            "modalidad_key": 3,
            "estado_key": 2,
            "cpv_key": 4,
            "lugar_key": 6,
            "adjudicatario_key": 8,
            "resultado_key": 5,
            "fecha_publicacion": "2024-01-01 00:00:00",
            "presupuesto_sin_iva": 100.0,
            "num_documentos": 2,
        },
        {
            "licitacion_key": 11,
            "id": "l-11",
            "titulo": "Limpieza viaria",
            "organo_key": 0,
            "modalidad_key": 3,
            "estado_key": 1,
            "cpv_key": 4,
            "lugar_key": 6,
            "adjudicatario_key": -1,
            "resultado_key": 0,
            "fecha_publicacion": "2024-02-01 00:00:00",
            "num_documentos": 0,
        },
    ],
    "adjudicacion": [
        {
            "licitacion_key": 10,
            "resultado_n": 1,
            "adjudicatario_n": 1,
            "empresa_key": 8,
            "organo_key": 7,
            "importe_sin_iva": 90.0,
        }
    ],
    "cambio_estado": [
        {"licitacion_key": 10, "momento": "2024-01-01 00:00:00", "estado_key": 1},
        {"licitacion_key": 10, "momento": "2024-03-01 00:00:00", "estado_key": 2},
        {"licitacion_key": 11, "momento": "2024-02-01 00:00:00", "estado_key": 1},
    ],
}


def _model(path: Path, data: dict[str, list[dict[str, Any]]]) -> Path:
    """Write a minimal model directory as export.modelo would."""
    path.mkdir(parents=True)
    con = duckdb.connect()
    for table, columns in _MODEL_COLUMNS.items():
        con.execute(f"CREATE TABLE {table} ({columns})")
        for row in data.get(table, []):
            names = ", ".join(row)
            marks = ", ".join("?" for _ in row)
            con.execute(
                f"INSERT INTO {table} ({names}) VALUES ({marks})", list(row.values())
            )
        con.execute(f"COPY {table} TO '{path / table}.parquet' (FORMAT parquet)")
    return path


def _apply(db: sqlite3.Connection, sql_dir: Path) -> None:
    for f in sorted(sql_dir.glob("d1-*.sql")):
        db.executescript(f.read_text())


def _dump(db: sqlite3.Connection) -> dict[str, list[tuple[Any, ...]]]:
    out = {}
    for table, spec in D1_TABLES.items():
        out[table] = db.execute(
            f"SELECT * FROM {table} ORDER BY {', '.join(spec.key)}"
        ).fetchall()
    out["fts"] = db.execute(
        "SELECT rowid, titulo, organo, adjudicatario FROM licitacion_fts ORDER BY rowid"
    ).fetchall()
    return out


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA.read_text())
    return conn


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="x", environment="test")


def test_sql_literal_escapes_and_types() -> None:
    assert sql_literal(None) == "NULL"
    assert sql_literal(True) == "1"
    assert sql_literal(Decimal("12.50")) == "12.50"
    assert sql_literal("O'Donnell") == "'O''Donnell'"
    assert sql_literal(date(2026, 1, 2)) == "'2026-01-02'"
    assert sql_literal(time(9, 30)) == "'09:30:00'"


def test_full_load_serves_the_flat_api_view(
    tmp_path: Path, db: sqlite3.Connection, settings: Settings
) -> None:
    build(tmp_path / "sql", _model(tmp_path / "m", _BASE), None, settings)
    _apply(db, tmp_path / "sql")

    row = db.execute(
        "SELECT id, organo, organo_id, tipo_contrato, estado, adjudicatario,"
        " adjudicatario_nif, cpv_principal, resultado, tiene_documentos"
        " FROM licitacion_api ORDER BY rid"
    ).fetchall()
    assert row == [
        (
            "l-10",
            "Ayuntamiento de Ávila",
            "o-1",
            "Servicios",
            "Adjudicada",
            "Datos SL",
            "B1",
            "72000000",
            "Adjudicado",
            1,
        ),
        # Reserved members are not loaded: the API sees NULLs, as before.
        ("l-11", None, None, "Servicios", "En plazo", None, None, "72000000", None, 0),
    ]
    # rid follows fecha_publicacion.
    assert [r[0] for r in db.execute("SELECT id FROM licitacion ORDER BY rid")] == [
        "l-10",
        "l-11",
    ]
    # The full-text index includes the names resolved from the dimensions.
    hits = db.execute(
        "SELECT l.id FROM licitacion_fts"
        " JOIN licitacion l ON l.rid = licitacion_fts.rowid"
        " WHERE licitacion_fts MATCH ?",
        ['"avila"*'],
    ).fetchall()
    assert hits == [("l-10",)]


def test_diff_matches_a_full_load_and_keeps_rowids(
    tmp_path: Path, db: sqlite3.Connection, settings: Settings
) -> None:
    prev = _model(tmp_path / "ayer", _BASE)
    today = {k: [dict(r) for r in v] for k, v in _BASE.items()}
    today["organo"][1]["nombre"] = "Ayuntamiento de Ávila (Concejalía)"
    today["licitacion"][1] |= {"organo_key": 7, "titulo": "Limpieza viaria 2024"}
    today["licitacion"].append(
        {
            "licitacion_key": 12,
            "id": "l-12",
            "titulo": "Suministro de papel",
            "organo_key": 7,
            "modalidad_key": 3,
            "estado_key": 1,
            "cpv_key": 4,
            "lugar_key": 6,
            "adjudicatario_key": -1,
            "resultado_key": 0,
            "fecha_publicacion": "2024-04-01 00:00:00",
        }
    )
    today["cambio_estado"] = today["cambio_estado"][:2]  # one status disappears
    today["empresa"] = today["empresa"][:1]  # the only company is gone
    today["adjudicacion"] = []
    new = _model(tmp_path / "hoy", today)

    build(tmp_path / "full_prev", prev, None, settings)
    _apply(db, tmp_path / "full_prev")
    rid_before = db.execute("SELECT rid FROM licitacion WHERE id = 'l-11'").fetchone()
    summary = build(tmp_path / "diff", new, prev, settings)
    _apply(db, tmp_path / "diff")

    expected = sqlite3.connect(":memory:")
    expected.executescript(_SCHEMA.read_text())
    build(tmp_path / "full_new", new, None, settings)
    _apply(expected, tmp_path / "full_new")

    got, want = _dump(db), _dump(expected)
    for table in D1_TABLES:
        # rid differs only in assignment order; compare rows without it.
        strip = (lambda r: r[1:]) if table == "licitacion" else (lambda r: r)
        assert sorted(map(strip, got[table])) == sorted(map(strip, want[table])), table
    # Updated rows keep their rid; new rows are appended after it.
    assert db.execute("SELECT rid FROM licitacion WHERE id = 'l-11'").fetchone() == (
        rid_before
    )
    # The index follows the rename of the updated row's organo.
    assert db.execute(
        "SELECT organo FROM licitacion_fts"
        " JOIN licitacion l ON l.rid = licitacion_fts.rowid"
        " WHERE l.id = 'l-11'"
    ).fetchone() == ("Ayuntamiento de Ávila (Concejalía)",)
    assert summary["licitacion"] == {"borradas": 0, "escritas": 2}
    assert summary["cambio_estado"]["borradas"] == 1
    assert summary["empresa"]["borradas"] == 1


def test_unchanged_model_writes_nothing_but_meta(
    tmp_path: Path, settings: Settings
) -> None:
    model = _model(tmp_path / "m", _BASE)
    summary = build(tmp_path / "sql", model, model, settings)
    assert all(v.get("escritas", 0) == 0 for v in summary.values())
    assert all(v.get("borradas", 0) == 0 for v in summary.values())


def test_injection_is_stored_as_text(
    tmp_path: Path, db: sqlite3.Connection, settings: Settings
) -> None:
    data = {k: [dict(r) for r in v] for k, v in _BASE.items()}
    data["licitacion"][0]["titulo"] = "x'); DROP TABLE licitacion; --"
    build(tmp_path / "sql", _model(tmp_path / "m", data), None, settings)
    _apply(db, tmp_path / "sql")
    assert db.execute("SELECT titulo FROM licitacion WHERE id = 'l-10'").fetchone() == (
        "x'); DROP TABLE licitacion; --",
    )
