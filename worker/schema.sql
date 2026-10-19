-- D1 schema: basic licitacion rows for the public API (rolling window).
-- Idempotent; applied by CI before every sync.

CREATE TABLE IF NOT EXISTS licitacion (
  rid INTEGER PRIMARY KEY,
  id TEXT NOT NULL UNIQUE,
  expediente TEXT,
  titulo TEXT,
  descripcion TEXT,
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

CREATE INDEX IF NOT EXISTS idx_lic_publicacion ON licitacion (fecha_publicacion);
CREATE INDEX IF NOT EXISTS idx_lic_organo ON licitacion (organo_id);
CREATE INDEX IF NOT EXISTS idx_lic_adjudicatario ON licitacion (adjudicatario_nif);

CREATE VIRTUAL TABLE IF NOT EXISTS licitacion_fts USING fts5(
  titulo, descripcion, organo, adjudicatario,
  content='licitacion', content_rowid='rid',
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS licitacion_ai AFTER INSERT ON licitacion BEGIN
  INSERT INTO licitacion_fts (rowid, titulo, descripcion, organo, adjudicatario)
  VALUES (new.rid, new.titulo, new.descripcion, new.organo, new.adjudicatario);
END;

CREATE TRIGGER IF NOT EXISTS licitacion_ad AFTER DELETE ON licitacion BEGIN
  INSERT INTO licitacion_fts (licitacion_fts, rowid, titulo, descripcion, organo, adjudicatario)
  VALUES ('delete', old.rid, old.titulo, old.descripcion, old.organo, old.adjudicatario);
END;

CREATE TRIGGER IF NOT EXISTS licitacion_au AFTER UPDATE ON licitacion BEGIN
  INSERT INTO licitacion_fts (licitacion_fts, rowid, titulo, descripcion, organo, adjudicatario)
  VALUES ('delete', old.rid, old.titulo, old.descripcion, old.organo, old.adjudicatario);
  INSERT INTO licitacion_fts (rowid, titulo, descripcion, organo, adjudicatario)
  VALUES (new.rid, new.titulo, new.descripcion, new.organo, new.adjudicatario);
END;

CREATE TABLE IF NOT EXISTS meta (
  clave TEXT PRIMARY KEY,
  valor TEXT
);
