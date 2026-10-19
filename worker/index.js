// licit Worker.
//   api.licit.es  → public API over D1 (/v1/*, /salud, /docs, /openapi.json)
//   licit.es      → static site (site/), Parquet from R2 (/data/*), API alias (/api/v1/*)

import { OPENAPI } from "./openapi.js";

const API_HOST = "api.licit.es";

const RESUMEN_COLS = `id, expediente, titulo, organo, organo_id, tipo_contrato, estado,
  presupuesto_sin_iva, importe_adjudicacion, fecha_publicacion,
  fecha_actualizacion, fecha_adjudicacion, fecha_limite, cpv_principal,
  num_licitadores, adjudicatario, adjudicatario_nif,
  lugar_subentidad AS lugar, tiene_documentos, num_lotes, url_place`;

const MAX_LIMIT = 100;
const DEFAULT_LIMIT = 20;

const CATALOGOS = {
  tipo_contrato: "tipo_contrato",
  estado: "estado",
  procedimiento: "procedimiento",
  tramitacion: "tramitacion",
  organo_tipo: "organo_tipo",
  cpv: "cpv_principal",
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.hostname === "www.licit.es") {
      url.hostname = "licit.es";
      return Response.redirect(url.toString(), 301);
    }
    try {
      if (url.hostname === API_HOST) return await apiHost(request, env, url);
      if (url.pathname.startsWith("/data/")) return serveData(request, env, url);
      if (url.pathname === "/docs") return Response.redirect(`https://${API_HOST}/docs`, 302);
      if (url.pathname.startsWith("/api/")) {
        return await api(request, env, url, url.pathname.slice("/api".length));
      }
    } catch (err) {
      return errorResponse(err);
    }
    return env.ASSETS.fetch(request);
  },
};

function errorResponse(err) {
  if (err instanceof HttpError) return json({ detail: err.message }, err.status);
  console.error(err);
  return json({ detail: "Error interno" }, 500);
}

async function apiHost(request, env, url) {
  const path = url.pathname.replace(/\/+$/, "") || "/";
  if (path === "/") return Response.redirect(`https://${API_HOST}/docs`, 302);
  if (path === "/docs") return swaggerUi();
  if (path === "/openapi.json") return json(OPENAPI, 200, { "cache-control": "public, max-age=3600" });
  return api(request, env, url, path);
}

function swaggerUi() {
  const html = `<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>licit API</title>
<link rel="icon" href="https://licit.es/favicon.svg">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css">
<style>body{margin:0}.topbar{display:none}.swagger-ui .info .title{font-family:ui-monospace,Menlo,monospace}</style>
</head><body><div id="ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
<script>SwaggerUIBundle({url:"/openapi.json",dom_id:"#ui",deepLinking:true,tryItOutEnabled:true,defaultModelsExpandDepth:0});</script>
</body></html>`;
  return new Response(html, { headers: { "content-type": "text/html; charset=utf-8" } });
}

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// ------------------------------------------------------------------ R2 data

async function serveData(request, env, url) {
  const key = decodeURIComponent(url.pathname.slice("/data/".length));
  if (key === "" || key === "index.json") return dataIndex(env);
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response("Method not allowed", { status: 405 });
  }
  const obj = await env.DATA.get(key, { range: request.headers, onlyIf: request.headers });
  if (obj === null) return new Response("Not found", { status: 404 });
  const headers = new Headers();
  obj.writeHttpMetadata(headers);
  headers.set("etag", obj.httpEtag);
  headers.set("accept-ranges", "bytes");
  headers.set("cache-control", "public, max-age=3600");
  headers.set("access-control-allow-origin", "*");
  headers.set("access-control-expose-headers", "content-range, content-length, etag");
  if (!("body" in obj)) return new Response(null, { status: 304, headers });
  if (obj.range && request.headers.has("range")) {
    const { offset = 0, length = obj.size - offset } = obj.range;
    headers.set("content-range", `bytes ${offset}-${offset + length - 1}/${obj.size}`);
    headers.set("content-length", String(length));
    return new Response(request.method === "HEAD" ? null : obj.body, { status: 206, headers });
  }
  headers.set("content-length", String(obj.size));
  return new Response(request.method === "HEAD" ? null : obj.body, { headers });
}

