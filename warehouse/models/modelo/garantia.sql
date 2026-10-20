MODEL (
  name modelo.garantia,
  kind FULL,
  tags (hecho),
  depends_on (modelo.tipo_garantia, modelo.organo),
  grain (licitacion_key, garantia_n),
  description 'Garantías exigidas al licitador o al adjudicatario.',
  audits (
    not_null(columns := (licitacion_key, garantia_n, tipo_garantia_key, organo_key)),
    unique_combination_of_columns(columns := (licitacion_key, garantia_n)),
    clave_existe(columna := tipo_garantia_key, dimension := modelo.tipo_garantia)
  )
);

SELECT
  g.licitacion_key,
  g.n AS garantia_n,
  @clave_o('tipo_garantia', g.guarantee_type_code) AS tipo_garantia_key,
  e.organo_key,
  e.fecha_publicacion::DATE AS fecha_publicacion,
  g.amount_rate AS porcentaje,
  g.liability_amount AS importe,
  g.currency_id AS moneda
FROM stage.financial_guarantee AS g
JOIN stage.expediente_claves AS e USING (licitacion_key)
