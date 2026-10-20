MODEL (
  name stage.sociedad_nombre,
  kind VIEW,
  grain (sociedad_ref, nombre_normalizado),
  description 'Todos los nombres que ha tenido cada sociedad en el BORME (cabeceras de sus anuncios y cambios de denominación), normalizados para cruzarlos con otras fuentes.'
);

SELECT DISTINCT sociedad_ref, company_normalized AS nombre_normalizado
FROM stage.borme_filing
WHERE company_normalized IS NOT NULL
UNION
SELECT DISTINCT f.sociedad_ref, @nombre_normalizado(a.new_name)
FROM stage.borme_act AS a
JOIN stage.borme_filing AS f USING (doc_id, number)
WHERE a.kind = 'Cambio de denominación social' AND a.new_name IS NOT NULL
