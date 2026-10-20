-- D1 schema: basic licitacion rows for the public API (full history since 2017).
-- Idempotent; applied by CI before every sync.

CREATE TABLE IF NOT EXISTS licitacion (
  rid INTEGER PRIMARY KEY,
  id TEXT NOT NULL UNIQUE,
  expediente TEXT,
  titulo TEXT,
  url_place TEXT,
  fecha_actualizacion TEXT,
  fecha_publicacion TEXT,
  historial_estados TEXT,
  status_code TEXT,
  type_code TEXT,
  procedure_code TEXT,
  estado TEXT,
  tipo_contrato TEXT,
  procedimiento TEXT,
  tramitacion TEXT,
  sistema_contratacion TEXT,
  presupuesto_sin_iva REAL,
  presupuesto_con_iva REAL,
  valor_estimado REAL,
  fecha_limite TEXT,
  hora_limite TEXT,
  duracion REAL,
  duracion_unidad TEXT,
  lugar_nuts TEXT,
  lugar_subentidad TEXT,
  funding_program_code TEXT,
  programa_financiacion TEXT,
  tasa_subcontratacion REAL,
  organo_id TEXT,
  organo TEXT,
  organo_nif TEXT,
  organo_tipo TEXT,
  cpv_principal TEXT,
  cpv_principal_desc TEXT,
  fecha_adjudicacion TEXT,
  importe_adjudicacion REAL,
  num_licitadores INTEGER,
  resultado TEXT,
  adjudicatario TEXT,
  adjudicatario_nif TEXT,
  fecha_formalizacion TEXT,
  num_lotes INTEGER,
  tiene_documentos INTEGER
);

-- rid follows load order, which is chronological (bulk loads are sorted by
-- fecha_publicacion and daily rows are appended), so "newest first" is a
-- reverse rowid scan. Single-column indexes end in rowid, so equality
-- filters below also come out newest-first without sorting.
CREATE INDEX IF NOT EXISTS idx_lic_publicacion ON licitacion (fecha_publicacion);
CREATE INDEX IF NOT EXISTS idx_lic_organo ON licitacion (organo_id);
CREATE INDEX IF NOT EXISTS idx_lic_adjudicatario ON licitacion (adjudicatario_nif);
CREATE INDEX IF NOT EXISTS idx_lic_expediente ON licitacion (expediente);
CREATE INDEX IF NOT EXISTS idx_lic_tipo ON licitacion (type_code);
CREATE INDEX IF NOT EXISTS idx_lic_estado ON licitacion (status_code);
CREATE INDEX IF NOT EXISTS idx_lic_cpv ON licitacion (cpv_principal);
CREATE INDEX IF NOT EXISTS idx_lic_importe ON licitacion (presupuesto_sin_iva);

CREATE VIRTUAL TABLE IF NOT EXISTS licitacion_fts USING fts5(
  titulo, organo, adjudicatario,
  content='licitacion', content_rowid='rid',
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS licitacion_ai AFTER INSERT ON licitacion BEGIN
  INSERT INTO licitacion_fts (rowid, titulo, organo, adjudicatario)
  VALUES (new.rid, new.titulo, new.organo, new.adjudicatario);
END;

CREATE TRIGGER IF NOT EXISTS licitacion_ad AFTER DELETE ON licitacion BEGIN
  INSERT INTO licitacion_fts (licitacion_fts, rowid, titulo, organo, adjudicatario)
  VALUES ('delete', old.rid, old.titulo, old.organo, old.adjudicatario);
END;

CREATE TRIGGER IF NOT EXISTS licitacion_au AFTER UPDATE OF titulo, organo, adjudicatario ON licitacion BEGIN
  INSERT INTO licitacion_fts (licitacion_fts, rowid, titulo, organo, adjudicatario)
  VALUES ('delete', old.rid, old.titulo, old.organo, old.adjudicatario);
  INSERT INTO licitacion_fts (rowid, titulo, organo, adjudicatario)
  VALUES (new.rid, new.titulo, new.organo, new.adjudicatario);
END;

-- Derived tables, refreshed by scripts/d1-load.sh after every load so the
-- API never aggregates the 1.5M-row table at request time.

CREATE TABLE IF NOT EXISTS empresa (
  rid INTEGER PRIMARY KEY,
  nif TEXT NOT NULL UNIQUE,
  nombre TEXT,
  contratos INTEGER NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS empresa_fts USING fts5(
  nombre, content='empresa', content_rowid='rid',
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS empresa_ai AFTER INSERT ON empresa BEGIN
  INSERT INTO empresa_fts (rowid, nombre) VALUES (new.rid, new.nombre);
END;

CREATE TRIGGER IF NOT EXISTS empresa_au AFTER UPDATE OF nombre ON empresa BEGIN
  INSERT INTO empresa_fts (empresa_fts, rowid, nombre) VALUES ('delete', old.rid, old.nombre);
  INSERT INTO empresa_fts (rowid, nombre) VALUES (new.rid, new.nombre);
END;

CREATE TABLE IF NOT EXISTS organo (
  rid INTEGER PRIMARY KEY,
  id TEXT NOT NULL UNIQUE,
  nombre TEXT,
  nif TEXT,
  licitaciones INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_organo_nif ON organo (nif);

CREATE VIRTUAL TABLE IF NOT EXISTS organo_fts USING fts5(
  nombre, content='organo', content_rowid='rid',
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS organo_ai AFTER INSERT ON organo BEGIN
  INSERT INTO organo_fts (rowid, nombre) VALUES (new.rid, new.nombre);
END;

CREATE TRIGGER IF NOT EXISTS organo_au AFTER UPDATE OF nombre ON organo BEGIN
  INSERT INTO organo_fts (organo_fts, rowid, nombre) VALUES ('delete', old.rid, old.nombre);
  INSERT INTO organo_fts (rowid, nombre) VALUES (new.rid, new.nombre);
END;

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
