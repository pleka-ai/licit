MODEL (
  name stage.sociedad_nombre,
  kind VIEW,
  grain (sociedad_ref, nombre_normalizado),
  description 'Todos los nombres que ha tenido cada sociedad en el BORME (cabeceras de sus anuncios y cambios de denominación), normalizados para cruzarlos con otras fuentes; nombre_base es el mismo nombre sin la forma jurídica final.'
);

WITH nombres AS (
  SELECT DISTINCT sociedad_ref, company_normalized AS nombre_normalizado
  FROM stage.borme_filing
  WHERE company_normalized IS NOT NULL
  UNION
  SELECT DISTINCT f.sociedad_ref, @nombre_normalizado(a.new_name)
  FROM stage.borme_act AS a
  JOIN stage.borme_filing AS f USING (doc_id, number)
  WHERE a.kind = 'Cambio de denominación social' AND a.new_name IS NOT NULL
)
SELECT sociedad_ref, nombre_normalizado, @sin_forma_juridica(nombre_normalizado) AS nombre_base
FROM nombres
