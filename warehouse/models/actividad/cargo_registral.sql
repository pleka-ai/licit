MODEL (
  name modelo.cargo_registral,
  kind FULL,
  depends_on (modelo.sociedad, modelo.persona),
  grain (documento, anuncio, acto_n, cargo_n),
  description 'Cada movimiento de un cargo publicado en el BORME: nombramiento, reelección, cese, revocación, cancelación de oficio o declaración de socio único, de una persona en una sociedad. cargo es la etiqueta publicada y cargo_tipo su grupo (Administrador único, Consejero, Apoderado…).',
  audits (
    not_null(columns := (documento, anuncio, acto_n, cargo_n, sociedad_key, persona_key, fecha, movimiento)),
    unique_combination_of_columns(columns := (documento, anuncio, acto_n, cargo_n)),
    clave_existe(columna := sociedad_key, tabla := modelo.sociedad),
    clave_existe(columna := persona_key, tabla := modelo.persona)
  )
);

SELECT
  p.doc_id AS documento,
  p.number AS anuncio,
  p.act_n AS acto_n,
  p.n AS cargo_n,
  @clave_o('sociedad', f.sociedad_ref) AS sociedad_key,
  @clave_o('persona', p.name_normalized) AS persona_key,
  f.published AS fecha,
  f.province AS provincia,
  p.movement AS movimiento,
  p.role AS cargo,
  p.role_group AS cargo_tipo
FROM stage.borme_position AS p
JOIN stage.borme_filing AS f USING (doc_id, number)
WHERE p.movement IS NOT NULL
