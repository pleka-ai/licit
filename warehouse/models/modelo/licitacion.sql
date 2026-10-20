MODEL (
  name modelo.licitacion,
  kind FULL,
  tags (hecho),
  depends_on (modelo.organo, modelo.modalidad, modelo.estado, modelo.cpv, modelo.lugar, modelo.empresa, modelo.resultado),
  grain licitacion_key,
  description 'Snapshot acumulativo: una fila por expediente con los hitos de su ciclo de vida (publicación, plazo, cada estado alcanzado, adjudicación, formalización) y medidas acumuladas de sus lotes, adjudicaciones, modificaciones y documentos. Se reescribe cada vez que PLACSP publica una versión nueva del expediente.',
  audits (
    not_null(columns := (licitacion_key, id, organo_key, modalidad_key, estado_key, cpv_key, lugar_key, adjudicatario_key, resultado_key, fecha_publicacion)),
    unique_values(columns := (licitacion_key)),
    unique_values(columns := (id)),
    clave_existe(columna := organo_key, dimension := modelo.organo),
    clave_existe(columna := modalidad_key, dimension := modelo.modalidad),
    clave_existe(columna := estado_key, dimension := modelo.estado),
    clave_existe(columna := cpv_key, dimension := modelo.cpv),
    clave_existe(columna := lugar_key, dimension := modelo.lugar),
    clave_existe(columna := resultado_key, dimension := modelo.resultado)
  )
);

