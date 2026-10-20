MODEL (
  name modelo.licitacion,
  kind FULL,
  grain licitacion_key,
  description 'La licitación (expediente): qué se contrata y cómo. Título, descripción, enlaces, estado actual, tipo y subtipo de contrato, procedimiento, tramitación, sistema, forma de presentación, regulación armonizada, financiación, duración y condiciones del pliego, según su última versión publicada. Fechas e importes están en ciclo_licitacion, presupuesto_lote y adjudicacion.',
  audits (
    not_null(columns := (licitacion_key, id, placsp_id)),
    unique_values(columns := (licitacion_key)),
    unique_values(columns := (id))
  )
);

SELECT
  f.licitacion_key,
  md5('licitacion:' || f.entry_id)::UUID::TEXT AS id,
  f.entry_id AS placsp_id,
  f.contract_folder_id AS expediente,
  coalesce(f.name, f.title) AS titulo,
  f.summary AS descripcion,
  f.link AS url_place,
  f.ted_uuid,
  CASE f.feed_type
    WHEN 'insiders' THEN 'Perfil alojado en PLACSP'
    WHEN 'outsiders' THEN 'Plataforma autonómica agregada'
    ELSE f.feed_type
  END AS plataforma,

  -- Current status (the timeline is the cambio_estado fact)
  f.status_code AS estado_codigo,
  @etiqueta('status_code', f.status_code) AS estado,

  -- How it is contracted
  f.type_code AS tipo_contrato_codigo,
  @etiqueta('type_code', f.type_code) AS tipo_contrato,
  f.sub_type_code AS subtipo_codigo,
  @etiqueta('sub_type_code', f.sub_type_code) AS subtipo,
  f.procedure_code AS procedimiento_codigo,
  @etiqueta('procedure_code', f.procedure_code) AS procedimiento,
  f.urgency_code AS tramitacion_codigo,
  @etiqueta('urgency_code', f.urgency_code) AS tramitacion,
  f.contracting_system_code AS sistema_contratacion_codigo,
  @etiqueta('contracting_system', f.contracting_system_code) AS sistema_contratacion,
  f.submission_method_code AS presentacion_ofertas_codigo,
  @etiqueta('submission_method', f.submission_method_code) AS presentacion_ofertas,
  f.part_presentation_code AS presentacion_lotes_codigo,
  @etiqueta('part_presentation', f.part_presentation_code) AS presentacion_lotes,
  f.over_threshold_indicator AS regulacion_armonizada,
  f.auction_constraint_indicator AS subasta_electronica,
  f.variant_constraint_indicator AS admite_variantes,
  f.mix_contract_indicator AS contrato_mixto,
  f.national_legislation_code AS legislacion_codigo,
  @etiqueta('national_legislation', f.national_legislation_code) AS legislacion,
  f.procurement_legislation_id AS legislacion_id,

  -- Funding
  f.funding_program_code AS financiacion_codigo,
  @etiqueta('funding_program', f.funding_program_code) AS financiacion,
  f.funding_program_code = 'EU' AS financiacion_ue,
  f.funding_program_name AS programa_financiacion,
  f.funding_program_description AS financiacion_descripcion,

  -- Duration and terms
  f.duration_measure AS duracion,
  f.duration_unit_code AS duracion_unidad,
  f.currency_id AS moneda,
  f.submission_deadline_description AS plazo_descripcion,
  f.document_availability_end_time AS hora_fin_documentacion,
  f.participation_request_end_time AS hora_fin_solicitudes,
  f.allowed_subcontract_rate AS tasa_subcontratacion_maxima,
  f.allowed_subcontract_description AS subcontratacion_descripcion,
  f.options_description AS opciones,
  f.option_validity_description AS opciones_validez,
  f.price_revision_formula AS formula_revision_precios,
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
