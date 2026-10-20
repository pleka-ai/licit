MODEL (
  name modelo.resultado,
  kind FULL,
  grain resultado_key,
  description 'Resultado de un procedimiento o lote (adjudicado, desierto, desistimiento…).',
  audits (
    not_null(columns := (resultado_key, codigo)),
    unique_values(columns := (resultado_key))
  )
);

WITH codigos AS (
  SELECT code AS codigo FROM stage.codice_code WHERE list = 'result_code'
  UNION
  SELECT result_code FROM stage.tender_result WHERE result_code IS NOT NULL
)
SELECT
  @clave('resultado', codigo) AS resultado_key,
  codigo,
  @etiqueta('result_code', codigo) AS descripcion,
  -- 2 provisional, 8 definitiva, 9 formalizado, 10 parcialmente adjudicado
  codigo IN ('2', '8', '9', '10') AS es_adjudicacion
FROM codigos
UNION ALL
SELECT 0, '?', 'Desconocido', false
