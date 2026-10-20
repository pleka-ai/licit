MODEL (
  name stage.winning_party,
  kind VIEW,
  grain (entry_id, result_n, n),
  description 'Adjudicatarios de cada resultado, con la clave de empresa resuelta.'
);

SELECT
  @clave('licitacion', entry_id) AS licitacion_key,
  entry_id::TEXT AS entry_id,
  result_n::INT AS result_n,
  n::INT AS n,
  -- Business key: the (parser-normalised) NIF, else the name.
  coalesce(
    upper(@texto(identifier)),
    'SIN-NIF:' || upper(regexp_replace(@texto(name), '\s+', ' ', 'g'))
  ) AS empresa_ref,
  upper(@texto(identifier)) AS identifier,
  identifier_scheme::TEXT AS identifier_scheme,
  @texto(name) AS name,
  @texto(nuts_code) AS nuts_code,
  @texto(city_name) AS city_name,
  @texto(postal_zone) AS postal_zone,
  country_code::TEXT AS country_code,
  company_type_code::TEXT AS company_type_code
FROM @raw(winning_party)
WHERE @texto(identifier) IS NOT NULL OR @texto(name) IS NOT NULL
