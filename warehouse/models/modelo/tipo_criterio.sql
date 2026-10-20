MODEL (
  name modelo.tipo_criterio,
  kind FULL,
  tags (dimension),
  grain tipo_criterio_key,
  description 'Tipo y subtipo de criterio de adjudicación (automático o por juicio de valor; precio, calidad…).',
  audits (
    not_null(columns := (tipo_criterio_key)),
    unique_values(columns := (tipo_criterio_key))
  )
);

WITH combinaciones AS (
  SELECT DISTINCT criteria_type_code, criteria_sub_type_code FROM stage.awarding_criteria
)
SELECT
  @clave('tipo_criterio', coalesce(criteria_type_code, '∅'), coalesce(criteria_sub_type_code, '∅'))
    AS tipo_criterio_key,
  criteria_type_code AS tipo_codigo,
  @etiqueta('awarding_criteria_type', criteria_type_code) AS tipo,
  criteria_sub_type_code AS subtipo_codigo,
  @etiqueta('awarding_criteria_sub_type', criteria_sub_type_code) AS subtipo
FROM combinaciones
UNION ALL
SELECT 0, NULL, 'Desconocido', NULL, NULL
