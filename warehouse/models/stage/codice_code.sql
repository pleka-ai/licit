MODEL (
  name stage.codice_code,
  kind VIEW,
  grain (list, code),
  description 'Listas de códigos CODICE con su descripción.'
);

SELECT
  list::TEXT AS list,
  code::TEXT AS code,
  @texto(description) AS description
FROM @raw(codice_code)
