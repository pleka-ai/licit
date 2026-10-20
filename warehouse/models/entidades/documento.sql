MODEL (
  name modelo.documento,
  kind FULL,
  grain documento_key,
  description 'Documento de una licitación: pliegos de cláusulas administrativas y de prescripciones técnicas, documentación adicional y anuncios publicados, con su enlace.',
  audits (
    not_null(columns := (documento_key, licitacion_key)),
    unique_values(columns := (documento_key))
  )
);

SELECT
  @clave('documento', d.licitacion_key, d.n) AS documento_key,
  d.licitacion_key,
  d.n AS documento_n,
  d.notice_n AS anuncio_n,
  d.source_type AS origen_codigo,
  CASE d.source_type
    WHEN 'LEGAL' THEN 'Pliego de cláusulas administrativas'
    WHEN 'TECHNICAL' THEN 'Pliego de prescripciones técnicas'
    WHEN 'ADDITIONAL' THEN 'Documentación adicional'
    WHEN 'GENERAL' THEN 'Documento general'
    WHEN 'PUBLICATION' THEN 'Anuncio publicado'
    ELSE d.source_type
  END AS origen,
  d.document_type_code AS tipo_codigo,
  @etiqueta('document_type', d.document_type_code) AS tipo,
  d.filename AS nombre,
  d.uri AS url,
  d.document_hash AS huella
FROM stage.document_reference AS d
