MODEL (
  name modelo.cpv_licitacion,
  kind FULL,
  depends_on (modelo.cpv),
  grain (licitacion_key, cpv_n),
  description 'Todos los códigos CPV de una licitación y de sus lotes. `es_principal` marca el que usa ciclo_licitacion.cpv_key, y `peso` reparte 1 entre los códigos de la licitación para sumar sin contar dos veces.',
  audits (
    not_null(columns := (licitacion_key, cpv_n, cpv_key)),
    unique_combination_of_columns(columns := (licitacion_key, cpv_n)),
    clave_existe(columna := cpv_key, tabla := modelo.cpv)
  )
);

SELECT
  c.licitacion_key,
  c.n AS cpv_n,
  c.lot_number AS lote_numero,
  @clave_o('cpv', c.cpv_code) AS cpv_key,
  @clave_o('cpv', c.cpv_code) = e.cpv_key
    AND row_number() OVER (
      PARTITION BY c.licitacion_key, @clave_o('cpv', c.cpv_code) = e.cpv_key
      ORDER BY c.lot_number IS NOT NULL, c.n
    ) = 1 AS es_principal,
  1.0 / count(*) OVER (PARTITION BY c.licitacion_key) AS peso
FROM stage.cpv_classification AS c
JOIN stage.expediente_claves AS e USING (licitacion_key)
