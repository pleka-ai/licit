MODEL (
  name modelo.modificacion,
  kind FULL,
  tags (hecho),
  depends_on (modelo.licitacion, modelo.organo, modelo.cpv, modelo.lugar),
  grain (licitacion_key, modificacion_n),
  description 'Hecho transaccional: cada modificación de contrato, con su efecto en importe y plazo.',
  audits (
    not_null(columns := (licitacion_key, modificacion_n, organo_key, cpv_key, lugar_key)),
    unique_combination_of_columns(columns := (licitacion_key, modificacion_n)),
    clave_existe(columna := licitacion_key, dimension := modelo.licitacion),
    clave_existe(columna := organo_key, dimension := modelo.organo)
  )
);

SELECT
  m.licitacion_key,
  m.n AS modificacion_n,
  e.organo_key,
  e.cpv_key,
  e.lugar_key,
  e.fecha_publicacion::DATE AS fecha_publicacion,
  m.modification_number AS numero,
  m.contract_id AS contrato_id,
  m.note AS nota,
  m.modification_tax_exclusive_amount AS importe_modificacion_sin_iva,
  m.final_tax_exclusive_amount AS importe_final_sin_iva,
  m.modification_duration_measure AS plazo_modificacion,
  m.modification_duration_unit_code AS plazo_modificacion_unidad,
  m.final_duration_measure AS plazo_final,
  m.final_duration_unit_code AS plazo_final_unidad,
  m.currency_id AS moneda
FROM stage.contract_modification AS m
JOIN stage.expediente_claves AS e USING (licitacion_key)
