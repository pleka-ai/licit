MODEL (
  name stage.procurement_project_lot,
  kind VIEW,
  grain (entry_id, lot_number),
  description 'Lotes declarados en el expediente.'
);

SELECT
  @clave('licitacion', entry_id) AS licitacion_key,
  entry_id::TEXT AS entry_id,
  @texto(lot_number) AS lot_number,
  @texto(name) AS name,
  total_amount::DOUBLE AS total_amount,
  tax_exclusive_amount::DOUBLE AS tax_exclusive_amount,
  currency_id::TEXT AS currency_id,
  @texto(nuts_code) AS nuts_code,
  @texto(country_subentity) AS country_subentity
FROM @raw(procurement_project_lot)
