MODEL (
  name stage.awarding_criteria,
  kind VIEW,
  grain (entry_id, n),
  description 'Criterios de adjudicación del expediente o de un lote.'
);

SELECT
  @clave('licitacion', entry_id) AS licitacion_key,
  entry_id::TEXT AS entry_id,
  n::INT AS n,
  @texto(lot_number) AS lot_number,
  criteria_type_code::TEXT AS criteria_type_code,
  criteria_sub_type_code::TEXT AS criteria_sub_type_code,
  @texto(description) AS description,
  weight_numeric::DOUBLE AS weight_numeric,
  @texto(note) AS note
FROM @raw(awarding_criteria)
