MODEL (
  name resumen.resumen_presupuesto,
  kind FULL,
  grain (anio, comunidad, cpv_division_codigo, tipo_contrato),
  description 'Resumen: lotes licitados y su presupuesto por año de publicación, comunidad autónoma, división CPV y tipo de contrato. Parte de presupuesto_lote, así que sumar no cuenta nada dos veces.',
  audits (
    not_null(columns := (lotes))
  )
);

SELECT
  year(p.fecha_publicacion) AS anio,
  CASE WHEN g.pais_codigo = 'ES' THEN g.nuts2 END AS comunidad,
  c.division_codigo AS cpv_division_codigo,
  any_value(c.division) AS cpv_division,
  l.tipo_contrato,
  count(*) AS lotes,
  round(sum(p.presupuesto_sin_iva), 2) AS presupuesto_sin_iva
FROM modelo.presupuesto_lote AS p
JOIN modelo.licitacion AS l USING (licitacion_key)
JOIN modelo.lugar AS g USING (lugar_key)
JOIN modelo.cpv AS c USING (cpv_key)
GROUP BY anio, comunidad, cpv_division_codigo, l.tipo_contrato
ORDER BY anio, comunidad, cpv_division_codigo, l.tipo_contrato