async function dataIndex(env) {
  const files = [];
  let cursor;
  do {
    const page = await env.DATA.list({ prefix: "parquet/", cursor });
    for (const o of page.objects) {
      files.push({ ruta: `/data/${o.key}`, bytes: o.size, subido: o.uploaded });
    }
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);
  return json({ ficheros: files }, 200, { "cache-control": "public, max-age=300" });
}

// ---------------------------------------------------------------------- API

async function api(request, env, url, rawPath) {
  const path = rawPath.replace(/\/+$/, "");
  const m = (re) => path.match(re);
  let match;
  let data;
  let kind;

  if (request.method === "OPTIONS") return new Response(null, { headers: cors() });

  if (path === "/v1" || path === "") {
    data = indice();
    kind = "indice";
  } else if (path === "/salud" || path === "/v1/salud") {
    data = await salud(env);
    kind = "salud";
  } else if (path === "/v1/empresas" || path === "/v1/organos") {
    const body = request.method === "POST" ? await readJson(request) : Object.fromEntries(url.searchParams);
    data = await buscarEntidad(env, path.endsWith("empresas") ? "empresa" : "organo", body);
    kind = "entidades";
  } else if (path === "/v1/catalogos") {
    data = { catalogos: Object.keys(CATALOGOS).sort() };
    kind = "json";
  } else if (path === "/v1/buscar") {
    const body = request.method === "POST" ? await readJson(request) : queryToBody(url);
    data = await buscar(env, body);
    kind = "busqueda";
  } else if ((match = m(/^\/v1\/licitacion\/([^/]+)$/))) {
    data = await licitacion(env, decodeURIComponent(match[1]));
    kind = "licitacion";
  } else if ((match = m(/^\/v1\/empresa\/([^/]+)$/))) {
    data = await perfil(env, "adjudicatario_nif", decodeURIComponent(match[1]), url);
    kind = "perfil";
  } else if ((match = m(/^\/v1\/organo\/([^/]+)$/))) {
    data = await perfil(env, "organo_id", decodeURIComponent(match[1]), url);
    kind = "perfil";
  } else if ((match = m(/^\/v1\/similares\/([^/]+)$/))) {
    data = await similares(env, decodeURIComponent(match[1]));
    kind = "busqueda";
  } else if ((match = m(/^\/v1\/catalogos\/([^/]+)$/))) {
    data = await catalogo(env, match[1]);
    kind = "catalogo";
  } else {
    throw new HttpError(404, `Ruta no encontrada. Ver https://${API_HOST}/docs`);
  }

  if (wantsMarkdown(request, url)) {
    return new Response(toMarkdown(kind, data), {
      headers: { "content-type": "text/markdown; charset=utf-8", ...cors() },
    });
  }
  return json(data);
}

function indice() {
  return {
    nombre: "licit",
    descripcion: "API de licitaciones publicas de Espana (datos PLACSP).",
    documentacion: `https://${API_HOST}/docs`,
    openapi: `https://${API_HOST}/openapi.json`,
    datos_completos: "https://licit.es/data/index.json",
  };
}

async function salud(env) {
  // Aggregates are precomputed by CI after each load (scripts/d1-load.sh).
  const { results } = await env.DB.prepare(
    "SELECT clave, valor FROM meta WHERE clave IN ('ultima_sync', 'stats')",
  ).all();
  const meta = Object.fromEntries(results.map((r) => [r.clave, r.valor]));
  return { estado: "ok", ultima_sync: meta.ultima_sync ?? null, ...(parseJson(meta.stats ?? "{}") || {}) };
}

