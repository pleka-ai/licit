-- Refresh derived tables from licitacion. Run after every load
-- (scripts/d1-load.sh). Upserts only touch changed rows, so the daily cost in
-- rows written stays small.

INSERT INTO empresa (nif, nombre, contratos)
SELECT adjudicatario_nif, max(adjudicatario), count(*)
FROM licitacion WHERE adjudicatario_nif IS NOT NULL
GROUP BY adjudicatario_nif
ON CONFLICT(nif) DO UPDATE SET nombre = excluded.nombre, contratos = excluded.contratos
WHERE empresa.contratos <> excluded.contratos OR empresa.nombre IS NOT excluded.nombre;

INSERT INTO organo (id, nombre, nif, licitaciones)
SELECT organo_id, max(organo), max(organo_nif), count(*)
FROM licitacion WHERE organo_id IS NOT NULL
GROUP BY organo_id
ON CONFLICT(id) DO UPDATE SET nombre = excluded.nombre, nif = excluded.nif,
  licitaciones = excluded.licitaciones
WHERE organo.licitaciones <> excluded.licitaciones OR organo.nombre IS NOT excluded.nombre;

DELETE FROM catalogo;

INSERT INTO catalogo (tipo, valor, codigo, n)
SELECT 'tipo_contrato', tipo_contrato, max(type_code), count(*) FROM licitacion
WHERE tipo_contrato IS NOT NULL GROUP BY tipo_contrato;

INSERT INTO catalogo (tipo, valor, codigo, n)
SELECT 'estado', estado, max(status_code), count(*) FROM licitacion
WHERE estado IS NOT NULL GROUP BY estado;

INSERT INTO catalogo (tipo, valor, codigo, n)
SELECT 'procedimiento', procedimiento, max(procedure_code), count(*) FROM licitacion
WHERE procedimiento IS NOT NULL GROUP BY procedimiento;

INSERT INTO catalogo (tipo, valor, n)
SELECT 'tramitacion', tramitacion, count(*) FROM licitacion
WHERE tramitacion IS NOT NULL GROUP BY tramitacion;

INSERT INTO catalogo (tipo, valor, n)
SELECT 'organo_tipo', organo_tipo, count(*) FROM licitacion
WHERE organo_tipo IS NOT NULL GROUP BY organo_tipo;

INSERT INTO catalogo (tipo, valor, codigo, descripcion, n)
SELECT 'cpv', cpv_principal, cpv_principal, max(cpv_principal_desc), count(*) FROM licitacion
WHERE cpv_principal IS NOT NULL GROUP BY cpv_principal;

INSERT INTO meta (clave, valor)
SELECT 'stats', json_object(
  'total_licitaciones', count(*),
  'total_organos', count(DISTINCT organo_id),
  'total_empresas', count(DISTINCT adjudicatario_nif),
  'importe_total', round(coalesce(sum(presupuesto_sin_iva), 0)),
  'desde', min(fecha_publicacion),
  'ultima_actualizacion', max(fecha_actualizacion))
FROM licitacion
WHERE true
ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;
