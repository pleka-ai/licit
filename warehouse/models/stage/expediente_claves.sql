MODEL (
  name stage.expediente_claves,
  kind VIEW,
  grain licitacion_key,
  description 'Claves de dimensión de cada expediente, compartidas por la licitación y por todos sus hechos hijos (patrón cabecera/línea).'
);

WITH cpv_principal AS (
  -- The first CPV published for the whole folder, else the first lot CPV.
  SELECT
    licitacion_key,
    arg_min(cpv_code, (lot_number IS NOT NULL, n)) AS cpv_code
  FROM stage.cpv_classification
  GROUP BY licitacion_key
),
publicacion AS (
  -- First observed status; the earliest dated notice is usually earlier and
  -- is the real publication date.
  SELECT licitacion_key, min(updated) AS primera_vez
  FROM stage.status_change
  GROUP BY licitacion_key
),
anuncio AS (
  SELECT licitacion_key, min(notice_issue_date) AS primer_anuncio
  FROM stage.valid_notice_info
  GROUP BY licitacion_key
)
SELECT
  f.licitacion_key,
  f.entry_id,
  least(
    coalesce(p.primera_vez, f.updated),
    timezone('UTC', a.primer_anuncio::TIMESTAMP)
  ) AS fecha_publicacion,
  @clave_o('organo', f.organo_ref) AS organo_key,
  @modalidad_key(f) AS modalidad_key,
  @clave_o('estado', f.status_code) AS estado_key,
  @clave_o('cpv', c.cpv_code) AS cpv_key,
  c.cpv_code,
  @clave_o('lugar', f.nuts_code) AS lugar_key,
  f.tax_exclusive_amount,
  f.total_amount
FROM stage.contract_folder_status AS f
LEFT JOIN cpv_principal AS c USING (licitacion_key)
LEFT JOIN publicacion AS p USING (licitacion_key)
LEFT JOIN anuncio AS a USING (licitacion_key)
