MODEL (
  name stage.cpv_classification,
  kind VIEW,
  grain (entry_id, n),
  description 'Códigos CPV del expediente (lot_number NULL) o de un lote, en orden de publicación.'
);

SELECT
  @clave('licitacion', entry_id) AS licitacion_key,
  entry_id::TEXT AS entry_id,
  n::INT AS n,
  @texto(lot_number) AS lot_number,
  left(regexp_replace(item_classification_code, '[^0-9]', '', 'g'), 8) AS cpv_code
FROM @raw(cpv_classification)
WHERE regexp_replace(item_classification_code, '[^0-9]', '', 'g') <> ''
