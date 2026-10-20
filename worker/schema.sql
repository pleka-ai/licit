-- D1 schema: the public API's slice of the dimensional model (warehouse/).
-- Idempotent; applied by scripts/d1-load.sh before every load. Rows come from
-- the model's Parquet through export.d1 (full load or daily diff).
--
-- Dimensions carry only real members: the model's reserved members (0/-1)
-- are not loaded, so a LEFT JOIN yields NULL where the API returns null.

-- ---------------------------------------------------------------- dimensions

CREATE TABLE IF NOT EXISTS estado (
  estado_key INTEGER PRIMARY KEY,
  codigo TEXT NOT NULL,
  descripcion TEXT
);

CREATE TABLE IF NOT EXISTS resultado (
  resultado_key INTEGER PRIMARY KEY,
  codigo TEXT NOT NULL,
  descripcion TEXT
);

CREATE TABLE IF NOT EXISTS cpv (
  cpv_key INTEGER PRIMARY KEY,
  codigo TEXT NOT NULL,
  descripcion TEXT
);

CREATE INDEX IF NOT EXISTS idx_cpv_codigo ON cpv (codigo);

CREATE TABLE IF NOT EXISTS lugar (
  lugar_key INTEGER PRIMARY KEY,
  codigo TEXT NOT NULL,
  nombre TEXT,
  nombre_placsp TEXT,
  comunidad TEXT
);

