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
),
vigentes AS (
  SELECT
    m.*,
    -- A company has one sole member: the latest declaration replaces the
    -- earlier ones, which the BORME does not close with a removal.
    row_number() OVER (
      PARTITION BY m.sociedad_key, m.cargo_tipo
      ORDER BY m.fecha DESC, m.documento DESC, m.anuncio DESC, m.acto_n DESC, m.cargo_n DESC
    ) AS rn_tipo
  FROM movimientos AS m
  LEFT JOIN perdida_unipersonalidad AS u USING (sociedad_key)
  WHERE m.rn = 1
    AND m.movimiento IN ('Nombramiento', 'Reelección', 'Socio único')
    -- coalesce: most companies never lose the status (no row in u).
    AND NOT (m.cargo_tipo = 'Socio único' AND coalesce(u.fecha > m.fecha, FALSE))
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
FROM vigentes AS m
JOIN modelo.sociedad AS s USING (sociedad_key)
JOIN modelo.persona AS p USING (persona_key)
WHERE s.estado <> 'Extinguida'
  AND (m.cargo_tipo <> 'Socio único' OR m.rn_tipo = 1)
