// OpenAPI 3.1 description of the public licit API (served at /openapi.json).

const ref = (name) => ({ $ref: `#/components/schemas/${name}` });
const nullable = (type, extra = {}) => ({ type: [type, "null"], ...extra });
const jsonOrMd = (schema) => ({
  "application/json": { schema },
  "text/markdown": { schema: { type: "string" } },
});
const ok = (description, schema) => ({ description, content: jsonOrMd(schema) });
const errorResp = (description) => ({ description, content: { "application/json": { schema: ref("Error") } } });
const notFound = errorResp("No encontrado");
const badRequest = errorResp("Petición inválida (JSON, cursor o texto de búsqueda)");
const unprocessable = errorResp("Parámetros inválidos (q demasiado corto)");
const idParam = (name, description) => ({
  name,
  in: "path",
  required: true,
  description,
  schema: { type: "string" },
});
const pagination = [
  { name: "limit", in: "query", schema: { type: "integer", minimum: 1, maximum: 100, default: 20 } },
  { name: "cursor", in: "query", schema: { type: "string" }, description: "Valor de cursor_siguiente." },
];
const entitySearch = (title) => ({
  required: true,
  content: {
    "application/json": {
      schema: {
        type: "object",
        title,
        required: ["q"],
        properties: {
          q: { type: "string", minLength: 2, description: "Nombre (parcial) o NIF exacto." },
          limite: { type: "integer", minimum: 1, maximum: 100, default: 20 },
        },
      },
      example: { q: "Indra", limite: 5 },
    },
  },
});

