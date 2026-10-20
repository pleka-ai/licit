MODEL (
  name stage.publication_status,
  kind VIEW,
  grain (entry_id, notice_n, n),
  description 'Medios en los que se publicó cada anuncio.'
);

SELECT
  @clave('licitacion', entry_id) AS licitacion_key,
  entry_id::TEXT AS entry_id,
  notice_n::INT AS notice_n,
  n::INT AS n,
  @texto(publication_media_name) AS publication_media_name,
  @fecha(issue_date) AS issue_date
FROM @raw(publication_status)
