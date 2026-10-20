MODEL (
  name modelo.persona,
  kind FULL,
  depends_on (modelo.sociedad),
  grain persona_key,
  description 'Persona física o jurídica que aparece en cargos del BORME (administradores, apoderados, socios únicos, auditores…), identificada por su nombre normalizado: el BORME no publica DNI, así que dos homónimos son la misma persona aquí. Las personas jurídicas se enlazan con su sociedad cuando el nombre coincide con una sola.',
  audits (
    not_null(columns := (persona_key, nombre)),
    unique_values(columns := (persona_key)),
    rol_existe(columna := sociedad_key, tabla := modelo.sociedad, clave := sociedad_key)
  )
);

WITH nombres AS (
  SELECT name_normalized, mode(name) AS nombre, count(*) AS num_cargos
  FROM stage.borme_position
  WHERE name_normalized IS NOT NULL
  GROUP BY name_normalized
),
unica AS (
  SELECT nombre_normalizado, any_value(sociedad_ref) AS sociedad_ref
  FROM stage.sociedad_nombre
  GROUP BY nombre_normalizado
  HAVING count(DISTINCT sociedad_ref) = 1
)
SELECT
  @clave('persona', n.name_normalized) AS persona_key,
  n.name_normalized AS nombre_normalizado,
  n.nombre,
  @forma_juridica(n.name_normalized) IS NOT NULL OR u.sociedad_ref IS NOT NULL
    AS es_persona_juridica,
  coalesce(@clave('sociedad', u.sociedad_ref), -1) AS sociedad_key,
  n.num_cargos
FROM nombres AS n
LEFT JOIN unica AS u ON u.nombre_normalizado = n.name_normalized
UNION ALL
SELECT 0, NULL, 'Persona desconocida', false, -1, 0
