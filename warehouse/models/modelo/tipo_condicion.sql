MODEL (
  name modelo.tipo_condicion,
  kind FULL,
  tags (dimension),
  grain tipo_condicion_key,
  description 'Tipo de condición especial de ejecución (social, medioambiental, innovación…).',
  audits (
    not_null(columns := (tipo_condicion_key)),
    unique_values(columns := (tipo_condicion_key))
  )
);

WITH codigos AS (
  SELECT code AS codigo FROM stage.codice_code WHERE list = 'execution_requirement'
  UNION
  SELECT execution_requirement_code FROM stage.execution_condition
  WHERE execution_requirement_code IS NOT NULL
)
SELECT
  @clave('tipo_condicion', codigo) AS tipo_condicion_key,
  codigo,
  @etiqueta('execution_requirement', codigo) AS descripcion
FROM codigos
UNION ALL
SELECT 0, '?', 'Desconocida'
