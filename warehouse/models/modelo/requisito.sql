MODEL (
  name modelo.requisito,
  kind FULL,
  depends_on (modelo.tipo_requisito, modelo.organo),
  grain (licitacion_key, requisito_n),
  description 'Requisitos de participación: solvencia técnica y económica (con umbrales) y declaraciones exigidas.',
  audits (
    not_null(columns := (licitacion_key, requisito_n, tipo_requisito_key, organo_key)),
    unique_combination_of_columns(columns := (licitacion_key, requisito_n)),
    clave_existe(columna := tipo_requisito_key, dimension := modelo.tipo_requisito)
  )
);

SELECT
  q.licitacion_key,
  q.n AS requisito_n,
  q.lot_number AS lote_numero,
  @clave_o(
    'tipo_requisito',
    coalesce(q.origin_type, '∅'),
    coalesce(q.evaluation_criteria_type_code, '∅')
  ) AS tipo_requisito_key,
  e.organo_key,
  e.fecha_publicacion::DATE AS fecha_publicacion,
  q.description AS descripcion,
  q.personal_situation AS situacion_personal,
  q.threshold_quantity AS umbral,
  q.operating_years_quantity AS anios_experiencia,
  q.employee_quantity AS num_empleados
FROM stage.qualification_requirement AS q
JOIN stage.expediente_claves AS e USING (licitacion_key)
