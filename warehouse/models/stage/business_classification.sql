MODEL (
  name stage.business_classification,
  kind VIEW,
  grain (entry_id, n),
  description 'Clasificación empresarial exigida.'
);

SELECT
  @clave('licitacion', entry_id) AS licitacion_key,
  entry_id::TEXT AS entry_id,
  n::INT AS n,
  @texto(code_value) AS code_value
FROM @raw(business_classification)
WHERE @texto(code_value) IS NOT NULL
