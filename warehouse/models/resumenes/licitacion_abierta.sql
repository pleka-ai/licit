MODEL (
  name resumen.licitacion_abierta,
  kind FULL,
  grain licitacion_key,
  description 'Licitaciones con el plazo de ofertas abierto el día de la carga, desnormalizadas para consultarlas directamente.'
);

SELECT
  c.licitacion_key,
  l.id,
  c.fecha_publicacion::DATE AS fecha_publicacion,
  c.fecha_limite,
  l.titulo,
  o.nombre AS organo,
  l.tipo_contrato,
  l.procedimiento,
  l.estado,
  c.presupuesto_sin_iva,
  p.codigo AS cpv,
  p.descripcion AS cpv_descripcion,
  g.nombre_placsp AS lugar,
  l.url_place
FROM modelo.ciclo_licitacion AS c
JOIN modelo.licitacion AS l USING (licitacion_key)
JOIN modelo.organo AS o USING (organo_key)
JOIN modelo.cpv AS p USING (cpv_key)
JOIN modelo.lugar AS g USING (lugar_key)
WHERE c.fecha_limite >= current_date
ORDER BY c.fecha_limite, c.presupuesto_sin_iva DESC
