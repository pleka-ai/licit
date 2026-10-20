MODEL (
  name stage.financial_guarantee,
  kind VIEW,
  grain (entry_id, n),
  description 'Garantías exigidas.'
);

SELECT
  @clave('licitacion', entry_id) AS licitacion_key,
  entry_id::TEXT AS entry_id,
  n::INT AS n,
  guarantee_type_code::TEXT AS guarantee_type_code,
  amount_rate::DOUBLE AS amount_rate,
  liability_amount::DOUBLE AS liability_amount,
  currency_id::TEXT AS currency_id
FROM @raw(financial_guarantee)
