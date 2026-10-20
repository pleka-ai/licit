MODEL (
  name stage.valid_notice_info,
  kind VIEW,
  grain (entry_id, n),
  description 'Anuncios publicados del expediente.'
);

SELECT
  @clave('licitacion', entry_id) AS licitacion_key,
  entry_id::TEXT AS entry_id,
  n::INT AS n,
  notice_type_code::TEXT AS notice_type_code,
  @fecha(notice_issue_date) AS notice_issue_date
FROM @raw(valid_notice_info)
