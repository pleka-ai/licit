MODEL (
  name resumen.resumen_mensual,
  kind FULL,
  grain (mes, tipo_contrato),
  description 'Resumen: licitaciones e importes por mes de publicación y tipo de contrato.'
);

SELECT
  date_trunc('month', c.fecha_publicacion)::DATE AS mes,
  l.tipo_contrato,
  count(*) AS licitaciones,
  round(sum(c.presupuesto_sin_iva)) AS importe_licitado,
  round(sum(c.importe_adjudicado_sin_iva)) AS importe_adjudicado
FROM modelo.ciclo_licitacion AS c
JOIN modelo.licitacion AS l USING (licitacion_key)
GROUP BY ALL
ORDER BY mes, tipo_contrato