-- organo and empresa carry their activity count to rank entity search.
CREATE TABLE IF NOT EXISTS organo (
  organo_key INTEGER PRIMARY KEY,
  id TEXT NOT NULL UNIQUE,
  nombre TEXT,
  nif TEXT,
  tipo TEXT,
  licitaciones INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_organo_nif ON organo (nif);

CREATE VIRTUAL TABLE IF NOT EXISTS organo_fts USING fts5(
  nombre, content='organo', content_rowid='organo_key',
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS organo_ai AFTER INSERT ON organo BEGIN
  INSERT INTO organo_fts (rowid, nombre) VALUES (new.organo_key, new.nombre);
END;

CREATE TRIGGER IF NOT EXISTS organo_ad AFTER DELETE ON organo BEGIN
  INSERT INTO organo_fts (organo_fts, rowid, nombre)
  VALUES ('delete', old.organo_key, old.nombre);
END;

CREATE TRIGGER IF NOT EXISTS organo_au AFTER UPDATE OF nombre ON organo BEGIN
  INSERT INTO organo_fts (organo_fts, rowid, nombre)
  VALUES ('delete', old.organo_key, old.nombre);
  INSERT INTO organo_fts (rowid, nombre) VALUES (new.organo_key, new.nombre);
END;

CREATE TABLE IF NOT EXISTS empresa (
  empresa_key INTEGER PRIMARY KEY,
  nif TEXT,
  nombre TEXT,
  contratos INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_empresa_nif ON empresa (nif);

CREATE VIRTUAL TABLE IF NOT EXISTS empresa_fts USING fts5(
  nombre, content='empresa', content_rowid='empresa_key',
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS empresa_ai AFTER INSERT ON empresa BEGIN
  INSERT INTO empresa_fts (rowid, nombre) VALUES (new.empresa_key, new.nombre);
END;

CREATE TRIGGER IF NOT EXISTS empresa_ad AFTER DELETE ON empresa BEGIN
  INSERT INTO empresa_fts (empresa_fts, rowid, nombre)
  VALUES ('delete', old.empresa_key, old.nombre);
END;

CREATE TRIGGER IF NOT EXISTS empresa_au AFTER UPDATE OF nombre ON empresa BEGIN
  INSERT INTO empresa_fts (empresa_fts, rowid, nombre)
  VALUES ('delete', old.empresa_key, old.nombre);
  INSERT INTO empresa_fts (rowid, nombre) VALUES (new.empresa_key, new.nombre);
END;

-- --------------------------------------------------------------------- facts

-- The licitacion entity joined to its ciclo_licitacion fact: one row per
-- licitación, as the API serves it. rid follows load order, which
-- is chronological (full loads are sorted by fecha_publicacion and new rows
-- are appended), so "newest first" is a reverse rowid scan. Single-column
-- indexes end in rowid, so equality filters also come out newest-first.
CREATE TABLE IF NOT EXISTS licitacion (
  rid INTEGER PRIMARY KEY,
  licitacion_key INTEGER NOT NULL UNIQUE,
  id TEXT NOT NULL UNIQUE,
  expediente TEXT,
  titulo TEXT,
  url_place TEXT,
  organo_key INTEGER NOT NULL,
  estado_key INTEGER NOT NULL,
  cpv_key INTEGER NOT NULL,
  lugar_key INTEGER NOT NULL,
  adjudicatario_key INTEGER NOT NULL,
  resultado_key INTEGER NOT NULL,
  -- Attributes of the licitacion dimension; the two codes are the API's most
  -- used filters, single-index equality lookups in rowid order (no sort).
  tipo_contrato_codigo TEXT,
  tipo_contrato TEXT,
  procedimiento_codigo TEXT,
  procedimiento TEXT,
  tramitacion TEXT,
  sistema_contratacion TEXT,
  financiacion_codigo TEXT,
  financiacion TEXT,
  fecha_publicacion TEXT,
  fecha_actualizacion TEXT,
  fecha_limite TEXT,
  hora_limite TEXT,
  fecha_adjudicacion TEXT,
  fecha_formalizacion TEXT,
  presupuesto_sin_iva REAL,
  presupuesto_con_iva REAL,
  valor_estimado REAL,
  duracion REAL,
  duracion_unidad TEXT,
  num_lotes INTEGER,
  num_ofertas INTEGER,
  importe_adjudicado_sin_iva REAL,
  num_documentos INTEGER,
  tasa_subcontratacion_maxima REAL
);

CREATE INDEX IF NOT EXISTS idx_lic_publicacion ON licitacion (fecha_publicacion);
CREATE INDEX IF NOT EXISTS idx_lic_expediente ON licitacion (expediente);
CREATE INDEX IF NOT EXISTS idx_lic_organo ON licitacion (organo_key);
CREATE INDEX IF NOT EXISTS idx_lic_adjudicatario ON licitacion (adjudicatario_key);
CREATE INDEX IF NOT EXISTS idx_lic_tipo ON licitacion (tipo_contrato_codigo);
CREATE INDEX IF NOT EXISTS idx_lic_procedimiento ON licitacion (procedimiento_codigo);
CREATE INDEX IF NOT EXISTS idx_lic_estado ON licitacion (estado_key);
CREATE INDEX IF NOT EXISTS idx_lic_cpv ON licitacion (cpv_key);
CREATE INDEX IF NOT EXISTS idx_lic_lugar ON licitacion (lugar_key);
CREATE INDEX IF NOT EXISTS idx_lic_importe ON licitacion (presupuesto_sin_iva);

-- Full-text index over the title and the names of the contracting party and
-- the main winner. A plain (not external-content) FTS5 table, so stale rows
-- can be deleted by rowid; triggers resolve the names from the dimensions,
-- which export.d1 always loads before the facts.
CREATE VIRTUAL TABLE IF NOT EXISTS licitacion_fts USING fts5(
  titulo, organo, adjudicatario,
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS licitacion_ai AFTER INSERT ON licitacion BEGIN
  INSERT INTO licitacion_fts (rowid, titulo, organo, adjudicatario)
  VALUES (
    new.rid, new.titulo,
    (SELECT nombre FROM organo WHERE organo_key = new.organo_key),
    (SELECT nombre FROM empresa WHERE empresa_key = new.adjudicatario_key)
  );
END;

CREATE TRIGGER IF NOT EXISTS licitacion_ad AFTER DELETE ON licitacion BEGIN
  DELETE FROM licitacion_fts WHERE rowid = old.rid;
END;

CREATE TRIGGER IF NOT EXISTS licitacion_au
AFTER UPDATE OF titulo, organo_key, adjudicatario_key ON licitacion BEGIN
  DELETE FROM licitacion_fts WHERE rowid = old.rid;
  INSERT INTO licitacion_fts (rowid, titulo, organo, adjudicatario)
  VALUES (
    new.rid, new.titulo,
    (SELECT nombre FROM organo WHERE organo_key = new.organo_key),
    (SELECT nombre FROM empresa WHERE empresa_key = new.adjudicatario_key)
  );
END;

-- Every award (per lot and per winner): company profiles and filters.
CREATE TABLE IF NOT EXISTS adjudicacion (
  licitacion_key INTEGER NOT NULL,
  resultado_n INTEGER NOT NULL,
  adjudicatario_n INTEGER NOT NULL,
  empresa_key INTEGER NOT NULL,
  organo_key INTEGER NOT NULL,
  fecha_adjudicacion TEXT,
  importe_sin_iva REAL,
  presupuesto_sin_iva REAL,
  PRIMARY KEY (licitacion_key, resultado_n, adjudicatario_n)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_adj_empresa ON adjudicacion (empresa_key);

-- Status timeline of each licitación.
CREATE TABLE IF NOT EXISTS cambio_estado (
  licitacion_key INTEGER NOT NULL,
  momento TEXT NOT NULL,
  estado_key INTEGER NOT NULL,
  PRIMARY KEY (licitacion_key, momento, estado_key)
) WITHOUT ROWID;

-- ----------------------------------------------------------- API projection

-- The flat licitacion the API has always returned, resolved through the
-- dimensions. SQLite flattens the view into each query, so filters on the
-- key columns still use licitacion's indexes and its rowid order.
CREATE VIEW IF NOT EXISTS licitacion_api AS
SELECT
  l.rid,
  l.licitacion_key,
  l.organo_key,
  l.estado_key,
  l.cpv_key,
  l.lugar_key,
  l.adjudicatario_key,
  l.id,
  l.expediente,
  l.titulo,
  l.url_place,
  l.fecha_actualizacion,
  l.fecha_publicacion,
  e.codigo AS status_code,
  l.tipo_contrato_codigo AS type_code,
  l.procedimiento_codigo AS procedure_code,
  e.descripcion AS estado,
  l.tipo_contrato,
  l.procedimiento,
  l.tramitacion,
  l.sistema_contratacion,
  l.presupuesto_sin_iva,
  l.presupuesto_con_iva,
  l.valor_estimado,
  l.fecha_limite,
  l.hora_limite,
  l.duracion,
  l.duracion_unidad,
  g.nombre AS lugar_nuts,
  g.nombre_placsp AS lugar_subentidad,
  l.financiacion_codigo AS funding_program_code,
  l.financiacion AS programa_financiacion,
  l.tasa_subcontratacion_maxima AS tasa_subcontratacion,
  o.id AS organo_id,
  o.nombre AS organo,
  o.nif AS organo_nif,
  o.tipo AS organo_tipo,
  c.codigo AS cpv_principal,
  c.descripcion AS cpv_principal_desc,
  l.fecha_adjudicacion,
  l.importe_adjudicado_sin_iva AS importe_adjudicacion,
  l.num_ofertas AS num_licitadores,
  r.descripcion AS resultado,
  a.nombre AS adjudicatario,
  a.nif AS adjudicatario_nif,
  l.fecha_formalizacion,
  l.num_lotes,
  l.num_documentos > 0 AS tiene_documentos
FROM licitacion l
LEFT JOIN organo o ON o.organo_key = l.organo_key
LEFT JOIN estado e ON e.estado_key = l.estado_key
LEFT JOIN cpv c ON c.cpv_key = l.cpv_key
LEFT JOIN lugar g ON g.lugar_key = l.lugar_key
LEFT JOIN empresa a ON a.empresa_key = l.adjudicatario_key
LEFT JOIN resultado r ON r.resultado_key = l.resultado_key;

-- ------------------------------------------------------------------- derived

-- Filter values per catalog with their counts (export.derived).
CREATE TABLE IF NOT EXISTS catalogo (
  tipo TEXT NOT NULL,
  valor TEXT NOT NULL,
  codigo TEXT,
  descripcion TEXT,
  n INTEGER NOT NULL,
  PRIMARY KEY (tipo, valor)
);

CREATE TABLE IF NOT EXISTS meta (
  clave TEXT PRIMARY KEY,
  valor TEXT
);
