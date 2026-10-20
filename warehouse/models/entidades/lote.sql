MODEL (
  name modelo.lote,
  kind FULL,
  grain lote_key,
  description 'Lote de una licitación: la parte del objeto que se adjudica por separado. Las licitaciones sin lotes tienen un único lote "0" (es_objeto_unico). Su presupuesto está en presupuesto_lote y sus adjudicaciones en adjudicacion.',
  audits (
    not_null(columns := (lote_key, lote_numero)),
    unique_values(columns := (lote_key))
  )
);

SELECT
  @clave('lote', licitacion_key, lote_numero) AS lote_key,
  licitacion_key,
  lote_numero,
  es_objeto_unico,
  titulo
FROM stage.lote
UNION ALL
-- Results that name a lot the licitación does not declare.
SELECT 0, NULL, '?', false, 'Lote desconocido'
