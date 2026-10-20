MODEL (
  name modelo.anuncio,
  kind FULL,
  tags (hecho),
  depends_on (modelo.tipo_anuncio, modelo.organo),
  grain (licitacion_key, anuncio_n, publicacion_n),
  description 'Hecho sin medidas: cada publicación de un anuncio en un medio (perfil del contratante, DOUE, BOE, boletines autonómicos). Los anuncios sin medio tienen publicacion_n = 0.',
  audits (
    not_null(columns := (licitacion_key, anuncio_n, publicacion_n, tipo_anuncio_key, organo_key)),
    unique_combination_of_columns(columns := (licitacion_key, anuncio_n, publicacion_n)),
    clave_existe(columna := tipo_anuncio_key, dimension := modelo.tipo_anuncio)
  )
);

SELECT
  v.licitacion_key,
  v.n AS anuncio_n,
  coalesce(p.n, 0) AS publicacion_n,
  @clave_o('tipo_anuncio', v.notice_type_code) AS tipo_anuncio_key,
  e.organo_key,
  v.notice_issue_date AS fecha_anuncio,
  coalesce(p.issue_date, v.notice_issue_date) AS fecha_publicacion,
  p.publication_media_name AS medio
FROM stage.valid_notice_info AS v
JOIN stage.expediente_claves AS e USING (licitacion_key)
LEFT JOIN stage.publication_status AS p
  ON p.licitacion_key = v.licitacion_key AND p.notice_n = v.n
