MODEL (
  name modelo.clasificacion_exigida,
  kind FULL,
  depends_on (modelo.organo),
  grain (licitacion_key, clasificacion_n),
  description 'Hecho sin medidas: clasificación empresarial (grupo, subgrupo, categoría) exigida para licitar.',
  audits (
    not_null(columns := (licitacion_key, clasificacion_n, organo_key, codigo)),
    unique_combination_of_columns(columns := (licitacion_key, clasificacion_n))
  )
);

SELECT
  b.licitacion_key,
  b.n AS clasificacion_n,
  e.organo_key,
  e.fecha_publicacion::DATE AS fecha_publicacion,
  b.code_value AS codigo
FROM stage.business_classification AS b
JOIN stage.expediente_claves AS e USING (licitacion_key)
