MODEL (
  name resumen.resumen_empresa,
  kind FULL,
  grain empresa_key,
  description 'Resumen: adjudicaciones de cada empresa (todas, incluidas las de lotes).'
);

SELECT
  e.empresa_key,
  e.nif AS adjudicatario_nif,
  e.nombre AS adjudicatario,
  count(*) AS contratos,
  count(DISTINCT a.licitacion_key) AS licitaciones,
  count(DISTINCT a.organo_key) AS organos,
  round(sum(a.importe_sin_iva)) AS importe_adjudicado,
  max(a.fecha_adjudicacion) AS ultima_adjudicacion
FROM modelo.adjudicacion AS a
JOIN modelo.empresa AS e USING (empresa_key)
JOIN modelo.resultado AS r USING (resultado_key)
WHERE a.empresa_key > 0 AND r.es_adjudicacion
GROUP BY ALL
ORDER BY contratos DESC