WITH hitos AS (
  SELECT
    licitacion_key,
    min(updated) FILTER (WHERE status_code = 'PUB')::DATE AS fecha_en_plazo,
    min(updated) FILTER (WHERE status_code = 'EV')::DATE AS fecha_evaluacion,
    min(updated) FILTER (WHERE status_code = 'ADJ')::DATE AS fecha_adjudicada,
    min(updated) FILTER (WHERE status_code = 'RES')::DATE AS fecha_resuelta,
    min(updated) FILTER (WHERE status_code = 'ANUL')::DATE AS fecha_anulada
  FROM stage.status_change
  GROUP BY licitacion_key
),
adjudicaciones AS (
  SELECT
    a.licitacion_key,
    max(a.fecha_adjudicacion) AS fecha_adjudicacion,
    max(a.fecha_formalizacion) AS fecha_formalizacion,
    count(DISTINCT a.resultado_n) FILTER (WHERE r.es_adjudicacion) AS num_adjudicaciones,
    count(DISTINCT a.empresa_key) FILTER (WHERE a.empresa_key > 0) AS num_adjudicatarios,
    max(a.num_ofertas) AS num_ofertas,
    sum(a.importe_sin_iva) FILTER (WHERE r.es_adjudicacion) AS importe_adjudicado_sin_iva,
    sum(a.importe_con_iva) FILTER (WHERE r.es_adjudicacion) AS importe_adjudicado_con_iva,
    -- Principal result and winner: the latest award, largest amount first.
    arg_max(
      a.empresa_key,
      (a.empresa_key > 0, a.fecha_adjudicacion, a.importe_sin_iva, -a.resultado_n)
    ) AS adjudicatario_key,
    arg_max(
      a.resultado_key,
      (a.empresa_key > 0, a.fecha_adjudicacion, a.importe_sin_iva, -a.resultado_n)
    ) AS resultado_key
  FROM modelo.adjudicacion AS a
  JOIN modelo.resultado AS r USING (resultado_key)
  GROUP BY a.licitacion_key
),
lotes AS (
  SELECT licitacion_key, count(*) AS num_lotes
  FROM stage.procurement_project_lot
  GROUP BY licitacion_key
),
modificaciones AS (
  SELECT
    licitacion_key,
    count(*) AS num_modificaciones,
    sum(modification_tax_exclusive_amount) AS importe_modificaciones_sin_iva
  FROM stage.contract_modification
  GROUP BY licitacion_key
),
documentos AS (
  SELECT licitacion_key, count(*) AS num_documentos
  FROM stage.document_reference
  GROUP BY licitacion_key
),
anuncios AS (
  SELECT licitacion_key, count(*) AS num_anuncios
  FROM stage.valid_notice_info
  GROUP BY licitacion_key
)
SELECT
  f.licitacion_key,
  md5('licitacion:' || f.entry_id)::UUID::TEXT AS id,
  f.entry_id AS placsp_id,
  f.contract_folder_id AS expediente,
  coalesce(f.name, f.title) AS titulo,
  f.summary AS descripcion,
  f.link AS url_place,
  f.ted_uuid,

  -- Dimensions
  e.organo_key,
  e.modalidad_key,
  e.estado_key,
  e.cpv_key,
  e.lugar_key,
  coalesce(a.adjudicatario_key, -1) AS adjudicatario_key,
  coalesce(a.resultado_key, 0) AS resultado_key,

  -- Milestones (dates join modelo.calendario on fecha)
  e.fecha_publicacion,
  f.updated AS fecha_actualizacion,
  f.submission_deadline_date AS fecha_limite,
  f.submission_deadline_time AS hora_limite,
  f.document_availability_end_date AS fecha_fin_documentacion,
  f.participation_request_end_date AS fecha_fin_solicitudes,
  h.fecha_en_plazo,
  h.fecha_evaluacion,
  h.fecha_adjudicada,
  h.fecha_resuelta,
  h.fecha_anulada,
  a.fecha_adjudicacion,
  a.fecha_formalizacion,
  f.planned_start_date AS fecha_inicio_prevista,
  f.planned_end_date AS fecha_fin_prevista,

  -- Measures
  f.tax_exclusive_amount AS presupuesto_sin_iva,
  f.total_amount AS presupuesto_con_iva,
  f.estimated_overall_contract_amount AS valor_estimado,
  f.duration_measure AS duracion,
  f.duration_unit_code AS duracion_unidad,
  round(f.duration_measure * CASE f.duration_unit_code
    WHEN 'DAY' THEN 1 WHEN 'WEE' THEN 7 WHEN 'MON' THEN 30.4375 WHEN 'ANN' THEN 365.25
  END)::INT AS duracion_dias,
  coalesce(lo.num_lotes, 0) AS num_lotes,
  coalesce(a.num_adjudicaciones, 0) AS num_adjudicaciones,
  coalesce(a.num_adjudicatarios, 0) AS num_adjudicatarios,
  a.num_ofertas,
  a.importe_adjudicado_sin_iva,
  a.importe_adjudicado_con_iva,
  coalesce(m.num_modificaciones, 0) AS num_modificaciones,
  m.importe_modificaciones_sin_iva,
  coalesce(d.num_documentos, 0) AS num_documentos,
  coalesce(an.num_anuncios, 0) AS num_anuncios,
  f.received_appeal_quantity AS num_recursos,
  a.fecha_adjudicacion - e.fecha_publicacion::DATE AS dias_hasta_adjudicacion,
  f.submission_deadline_date - e.fecha_publicacion::DATE AS dias_plazo_ofertas,

  -- Tender terms (degenerate attributes, one per expediente)
  f.currency_id AS moneda,
  f.allowed_subcontract_rate AS tasa_subcontratacion_maxima,
  f.allowed_subcontract_description AS subcontratacion_descripcion,
  f.funding_program_name AS programa_financiacion,
  f.funding_program_description AS financiacion_descripcion,
  f.submission_deadline_description AS plazo_descripcion,
  f.document_availability_end_time AS hora_fin_documentacion,
  f.participation_request_end_time AS hora_fin_solicitudes,
  f.options_description AS opciones,
  f.option_validity_description AS opciones_validez,
  f.price_revision_formula AS formula_revision_precios,
  f.procurement_legislation_id AS legislacion_id,
  f.required_curricula_indicator AS exige_curriculos,
  f.max_lot_presentation_quantity AS max_lotes_por_oferta,
  f.max_tenderer_awarded_lots_qty AS max_lotes_por_adjudicatario,
  f.lots_combination_rights AS combinacion_lotes,
  f.short_list_limitation_description AS preseleccion_descripcion,
  f.short_list_min_quantity AS preseleccion_minimo,
  f.short_list_expected_quantity AS preseleccion_previsto,
  f.short_list_max_quantity AS preseleccion_maximo,
  f.tender_recipient_endpoint_id AS enlace_presentacion
FROM stage.contract_folder_status AS f
JOIN stage.expediente_claves AS e USING (licitacion_key)
LEFT JOIN hitos AS h USING (licitacion_key)
LEFT JOIN adjudicaciones AS a USING (licitacion_key)
LEFT JOIN lotes AS lo USING (licitacion_key)
LEFT JOIN modificaciones AS m USING (licitacion_key)
LEFT JOIN documentos AS d USING (licitacion_key)
LEFT JOIN anuncios AS an USING (licitacion_key)
