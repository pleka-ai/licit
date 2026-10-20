MODEL (
  name resumen.resumen_adjudicacion,
  kind FULL,
  grain (anio, comunidad, cpv_division_codigo, procedimiento, tipo_contrato),
  description 'Resumen: resultados de adjudicación por año de publicación, comunidad autónoma, división CPV, procedimiento y tipo de contrato. Guarda sumas y recuentos, no medias, para que cualquier agrupación dé medias exactas: baja media = suma_baja_pct / con_baja; ofertas medias = ofertas / con_ofertas. La baja solo cuenta adjudicaciones con importe entre 0 y el presupuesto (por encima suele ser un error de carga).',
  audits (
    not_null(columns := (adjudicaciones, con_baja, con_ofertas, ofertas, una_oferta))
  )
);

WITH filas AS (
  SELECT
    year(a.fecha_publicacion) AS anio,
    CASE WHEN g.pais_codigo = 'ES' THEN g.nuts2 END AS comunidad,
    c.division_codigo AS cpv_division_codigo,
    c.division AS cpv_division,
    l.procedimiento,
    l.tipo_contrato,
    r.es_adjudicacion,
    a.importe_sin_iva,
    a.num_ofertas,
    r.es_adjudicacion
      AND a.importe_sin_iva > 0
      AND a.importe_sin_iva <= a.presupuesto_sin_iva AS con_baja,
    100 * (a.presupuesto_sin_iva - a.importe_sin_iva) / a.presupuesto_sin_iva AS baja_pct
  FROM modelo.adjudicacion AS a
  JOIN modelo.licitacion AS l USING (licitacion_key)
  JOIN modelo.lugar AS g USING (lugar_key)
  JOIN modelo.cpv AS c USING (cpv_key)
  JOIN modelo.resultado AS r USING (resultado_key)
)
SELECT
  anio,
  comunidad,
  cpv_division_codigo,
  any_value(cpv_division) AS cpv_division,
  procedimiento,
  tipo_contrato,
  count(*) FILTER (es_adjudicacion) AS adjudicaciones,
  round(sum(importe_sin_iva) FILTER (es_adjudicacion), 2) AS importe_adjudicado,
  count(*) FILTER (con_baja) AS con_baja,
  round(sum(baja_pct) FILTER (con_baja), 4) AS suma_baja_pct,
  count(*) FILTER (num_ofertas > 0) AS con_ofertas,
  coalesce(sum(num_ofertas) FILTER (num_ofertas > 0), 0) AS ofertas,
  count(*) FILTER (num_ofertas = 1) AS una_oferta
FROM filas
GROUP BY anio, comunidad, cpv_division_codigo, procedimiento, tipo_contrato
ORDER BY anio, comunidad, cpv_division_codigo, procedimiento, tipo_contrato
