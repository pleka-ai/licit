MODEL (
  name stage.execution_condition,
  kind VIEW,
  grain (entry_id, n),
  description 'Condiciones especiales de ejecución.'
);

SELECT
  @clave('licitacion', entry_id) AS licitacion_key,
  entry_id::TEXT AS entry_id,
  n::INT AS n,
  @texto(name) AS name,
  execution_requirement_code::TEXT AS execution_requirement_code,
  @texto(description) AS description
FROM @raw(execution_condition)
