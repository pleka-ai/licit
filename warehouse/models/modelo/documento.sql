MODEL (
  name modelo.documento,
  kind FULL,
  tags (hecho),
  depends_on (modelo.tipo_documento, modelo.organo),
  grain (licitacion_key, documento_n),
  description 'Hecho sin medidas: cada documento publicado del expediente (pliegos, documentación adicional, anuncios en PDF).',
  audits (
    not_null(columns := (licitacion_key, documento_n, tipo_documento_key, organo_key)),
    unique_combination_of_columns(columns := (licitacion_key, documento_n)),
    clave_existe(columna := tipo_documento_key, dimension := modelo.tipo_documento)
  )
);

SELECT
  d.licitacion_key,
  d.n AS documento_n,
  d.notice_n AS anuncio_n,
  @clave_o(
    'tipo_documento', coalesce(d.source_type, '∅'), coalesce(d.document_type_code, '∅')
  ) AS tipo_documento_key,
  e.organo_key,
  e.fecha_publicacion::DATE AS fecha_publicacion,
  d.filename AS nombre,
  d.uri AS url,
  d.document_hash AS huella
FROM stage.document_reference AS d
JOIN stage.expediente_claves AS e USING (licitacion_key)
