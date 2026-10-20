MODEL (
  name modelo.cpv,
  kind FULL,
  grain cpv_key,
  description 'Código del Vocabulario Común de Contratos Públicos con su jerarquía aplanada (división, grupo, clase, categoría).',
  audits (
    not_null(columns := (cpv_key, codigo)),
    unique_values(columns := (cpv_key)),
    unique_values(columns := (codigo))
  )
);

WITH catalogo AS (
  SELECT left(regexp_replace(code, '[^0-9]', '', 'g'), 8) AS codigo, description
  FROM stage.codice_code
  WHERE list = 'cpv'
),
codigos AS (
  SELECT codigo FROM catalogo
  UNION
  SELECT cpv_code FROM stage.cpv_classification
),
nombres AS (
  SELECT codigo, any_value(description) AS descripcion FROM catalogo GROUP BY codigo
)
SELECT
  @clave('cpv', c.codigo) AS cpv_key,
  c.codigo,
  coalesce(n.descripcion, c.codigo) AS descripcion,
  CASE
    WHEN c.codigo LIKE '%000000' THEN 'División'
    WHEN c.codigo LIKE '%00000' THEN 'Grupo'
    WHEN c.codigo LIKE '%0000' THEN 'Clase'
    WHEN c.codigo LIKE '%000' THEN 'Categoría'
    ELSE 'Subcategoría'
  END AS nivel,
  left(c.codigo, 2) || '000000' AS division_codigo,
  d.descripcion AS division,
  left(c.codigo, 3) || '00000' AS grupo_codigo,
  g.descripcion AS grupo,
  left(c.codigo, 4) || '0000' AS clase_codigo,
  cl.descripcion AS clase,
  left(c.codigo, 5) || '000' AS categoria_codigo,
  ca.descripcion AS categoria
FROM codigos AS c
LEFT JOIN nombres AS n ON n.codigo = c.codigo
LEFT JOIN nombres AS d ON d.codigo = left(c.codigo, 2) || '000000'
LEFT JOIN nombres AS g ON g.codigo = left(c.codigo, 3) || '00000'
LEFT JOIN nombres AS cl ON cl.codigo = left(c.codigo, 4) || '0000'
LEFT JOIN nombres AS ca ON ca.codigo = left(c.codigo, 5) || '000'
WHERE c.codigo <> ''
UNION ALL
SELECT 0, '?', 'CPV desconocido', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
