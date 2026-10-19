# licit

Landing: [licit.es](https://licit.es)

API + ETL para explorar datos de licitaciones de la [Plataforma de Contratación del Sector Público](https://contrataciondelestado.es).

Optimizada para consumo por agentes de IA: búsqueda unificada, respuestas densas, códigos CODICE resueltos a etiquetas legibles. Todo corre en el free tier de Cloudflare y GitHub Actions.

## Acceso

- Web: [licit.es](https://licit.es) · Explorador SQL: [licit.es/explorar](https://licit.es/explorar)
- API: `https://licit.es/api/v1` · Docs: [licit.es/docs](https://licit.es/docs)
- Datos abiertos (Parquet): [licit.es/data/index.json](https://licit.es/data/index.json)

Sin autenticación. Respuestas en JSON, o Markdown con `Accept: text/markdown`.

```bash
curl -X POST https://licit.es/api/v1/buscar \
  -H 'Content-Type: application/json' \
  -d '{"q": "desarrollo software", "filtros": {"tipo_contrato": ["Servicios"]}, "limit": 5}'
```

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/buscar` | Texto libre + filtros + cursor |
| GET | `/licitacion/{id}` | Ficha de una licitación |
| GET | `/empresa/{nif}` | Perfil de empresa adjudicataria |
| GET | `/organo/{id}` | Perfil de órgano de contratación |
| GET | `/similares/{id}` | Mismo CPV e importe parecido |
| GET | `/catalogos/{tipo}` | Valores válidos para filtros |
| GET | `/salud` | Estado y última sincronización |

## Arquitectura (coste 0 €)

```
PLACSP feeds ──► GitHub Actions (cron diario, Postgres efímero, ETL Python)
                   │  estado: pg_dump de la ventana reciente ──► R2 state/
                   ├─► Parquet básico ──► R2 parquet/{reciente,historico/<año>}/
                   └─► filas básicas (últimos 12 meses) ──► D1 (SQLite + FTS5)

Cloudflare Worker "licit" (licit.es)
  /            landing estática (site/)
  /explorar    DuckDB-WASM en el navegador sobre los Parquet
  /api/v1/*    API sobre D1 (worker/index.js)
  /data/*      Parquet desde R2 con soporte de rangos
```

- **ETL** (`.github/workflows/etl.yml`): reutiliza los parsers y repositorios de
  `src/etl` contra un Postgres de servicio. Postgres solo guarda una ventana de
  `ETL_WINDOW_DAYS` (730) para que el volcado quepa en el free tier de R2.
- **D1** recibe como mucho `D1_MAX_ROWS_PER_RUN` (9000) licitaciones por día
  (límite gratuito: 100k filas escritas/día), las más recientes primero.
- **Histórico**: cada año antiguo se archiva una vez como Parquet congelado.

### Puesta en marcha

1. Secrets del repo: `CLOUDFLARE_API_TOKEN` (Workers + D1 edit),
   `CLOUDFLARE_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.
2. Ventana reciente: *Actions → ETL → Run workflow*, modo `semilla`,
   años `2025 2026`.
3. Histórico (opcional, un año por ejecución): modo `historico`, año `2019`.
4. A partir de ahí el cron `diario` mantiene todo al día.

El Worker se despliega con `.github/workflows/site.yml` (o `npx wrangler deploy`).

## Desarrollo local

```bash
cp .env.example .env
uv sync
PYTHONPATH=src uv run pytest tests/
PYTHONPATH=src uv run uvicorn api.main:app --reload
```
