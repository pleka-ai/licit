MODEL (
  name modelo.clasificacion_exigida,
  kind FULL,
  grain clasificacion_key,
  description 'Clasificación empresarial (grupo, subgrupo, categoría) exigida para licitar.',
  audits (
    not_null(columns := (clasificacion_key, licitacion_key, codigo)),
    unique_values(columns := (clasificacion_key))
  )
);

SELECT
  @clave('clasificacion', b.licitacion_key, b.n) AS clasificacion_key,
  b.licitacion_key,
  b.n AS clasificacion_n,
  b.code_value AS codigo
FROM stage.business_classification AS b
