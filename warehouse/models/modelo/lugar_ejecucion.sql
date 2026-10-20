MODEL (
  name modelo.lugar_ejecucion,
  kind FULL,
  depends_on (modelo.lugar, modelo.organo),
  grain (licitacion_key, lote_numero, ubicacion_n),
  description 'Hecho sin medidas: lugares concretos donde se ejecuta cada lote.',
  audits (
    not_null(columns := (licitacion_key, lote_numero, ubicacion_n, lugar_key, organo_key)),
    unique_combination_of_columns(columns := (licitacion_key, lote_numero, ubicacion_n)),
    clave_existe(columna := lugar_key, dimension := modelo.lugar)
  )
);

SELECT
  r.licitacion_key,
  r.lot_number AS lote_numero,
  r.n AS ubicacion_n,
  coalesce(@clave('lugar', r.nuts_code), e.lugar_key) AS lugar_key,
  e.organo_key,
  r.city_name AS ciudad,
  r.postal_zone AS codigo_postal,
  r.street_name AS direccion,
  r.country_code AS pais_codigo
FROM stage.realized_location AS r
JOIN stage.expediente_claves AS e USING (licitacion_key)
WHERE r.lot_number IS NOT NULL
