MODEL (
  name resumen.cargo_vigente,
  kind FULL,
  grain (sociedad_key, persona_key, cargo_tipo),
  description 'Resumen: cargos en vigor según el BORME, el último movimiento de cada persona en cada tipo de cargo y sociedad cuando es un nombramiento, una reelección o una declaración de socio único, en sociedades no extinguidas.'
);

WITH movimientos AS (
  SELECT
    *,
    row_number() OVER (
      PARTITION BY sociedad_key, persona_key, cargo_tipo
      ORDER BY fecha DESC, documento DESC, anuncio DESC, acto_n DESC, cargo_n DESC
    ) AS rn
  FROM modelo.cargo_registral
  WHERE sociedad_key > 0 AND persona_key > 0
),
-- A sole member stops being one when the company later loses that status.
perdida_unipersonalidad AS (
  SELECT sociedad_key, max(fecha) AS fecha
  FROM modelo.acto_registral
  WHERE tipo = 'Pérdida del carácter de unipersonalidad'
  GROUP BY sociedad_key
)
SELECT
  m.sociedad_key,
  m.persona_key,
  m.cargo_tipo,
  m.cargo,
  m.fecha AS desde,
  s.nombre AS sociedad,
  p.nombre AS persona,
  p.es_persona_juridica
FROM movimientos AS m
JOIN modelo.sociedad AS s USING (sociedad_key)
JOIN modelo.persona AS p USING (persona_key)
LEFT JOIN perdida_unipersonalidad AS u USING (sociedad_key)
WHERE m.rn = 1
  AND m.movimiento IN ('Nombramiento', 'Reelección', 'Socio único')
  AND s.estado <> 'Extinguida'
  AND NOT (m.cargo_tipo = 'Socio único' AND u.fecha > m.fecha)
