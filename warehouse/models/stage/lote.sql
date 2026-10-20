MODEL (
  name stage.lote,
  kind VIEW,
  grain (licitacion_key, lote_numero),
  description 'Lotes de cada licitación con su CPV y NUTS propios; una licitación sin lotes aparece como un único lote "0" (objeto único) con el presupuesto del expediente.'
);

WITH cpv_lote AS (
  SELECT licitacion_key, lot_number, arg_min(cpv_code, n) AS cpv_code
  FROM stage.cpv_classification
  WHERE lot_number IS NOT NULL
  GROUP BY ALL
)
SELECT
  l.licitacion_key::BIGINT AS licitacion_key,
  l.lot_number::TEXT AS lote_numero,
  false AS es_objeto_unico,
  l.name::TEXT AS titulo,
  c.cpv_code::TEXT AS cpv_code,
  l.nuts_code::TEXT AS nuts_code,
  l.tax_exclusive_amount::DOUBLE AS presupuesto_sin_iva,
  l.total_amount::DOUBLE AS presupuesto_con_iva
FROM stage.procurement_project_lot AS l
LEFT JOIN cpv_lote AS c
  ON c.licitacion_key = l.licitacion_key AND c.lot_number = l.lot_number
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
