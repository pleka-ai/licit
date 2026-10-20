MODEL (
  name modelo.calendario,
  kind FULL,
  tags (dimension),
  grain fecha,
  description 'Dimensión de fechas. Todas las fechas del modelo (publicación, plazo, adjudicación, formalización…) la usan como rol; la clave es la propia fecha.',
  audits (
    not_null(columns := (fecha)),
    unique_values(columns := (fecha))
  )
);

SELECT
  d::DATE AS fecha,
  year(d)::INT AS anio,
  quarter(d)::INT AS trimestre,
  month(d)::INT AS mes,
  strftime(d, '%Y-%m') AS anio_mes,
  ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
   'septiembre', 'octubre', 'noviembre', 'diciembre'][month(d)] AS nombre_mes,
  weekofyear(d)::INT AS semana_iso,
  yearweek(d)::INT AS anio_semana_iso,
  day(d)::INT AS dia_mes,
  isodow(d)::INT AS dia_semana,
  ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'][isodow(d)]
    AS nombre_dia,
  isodow(d) >= 6 AS es_fin_de_semana
FROM generate_series(DATE '1990-01-01', DATE '2100-12-31', INTERVAL 1 DAY) AS t(d)
