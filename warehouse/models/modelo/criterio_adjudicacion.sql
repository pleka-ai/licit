MODEL (
  name modelo.criterio_adjudicacion,
  kind FULL,
  tags (hecho),
  depends_on (modelo.tipo_criterio, modelo.organo),
  grain (licitacion_key, criterio_n),
  description 'Criterios de adjudicación con su ponderación, del expediente (lote_numero NULL) o de un lote.',
  audits (
    not_null(columns := (licitacion_key, criterio_n, tipo_criterio_key, organo_key)),
    unique_combination_of_columns(columns := (licitacion_key, criterio_n)),
    clave_existe(columna := tipo_criterio_key, dimension := modelo.tipo_criterio)
  )
);

SELECT
  c.licitacion_key,
  c.n AS criterio_n,
  c.lot_number AS lote_numero,
  @clave_o(
    'tipo_criterio',
    coalesce(c.criteria_type_code, '∅'),
    coalesce(c.criteria_sub_type_code, '∅')
  ) AS tipo_criterio_key,
  e.organo_key,
  e.modalidad_key,
  e.fecha_publicacion::DATE AS fecha_publicacion,
  c.description AS descripcion,
  c.note AS nota,
  c.weight_numeric AS ponderacion
FROM stage.awarding_criteria AS c
JOIN stage.expediente_claves AS e USING (licitacion_key)
