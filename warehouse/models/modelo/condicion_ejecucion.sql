MODEL (
  name modelo.condicion_ejecucion,
  kind FULL,
  depends_on (modelo.tipo_condicion, modelo.organo),
  grain (licitacion_key, condicion_n),
  description 'Hecho sin medidas: condiciones especiales de ejecución del contrato.',
  audits (
    not_null(columns := (licitacion_key, condicion_n, tipo_condicion_key, organo_key)),
    unique_combination_of_columns(columns := (licitacion_key, condicion_n)),
    clave_existe(columna := tipo_condicion_key, dimension := modelo.tipo_condicion)
  )
);

SELECT
  c.licitacion_key,
  c.n AS condicion_n,
  @clave_o('tipo_condicion', c.execution_requirement_code) AS tipo_condicion_key,
  e.organo_key,
  e.fecha_publicacion::DATE AS fecha_publicacion,
  c.name AS nombre,
  c.description AS descripcion
FROM stage.execution_condition AS c
JOIN stage.expediente_claves AS e USING (licitacion_key)
