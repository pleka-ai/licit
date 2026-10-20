MODEL (
  name agregado.resumen_mensual,
  kind FULL,
  tags (agregado),
  grain (mes, tipo_contrato),
  description 'Agregado: licitaciones e importe licitado por mes de publicación y tipo de contrato.'
);

SELECT
  date_trunc('month', l.fecha_publicacion)::DATE AS mes,
  m.tipo_contrato,
  count(*) AS licitaciones,
  round(sum(l.presupuesto_sin_iva)) AS importe_licitado,
  round(sum(l.importe_adjudicado_sin_iva)) AS importe_adjudicado
FROM modelo.licitacion AS l
JOIN modelo.modalidad AS m USING (modalidad_key)
GROUP BY ALL
ORDER BY mes, tipo_contrato
