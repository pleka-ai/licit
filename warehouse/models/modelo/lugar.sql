MODEL (
  name modelo.lugar,
  kind FULL,
  tags (dimension),
  grain lugar_key,
  description 'Territorio NUTS con sus niveles aplanados (país, macrorregión, comunidad autónoma, provincia).',
  audits (
    not_null(columns := (lugar_key, codigo)),
    unique_values(columns := (lugar_key)),
    unique_values(columns := (codigo))
  )
);

WITH catalogo AS (
  SELECT code AS codigo, any_value(description) AS nombre
  FROM stage.codice_code
  WHERE list = 'nuts'
  GROUP BY code
),
observados AS (
  SELECT nuts_code AS codigo, country_subentity FROM stage.contract_folder_status
  UNION ALL
  SELECT nuts_code, country_subentity FROM stage.procurement_project_lot
  UNION ALL
  SELECT nuts_code, country_subentity FROM stage.realized_location
  UNION ALL
  SELECT nuts_code, NULL FROM stage.winning_party
),
-- The free-text region PLACSP prints next to the code, most frequent first.
nombre_placsp AS (
  SELECT codigo, mode(country_subentity) AS nombre_placsp
  FROM observados
  WHERE codigo IS NOT NULL
  GROUP BY codigo
),
codigos AS (
  SELECT codigo FROM catalogo
  UNION
  SELECT codigo FROM nombre_placsp
)
SELECT
  @clave('lugar', c.codigo) AS lugar_key,
  c.codigo,
  coalesce(cat.nombre, p.nombre_placsp, c.codigo) AS nombre,
  coalesce(p.nombre_placsp, cat.nombre, c.codigo) AS nombre_placsp,
  greatest(length(c.codigo) - 2, 0) AS nivel,
  left(c.codigo, 2) AS pais_codigo,
  CASE WHEN length(c.codigo) >= 3 THEN left(c.codigo, 3) END AS nuts1_codigo,
  n1.nombre AS nuts1,
  CASE WHEN length(c.codigo) >= 4 THEN left(c.codigo, 4) END AS nuts2_codigo,
  n2.nombre AS nuts2,
  CASE WHEN length(c.codigo) >= 5 THEN left(c.codigo, 5) END AS nuts3_codigo,
  n3.nombre AS nuts3
FROM codigos AS c
LEFT JOIN catalogo AS cat ON cat.codigo = c.codigo
LEFT JOIN nombre_placsp AS p ON p.codigo = c.codigo
LEFT JOIN catalogo AS n1 ON n1.codigo = left(c.codigo, 3) AND length(c.codigo) >= 3
LEFT JOIN catalogo AS n2 ON n2.codigo = left(c.codigo, 4) AND length(c.codigo) >= 4
LEFT JOIN catalogo AS n3 ON n3.codigo = left(c.codigo, 5) AND length(c.codigo) >= 5
UNION ALL
SELECT 0, '?', 'Lugar desconocido', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
