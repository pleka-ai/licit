MODEL (
  name modelo.sociedad,
  kind FULL,
  grain sociedad_key,
  description 'Sociedad inscrita en el Registro Mercantil según el BORME (desde 2009): su hoja registral, nombre y datos actuales, constitución, capital y situación. "Activa" significa que no consta disolución ni extinción publicadas.',
  audits (
    not_null(columns := (sociedad_key, referencia, nombre)),
    unique_values(columns := (sociedad_key)),
    unique_values(columns := (referencia))
  )
);

WITH ultimo AS (
  SELECT
    sociedad_ref,
    arg_max(company, (published, number)) AS nombre,
    arg_max(province, (published, number)) AS provincia,
    arg_max(sheet, (published, number)) AS hoja,
    min(published) AS fecha_primera_publicacion,
    max(published) AS fecha_ultima_publicacion,
    count(*) AS num_anuncios
  FROM stage.borme_filing
  GROUP BY sociedad_ref
),
actos AS (
  SELECT f.sociedad_ref, f.published, f.number, a.*
  FROM stage.borme_act AS a
  JOIN stage.borme_filing AS f USING (doc_id, number)
),
historia AS (
  SELECT
    sociedad_ref,
    min(published) FILTER (WHERE kind = 'Constitución') AS fecha_constitucion,
    arg_min(start_of_operations, published) FILTER (WHERE kind = 'Constitución')
      AS comienzo_operaciones,
    arg_min(capital, published) FILTER (WHERE kind = 'Constitución') AS capital_inicial,
    -- On increases and reductions "Capital" is the change and "Resultante
    -- Suscrito" the new total.
    arg_max(
      CASE WHEN kind = 'Constitución' THEN capital ELSE resulting_capital END,
      (published, number)
    ) FILTER (
      WHERE (kind = 'Constitución' AND capital IS NOT NULL)
         OR (kind IN ('Ampliación de capital', 'Reducción de capital')
             AND resulting_capital IS NOT NULL)
    ) AS capital,
    arg_max(address, (published, number)) FILTER (WHERE address IS NOT NULL) AS domicilio,
    arg_max(purpose, (published, number)) FILTER (WHERE purpose IS NOT NULL) AS objeto_social,
    max(published) FILTER (WHERE kind = 'Disolución') AS fecha_disolucion,
    max(published) FILTER (WHERE kind = 'Extinción') AS fecha_extincion,
    max(published) FILTER (WHERE kind = 'Situación concursal') AS fecha_concurso,
    max(published) FILTER (
      WHERE kind IN (
        'Reapertura hoja registral',
        'Reactivación de la sociedad (Art. 242 del Reglamento del Registro Mercantil)'
      )
    ) AS fecha_reactivacion,
    count(*) AS num_actos
  FROM actos
  GROUP BY sociedad_ref
)
SELECT
  @clave('sociedad', u.sociedad_ref) AS sociedad_key,
  u.sociedad_ref AS referencia,
  u.hoja,
  u.nombre,
  @nombre_normalizado(u.nombre) AS nombre_normalizado,
  @forma_juridica(@nombre_normalizado(u.nombre)) AS forma_juridica,
  u.provincia,
  h.fecha_constitucion,
  h.comienzo_operaciones,
  h.capital_inicial,
  h.capital,
  h.domicilio,
  h.objeto_social,
  h.fecha_disolucion,
  h.fecha_extincion,
  h.fecha_concurso,
  CASE
    WHEN h.fecha_extincion IS NOT NULL
      AND (h.fecha_reactivacion IS NULL OR h.fecha_reactivacion < h.fecha_extincion)
      THEN 'Extinguida'
    WHEN h.fecha_disolucion IS NOT NULL
      AND (h.fecha_reactivacion IS NULL OR h.fecha_reactivacion < h.fecha_disolucion)
      THEN 'Disuelta'
    WHEN h.fecha_concurso IS NOT NULL THEN 'En concurso'
    ELSE 'Activa'
  END AS estado,
  u.fecha_primera_publicacion,
  u.fecha_ultima_publicacion,
  u.num_anuncios,
  coalesce(h.num_actos, 0) AS num_actos
FROM ultimo AS u
LEFT JOIN historia AS h USING (sociedad_ref)
UNION ALL
SELECT 0, '__desconocida__', NULL, 'Sociedad desconocida', NULL, NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, 0
UNION ALL
SELECT -1, '__no_aplica__', NULL, 'Sin datos registrales', NULL, NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, 0