async function buscar(env, body) {
  const f = body.filtros || {};
  const where = [];
  const params = [];
  const add = (sql, ...vals) => {
    where.push(sql);
    params.push(...vals);
  };

  let from = "licitacion l";
  const q = typeof body.q === "string" ? body.q.trim() : "";
  if (q) {
    from = "licitacion_fts JOIN licitacion l ON l.rid = licitacion_fts.rowid";
    add("licitacion_fts MATCH ?", ftsQuery(q));
  }
  if (Array.isArray(f.tipo_contrato) && f.tipo_contrato.length) {
    const marks = f.tipo_contrato.map(() => "?").join(", ");
    add(`(l.tipo_contrato IN (${marks}) OR l.type_code IN (${marks}))`, ...f.tipo_contrato, ...f.tipo_contrato);
  }
  if (Array.isArray(f.estado) && f.estado.length) {
    const marks = f.estado.map(() => "?").join(", ");
    add(`(l.estado IN (${marks}) OR l.status_code IN (${marks}))`, ...f.estado, ...f.estado);
  }
  if (Array.isArray(f.procedimiento) && f.procedimiento.length) {
    const marks = f.procedimiento.map(() => "?").join(", ");
    add(`(l.procedimiento IN (${marks}) OR l.procedure_code IN (${marks}))`, ...f.procedimiento, ...f.procedimiento);
  }
  if (f.cpv_prefijo) add("l.cpv_principal LIKE ?", `${String(f.cpv_prefijo)}%`);
  if (f.importe_min != null) add("l.presupuesto_sin_iva >= ?", Number(f.importe_min));
  if (f.importe_max != null) add("l.presupuesto_sin_iva <= ?", Number(f.importe_max));
  if (f.fecha_publicacion_desde) add("l.fecha_publicacion >= ?", String(f.fecha_publicacion_desde));
  if (f.fecha_publicacion_hasta) add("l.fecha_publicacion < date(?, '+1 day')", String(f.fecha_publicacion_hasta));
  if (f.ccaa) add("(l.lugar_subentidad LIKE ? OR l.lugar_nuts LIKE ?)", `%${f.ccaa}%`, `%${f.ccaa}%`);
  if (f.adjudicatario) add("l.adjudicatario LIKE ?", `%${f.adjudicatario}%`);
  if (f.organo_id) add("l.organo_id = ?", String(f.organo_id));
  else if (f.organo) add("l.organo LIKE ?", `%${f.organo}%`);
  if (f.financiacion_ue === true) add("l.funding_program_code = 'EU'");
  if (f.financiacion_ue === false) add("coalesce(l.funding_program_code, '') <> 'EU'");

  const order =
    body.ordenar === "importe"
      ? "l.presupuesto_sin_iva DESC"
      : body.ordenar === "relevancia" && q
        ? "licitacion_fts.rank"
        : "l.fecha_publicacion DESC";
  const limit = clampLimit(body.limit ?? body.limite);
  const offset = decodeCursor(body.cursor);
  const whereSql = where.length ? `WHERE ${where.join(" AND ")}` : "";
  const cols = RESUMEN_COLS.split(",").map((c) => `l.${c.trim()}`).join(", ");

  const [rows, total] = await env.DB.batch([
    env.DB.prepare(`SELECT ${cols} FROM ${from} ${whereSql} ORDER BY ${order} LIMIT ? OFFSET ?`).bind(
      ...params,
      limit + 1,
      offset,
    ),
    env.DB.prepare(`SELECT count(*) AS n FROM ${from} ${whereSql}`).bind(...params),
  ]);
  const results = rows.results.slice(0, limit).map(resumen);
  return {
    total: total.results[0].n,
    resultados: results,
    cursor_siguiente: rows.results.length > limit ? encodeCursor(offset + limit) : null,
  };
}

