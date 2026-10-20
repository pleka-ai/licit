MODEL (
  name resumen.adjudicataria_registro,
  kind FULL,
  grain empresa_key,
  description 'Resumen: cada empresa adjudicataria enlazada con su sociedad del BORME, con su constitución, situación, capital y cargos en vigor, y los días entre su constitución y la primera licitación que ganó.'
);

WITH adjudicaciones AS (
  SELECT
    a.empresa_key,
    count(*) AS adjudicaciones,
    round(sum(a.importe_sin_iva)) AS importe_adjudicado,
    min(coalesce(a.fecha_adjudicacion, a.fecha_publicacion)) AS primera_adjudicacion,
    max(coalesce(a.fecha_adjudicacion, a.fecha_publicacion)) AS ultima_adjudicacion
  FROM modelo.adjudicacion AS a
  JOIN modelo.resultado AS r USING (resultado_key)
  WHERE a.empresa_key > 0 AND r.es_adjudicacion
  GROUP BY a.empresa_key
),
cargos AS (
  SELECT sociedad_key, count(*) AS cargos_vigentes
  FROM resumen.cargo_vigente
  GROUP BY sociedad_key
)
SELECT
  e.empresa_key,
  e.nif,
  e.nombre,
  s.sociedad_key,
  s.nombre AS sociedad,
  s.hoja,
  s.provincia,
  s.forma_juridica,
  s.fecha_constitucion,
  s.estado,
  s.capital,
  s.fecha_extincion,
  coalesce(c.cargos_vigentes, 0) AS cargos_vigentes,
  a.adjudicaciones,
  a.importe_adjudicado,
  a.primera_adjudicacion,
  a.ultima_adjudicacion,
  date_diff('day', s.fecha_constitucion, a.primera_adjudicacion)
    AS dias_constitucion_a_primera_adjudicacion
FROM modelo.empresa AS e
JOIN modelo.sociedad AS s USING (sociedad_key)
LEFT JOIN adjudicaciones AS a USING (empresa_key)
LEFT JOIN cargos AS c USING (sociedad_key)
WHERE e.sociedad_key > 0
