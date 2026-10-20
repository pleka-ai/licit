MODEL (
  name modelo.garantia,
  kind FULL,
  grain garantia_key,
  description 'Garantía exigida en una licitación (provisional, definitiva, complementaria), en porcentaje o importe.',
  audits (
    not_null(columns := (garantia_key, licitacion_key)),
    unique_values(columns := (garantia_key))
  )
);

SELECT
  @clave('garantia', g.licitacion_key, g.n) AS garantia_key,
  g.licitacion_key,
  g.n AS garantia_n,
  g.guarantee_type_code AS tipo_codigo,
  @etiqueta('guarantee_type', g.guarantee_type_code) AS tipo,
  g.amount_rate AS porcentaje,
  g.liability_amount AS importe,
  g.currency_id AS moneda
FROM stage.financial_guarantee AS g