async function licitacion(env, id) {
  const row = await env.DB.prepare("SELECT * FROM licitacion WHERE id = ? OR expediente = ? LIMIT 1")
    .bind(id, id)
    .first();
  if (!row) throw new HttpError(404, "Licitacion no encontrada");
  delete row.rid;
  row.historial_estados = parseJson(row.historial_estados);
  row.tiene_documentos = Boolean(row.tiene_documentos);
  return row;
}

async function perfil(env, col, value, url) {
  const limit = clampLimit(url.searchParams.get("limit"));
  const offset = decodeCursor(url.searchParams.get("cursor"));
  const nameCol = col === "organo_id" ? "organo" : "adjudicatario";
  const otherCol = col === "organo_id" ? "adjudicatario" : "organo";
  const [stats, cpvs, otros, rows] = await env.DB.batch([
    env.DB.prepare(
      `SELECT max(${nameCol}) AS nombre, count(*) AS contratos,
              sum(coalesce(importe_adjudicacion, presupuesto_sin_iva)) AS importe_total,
              avg(coalesce(importe_adjudicacion, presupuesto_sin_iva)) AS importe_medio,
              avg(CASE WHEN presupuesto_sin_iva > 0 AND importe_adjudicacion IS NOT NULL
                  THEN 100.0 * (presupuesto_sin_iva - importe_adjudicacion) / presupuesto_sin_iva END) AS baja_media_pct
       FROM licitacion WHERE ${col} = ?`,
    ).bind(value),
    env.DB.prepare(
      `SELECT cpv_principal AS cpv, max(cpv_principal_desc) AS descripcion, count(*) AS n
       FROM licitacion WHERE ${col} = ? AND cpv_principal IS NOT NULL
       GROUP BY cpv_principal ORDER BY n DESC LIMIT 5`,
    ).bind(value),
    env.DB.prepare(
      `SELECT ${otherCol} AS nombre, count(*) AS n FROM licitacion
       WHERE ${col} = ? AND ${otherCol} IS NOT NULL
       GROUP BY ${otherCol} ORDER BY n DESC LIMIT 5`,
    ).bind(value),
    env.DB.prepare(
      `SELECT ${RESUMEN_COLS} FROM licitacion WHERE ${col} = ?
       ORDER BY fecha_publicacion DESC LIMIT ? OFFSET ?`,
    ).bind(value, limit + 1, offset),
  ]);
  const s = stats.results[0];
  if (!s || s.contratos === 0) throw new HttpError(404, "Sin licitaciones");
  return {
    id: value,
    nombre: s.nombre,
    stats: {
      contratos: s.contratos,
      importe_total: round2(s.importe_total),
      importe_medio: round2(s.importe_medio),
      baja_media_pct: round2(s.baja_media_pct),
      cpv_frecuentes: cpvs.results,
      [col === "organo_id" ? "adjudicatarios_frecuentes" : "organos_frecuentes"]: otros.results,
    },
    licitaciones: rows.results.slice(0, limit).map(resumen),
    cursor_siguiente: rows.results.length > limit ? encodeCursor(offset + limit) : null,
  };
}

async function buscarEntidad(env, tipo, body) {
  const q = typeof body.q === "string" ? body.q.trim() : "";
  if (q.length < 2) throw new HttpError(422, "q debe tener al menos 2 caracteres");
  const limit = clampLimit(body.limite ?? body.limit);
  const [idCol, nameCol, nifCol] =
    tipo === "empresa"
      ? ["adjudicatario_nif", "adjudicatario", "adjudicatario_nif"]
      : ["organo_id", "organo", "organo_nif"];
  const { results } = await env.DB.prepare(
    `SELECT ${idCol} AS id, max(${nameCol}) AS nombre, max(${nifCol}) AS nif,
            count(*) AS licitaciones
     FROM licitacion
     WHERE ${idCol} IS NOT NULL AND (${nameCol} LIKE ? OR ${nifCol} = ?)
     GROUP BY ${idCol} ORDER BY licitaciones DESC LIMIT ?`,
  )
    .bind(`%${q}%`, q.toUpperCase(), limit)
    .all();
  return tipo === "empresa"
    ? results.map(({ id, nombre, licitaciones }) => ({ id, nombre, contratos: licitaciones }))
    : results;
}

