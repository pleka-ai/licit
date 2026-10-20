MODEL (
  name modelo.tipo_documento,
  kind FULL,
  tags (dimension),
  grain tipo_documento_key,
  description 'Clase de documento: origen (pliego legal, técnico, adicional, general, anuncio) por tipo CODICE.',
  audits (
    not_null(columns := (tipo_documento_key)),
    unique_values(columns := (tipo_documento_key))
  )
);

WITH combinaciones AS (
  SELECT DISTINCT source_type, document_type_code FROM stage.document_reference
)
SELECT
  @clave('tipo_documento', coalesce(source_type, '∅'), coalesce(document_type_code, '∅'))
    AS tipo_documento_key,
  source_type AS origen_codigo,
  CASE source_type
    WHEN 'LEGAL' THEN 'Pliego de cláusulas administrativas'
    WHEN 'TECHNICAL' THEN 'Pliego de prescripciones técnicas'
    WHEN 'ADDITIONAL' THEN 'Documentación adicional'
    WHEN 'GENERAL' THEN 'Documento general'
    WHEN 'PUBLICATION' THEN 'Anuncio publicado'
    ELSE source_type
  END AS origen,
  document_type_code AS tipo_codigo,
  @etiqueta('document_type', document_type_code) AS tipo
FROM combinaciones
UNION ALL
SELECT 0, NULL, 'Desconocido', NULL, NULL
