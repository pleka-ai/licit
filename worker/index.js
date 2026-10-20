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

const RESUMEN_SELECT = RESUMEN_COLS.split(",").map((c) => `l.${c.trim()}`).join(", ");

// Two phases: pick one page of rids on the licitacion table alone (filters and
// sort never touch the other tables), then resolve only those rows through
// licitacion_api.
// `sortKey` is an expression of the inner FROM; ties go newest first.
function pageSql(from, whereSql, sortKey, desc) {
  const dir = desc ? "DESC" : "ASC";
  return `SELECT ${RESUMEN_SELECT} FROM (
      SELECT l.rid AS rid, ${sortKey} AS k FROM ${from} ${whereSql}
      ORDER BY k ${dir}, l.rid DESC LIMIT ? OFFSET ?) p
    JOIN licitacion_api l ON l.rid = p.rid
    ORDER BY p.k ${dir}, p.rid DESC`;
}

const MAX_LIMIT = 100;
const DEFAULT_LIMIT = 20;

const CATALOGOS = ["cpv", "estado", "organo_tipo", "procedimiento", "tipo_contrato", "tramitacion"];

// Filters on labels are resolved to codes via the catalogo table, then to an
// indexed column of licitacion (type and procedure codes are copied there) or
// to the keys of the estado table.
const CODE_FILTERS = {
  tipo_contrato: (marks) => `l.tipo_contrato_codigo IN (${marks})`,
  procedimiento: (marks) => `l.procedimiento_codigo IN (${marks})`,
  // A single state stays an equality, so its index comes out in rowid order.
  estado: (marks, n) =>
    n === 1
      ? `l.estado_key = (SELECT estado_key FROM estado WHERE codigo = ${marks})`
      : `l.estado_key IN (SELECT estado_key FROM estado WHERE codigo IN (${marks}))`,
};

// Past this many matches, "most expensive first" walks idx_lic_importe from
// the top and stops at the page; below it, the filters' indexes and a sort of
// the few matches are cheaper.
const IMPORTE_SCAN_MIN = 2000;

// Internal columns of licitacion_api the API never returns.
const KEY_COLS = [
  "rid",
  "licitacion_key",
  "organo_key",
  "estado_key",
  "cpv_key",
  "lugar_key",
  "adjudicatario_key",
];

// Expedientes awarded (any lot) to the companies selected by a subquery.
const ADJUDICADAS = (empresas) =>
  `l.licitacion_key IN (SELECT a.licitacion_key FROM adjudicacion a WHERE a.empresa_key IN (${empresas}))`;