async function similares(env, id) {
  const base = await env.DB.prepare(
    "SELECT id, cpv_principal, presupuesto_sin_iva FROM licitacion WHERE id = ?",
  )
    .bind(id)
    .first();
  if (!base) throw new HttpError(404, "Licitacion no encontrada");
  if (!base.cpv_principal) return { total: 0, resultados: [], cursor_siguiente: null };
  const amount = base.presupuesto_sin_iva || 0;
  const { results } = await env.DB.prepare(
    `SELECT ${RESUMEN_COLS} FROM licitacion
     WHERE id <> ? AND cpv_principal LIKE ?
       AND (? = 0 OR presupuesto_sin_iva BETWEEN ? AND ?)
     ORDER BY abs(coalesce(presupuesto_sin_iva, 0) - ?) LIMIT 10`,
  )
    .bind(id, `${base.cpv_principal.slice(0, 5)}%`, amount, amount * 0.5, amount * 2, amount)
    .all();
  return { total: results.length, resultados: results.map(resumen), cursor_siguiente: null };
}

async function catalogo(env, tipo) {
  const col = CATALOGOS[tipo];
  if (!col) throw new HttpError(404, `Catalogo desconocido. Validos: ${Object.keys(CATALOGOS).join(", ")}`);
  const extra = tipo === "cpv" ? ", max(cpv_principal_desc) AS descripcion" : "";
  const { results } = await env.DB.prepare(
    `SELECT ${col} AS valor${extra}, count(*) AS n FROM licitacion
     WHERE ${col} IS NOT NULL GROUP BY ${col} ORDER BY n DESC LIMIT 500`,
  ).all();
  return { tipo, valores: results };
}

// ------------------------------------------------------------------ helpers

function resumen(r) {
  return { ...r, tiene_documentos: Boolean(r.tiene_documentos) };
}

function ftsQuery(q) {
  // Each word becomes a quoted prefix term: safe against FTS syntax errors.
  const terms = q
    .normalize("NFKC")
    .split(/[^\p{L}\p{N}]+/u)
    .filter((t) => t.length > 1)
    .slice(0, 12);
  if (terms.length === 0) throw new HttpError(400, "Consulta de texto vacia");
  return terms.map((t) => `"${t}"*`).join(" ");
}

function queryToBody(url) {
  const p = url.searchParams;
  const list = (k) => (p.getAll(k).length ? p.getAll(k) : undefined);
  return {
    q: p.get("q") || undefined,
    ordenar: p.get("ordenar") || undefined,
    limit: p.get("limit") || undefined,
    cursor: p.get("cursor") || undefined,
    filtros: {
      tipo_contrato: list("tipo_contrato"),
      estado: list("estado"),
      procedimiento: list("procedimiento"),
      cpv_prefijo: p.get("cpv_prefijo") || undefined,
      importe_min: p.get("importe_min") ?? undefined,
      importe_max: p.get("importe_max") ?? undefined,
      ccaa: p.get("ccaa") || undefined,
      organo: p.get("organo") || undefined,
      adjudicatario: p.get("adjudicatario") || undefined,
    },
  };
}

async function readJson(request) {
  try {
    return (await request.json()) || {};
  } catch {
    throw new HttpError(400, "JSON invalido");
  }
}

function clampLimit(v) {
  const n = Number.parseInt(v ?? DEFAULT_LIMIT, 10);
  return Number.isFinite(n) ? Math.min(Math.max(n, 1), MAX_LIMIT) : DEFAULT_LIMIT;
}

function encodeCursor(offset) {
  return btoa(JSON.stringify({ o: offset }));
}

