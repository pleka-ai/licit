MODEL (
  name modelo.anuncio,
  kind FULL,
  tags (hecho),
  depends_on (modelo.licitacion, modelo.organo, modelo.cpv, modelo.lugar),
  grain (licitacion_key, anuncio_n, publicacion_n),
  description 'Hecho sin medidas: cada publicación de un anuncio en un medio (perfil del contratante, DOUE, BOE, boletines autonómicos). Los anuncios sin medio tienen publicacion_n = 0.',
  audits (
    not_null(columns := (licitacion_key, anuncio_n, publicacion_n, organo_key, cpv_key, lugar_key)),
    unique_combination_of_columns(columns := (licitacion_key, anuncio_n, publicacion_n)),
    clave_existe(columna := licitacion_key, dimension := modelo.licitacion),
    clave_existe(columna := organo_key, dimension := modelo.organo)
  )
);

SELECT
  v.licitacion_key,
  v.n AS anuncio_n,
  coalesce(p.n, 0) AS publicacion_n,
  e.organo_key,
  e.cpv_key,
  e.lugar_key,
  v.notice_type_code AS tipo_anuncio_codigo,
  @etiqueta('notice_type', v.notice_type_code) AS tipo_anuncio,
  coalesce(v.notice_type_code LIKE 'ANUL%', false) AS es_anulacion,
  v.notice_issue_date AS fecha_anuncio,
  coalesce(p.issue_date, v.notice_issue_date) AS fecha_publicacion,
  p.publication_media_name AS medio
FROM stage.valid_notice_info AS v
JOIN stage.expediente_claves AS e USING (licitacion_key)
LEFT JOIN stage.publication_status AS p
  ON p.licitacion_key = v.licitacion_key AND p.notice_n = v.n
