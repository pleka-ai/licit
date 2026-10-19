# licit

Landing: [licit.es](https://licit.es)

API + ETL para explorar datos de licitaciones de la [Plataforma de Contratación del Sector Público](https://contrataciondelestado.es).

Optimizada para consumo por agentes de IA: búsqueda unificada, respuestas densas, códigos CODICE resueltos a etiquetas legibles. Todo corre en Cloudflare y GitHub Actions sin coste recurrente.

## Acceso

- API: [api.licit.es](https://api.licit.es/docs) · OpenAPI: `https://api.licit.es/openapi.json`
- Web: [licit.es](https://licit.es) · Explorador SQL: [licit.es/explorar](https://licit.es/explorar)
- Datos abiertos (Parquet): [licit.es/data/index.json](https://licit.es/data/index.json)

Sin autenticación. Histórico desde 2017. Respuestas en JSON, o Markdown con
`Accept: text/markdown`.

```bash
curl -X POST https://api.licit.es/v1/buscar \
  -H 'Content-Type: application/json' \
  -d '{"q": "desarrollo software", "filtros": {"tipo_contrato": ["Servicios"]}, "limit": 5}'
```

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/v1/buscar` | Texto libre + filtros + cursor |
| GET | `/v1/licitacion/{id}` | Ficha de una licitación (id o expediente) |
| POST | `/v1/empresas` | Buscar empresas adjudicatarias |
| GET | `/v1/empresa/{nif}` | Perfil de empresa |
| POST | `/v1/organos` | Buscar órganos de contratación |
| GET | `/v1/organo/{id}` | Perfil de órgano |
| GET | `/v1/similares/{id}` | Mismo CPV e importe parecido |
| GET | `/v1/catalogos`, `/v1/catalogos/{tipo}` | Valores válidos para filtros |
| GET | `/salud` | Estado, totales y última sincronización |

## Arquitectura (sin coste recurrente)

```
PLACSP ──► GitHub Actions (Postgres efímero + ETL Python de src/etl)
             ├─ etl.yml (cron diario): ventana de 730 días, estado pg_dump en R2
             └─ historico.yml (una vez): años archivados 2017+, en paralelo
                    │
                    ├─► D1 (SQLite + FTS5): todas las licitaciones ──► api.licit.es
                    └─► Parquet en R2 ──► licit.es/explorar (DuckDB-WASM)

Worker "licit" (worker/): api.licit.es (API + Swagger), licit.es (site/ + /data)
```

- **Ids estables**: los ids públicos se derivan de claves naturales de la PLACSP
  (`md5(entry_id)` para licitaciones, `md5(platform_id|dir3|nombre)` para
  órganos), así que el ETL diario y cada año histórico generan los mismos ids.
- **Upserts sin orden**: una versión antigua nunca pisa a una nueva; se conserva
  la primera `fecha_publicacion` y se fusiona `historial_estados`.
- **Coste**: D1 dentro de lo incluido en Workers Paid; `scripts/d1-load.sh` falla
  si la base supera `D1_MAX_BYTES` (4,5 GB) para no generar coste de almacenamiento.

### Puesta en marcha

1. Secrets: `CLOUDFLARE_API_TOKEN` (Workers + D1 edit), `CLOUDFLARE_ACCOUNT_ID`,
   `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.
2. Ventana reciente: *Actions → ETL*, modo `semilla`, años `2025 2026`.
3. Histórico: *Actions → Historico* (por defecto 2017–2024).
4. El cron diario mantiene todo al día. El Worker se despliega con `site.yml`.

## Desarrollo local

```bash
cp .env.example .env
uv sync
PYTHONPATH=src uv run pytest tests/
PYTHONPATH=src uv run uvicorn api.main:app --reload
```
