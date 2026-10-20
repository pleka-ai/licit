MODEL (
  name modelo.lugar_ejecucion,
  kind FULL,
  tags (dimension),
  depends_on (modelo.lugar),
  grain ubicacion_key,
  description 'Lugar concreto donde se ejecuta un lote (dirección, municipio, código postal), con su territorio NUTS en lugar.',
  audits (
    not_null(columns := (ubicacion_key, licitacion_key, lote_numero, lugar_key)),
    unique_values(columns := (ubicacion_key)),
    clave_existe(columna := lugar_key, dimension := modelo.lugar)
  )
);

SELECT
  @clave('ubicacion', r.licitacion_key, r.lot_number, r.n) AS ubicacion_key,
  r.licitacion_key,
  r.lot_number AS lote_numero,
  @clave('lote', r.licitacion_key, r.lot_number) AS lote_key,
  coalesce(@clave('lugar', r.nuts_code), e.lugar_key) AS lugar_key,
  r.city_name AS ciudad,
  r.postal_zone AS codigo_postal,
  r.street_name AS direccion,
  r.country_code AS pais_codigo
FROM stage.realized_location AS r
JOIN stage.expediente_claves AS e USING (licitacion_key)
WHERE r.lot_number IS NOT NULL
