"""Column sets shared by the Parquet and D1 exporters."""

from __future__ import annotations

# Every mv_licitacion column except search_vector (tsvector is Postgres-only).
LICITACION_COLS: tuple[str, ...] = (
    "id",
    "expediente",
    "titulo",
    "descripcion",
    "url_place",
    "fecha_actualizacion",
    "fecha_publicacion",
    "historial_estados",
    "status_code",
    "type_code",
    "procedure_code",
    "estado",
    "tipo_contrato",
    "procedimiento",
    "tramitacion",
    "sistema_contratacion",
    "presupuesto_sin_iva",
    "presupuesto_con_iva",
    "valor_estimado",
    "fecha_limite",
    "hora_limite",
    "duracion",
    "duracion_unidad",
    "lugar_nuts",
    "lugar_subentidad",
    "funding_program_code",
    "programa_financiacion",
    "tasa_subcontratacion",
    "organo_id",
    "organo",
    "organo_nif",
    "organo_tipo",
    "cpv_principal",
    "cpv_principal_desc",
    "fecha_adjudicacion",
    "importe_adjudicacion",
    "num_licitadores",
    "resultado",
    "adjudicatario",
    "adjudicatario_nif",
    "fecha_formalizacion",
    "num_lotes",
    "tiene_documentos",
)


def licitacion_select() -> str:
    """Postgres SELECT over mv_licitacion with text-friendly casts."""
    casts = {
        "id": "id::text AS id",
        "organo_id": "organo_id::text AS organo_id",
        "historial_estados": "historial_estados::text AS historial_estados",
        "hora_limite": "hora_limite::text AS hora_limite",
    }
    cols = ", ".join(casts.get(c, c) for c in LICITACION_COLS)
    return f"SELECT {cols} FROM mv_licitacion"
