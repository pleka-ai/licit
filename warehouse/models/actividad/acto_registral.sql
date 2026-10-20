MODEL (
  name modelo.acto_registral,
  kind FULL,
  depends_on (modelo.sociedad),
  grain (documento, anuncio, acto_n),
  description 'Cada acto inscrito en el Registro Mercantil y publicado en el BORME (constitución, nombramientos, cambios de domicilio, ampliaciones de capital, disolución, extinción…), con los importes y datos que trae.',
  audits (
    not_null(columns := (documento, anuncio, acto_n, sociedad_key, fecha, tipo)),
    unique_combination_of_columns(columns := (documento, anuncio, acto_n)),
    clave_existe(columna := sociedad_key, tabla := modelo.sociedad)
  )
);

SELECT
  a.doc_id AS documento,
  a.number AS anuncio,
  a.n AS acto_n,
  @clave_o('sociedad', f.sociedad_ref) AS sociedad_key,
  f.published AS fecha,
  f.entry_date AS fecha_inscripcion,
  f.province AS provincia,
  a.kind AS tipo,
  a.text AS texto,
  a.capital,
  a.resulting_capital AS capital_resultante,
  a.address AS domicilio,
  a.new_name AS denominacion,
  a.purpose AS objeto_social,
  a.start_of_operations AS comienzo_operaciones,
  f.sheet AS hoja,
  f.entry AS inscripcion
FROM stage.borme_act AS a
JOIN stage.borme_filing AS f USING (doc_id, number)
