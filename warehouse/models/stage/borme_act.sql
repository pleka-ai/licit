MODEL (
  name stage.borme_act,
  kind VIEW,
  grain (doc_id, number, n),
  description 'Actos inscritos de cada anuncio del BORME, con los campos que el parser extrae.'
);

SELECT
  doc_id::TEXT AS doc_id,
  number::BIGINT AS number,
  n::INT AS n,
  kind::TEXT AS kind,
  @texto(text) AS text,
  capital::DOUBLE AS capital,
  resulting_capital::DOUBLE AS resulting_capital,
  @texto(address) AS address,
  @texto(new_name) AS new_name,
  @texto(purpose) AS purpose,
  @fecha(start_of_operations) AS start_of_operations
FROM @borme(act)
