"""Tests for merging Parquet snapshots (export.compact)."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from export.columns import LICITACION_COLS
from export.compact import compact

_TYPES = {
    "fecha_actualizacion": "TIMESTAMPTZ",
    "fecha_publicacion": "TIMESTAMPTZ",
    "presupuesto_sin_iva": "DOUBLE",
}


def _snapshot(path: Path, rows: list[dict[str, object]], lotes: list[str]) -> Path:
    path.mkdir(parents=True)
    con = duckdb.connect()
    cols = ", ".join(f"{c} {_TYPES.get(c, 'VARCHAR')}" for c in LICITACION_COLS)
    con.execute(f"CREATE TABLE licitacion ({cols})")
    for r in rows:
        names = ", ".join(r)
        marks = ", ".join("?" for _ in r)
        con.execute(
            f"INSERT INTO licitacion ({names}) VALUES ({marks})", list(r.values())
        )
    con.execute(
        "CREATE TABLE lote AS"
        " SELECT 'a' AS licitacion_id, unnest(?::VARCHAR[]) AS titulo",
        [lotes],
    )
    con.execute("CREATE TABLE adjudicacion AS SELECT 'a' AS licitacion_id, 1 AS n")
    con.execute("CREATE TABLE cpv AS SELECT 'a' AS licitacion_id, '45' AS codigo")
    con.execute(
        "CREATE TABLE empresa AS"
        " SELECT 'B1' AS nif, 'X' AS nombre, NULL AS ciudad, NULL AS tipo"
    )
    for t in ("licitacion", "lote", "adjudicacion", "cpv", "empresa"):
        con.execute(f"COPY {t} TO '{path / (t + '.parquet')}' (FORMAT parquet)")
    return path


def test_newest_snapshot_wins_with_merged_history(tmp_path: Path) -> None:
    old = _snapshot(
        tmp_path / "2024",
        [
            {
                "id": "a",
                "titulo": "Viejo",
                "fecha_publicacion": "2024-01-01 00:00:00+00",
                "fecha_actualizacion": "2024-01-01 00:00:00+00",
                "historial_estados": json.dumps(
                    [{"estado": "Publicada", "fecha": "2024-01-01"}]
                ),
            }
        ],
        ["lote viejo 1", "lote viejo 2"],
    )
    new = _snapshot(
        tmp_path / "reciente",
        [
            {
                "id": "a",
                "titulo": "Nuevo",
                "fecha_publicacion": "2025-03-01 00:00:00+00",
                "fecha_actualizacion": "2025-03-01 00:00:00+00",
                "historial_estados": json.dumps(
                    [{"estado": "Adjudicada", "fecha": "2025-03-01"}]
                ),
            }
        ],
        ["lote nuevo"],
    )

    manifest = compact(tmp_path / "todo", [old, new])

    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    titulo, publicada, historial = (
        con.execute(
            "SELECT titulo, fecha_publicacion::DATE::VARCHAR, historial_estados"
            f" FROM '{tmp_path / 'todo' / 'licitacion.parquet'}'"
        ).fetchone()
        or ()
    )
    assert titulo == "Nuevo"
    assert publicada == "2024-01-01"
    assert [h["estado"] for h in json.loads(historial)] == ["Publicada", "Adjudicada"]
    lotes = con.execute(
        f"SELECT titulo FROM '{tmp_path / 'todo' / 'lote.parquet'}'"
    ).fetchall()
    assert lotes == [("lote nuevo",)]
    assert manifest["tablas"]["licitacion"]["rows"] == 1  # type: ignore[index]
