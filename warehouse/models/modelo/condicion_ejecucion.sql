MODEL (
  name modelo.condicion_ejecucion,
  kind FULL,
  tags (dimension),
  grain condicion_key,
  description 'Condición especial de ejecución de una licitación (social, medioambiental, innovación…).',
  audits (
    not_null(columns := (condicion_key, licitacion_key)),
    unique_values(columns := (condicion_key))
  )
);

SELECT
  @clave('condicion', c.licitacion_key, c.n) AS condicion_key,
  c.licitacion_key,
  c.n AS condicion_n,
  c.execution_requirement_code AS tipo_codigo,
  @etiqueta('execution_requirement', c.execution_requirement_code) AS tipo,
  c.name AS nombre,
  c.description AS descripcion
FROM stage.execution_condition AS c
