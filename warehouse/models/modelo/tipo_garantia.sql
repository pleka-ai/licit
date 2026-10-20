MODEL (
  name modelo.tipo_garantia,
  kind FULL,
  grain tipo_garantia_key,
  description 'Tipo de garantía (provisional, definitiva, complementaria).',
  audits (
    not_null(columns := (tipo_garantia_key)),
    unique_values(columns := (tipo_garantia_key))
  )
);

WITH codigos AS (
  SELECT code AS codigo FROM stage.codice_code WHERE list = 'guarantee_type'
  UNION
  SELECT guarantee_type_code FROM stage.financial_guarantee
  WHERE guarantee_type_code IS NOT NULL
)
SELECT
  @clave('tipo_garantia', codigo) AS tipo_garantia_key,
  codigo,
  @etiqueta('guarantee_type', codigo) AS descripcion
FROM codigos
UNION ALL
SELECT 0, '?', 'Desconocida'
