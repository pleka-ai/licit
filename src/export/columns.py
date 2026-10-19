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


# Public identifiers are derived from PLACSP natural keys, so every ephemeral
# Postgres (daily window, each archived year) yields the same ids.
PUBLIC_ID = "md5('licitacion:' || c.entry_id)::uuid::text"
ORGANO_ID = "md5('organo:' || coalesce(cp.platform_id, cp.dir3, cp.name))::uuid::text"

_CASTS = {
    "id": f"{PUBLIC_ID} AS id",
    "organo_id": f"{ORGANO_ID} AS organo_id",
    "historial_estados": "m.historial_estados::text AS historial_estados",
    "hora_limite": "m.hora_limite::text AS hora_limite",
}


def licitacion_select(*, with_pk: bool = False) -> str:
    """Postgres SELECT over mv_licitacion with public ids and text casts.

    ``with_pk`` adds the internal ``pk`` (Postgres uuid) for sync tracking.
    """
    cols = [_CASTS.get(c, f"m.{c}") for c in LICITACION_COLS]
    if with_pk:
        cols.append("m.id AS pk")
    return (
        f"SELECT {', '.join(cols)} FROM mv_licitacion m"
        " JOIN contract_folder_status c ON c.id = m.id"
        " LEFT JOIN contracting_party cp ON cp.id = m.organo_id"
    )


LOTE_SELECT = (
    f"SELECT {PUBLIC_ID} AS licitacion_id, v.numero, v.titulo,"
    " v.presupuesto_sin_iva, v.lugar_nuts, v.lugar_subentidad"
    " FROM v_lote v JOIN contract_folder_status c ON c.id = v.licitacion_id"
)

CPV_SELECT = (
    f"SELECT {PUBLIC_ID} AS licitacion_id, v.codigo, v.descripcion"
    " FROM v_cpv v JOIN contract_folder_status c ON c.id = v.licitacion_id"
)

ADJUDICACION_SELECT = (
    f"SELECT {PUBLIC_ID} AS licitacion_id, v.presupuesto_sin_iva,"
    " v.importe_adjudicacion, v.fecha_adjudicacion, v.num_licitadores,"
    f" v.adjudicatario, v.adjudicatario_nif, {ORGANO_ID} AS organo_id, v.organo"
    " FROM v_adjudicacion v JOIN contract_folder_status c ON c.id = v.licitacion_id"
    " LEFT JOIN contracting_party cp ON cp.id = v.organo_id"
)
