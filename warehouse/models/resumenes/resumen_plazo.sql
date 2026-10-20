MODEL (
  name resumen.resumen_plazo,
  kind FULL,
  grain (anio, tipo_contrato),
  description 'Resumen: días desde la publicación hasta la adjudicación por año de publicación y tipo de contrato. Solo cuenta licitaciones publicadas antes de adjudicarse: muchas aparecen por primera vez ya adjudicadas (0 días) y hundirían la mediana; se descartan también plazos de más de 1000 días. Las medianas no se pueden sumar, así que van calculadas por año.'
);

SELECT
  year(c.fecha_publicacion) AS anio,
  l.tipo_contrato,
  count(*) AS adjudicadas,
  median(c.dias_hasta_adjudicacion) AS mediana_dias,
  round(quantile_cont(c.dias_hasta_adjudicacion, 0.9)) AS p90_dias
FROM modelo.ciclo_licitacion AS c
JOIN modelo.licitacion AS l USING (licitacion_key)
WHERE c.dias_hasta_adjudicacion BETWEEN 1 AND 1000
GROUP BY anio, l.tipo_contrato
ORDER BY anio, l.tipo_contrato