export const OPENAPI = {
  openapi: "3.1.0",
  info: {
    title: "licit",
    version: "1.0.0",
    description:
      "API estructurada de licitaciones públicas de España, con datos de la " +
      "[Plataforma de Contratación del Sector Público](https://contrataciondelestado.es).\n\n" +
      "- Abierta y sin autenticación.\n" +
      "- Histórico desde 2017, actualizado a diario. También en Parquet y con SQL " +
      "en el navegador: [licit.es/explorar](https://licit.es/explorar).\n" +
      "- Todas las respuestas en JSON, o en Markdown con `Accept: text/markdown` " +
      "(o `?formato=md`), pensado para agentes de IA.",
    contact: { name: "licit", url: "https://licit.es" },
    license: { name: "Datos: PLACSP (reutilización de información del sector público)" },
  },
  servers: [{ url: "https://api.licit.es" }],
  externalDocs: { description: "Código fuente", url: "https://github.com/pleka-ai/licit" },
  tags: [
    { name: "Licitaciones" },
    { name: "Empresas" },
    { name: "Organos" },
    { name: "Similares" },
    { name: "Catalogos" },
    { name: "Salud" },
  ],
  paths: {
    "/v1/buscar": {
      post: {
        tags: ["Licitaciones"],
        summary: "Buscar licitaciones",
        description:
          "Texto libre (full-text en español, por prefijo) combinado con filtros " +
          "estructurados (AND). Paginación por cursor opaco.",
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: ref("PeticionBusqueda"),
              example: {
                q: "mantenimiento ascensores",
                filtros: { tipo_contrato: ["Servicios"], importe_min: 50000 },
                ordenar: "fecha",
                limit: 10,
              },
            },
          },
        },
        responses: { 200: ok("Resultados", ref("RespuestaBusqueda")), 400: badRequest },
      },
    },
    "/v1/licitacion/{licitacion_id}": {
      get: {
        tags: ["Licitaciones"],
        summary: "Detalle de licitación",
        parameters: [idParam("licitacion_id", "UUID interno o número de expediente.")],
        responses: { 200: ok("Licitación", ref("LicitacionDetalle")), 404: notFound },
      },
    },
    "/v1/empresas": {
      post: {
        tags: ["Empresas"],
        summary: "Buscar empresas adjudicatarias",
        requestBody: entitySearch("PeticionBusquedaEmpresas"),
        responses: { 200: ok("Empresas", { type: "array", items: ref("EmpresaResumen") }), 422: unprocessable },
      },
    },
    "/v1/empresa/{empresa_id}": {
      get: {
        tags: ["Empresas"],
        summary: "Perfil de empresa",
        parameters: [idParam("empresa_id", "NIF de la empresa."), ...pagination],
        responses: { 200: ok("Perfil", ref("Perfil")), 404: notFound },
      },
    },
    "/v1/organos": {
      post: {
        tags: ["Organos"],
        summary: "Buscar órganos de contratación",
        requestBody: entitySearch("PeticionBusquedaOrganos"),
        responses: { 200: ok("Órganos", { type: "array", items: ref("OrganoResumen") }), 422: unprocessable },
      },
    },
    "/v1/organo/{organo_id}": {
      get: {
        tags: ["Organos"],
        summary: "Perfil de órgano",
        parameters: [idParam("organo_id", "UUID del órgano."), ...pagination],
        responses: { 200: ok("Perfil", ref("Perfil")), 404: notFound },
      },
    },
    "/v1/similares/{licitacion_id}": {
      get: {
        tags: ["Similares"],
        summary: "Licitaciones similares",
        description: "Mismo CPV (5 dígitos) y presupuesto entre la mitad y el doble.",
        parameters: [idParam("licitacion_id", "UUID interno.")],
        responses: { 200: ok("Similares", ref("RespuestaBusqueda")), 404: notFound },
      },
    },
    "/v1/catalogos": {
      get: {
        tags: ["Catalogos"],
        summary: "Catálogos disponibles",
        responses: {
          200: {
            description: "Tipos",
            content: {
              "application/json": {
                schema: { type: "object", properties: { catalogos: { type: "array", items: { type: "string" } } } },
              },
            },
          },
        },
      },
    },
    "/v1/catalogos/{tipo}": {
      get: {
        tags: ["Catalogos"],
        summary: "Valores de un catálogo",
        parameters: [
          {
            name: "tipo",
            in: "path",
            required: true,
            schema: {
              type: "string",
              enum: ["tipo_contrato", "estado", "procedimiento", "tramitacion", "organo_tipo", "cpv"],
            },
          },
        ],
        responses: { 200: ok("Valores", ref("Catalogo")), 404: notFound },
      },
    },
    "/salud": {
      get: {
        tags: ["Salud"],
        summary: "Estado del servicio",
        responses: { 200: ok("Estado", ref("Salud")) },
      },
    },
  },
  components: {
    schemas: {
      Error: { type: "object", properties: { detail: { type: "string" } } },
      FiltrosBusqueda: {
        type: "object",
        description: "Todos opcionales, combinados con AND. Aceptan etiqueta legible o código CODICE.",
        properties: {
          tipo_contrato: { type: "array", items: { type: "string" }, examples: [["Servicios", "Suministros"]] },
          estado: { type: "array", items: { type: "string" }, examples: [["Adjudicada"]] },
          procedimiento: { type: "array", items: { type: "string" }, examples: [["Abierto"]] },
          cpv_prefijo: { type: "string", description: "Prefijo CPV: '72' IT, '45' construcción.", examples: ["722"] },
          importe_min: { type: "number", description: "Presupuesto sin IVA mínimo (EUR)." },
          importe_max: { type: "number", description: "Presupuesto sin IVA máximo (EUR)." },
          fecha_publicacion_desde: { type: "string", format: "date" },
          fecha_publicacion_hasta: { type: "string", format: "date" },
          ccaa: { type: "string", description: "Comunidad / provincia (parcial).", examples: ["Madrid"] },
          adjudicatario: { type: "string", description: "Nombre de la adjudicataria (parcial)." },
          organo: { type: "string", description: "Nombre del órgano (parcial)." },
          organo_id: { type: "string", description: "UUID del órgano (exacto)." },
          financiacion_ue: { type: "boolean" },
        },
      },
      PeticionBusqueda: {
        type: "object",
        properties: {
          q: nullable("string", { description: "Texto libre en título, órgano y adjudicatario." }),
          filtros: ref("FiltrosBusqueda"),
          ordenar: { type: "string", enum: ["fecha", "importe", "relevancia"], default: "fecha" },
          limit: { type: "integer", minimum: 1, maximum: 100, default: 20 },
          cursor: nullable("string"),
        },
      },
      LicitacionResumen: {
        type: "object",
        properties: {
          id: { type: "string", format: "uuid" },
          expediente: nullable("string"),
          titulo: nullable("string"),
          organo: nullable("string"),
          organo_id: nullable("string"),
          tipo_contrato: nullable("string"),
          estado: nullable("string"),
          presupuesto_sin_iva: nullable("number"),
          importe_adjudicacion: nullable("number"),
          fecha_publicacion: { type: "string", format: "date-time" },
          fecha_actualizacion: { type: "string", format: "date-time" },
          fecha_adjudicacion: nullable("string", { format: "date" }),
          fecha_limite: nullable("string", { format: "date" }),
          cpv_principal: nullable("string"),
          num_licitadores: nullable("integer"),
          adjudicatario: nullable("string"),
          adjudicatario_nif: nullable("string"),
          lugar: nullable("string"),
          tiene_documentos: { type: "boolean" },
          num_lotes: nullable("integer"),
          url_place: nullable("string", { format: "uri" }),
        },
      },
      RespuestaBusqueda: {
        type: "object",
        properties: {
          total: { type: "integer" },
          resultados: { type: "array", items: ref("LicitacionResumen") },
          cursor_siguiente: nullable("string"),
        },
      },
      LicitacionDetalle: {
        allOf: [
          ref("LicitacionResumen"),
          {
            type: "object",
            properties: {
              historial_estados: {
                type: "array",
                items: { type: "object", properties: { estado: { type: "string" }, fecha: { type: "string" } } },
              },
              procedimiento: nullable("string"),
              tramitacion: nullable("string"),
              sistema_contratacion: nullable("string"),
              presupuesto_con_iva: nullable("number"),
              valor_estimado: nullable("number"),
              hora_limite: nullable("string"),
              duracion: nullable("number"),
              duracion_unidad: nullable("string"),
              lugar_nuts: nullable("string"),
              lugar_subentidad: nullable("string"),
              programa_financiacion: nullable("string"),
              organo_nif: nullable("string"),
              organo_tipo: nullable("string"),
              cpv_principal_desc: nullable("string"),
              resultado: nullable("string"),
              fecha_formalizacion: nullable("string"),
            },
          },
        ],
      },
      EmpresaResumen: {
        type: "object",
        properties: { id: { type: "string" }, nombre: { type: "string" }, contratos: { type: "integer" } },
      },
      OrganoResumen: {
        type: "object",
        properties: {
          id: { type: "string", format: "uuid" },
          nombre: { type: "string" },
          nif: nullable("string"),
          licitaciones: { type: "integer" },
        },
      },
      Perfil: {
        type: "object",
        properties: {
          id: { type: "string" },
          nombre: { type: "string" },
          stats: {
            type: "object",
            properties: {
              contratos: { type: "integer" },
              importe_total: nullable("number"),
              importe_medio: nullable("number"),
              baja_media_pct: nullable("number"),
              cpv_frecuentes: { type: "array", items: { type: "object" } },
              organos_frecuentes: { type: "array", items: { type: "object" } },
              adjudicatarios_frecuentes: { type: "array", items: { type: "object" } },
            },
          },
          licitaciones: { type: "array", items: ref("LicitacionResumen") },
          cursor_siguiente: nullable("string"),
        },
      },
      Catalogo: {
        type: "object",
        properties: {
          tipo: { type: "string" },
          valores: {
            type: "array",
            items: { type: "object", properties: { valor: { type: "string" }, n: { type: "integer" } } },
          },
        },
      },
      Salud: {
        type: "object",
        properties: {
          estado: { type: "string" },
          ultima_sync: nullable("string"),
          total_licitaciones: { type: "integer" },
          total_organos: { type: "integer" },
          total_empresas: { type: "integer" },
          importe_total: { type: "number" },
          desde: nullable("string"),
          ultima_actualizacion: nullable("string"),
        },
      },
    },
  },
};
