MODEL (
  name modelo.presupuesto_lote,
  kind FULL,
  tags (hecho),
  depends_on (modelo.licitacion, modelo.lote, modelo.organo, modelo.estado, modelo.cpv, modelo.lugar),
  grain lote_key,
  description 'Hecho de publicación: lo que se licita, al nivel más atómico. Una fila por lote (o por licitación si no tiene lotes) con su presupuesto y las claves de todas sus dimensiones. Sumar presupuesto_sin_iva aquí nunca cuenta dos veces.',
  audits (
    not_null(columns := (lote_key, licitacion_key, organo_key, estado_key, cpv_key, lugar_key, fecha_publicacion)),
    unique_values(columns := (lote_key)),
    clave_existe(columna := lote_key, dimension := modelo.lote),
    clave_existe(columna := licitacion_key, dimension := modelo.licitacion),
    clave_existe(columna := organo_key, dimension := modelo.organo),
    clave_existe(columna := cpv_key, dimension := modelo.cpv),
    clave_existe(columna := lugar_key, dimension := modelo.lugar)
  )
);

SELECT
  @clave('lote', x.licitacion_key, x.lote_numero) AS lote_key,
  x.licitacion_key,
  e.organo_key,
  e.estado_key,
  coalesce(@clave('cpv', x.cpv_code), e.cpv_key) AS cpv_key,
  coalesce(@clave('lugar', x.nuts_code), e.lugar_key) AS lugar_key,
  x.lote_numero,
  e.fecha_publicacion::DATE AS fecha_publicacion,
  f.submission_deadline_date AS fecha_limite,
  x.presupuesto_sin_iva,
  x.presupuesto_con_iva
FROM stage.lote AS x
JOIN stage.expediente_claves AS e USING (licitacion_key)
JOIN stage.contract_folder_status AS f USING (licitacion_key)
