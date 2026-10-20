MODEL (
  name stage.qualification_requirement,
  kind VIEW,
  grain (entry_id, n),
  description 'Requisitos de solvencia y declaraciones exigidas.'
);

SELECT
  @clave('licitacion', entry_id) AS licitacion_key,
  entry_id::TEXT AS entry_id,
  n::INT AS n,
  @texto(lot_number) AS lot_number,
  origin_type::TEXT AS origin_type,
  evaluation_criteria_type_code::TEXT AS evaluation_criteria_type_code,
  @texto(description) AS description,
  threshold_quantity::DOUBLE AS threshold_quantity,
  @texto(personal_situation) AS personal_situation,
  operating_years_quantity::INT AS operating_years_quantity,
  employee_quantity::INT AS employee_quantity
FROM @raw(qualification_requirement)
