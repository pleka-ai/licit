MODEL (
  name stage.document_reference,
  kind VIEW,
  grain (entry_id, n),
  description 'Documentos del expediente (pliegos, anuncios, adicionales).'
);

SELECT
  @clave('licitacion', entry_id) AS licitacion_key,
  entry_id::TEXT AS entry_id,
  n::INT AS n,
  notice_n::INT AS notice_n,
  source_type::TEXT AS source_type,
  @texto(filename) AS filename,
  @texto(uri) AS uri,
  @texto(document_hash) AS document_hash,
  document_type_code::TEXT AS document_type_code
FROM @raw(document_reference)
