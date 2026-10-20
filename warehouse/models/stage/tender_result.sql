MODEL (
  name stage.tender_result,
  kind VIEW,
  grain (entry_id, n),
  description 'Resultados de adjudicación (por expediente o por lote).'
);

SELECT
  @clave('licitacion', entry_id) AS licitacion_key,
  entry_id::TEXT AS entry_id,
  n::INT AS n,
  coalesce(@texto(lot_number), @texto(awarded_lot_number)) AS lot_number,
  result_code::TEXT AS result_code,
  @texto(description) AS description,
  @fecha(award_date) AS award_date,
  received_tender_quantity::INT AS received_tender_quantity,
  lower_tender_amount::DOUBLE AS lower_tender_amount,
  higher_tender_amount::DOUBLE AS higher_tender_amount,
  sme_awarded_indicator::BOOLEAN AS sme_awarded_indicator,
  abnormally_low_tenders_indicator::BOOLEAN AS abnormally_low_tenders_indicator,
  @fecha(start_date) AS start_date,
  smes_received_tender_quantity::INT AS smes_received_tender_quantity,
  eu_nationals_received_quantity::INT AS eu_nationals_received_quantity,
  non_eu_nationals_received_qty::INT AS non_eu_nationals_received_qty,
  awarded_owner_nationality_code::TEXT AS awarded_owner_nationality_code,
  subcontract_rate::DOUBLE AS subcontract_rate,
  @texto(subcontract_description) AS subcontract_description,
  awarded_tax_exclusive_amount::DOUBLE AS awarded_tax_exclusive_amount,
  awarded_payable_amount::DOUBLE AS awarded_payable_amount,
  awarded_currency_id::TEXT AS awarded_currency_id
FROM @raw(tender_result)
