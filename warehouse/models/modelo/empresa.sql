MODEL (
  name modelo.empresa,
  kind FULL,
  tags (dimension),
  grain empresa_key,
  description 'Empresa adjudicataria identificada por NIF (o por nombre si PLACSP no da NIF). SCD tipo 1: nombre y domicilio de su adjudicación más reciente.',
  audits (
    not_null(columns := (empresa_key, nombre)),
    unique_values(columns := (empresa_key)),
    unique_values(columns := (referencia))
  )
);

WITH apariciones AS (
  SELECT w.empresa_ref, w.identifier, w.identifier_scheme, w.name, w.city_name,
    w.postal_zone, w.nuts_code, w.country_code, w.company_type_code, w.entry_id, f.updated
  FROM stage.winning_party AS w
  JOIN stage.contract_folder_status AS f USING (entry_id)
),
actual AS (
  SELECT
    *,
    row_number() OVER (
      PARTITION BY empresa_ref
      ORDER BY updated DESC, length(name) DESC NULLS LAST, entry_id
    ) AS rn,
    count(*) OVER (PARTITION BY empresa_ref) AS adjudicaciones
  FROM apariciones
)
SELECT
  @clave('empresa', empresa_ref) AS empresa_key,
  empresa_ref AS referencia,
  identifier AS nif,
  coalesce(name, identifier) AS nombre,
  identifier_scheme AS esquema_identificador,
  identifier_scheme = 'UTE'
    OR regexp_matches(name, '^\s*(U\.?\s?T\.?\s?E\.?|UNI[OÓ]N TEMPORAL)', 'i') AS es_ute,
  company_type_code AS tipo_codigo,
  city_name AS ciudad,
  postal_zone AS codigo_postal,
  nuts_code AS nuts_codigo,
  country_code AS pais_codigo,
  @etiqueta('country_code', country_code) AS pais
FROM actual
WHERE rn = 1
UNION ALL
SELECT 0, '__desconocida__', NULL, 'Empresa desconocida', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
UNION ALL
SELECT -1, '__no_aplica__', NULL, 'Sin adjudicatario', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL

ORDER BY empresa_key
