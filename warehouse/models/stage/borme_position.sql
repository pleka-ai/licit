MODEL (
  name stage.borme_position,
  kind VIEW,
  grain (doc_id, number, act_n, n),
  description 'Personas y sociedades de los actos sobre cargos del BORME, con el cargo agrupado y el tipo de movimiento.'
);

WITH p AS (
  SELECT
    p.doc_id::TEXT AS doc_id,
    p.number::BIGINT AS number,
    p.act_n::INT AS act_n,
    p.n::INT AS n,
    @texto(p.role) AS role,
    @texto(p.name) AS name,
    a.kind::TEXT AS act_kind,
    -- Comparison form of the role label: 'Adm. Unico', 'ADM.UNICO' -> 'admunico'.
    regexp_replace(lower(strip_accents(p.role)), '[^a-z]', '', 'g') AS role_key
  FROM @borme(position) AS p
  JOIN @borme(act) AS a
    ON a.doc_id = p.doc_id AND a.number = p.number AND a.n = p.act_n
)
SELECT
  doc_id,
  number,
  act_n,
  n,
  role,
  name,
  @nombre_normalizado(name) AS name_normalized,
  CASE act_kind
    WHEN 'Nombramientos' THEN 'Nombramiento'
    WHEN 'Reelecciones' THEN 'Reelección'
    WHEN 'Ceses/Dimisiones' THEN 'Cese'
    WHEN 'Revocaciones' THEN 'Revocación'
    WHEN 'Cancelaciones de oficio de nombramientos' THEN 'Cancelación de oficio'
    WHEN 'Declaración de unipersonalidad' THEN 'Socio único'
  END AS movement,
  -- Some 270 spellings of the roles, grouped. Order matters: specific first.
  CASE
    WHEN role_key LIKE '%concurs%' THEN 'Administrador concursal'
    WHEN role_key LIKE 'socio%unic%' OR act_kind = 'Declaración de unipersonalidad'
      THEN 'Socio único'
    WHEN role_key LIKE 'liq%' THEN 'Liquidador'
    WHEN role_key LIKE 'ad%unic%' THEN 'Administrador único'
    WHEN role_key LIKE 'adm%solid%' OR role_key LIKE 'admin%sol%' THEN 'Administrador solidario'
    WHEN role_key LIKE 'adm%manc%' OR role_key LIKE 'adm%conj%' THEN 'Administrador mancomunado'
    WHEN role_key LIKE 'adm%' THEN 'Administrador'
    -- 'Co.De.Ma.So' (mancomunado/solidario); not 'Cons.Indep.' nor 'Coms.Del.'.
    WHEN role_key LIKE 'con%del%' OR role_key LIKE 'code%' THEN 'Consejero delegado'
    WHEN role_key LIKE 'cons%' THEN 'Consejero'
    WHEN role_key LIKE 'vicepres%' THEN 'Vicepresidente'
    WHEN role_key LIKE 'pres%' OR role_key LIKE 'copres%' THEN 'Presidente'
    WHEN role_key LIKE 'v%sec%' OR role_key LIKE 'vicesec%' THEN 'Vicesecretario'
    WHEN role_key LIKE 'sec%' THEN 'Secretario'
    WHEN role_key LIKE 'apo%' THEN 'Apoderado'
    WHEN role_key LIKE 'aud%' THEN 'Auditor'
    WHEN role_key LIKE 'rep%' THEN 'Representante'
    WHEN role_key LIKE 'socio%' THEN 'Socio'
    ELSE 'Otro'
  END AS role_group
FROM p
WHERE name IS NOT NULL
