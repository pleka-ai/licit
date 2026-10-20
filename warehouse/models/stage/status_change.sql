MODEL (
  name stage.status_change,
  kind VIEW,
  grain (entry_id, status_code, updated),
  description 'Cada estado observado de un expediente y cuándo (unión de todos los snapshots).'
);

SELECT
  @clave('licitacion', entry_id) AS licitacion_key,
  entry_id::TEXT AS entry_id,
  status_code::TEXT AS status_code,
  updated::TIMESTAMPTZ AS updated
FROM @raw(status_change)
