MODEL (
  name agregado.licitacion_abierta,
  kind FULL,
  tags (agregado),
  grain licitacion_key,
  description 'Licitaciones con el plazo de ofertas abierto el día de la carga, desnormalizadas para consultarlas directamente.'
);

SELECT
  l.licitacion_key,
  l.id,
  l.fecha_publicacion::DATE AS fecha_publicacion,
  l.fecha_limite,
  l.titulo,
  o.nombre AS organo,
  m.tipo_contrato,
  e.descripcion AS estado,
  l.presupuesto_sin_iva,
  c.codigo AS cpv,
  c.descripcion AS cpv_descripcion,
  g.nombre_placsp AS lugar,
  l.url_place
FROM modelo.licitacion AS l
JOIN modelo.organo AS o USING (organo_key)
JOIN modelo.modalidad AS m USING (modalidad_key)
JOIN modelo.estado AS e USING (estado_key)
JOIN modelo.cpv AS c USING (cpv_key)
JOIN modelo.lugar AS g USING (lugar_key)
WHERE l.fecha_limite >= current_date
ORDER BY l.fecha_limite, l.presupuesto_sin_iva DESC
