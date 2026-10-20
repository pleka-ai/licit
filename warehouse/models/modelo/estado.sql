MODEL (
  name modelo.estado,
  kind FULL,
  tags (dimension),
  grain estado_key,
  description 'Estado de un expediente en su ciclo de vida, con la fase y el orden del ciclo.',
  audits (
    not_null(columns := (estado_key, codigo)),
    unique_values(columns := (estado_key)),
    unique_values(columns := (codigo))
  )
);

WITH codigos AS (
  SELECT code AS codigo FROM stage.codice_code WHERE list = 'status_code'
  UNION
  SELECT status_code FROM stage.contract_folder_status WHERE status_code IS NOT NULL
  UNION
  SELECT status_code FROM stage.status_change WHERE status_code IS NOT NULL
)
SELECT
  @clave('estado', codigo) AS estado_key,
  codigo,
  @etiqueta('status_code', codigo) AS descripcion,
  CASE codigo
    WHEN 'PRE' THEN 'Anuncio previo'
    WHEN 'PUB' THEN 'En plazo'
    WHEN 'EV' THEN 'Evaluación'
    WHEN 'ADJ' THEN 'Adjudicación'
    WHEN 'RES' THEN 'Formalización'
    WHEN 'ANUL' THEN 'Anulación'
    ELSE 'Otra'
  END AS fase,
  CASE codigo
    WHEN 'PRE' THEN 1 WHEN 'PUB' THEN 2 WHEN 'EV' THEN 3
    WHEN 'ADJ' THEN 4 WHEN 'RES' THEN 5 WHEN 'ANUL' THEN 6
  END AS orden,
  codigo IN ('RES', 'ANUL') AS es_final,
  codigo IN ('PRE', 'PUB') AS admite_ofertas
FROM codigos
UNION ALL
SELECT 0, '?', 'Desconocido', 'Desconocida', NULL, false, false
