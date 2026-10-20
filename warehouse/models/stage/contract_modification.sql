MODEL (
  name stage.contract_modification,
  kind VIEW,
  grain (entry_id, n),
  description 'Modificaciones de contrato.'
);

SELECT
  @clave('licitacion', entry_id) AS licitacion_key,
  entry_id::TEXT AS entry_id,
  n::INT AS n,
  @texto(modification_number) AS modification_number,
  @texto(contract_id) AS contract_id,
  @texto(note) AS note,
  modification_duration_measure::DOUBLE AS modification_duration_measure,
  modification_duration_unit_code::TEXT AS modification_duration_unit_code,
  final_duration_measure::DOUBLE AS final_duration_measure,
  final_duration_unit_code::TEXT AS final_duration_unit_code,
  modification_tax_exclusive_amount::DOUBLE AS modification_tax_exclusive_amount,
  final_tax_exclusive_amount::DOUBLE AS final_tax_exclusive_amount,
  currency_id::TEXT AS currency_id
FROM @raw(contract_modification)