function decodeCursor(c) {
  if (!c) return 0;
  try {
    const o = JSON.parse(atob(c)).o;
    return Number.isInteger(o) && o >= 0 ? o : 0;
  } catch {
    throw new HttpError(400, "Cursor invalido");
  }
}

function parseJson(s) {
  try {
    return JSON.parse(s);
  } catch {
    return s;
  }
}

function round2(n) {
  return n == null ? null : Math.round(n * 100) / 100;
}

function cors() {
  return {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET, POST, OPTIONS",
    "access-control-allow-headers": "content-type, accept",
  };
}

function json(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...cors(), ...extra },
  });
}

// ----------------------------------------------------------------- markdown

function wantsMarkdown(request, url) {
  if (url.searchParams.get("formato") === "md") return true;
  const accept = request.headers.get("accept") || "";
  return accept.includes("text/markdown");
}

const DASH = "—";
const cell = (v) => (v == null || v === "" ? DASH : String(v).replace(/\|/g, "\\|").replace(/\n/g, " "));
const money = (v) => (v == null ? DASH : `${Number(v).toLocaleString("es-ES", { maximumFractionDigits: 2 })} €`);
const day = (v) => (v ? String(v).slice(0, 10) : DASH);

function table(rows) {
  const head = "| Fecha | Título | Órgano | Estado | Presupuesto | Adjudicatario | ID |\n|---|---|---|---|---|---|---|";
  const body = rows.map(
    (r) =>
      `| ${day(r.fecha_publicacion)} | ${cell(r.titulo)} | ${cell(r.organo)} | ${cell(r.estado)} | ${money(r.presupuesto_sin_iva)} | ${cell(r.adjudicatario)} | ${r.id} |`,
  );
  return [head, ...body].join("\n");
}

function toMarkdown(kind, d) {
  switch (kind) {
    case "busqueda":
      return `# Resultados (${d.total})\n\n${table(d.resultados)}\n${d.cursor_siguiente ? `\n_cursor_siguiente: ${d.cursor_siguiente}_\n` : ""}`;
    case "licitacion":
      return [
        `# ${d.titulo}`,
        "",
        `- **Expediente:** ${cell(d.expediente)}`,
        `- **Órgano:** ${cell(d.organo)}`,
        `- **Estado:** ${cell(d.estado)}`,
        `- **Tipo:** ${cell(d.tipo_contrato)} · ${cell(d.procedimiento)}`,
        `- **Presupuesto sin IVA:** ${money(d.presupuesto_sin_iva)}`,
        `- **CPV:** ${cell(d.cpv_principal)} ${cell(d.cpv_principal_desc)}`,
        `- **Publicación:** ${day(d.fecha_publicacion)} · **Límite:** ${day(d.fecha_limite)}`,
        `- **Adjudicatario:** ${cell(d.adjudicatario)} (${cell(d.adjudicatario_nif)}) · ${money(d.importe_adjudicacion)}`,
        `- **PLACSP:** ${cell(d.url_place)}`,
        "",
      ].join("\n");
    case "perfil":
      return `# ${cell(d.nombre)}\n\n- **Contratos:** ${d.stats.contratos}\n- **Importe total:** ${money(d.stats.importe_total)}\n- **Baja media:** ${d.stats.baja_media_pct == null ? DASH : `${d.stats.baja_media_pct}%`}\n\n## Licitaciones\n\n${table(d.licitaciones)}\n`;
    case "catalogo":
      return `# Catálogo: ${d.tipo}\n\n| Valor | N |\n|---|---|\n${d.valores.map((v) => `| ${cell(v.valor)} | ${v.n} |`).join("\n")}\n`;
    case "entidades":
      return `| Nombre | ID | N |\n|---|---|---|\n${d.map((e) => `| ${cell(e.nombre)} | ${e.id} | ${e.contratos ?? e.licitaciones} |`).join("\n")}\n`;
    default:
      return "```json\n" + JSON.stringify(d, null, 2) + "\n```\n";
  }
}
