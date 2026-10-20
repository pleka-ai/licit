MODEL (
  name stage.realized_location,
  kind VIEW,
  grain (entry_id, lot_number, n),
  description 'Lugares de ejecución de cada lote.'
);

SELECT
  @clave('licitacion', entry_id) AS licitacion_key,
  entry_id::TEXT AS entry_id,
  @texto(lot_number) AS lot_number,
  n::INT AS n,
  @texto(nuts_code) AS nuts_code,
  @texto(country_subentity) AS country_subentity,
  country_code::TEXT AS country_code,
  @texto(city_name) AS city_name,
  @texto(postal_zone) AS postal_zone,
  @texto(street_name) AS street_name
FROM @raw(realized_location)
