MODEL (
  name modelo.adjudicacion,
  kind FULL,
  tags (hecho),
  depends_on (modelo.licitacion, modelo.lote, modelo.empresa, modelo.organo, modelo.resultado, modelo.cpv, modelo.lugar),
  grain (licitacion_key, resultado_n, adjudicatario_n),
  description 'Hecho transaccional: un resultado de adjudicación (de la licitación o de un lote) por adjudicatario, con las claves de todas sus dimensiones. Si hay varios adjudicatarios, los importes se reparten con `peso`, así que todas las medidas suman. Los resultados sin adjudicatario (desierto, desistimiento) llevan empresa -1.',
  audits (
    not_null(columns := (licitacion_key, lote_key, resultado_n, adjudicatario_n, empresa_key, organo_key, resultado_key, cpv_key, lugar_key)),
    unique_combination_of_columns(columns := (licitacion_key, resultado_n, adjudicatario_n)),
    clave_existe(columna := licitacion_key, dimension := modelo.licitacion),
    clave_existe(columna := lote_key, dimension := modelo.lote),
    clave_existe(columna := empresa_key, dimension := modelo.empresa),
    clave_existe(columna := organo_key, dimension := modelo.organo),
    clave_existe(columna := resultado_key, dimension := modelo.resultado),
    clave_existe(columna := cpv_key, dimension := modelo.cpv),
    clave_existe(columna := lugar_key, dimension := modelo.lugar)
  )
);

WITH ganadores AS (
  SELECT
    licitacion_key,
    result_n,
    n,
    empresa_ref,
    count(*) OVER (PARTITION BY licitacion_key, result_n) AS n_ganadores
  FROM stage.winning_party
)
SELECT
  r.licitacion_key,
  r.n AS resultado_n,
  coalesce(w.n, 0) AS adjudicatario_n,
  -- The result's lot, the whole object for licitaciones without lots, or the
  -- 'lote desconocido' member when the lot is not declared.
  coalesce(
    @clave('lote', l.licitacion_key, l.lote_numero),
    CASE WHEN l1.es_objeto_unico THEN @clave('lote', l1.licitacion_key, '0') END,
    0
  ) AS lote_key,
  r.lot_number AS lote_numero,
  coalesce(@clave('empresa', w.empresa_ref), -1) AS empresa_key,
  e.organo_key,
  @clave_o('resultado', r.result_code) AS resultado_key,
  coalesce(@clave('cpv', l.cpv_code), e.cpv_key) AS cpv_key,
  coalesce(@clave('lugar', l.nuts_code), e.lugar_key) AS lugar_key,
  e.fecha_publicacion::DATE AS fecha_publicacion,
  r.award_date AS fecha_adjudicacion,
  c.issue_date AS fecha_formalizacion,
  r.start_date AS fecha_inicio,
  c.contract_number AS numero_contrato,
  r.description AS descripcion,
  r.awarded_owner_nationality_code AS nacionalidad_adjudicatario,
  r.sme_awarded_indicator AS adjudicatario_pyme,
  r.abnormally_low_tenders_indicator AS ofertas_anormalmente_bajas,
  r.subcontract_rate AS tasa_subcontratacion,
  r.subcontract_description AS subcontratacion_descripcion,
  1.0 / coalesce(w.n_ganadores, 1) AS peso,
  r.awarded_tax_exclusive_amount / coalesce(w.n_ganadores, 1) AS importe_sin_iva,
  r.awarded_payable_amount / coalesce(w.n_ganadores, 1) AS importe_con_iva,
  coalesce(l.presupuesto_sin_iva, e.tax_exclusive_amount) / coalesce(w.n_ganadores, 1)
    AS presupuesto_sin_iva,
  r.lower_tender_amount AS oferta_minima,
  r.higher_tender_amount AS oferta_maxima,
  r.received_tender_quantity AS num_ofertas,
  r.smes_received_tender_quantity AS num_ofertas_pyme,
  r.eu_nationals_received_quantity AS num_ofertas_ue,
  r.non_eu_nationals_received_qty AS num_ofertas_no_ue
FROM stage.tender_result AS r
JOIN stage.expediente_claves AS e USING (licitacion_key)
LEFT JOIN ganadores AS w ON w.licitacion_key = r.licitacion_key AND w.result_n = r.n
LEFT JOIN stage.contract AS c ON c.licitacion_key = r.licitacion_key AND c.result_n = r.n
LEFT JOIN stage.lote AS l
  ON l.licitacion_key = r.licitacion_key AND l.lote_numero = r.lot_number
  AND NOT l.es_objeto_unico
LEFT JOIN stage.lote AS l1
  ON l1.licitacion_key = r.licitacion_key AND l1.es_objeto_unico
