MODEL (
  name modelo.requisito,
  kind FULL,
  grain requisito_key,
  description 'Requisito para participar en una licitación: solvencia técnica o económica (con su umbral, años de experiencia o plantilla) o declaración exigida.',
  audits (
    not_null(columns := (requisito_key, licitacion_key)),
    unique_values(columns := (requisito_key))
  )
);

SELECT
  @clave('requisito', q.licitacion_key, q.n) AS requisito_key,
  q.licitacion_key,
  q.n AS requisito_n,
  q.lot_number AS lote_numero,
  q.origin_type AS clase_codigo,
  CASE q.origin_type
    WHEN 'TECHNICAL' THEN 'Solvencia técnica'
    WHEN 'FINANCIAL' THEN 'Solvencia económica'
    WHEN 'DECLARATION' THEN 'Declaración'
    ELSE q.origin_type
  END AS clase,
  q.evaluation_criteria_type_code AS criterio_codigo,
  CASE
    WHEN q.origin_type = 'DECLARATION'
      THEN @etiqueta('declaration_type', q.evaluation_criteria_type_code)
    ELSE @etiqueta('evaluation_criteria_type', q.evaluation_criteria_type_code)
  END AS criterio,
  q.description AS descripcion,
  q.personal_situation AS situacion_personal,
  q.threshold_quantity AS umbral,
  q.operating_years_quantity AS anios_experiencia,
  q.employee_quantity AS num_empleados
FROM stage.qualification_requirement AS q
