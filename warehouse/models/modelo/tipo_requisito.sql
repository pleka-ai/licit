MODEL (
  name modelo.tipo_requisito,
  kind FULL,
  grain tipo_requisito_key,
  description 'Clase de requisito de participación: solvencia técnica, económica o declaración, por criterio de evaluación.',
  audits (
    not_null(columns := (tipo_requisito_key)),
    unique_values(columns := (tipo_requisito_key))
  )
);

WITH combinaciones AS (
  SELECT DISTINCT origin_type, evaluation_criteria_type_code
  FROM stage.qualification_requirement
)
SELECT
  @clave('tipo_requisito', coalesce(origin_type, '∅'), coalesce(evaluation_criteria_type_code, '∅'))
    AS tipo_requisito_key,
  origin_type AS clase_codigo,
  CASE origin_type
    WHEN 'TECHNICAL' THEN 'Solvencia técnica'
    WHEN 'FINANCIAL' THEN 'Solvencia económica'
    WHEN 'DECLARATION' THEN 'Declaración'
    ELSE origin_type
  END AS clase,
  evaluation_criteria_type_code AS criterio_codigo,
  CASE
    WHEN origin_type = 'DECLARATION'
      THEN @etiqueta('declaration_type', evaluation_criteria_type_code)
    ELSE @etiqueta('evaluation_criteria_type', evaluation_criteria_type_code)
  END AS criterio
FROM combinaciones
UNION ALL
SELECT 0, NULL, 'Desconocido', NULL, NULL
