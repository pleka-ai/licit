MODEL (
  name modelo.tipo_anuncio,
  kind FULL,
  tags (dimension),
  grain tipo_anuncio_key,
  description 'Tipo de anuncio publicado (licitación, adjudicación, formalización, anulaciones…).',
  audits (
    not_null(columns := (tipo_anuncio_key)),
    unique_values(columns := (tipo_anuncio_key))
  )
);

WITH codigos AS (
  SELECT code AS codigo FROM stage.codice_code WHERE list = 'notice_type'
  UNION
  SELECT notice_type_code FROM stage.valid_notice_info WHERE notice_type_code IS NOT NULL
)
SELECT
  @clave('tipo_anuncio', codigo) AS tipo_anuncio_key,
  codigo,
  @etiqueta('notice_type', codigo) AS descripcion,
  codigo LIKE 'ANUL%' AS es_anulacion
FROM codigos
UNION ALL
SELECT 0, '?', 'Desconocido', false
