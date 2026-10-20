MODEL (
  name stage.contract,
  kind VIEW,
  grain (entry_id, result_n),
  description 'Formalización del contrato de un resultado.'
);

SELECT
  @clave('licitacion', entry_id) AS licitacion_key,
  entry_id::TEXT AS entry_id,
  result_n::INT AS result_n,
  @texto(contract_number) AS contract_number,
  @fecha(issue_date) AS issue_date
FROM @raw(contract)
