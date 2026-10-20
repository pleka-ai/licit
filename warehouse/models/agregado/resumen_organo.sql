MODEL (
  name agregado.resumen_organo,
  kind FULL,
  tags (agregado),
  grain organo_key,
  description 'Agregado: actividad de cada órgano de contratación.'
);

SELECT
  o.organo_key,
  o.id AS organo_id,
  o.nombre AS organo,
  o.nif AS organo_nif,
  o.tipo AS organo_tipo,
  count(*) AS licitaciones,
  round(sum(l.presupuesto_sin_iva)) AS importe_licitado,
  round(sum(l.importe_adjudicado_sin_iva)) AS importe_adjudicado,
  max(l.fecha_publicacion)::DATE AS ultima_publicacion
FROM modelo.ciclo_licitacion AS l
JOIN modelo.organo AS o USING (organo_key)
WHERE l.organo_key > 0
GROUP BY ALL
ORDER BY licitaciones DESC
