MODEL (
  name modelo.empresa,
  kind FULL,
  depends_on (modelo.sociedad),
  grain empresa_key,
  description 'Empresa adjudicataria identificada por NIF (o por nombre si PLACSP no da NIF), con el nombre y domicilio de su adjudicación más reciente. sociedad_key la enlaza con su sociedad del BORME cuando alguno de sus nombres en PLACSP, normalizado, coincide con los de una sola sociedad (-1 si no).',
  audits (
    not_null(columns := (empresa_key, nombre)),
    unique_values(columns := (empresa_key)),
    unique_values(columns := (referencia)),
    rol_existe(columna := sociedad_key, tabla := modelo.sociedad, clave := sociedad_key)
  )
);

WITH apariciones AS (
  SELECT w.empresa_ref, w.identifier, w.identifier_scheme, w.name, w.city_name,
    w.postal_zone, w.nuts_code, w.country_code, w.company_type_code, w.entry_id, f.updated
  FROM stage.winning_party AS w
  JOIN stage.contract_folder_status AS f USING (entry_id)
),
-- Every name a winner has used in PLACSP against every name a company has
-- had in the BORME; kept only when they point to a single company. UTEs are
-- not registered companies.
cruce AS (
  SELECT
    w.empresa_ref,
    CASE WHEN count(DISTINCT n.sociedad_ref) = 1 THEN any_value(n.sociedad_ref) END
      AS sociedad_ref
  FROM (
    SELECT DISTINCT empresa_ref, @nombre_normalizado(name) AS nombre_normalizado
    FROM stage.winning_party
    WHERE coalesce(identifier_scheme, '') <> 'UTE'
  ) AS w
  JOIN stage.sociedad_nombre AS n USING (nombre_normalizado)
  GROUP BY w.empresa_ref
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
  @etiqueta('country_code', country_code) AS pais,
  coalesce(@clave('sociedad', c.sociedad_ref), -1) AS sociedad_key
FROM actual
LEFT JOIN cruce AS c USING (empresa_ref)
WHERE rn = 1
UNION ALL
SELECT 0, '__desconocida__', NULL, 'Empresa desconocida', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, -1
UNION ALL
SELECT -1, '__no_aplica__', NULL, 'Sin adjudicatario', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, -1

ORDER BY empresa_key
