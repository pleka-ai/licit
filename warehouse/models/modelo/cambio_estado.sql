MODEL (
  name modelo.cambio_estado,
  kind FULL,
  tags (hecho),
  depends_on (modelo.estado, modelo.organo),
  grain (licitacion_key, momento, estado_key),
  description 'Hecho transaccional: cada estado en que se ha observado un expediente, con cuánto tiempo permaneció en él. Recoge todas las versiones publicadas, no solo la última.',
  audits (
    not_null(columns := (licitacion_key, estado_key, organo_key, momento, fecha)),
    unique_combination_of_columns(columns := (licitacion_key, momento, estado_key)),
    clave_existe(columna := estado_key, dimension := modelo.estado)
  )
);

SELECT
  s.licitacion_key,
  @clave_o('estado', s.status_code) AS estado_key,
  e.organo_key,
  s.updated AS momento,
  s.updated::DATE AS fecha,
  row_number() OVER w AS orden,
  lead(s.updated) OVER w IS NULL AS es_actual,
  date_diff('day', s.updated, lead(s.updated) OVER w) AS dias_en_estado
FROM stage.status_change AS s
JOIN stage.expediente_claves AS e USING (licitacion_key)
WINDOW w AS (PARTITION BY s.licitacion_key ORDER BY s.updated, s.status_code)
