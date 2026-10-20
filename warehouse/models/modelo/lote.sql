MODEL (
  name modelo.lote,
  kind FULL,
  tags (hecho),
  depends_on (modelo.organo, modelo.modalidad, modelo.estado, modelo.cpv, modelo.lugar),
  grain (licitacion_key, lote_numero),
  description 'Objeto del contrato al nivel más atómico: una fila por lote; los expedientes sin lotes tienen una sola fila (lote_numero = 0, es_objeto_unico) con el presupuesto del expediente. Sumar presupuesto_sin_iva aquí nunca cuenta dos veces.',
  audits (
    not_null(columns := (licitacion_key, lote_numero, organo_key, modalidad_key, estado_key, cpv_key, lugar_key)),
    unique_combination_of_columns(columns := (licitacion_key, lote_numero)),
    clave_existe(columna := cpv_key, dimension := modelo.cpv),
    clave_existe(columna := lugar_key, dimension := modelo.lugar)
  )
);

WITH cpv_lote AS (
  SELECT licitacion_key, lot_number, arg_min(cpv_code, n) AS cpv_code
  FROM stage.cpv_classification
  WHERE lot_number IS NOT NULL
  GROUP BY ALL
),
lotes AS (
  SELECT
    l.licitacion_key,
    l.lot_number AS lote_numero,
    false AS es_objeto_unico,
    l.name AS titulo,
    c.cpv_code,
    l.nuts_code,
    l.tax_exclusive_amount AS presupuesto_sin_iva,
    l.total_amount AS presupuesto_con_iva
  FROM stage.procurement_project_lot AS l
  LEFT JOIN cpv_lote AS c USING (licitacion_key, lot_number)
  UNION ALL
  SELECT
    f.licitacion_key,
    '0',
    true,
    coalesce(f.name, f.title),
    NULL,
    NULL,
    f.tax_exclusive_amount,
    f.total_amount
  FROM stage.contract_folder_status AS f
  WHERE NOT EXISTS (
    SELECT 1 FROM stage.procurement_project_lot AS l
    WHERE l.licitacion_key = f.licitacion_key
  )
)
SELECT
  x.licitacion_key,
  x.lote_numero,
  x.es_objeto_unico,
  x.titulo,
  e.organo_key,
  e.modalidad_key,
  e.estado_key,
  coalesce(@clave('cpv', x.cpv_code), e.cpv_key) AS cpv_key,
  coalesce(@clave('lugar', x.nuts_code), e.lugar_key) AS lugar_key,
  e.fecha_publicacion::DATE AS fecha_publicacion,
  x.presupuesto_sin_iva,
  x.presupuesto_con_iva
FROM lotes AS x
JOIN stage.expediente_claves AS e USING (licitacion_key)