// Exact counts stop here: past this point "total" is a lower bound.
const COUNT_CAP = 10000;
// Data changes once a day; edge-cache API answers for an hour.
const CACHE_TTL = 3600;
const NIF_RE = /^[A-Z0-9][0-9]{7}[A-Z0-9]$/i;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.hostname === "www.licit.es") {
      url.hostname = "licit.es";
      return Response.redirect(url.toString(), 301);
    }
    try {
      if (url.hostname === API_HOST) return await apiHost(request, env, ctx, url);
      if (url.pathname.startsWith("/data/")) return await serveData(request, env, url, ctx);
      if (url.pathname === "/docs") return Response.redirect(`https://${API_HOST}/docs`, 302);
      if (url.pathname.startsWith("/api/")) {
        return await cachedApi(request, env, ctx, url, url.pathname.slice("/api".length));
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

async function apiHost(request, env, ctx, url) {
  const path = url.pathname.replace(/\/+$/, "") || "/";
  if (path === "/") return Response.redirect(`https://${API_HOST}/docs`, 302);
  if (path === "/docs") return swaggerUi();
  if (path === "/openapi.json") return json(OPENAPI, 200, { "cache-control": "public, max-age=3600" });
  return cachedApi(request, env, ctx, url, path);
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

async function serveData(request, env, url, ctx) {
  const key = decodeURIComponent(url.pathname.slice("/data/".length));
  if (key === "" || key === "index.json") return dataIndex(env);
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response("Method not allowed", { status: 405 });
  }
  const range = request.headers.get("range");
  if (request.method === "GET" && range) return cachedRange(env, ctx, url, key, range);

  const obj = await env.DATA.get(key, { range: request.headers, onlyIf: request.headers });
  if (obj === null) return new Response("Not found", { status: 404 });
  const headers = dataHeaders(obj, url);
  if (!("body" in obj)) return new Response(null, { status: 304, headers });
  headers.set("content-length", String(obj.size));
  return new Response(request.method === "HEAD" ? null : obj.body, { headers });
}

// Files are replaced in place every day. Versioned URLs (?v=<etag>, as the
// explorer requests them) are immutable; bare URLs must never be served from a
// browser cache, or ranges of two versions get mixed.
function dataHeaders(obj, url) {
  const headers = new Headers();
  obj.writeHttpMetadata(headers);
  headers.set("etag", obj.httpEtag);
  headers.set("accept-ranges", "bytes");
  headers.set(
    "cache-control",
    url.searchParams.get("v") === obj.etag ? "public, max-age=31536000, immutable" : "no-store",
  );
  headers.set("access-control-allow-origin", "*");
  headers.set("access-control-expose-headers", "content-range, content-length, etag");
  return headers;
}

// DuckDB-WASM reads Parquet as many small byte ranges, and every viewer asks
// for the same ones. The Cache API won't store 206s, so each range is cached
// as a 200 keyed by object etag + range and replayed as a 206.
async function cachedRange(env, ctx, url, key, range) {
  const head = await env.DATA.head(key);
  if (head === null) return new Response("Not found", { status: 404 });
  const cacheKey = new Request(
    `${url.origin}/__r2/${encodeURIComponent(key)}?etag=${head.etag}&range=${encodeURIComponent(range)}`,
  );
  const cache = caches.default;
  const hit = await cache.match(cacheKey);
  if (hit) {
    const headers = new Headers(hit.headers);
    headers.set("content-range", headers.get("x-content-range"));
    headers.delete("x-content-range");
    headers.set("x-cache", "HIT");
    return new Response(hit.body, { status: 206, headers });
  }

  const obj = await env.DATA.get(key, { range: new Headers({ range }) });
  if (obj === null) return new Response("Not found", { status: 404 });
  const headers = dataHeaders(obj, url);
  const { offset = 0, length = obj.size - offset } = obj.range || {};
  const contentRange = `bytes ${offset}-${offset + length - 1}/${obj.size}`;
  const body = await obj.arrayBuffer();
  headers.set("content-length", String(body.byteLength));

  const stored = new Headers(headers);
  stored.set("x-content-range", contentRange);
  stored.set("cache-control", "public, max-age=86400");
  ctx.waitUntil(cache.put(cacheKey, new Response(body, { status: 200, headers: stored })));

  headers.set("content-range", contentRange);
  headers.set("x-cache", "MISS");
  return new Response(body, { status: 206, headers });
}

async function dataIndex(env) {
  const files = [];
  let cursor;
  do {
    const page = await env.DATA.list({ prefix: "parquet/", cursor });
    for (const o of page.objects) {
      files.push({ ruta: `/data/${o.key}`, version: o.etag, bytes: o.size, subido: o.uploaded });
    }
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);
  return json({ ficheros: files }, 200, { "cache-control": "no-cache" });
}

// ---------------------------------------------------------------------- API

// Edge cache in front of the API. POST bodies are hashed into the cache key so
// repeated searches (the common demo path) never touch D1.
async function cachedApi(request, env, ctx, url, path) {
  if (request.method === "OPTIONS") return new Response(null, { headers: cors() });
  if (request.method !== "GET" && request.method !== "POST") {
    throw new HttpError(405, "Metodo no permitido");
  }
  const body = request.method === "POST" ? await request.text() : "";
  const keyUrl = new URL(url);
  keyUrl.searchParams.set("__md", wantsMarkdown(request, url) ? "1" : "0");
  if (body) keyUrl.searchParams.set("__body", await sha256(body));
  const key = new Request(keyUrl.toString(), { method: "GET" });
  const cache = caches.default;

  const hit = await cache.match(key);
  if (hit) {
    const res = new Response(hit.body, hit);
    res.headers.set("x-cache", "HIT");
    return res;
  }
  const res = await api(request, env, url, path, body);
  if (res.status === 200) {
    const ttl = path.endsWith("/salud") ? 300 : CACHE_TTL;
    res.headers.set("cache-control", `public, max-age=${ttl}`);
    ctx.waitUntil(cache.put(key, res.clone()));
  }
  res.headers.set("x-cache", "MISS");
  return res;
}

async function api(request, env, url, rawPath, rawBody) {
  const path = rawPath.replace(/\/+$/, "");
  const m = (re) => path.match(re);
  const body = () => (request.method === "POST" ? parseBody(rawBody) : null);
  let match;
  let data;
  let kind;

  if (path === "/v1" || path === "") {
    data = indice();
    kind = "indice";
  } else if (path === "/salud" || path === "/v1/salud") {
    data = await salud(env);
    kind = "salud";
  } else if (path === "/v1/empresas" || path === "/v1/organos") {
    const b = body() ?? Object.fromEntries(url.searchParams);
    data = await buscarEntidad(env, path.endsWith("empresas") ? "empresa" : "organo", b);
    kind = "entidades";
  } else if (path === "/v1/catalogos") {
    data = { catalogos: CATALOGOS };
    kind = "json";
  } else if (path === "/v1/buscar") {
    data = await buscar(env, body() ?? queryToBody(url));
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

async function meta(env) {
  const { results } = await env.DB.prepare(
    "SELECT clave, valor FROM meta WHERE clave IN ('ultima_sync', 'stats')",
  ).all();
  return Object.fromEntries(results.map((r) => [r.clave, r.valor]));
}

async function salud(env) {
  // Aggregates are precomputed after each load (worker/derived.sql).
  const m = await meta(env);
  return { estado: "ok", ultima_sync: m.ultima_sync ?? null, ...(parseJson(m.stats ?? "{}") || {}) };
}

// label|code → code, per catalog; cached for the isolate's lifetime.
let codeCache = null;
async function codesFor(env, tipo, values) {
  if (!codeCache || Date.now() - codeCache.at > CACHE_TTL * 1000) {
    const { results } = await env.DB.prepare(
      "SELECT tipo, valor, codigo FROM catalogo WHERE codigo IS NOT NULL",
    ).all();
    const map = {};
    for (const r of results) {
      const t = (map[r.tipo] ||= new Map());
      t.set(r.valor.toLowerCase(), r.codigo);
      t.set(String(r.codigo).toLowerCase(), r.codigo);
    }
    codeCache = { at: Date.now(), map };
  }
  const t = codeCache.map[tipo] || new Map();
  return [...new Set(values.map((v) => t.get(String(v).trim().toLowerCase())).filter(Boolean))];
}

// Name (or NIF/UUID) → SQL condition on an indexed key column, resolved
// inside D1 through the FTS-indexed organo and empresa tables (one bound parameter). Keys
// never travel to JavaScript.
function entityFilter(tipo, q) {
  const v = String(q).trim();
  if (tipo === "empresa") {
    if (NIF_RE.test(v)) return [ADJUDICADAS("SELECT empresa_key FROM empresa WHERE nif = ?"), v.toUpperCase()];
    return [
      ADJUDICADAS(`SELECT e.empresa_key FROM empresa_fts f JOIN empresa e ON e.empresa_key = f.rowid
        WHERE empresa_fts MATCH ? ORDER BY e.contratos DESC LIMIT 100`),
      ftsQuery(v),
    ];
  }
  if (UUID_RE.test(v)) return ["l.organo_key IN (SELECT organo_key FROM organo WHERE id = ?)", v.toLowerCase()];
  return [
    `l.organo_key IN (SELECT o.organo_key FROM organo_fts f JOIN organo o ON o.organo_key = f.rowid
      WHERE organo_fts MATCH ? ORDER BY o.licitaciones DESC LIMIT 100)`,
    ftsQuery(v),
  ];
}

async function buscar(env, body) {
  const f = body.filtros || {};
  const where = [];
  const params = [];
  const add = (sql, ...vals) => {
    where.push(sql);
    params.push(...vals);
  };

  // Filters use licitacion's own columns (see pageSql).
  let from = "licitacion l";
  const q = typeof body.q === "string" ? body.q.trim() : "";
  if (q) {
    from = "licitacion_fts JOIN licitacion l ON l.rid = licitacion_fts.rowid";
    add("licitacion_fts MATCH ?", ftsQuery(q));
  }
  for (const [name, condition] of Object.entries(CODE_FILTERS)) {
    if (!Array.isArray(f[name]) || !f[name].length) continue;
    const codes = await codesFor(env, name, f[name]);
    if (codes.length === 0) add("0");
    else add(condition(codes.map(() => "?").join(", "), codes.length), ...codes);
  }
  if (f.cpv_prefijo) {
    const p = String(f.cpv_prefijo).replace(/[^0-9]/g, "");
    add("l.cpv_key IN (SELECT cpv_key FROM cpv WHERE codigo >= ? AND codigo < ?)", p, `${p}~`);
  }
  if (f.importe_min != null) add("l.presupuesto_sin_iva >= ?", Number(f.importe_min));
  if (f.importe_max != null) add("l.presupuesto_sin_iva <= ?", Number(f.importe_max));
  if (f.fecha_publicacion_desde) add("l.fecha_publicacion >= ?", String(f.fecha_publicacion_desde));
  if (f.fecha_publicacion_hasta) add("l.fecha_publicacion < date(?, '+1 day')", String(f.fecha_publicacion_hasta));
  // Broad filters: the unary + keeps SQLite on the newest-first rowid scan
  // instead of an index lookup followed by a sort.
  if (f.ccaa) {
    const like = `%${f.ccaa}%`;
    add(
      "+l.lugar_key IN (SELECT lugar_key FROM lugar WHERE nombre LIKE ? OR nombre_placsp LIKE ? OR comunidad LIKE ?)",
      like,
      like,
      like,
    );
  }
  if (f.adjudicatario) add(...entityFilter("empresa", f.adjudicatario));
  if (f.organo_id) add(...entityFilter("organo", String(f.organo_id)));
  else if (f.organo) add(...entityFilter("organo", f.organo));
  if (f.financiacion_ue === true) add("l.financiacion_codigo = 'EU'");
  if (f.financiacion_ue === false) add("coalesce(l.financiacion_codigo, '') <> 'EU'");

  // rid is chronological, so "newest first" is a reverse rowid scan (no sort);
  // with text, the FTS index yields its rowids (= rid) in order.
  const porImporte = body.ordenar === "importe";
  const [sortKey, desc] = porImporte
    ? ["l.presupuesto_sin_iva", true]
    : body.ordenar === "relevancia" && q
      ? ["licitacion_fts.rank", false]
      : [q ? "licitacion_fts.rowid" : "l.rid", true];
  const limit = clampLimit(body.limit ?? body.limite);
  const offset = decodeCursor(body.cursor);
  const whereSql = where.length ? `WHERE ${where.join(" AND ")}` : "";
  const page = (fromSql) =>
    env.DB.prepare(pageSql(fromSql, whereSql, sortKey, desc)).bind(...params, limit + 1, offset);

  let total;
  let exact = true;
  let rows;
  if (!where.length) {
    const [r, m] = await Promise.all([page(from).all(), meta(env)]);
    rows = r;
    total = parseJson(m.stats ?? "{}")?.total_licitaciones ?? 0;
  } else {
    const count = env.DB.prepare(`SELECT count(*) AS n FROM (SELECT 1 FROM ${from} ${whereSql} LIMIT ?)`).bind(
      ...params,
      COUNT_CAP + 1,
    );
    let n;
    if (porImporte && !q) {
      // The count decides how to sort (IMPORTE_SCAN_MIN).
      n = (await count.first()).n;
      rows = await page(n > IMPORTE_SCAN_MIN ? "licitacion l INDEXED BY idx_lic_importe" : from).all();
    } else {
      const [r, c] = await env.DB.batch([page(from), count]);
      rows = r;
      n = c.results[0].n;
    }
    total = Math.min(n, COUNT_CAP);
    exact = n <= COUNT_CAP;
  }
  return {
    total,
    total_exacto: exact,
    resultados: rows.results.slice(0, limit).map(resumen),
    cursor_siguiente: rows.results.length > limit ? encodeCursor(offset + limit) : null,
  };
}

async function licitacion(env, id) {
  const col = UUID_RE.test(id) ? "id" : "expediente";
  const row = await env.DB.prepare(`SELECT * FROM licitacion_api WHERE ${col} = ? ORDER BY rid DESC LIMIT 1`)
    .bind(col === "id" ? id.toLowerCase() : id)
    .first();
  if (!row) throw new HttpError(404, "Licitacion no encontrada");
  // Status timeline from cambio_estado, oldest first.
  const historial = await env.DB.prepare(
    `SELECT coalesce(e.descripcion, c.estado_key) AS estado, c.momento AS fecha
     FROM cambio_estado c LEFT JOIN estado e ON e.estado_key = c.estado_key
     WHERE c.licitacion_key = (SELECT licitacion_key FROM licitacion WHERE id = ?)
     ORDER BY c.momento`,
  )
    .bind(row.id)
    .all();
  for (const k of KEY_COLS) delete row[k];
  row.historial_estados = historial.results;
  row.tiene_documentos = Boolean(row.tiene_documentos);
  return row;
}

// Company profiles count every award (per lot, per winner) from the
// adjudicacion table; contracting-party profiles count their expedientes.
async function perfil(env, col, value, url) {
  const limit = clampLimit(url.searchParams.get("limit"));
  const offset = decodeCursor(url.searchParams.get("cursor"));
  const empresa = col === "adjudicatario_nif";
  const key = empresa ? value.toUpperCase() : value.toLowerCase();
  // Every query below reads licitacion's own columns and keys; names come
  // from the small tables only for the top rows.
  const scope = empresa
    ? ADJUDICADAS("SELECT empresa_key FROM empresa WHERE nif = ?")
    : "l.organo_key IN (SELECT organo_key FROM organo WHERE id = ?)";
  const stats = empresa
    ? env.DB.prepare(
        `SELECT e.nombre, count(*) AS contratos,
                sum(coalesce(a.importe_sin_iva, a.presupuesto_sin_iva)) AS importe_total,
                avg(coalesce(a.importe_sin_iva, a.presupuesto_sin_iva)) AS importe_medio,
                avg(CASE WHEN a.presupuesto_sin_iva > 0 AND a.importe_sin_iva IS NOT NULL
                    THEN 100.0 * (a.presupuesto_sin_iva - a.importe_sin_iva) / a.presupuesto_sin_iva END) AS baja_media_pct
         FROM empresa e JOIN adjudicacion a ON a.empresa_key = e.empresa_key
         WHERE e.nif = ? GROUP BY e.empresa_key ORDER BY contratos DESC LIMIT 1`,
      )
    : env.DB.prepare(
        `SELECT (SELECT nombre FROM organo WHERE id = ?1) AS nombre, count(*) AS contratos,
                sum(coalesce(l.importe_adjudicado_sin_iva, l.presupuesto_sin_iva)) AS importe_total,
                avg(coalesce(l.importe_adjudicado_sin_iva, l.presupuesto_sin_iva)) AS importe_medio,
                avg(CASE WHEN l.presupuesto_sin_iva > 0 AND l.importe_adjudicado_sin_iva IS NOT NULL
                    THEN 100.0 * (l.presupuesto_sin_iva - l.importe_adjudicado_sin_iva) / l.presupuesto_sin_iva END) AS baja_media_pct
         FROM licitacion l WHERE l.organo_key IN (SELECT organo_key FROM organo WHERE id = ?1)`,
      );
  // Most frequent CPVs and counterparts: group by key, then name the top 5.
  const otros = empresa
    ? `SELECT o.nombre, x.n FROM (
         SELECT l.organo_key AS k, count(*) AS n FROM licitacion l WHERE ${scope}
         GROUP BY l.organo_key ORDER BY n DESC LIMIT 6) x
       JOIN organo o ON o.organo_key = x.k ORDER BY x.n DESC LIMIT 5`
    : `SELECT e.nombre, x.n FROM (
         SELECT l.adjudicatario_key AS k, count(*) AS n FROM licitacion l WHERE ${scope}
         GROUP BY l.adjudicatario_key ORDER BY n DESC LIMIT 7) x
       JOIN empresa e ON e.empresa_key = x.k ORDER BY x.n DESC LIMIT 5`;
  const [statsRes, cpvs, otrosRes, rows] = await env.DB.batch([
    stats.bind(key),
    env.DB.prepare(
      `SELECT c.codigo AS cpv, c.descripcion, x.n FROM (
         SELECT l.cpv_key AS k, count(*) AS n FROM licitacion l WHERE ${scope}
         GROUP BY l.cpv_key ORDER BY n DESC LIMIT 6) x
       JOIN cpv c ON c.cpv_key = x.k ORDER BY x.n DESC LIMIT 5`,
    ).bind(key),
    env.DB.prepare(otros).bind(key),
    env.DB.prepare(pageSql("licitacion l", `WHERE ${scope}`, "l.rid", true)).bind(
      key,
      limit + 1,
      offset,
    ),
  ]);
  const s = statsRes.results[0];
  if (!s || !s.contratos) throw new HttpError(404, "Sin licitaciones");
  return {
    id: key,
    nombre: s.nombre,
    ...(empresa ? { registro: await registro(env, key) } : {}),
    stats: {
      contratos: s.contratos,
      importe_total: round2(s.importe_total),
      importe_medio: round2(s.importe_medio),
      baja_media_pct: round2(s.baja_media_pct),
      cpv_frecuentes: cpvs.results,
      [empresa ? "organos_frecuentes" : "adjudicatarios_frecuentes"]: otrosRes.results,
    },
    licitaciones: rows.results.slice(0, limit).map(resumen),
    cursor_siguiente: rows.results.length > limit ? encodeCursor(offset + limit) : null,
  };
}

// The company's entry in the Mercantile Registry (BORME), when one of its
// names in PLACSP matches a single registered company; null otherwise.
async function registro(env, nif) {
  const sociedad = `(SELECT r.sociedad_key FROM empresa e JOIN empresa_registro r ON r.empresa_key = e.empresa_key
    WHERE e.nif = ?1 ORDER BY e.contratos DESC LIMIT 1)`;
  const [soc, cargos] = await env.DB.batch([
    env.DB.prepare(
      `SELECT nombre AS sociedad, hoja, forma_juridica, provincia, fecha_constitucion, estado,
              capital, domicilio, fecha_extincion, fecha_ultima_publicacion AS ultima_publicacion
       FROM sociedad WHERE sociedad_key = ${sociedad}`,
    ).bind(nif),
    env.DB.prepare(
      `SELECT persona AS nombre, cargo_tipo AS cargo, desde, es_persona_juridica = 1 AS persona_juridica
       FROM cargo_vigente WHERE sociedad_key = ${sociedad}
       ORDER BY cargo_tipo, desde DESC LIMIT 25`,
    ).bind(nif),
  ]);
  const r = soc.results[0];
  if (!r) return null;
  return {
    ...r,
    fuente: "BORME",
    cargos_vigentes: cargos.results.map((c) => ({ ...c, persona_juridica: Boolean(c.persona_juridica) })),
  };
}

async function buscarEntidad(env, tipo, body) {
  const q = typeof body.q === "string" ? body.q.trim() : "";
  if (q.length < 2) throw new HttpError(422, "q debe tener al menos 2 caracteres");
  const limit = clampLimit(body.limite ?? body.limit);
  if (tipo === "empresa") {
    // Companies without a NIF cannot be profiled (the NIF is their public id).
    const sql = NIF_RE.test(q)
      ? "SELECT nif AS id, nombre, contratos FROM empresa WHERE nif = ? ORDER BY contratos DESC LIMIT ?"
      : `SELECT e.nif AS id, e.nombre, e.contratos FROM empresa_fts f JOIN empresa e ON e.empresa_key = f.rowid
         WHERE empresa_fts MATCH ? AND e.nif IS NOT NULL ORDER BY e.contratos DESC LIMIT ?`;
    const { results } = await env.DB.prepare(sql)
      .bind(NIF_RE.test(q) ? q.toUpperCase() : ftsQuery(q), limit)
      .all();
    return results;
  }
  const sql = NIF_RE.test(q)
    ? "SELECT id, nombre, nif, licitaciones FROM organo WHERE nif = ? ORDER BY licitaciones DESC LIMIT ?"
    : `SELECT o.id, o.nombre, o.nif, o.licitaciones FROM organo_fts f JOIN organo o ON o.organo_key = f.rowid
       WHERE organo_fts MATCH ? ORDER BY o.licitaciones DESC LIMIT ?`;
  const { results } = await env.DB.prepare(sql)
    .bind(NIF_RE.test(q) ? q.toUpperCase() : ftsQuery(q), limit)
    .all();
  return results;
}

async function similares(env, id) {
  const base = await env.DB.prepare(
    "SELECT cpv_principal, presupuesto_sin_iva FROM licitacion_api WHERE id = ?",
  )
    .bind(id.toLowerCase())
    .first();
  if (!base) throw new HttpError(404, "Licitacion no encontrada");
  if (!base.cpv_principal) return { total: 0, total_exacto: true, resultados: [], cursor_siguiente: null };
  const amount = base.presupuesto_sin_iva || 0;
  const prefix = base.cpv_principal.slice(0, 5);
  // The newest 200 candidates of the same CPV class, the 10 closest in price,
  // and only those 10 resolved through licitacion_api.
  const { results } = await env.DB.prepare(
    `SELECT ${RESUMEN_SELECT} FROM (
       SELECT rid FROM (
         SELECT l.rid, l.presupuesto_sin_iva AS p FROM licitacion l
         WHERE l.cpv_key IN (SELECT cpv_key FROM cpv WHERE codigo >= ?1 AND codigo < ?2)
           AND l.id <> ?3 AND (?4 = 0 OR l.presupuesto_sin_iva BETWEEN ?4 * 0.5 AND ?4 * 2)
         ORDER BY l.rid DESC LIMIT 200)
       ORDER BY abs(coalesce(p, 0) - ?4) LIMIT 10) x
     JOIN licitacion_api l ON l.rid = x.rid`,
  )
    .bind(prefix, `${prefix}~`, id.toLowerCase(), amount)
    .all();
  const top = results
    .sort((a, b) => Math.abs((a.presupuesto_sin_iva || 0) - amount) - Math.abs((b.presupuesto_sin_iva || 0) - amount))
    .slice(0, 10)
    .map(resumen);
  return { total: top.length, total_exacto: true, resultados: top, cursor_siguiente: null };
}

async function catalogo(env, tipo) {
  if (!CATALOGOS.includes(tipo)) {
    throw new HttpError(404, `Catalogo desconocido. Validos: ${CATALOGOS.join(", ")}`);
  }
  const cols = tipo === "cpv" ? "valor, descripcion, n" : "valor, codigo, n";
  const { results } = await env.DB.prepare(
    `SELECT ${cols} FROM catalogo WHERE tipo = ? ORDER BY n DESC LIMIT 1000`,
  )
    .bind(tipo)
    .all();
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

function parseBody(text) {
  try {
    return JSON.parse(text || "{}") || {};
  } catch {
    throw new HttpError(400, "JSON invalido");
  }
}

async function sha256(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
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
    "access-control-expose-headers": "x-cache",
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

function registroMd(r) {
  if (!r) return "";
  const cargos = r.cargos_vigentes.map((c) => `| ${cell(c.cargo)} | ${cell(c.nombre)} | ${day(c.desde)} |`);
  return [
    "",
    "## Registro Mercantil (BORME)",
    "",
    `- **Sociedad:** ${cell(r.sociedad)} · hoja ${cell(r.hoja)} (${cell(r.provincia)})`,
    `- **Constitución:** ${day(r.fecha_constitucion)} · **Situación:** ${cell(r.estado)} · **Capital:** ${money(r.capital)}`,
    "",
    ...(cargos.length ? ["| Cargo | Nombre | Desde |", "|---|---|---|", ...cargos, ""] : []),
  ].join("\n");
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
      return `# ${cell(d.nombre)}\n\n- **Contratos:** ${d.stats.contratos}\n- **Importe total:** ${money(d.stats.importe_total)}\n- **Baja media:** ${d.stats.baja_media_pct == null ? DASH : `${d.stats.baja_media_pct}%`}\n${registroMd(d.registro)}\n## Licitaciones\n\n${table(d.licitaciones)}\n`;
    case "catalogo":
      return `# Catálogo: ${d.tipo}\n\n| Valor | N |\n|---|---|\n${d.valores.map((v) => `| ${cell(v.valor)} | ${v.n} |`).join("\n")}\n`;
    case "entidades":
      return `| Nombre | ID | N |\n|---|---|---|\n${d.map((e) => `| ${cell(e.nombre)} | ${e.id} | ${e.contratos ?? e.licitaciones} |`).join("\n")}\n`;
    default:
      return "```json\n" + JSON.stringify(d, null, 2) + "\n```\n";
  }
}
