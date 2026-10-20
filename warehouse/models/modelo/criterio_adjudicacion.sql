MODEL (
  name modelo.criterio_adjudicacion,
  kind FULL,
  tags (dimension),
  grain criterio_key,
  description 'Criterio de adjudicación de una licitación (lote_numero NULL) o de un lote: tipo (automático o juicio de valor), subtipo (precio, calidad…), descripción y ponderación.',
  audits (
    not_null(columns := (criterio_key, licitacion_key)),
    unique_values(columns := (criterio_key))
  )
);

SELECT
  @clave('criterio', c.licitacion_key, c.n) AS criterio_key,
  c.licitacion_key,
  c.n AS criterio_n,
  c.lot_number AS lote_numero,
  c.criteria_type_code AS tipo_codigo,
  @etiqueta('awarding_criteria_type', c.criteria_type_code) AS tipo,
  c.criteria_sub_type_code AS subtipo_codigo,
  @etiqueta('awarding_criteria_sub_type', c.criteria_sub_type_code) AS subtipo,
  c.description AS descripcion,
  c.note AS nota,
  c.weight_numeric AS ponderacion
FROM stage.awarding_criteria AS c
