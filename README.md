# licit

Landing: [licit.es](https://licit.es)

API + ETL para explorar datos de licitaciones de la [Plataforma de Contratación del Sector Público](https://contrataciondelestado.es).

Optimizada para consumo por agentes de IA: búsqueda unificada, respuestas densas, códigos CODICE resueltos a etiquetas legibles.

## Acceso a la API

Base URL: `https://api.licit.es/api/v1`

Documentación interactiva: `https://api.licit.es/docs`

No requiere autenticación. Rate limit: 30 req/min por IP.

### Ejemplo: buscar licitaciones

```bash
curl -X POST https://api.licit.es/api/v1/buscar \
  -H 'Content-Type: application/json' \
  -d '{"q": "desarrollo software", "filtros": {"tipo_contrato": ["Servicios"]}, "limit": 5}'
```

### Ejemplo: detalle de una licitación

```bash
curl https://api.licit.es/api/v1/licitacion/<uuid>
```

### Ejemplo: valores válidos para filtros

```bash
curl https://api.licit.es/api/v1/catalogos/tipo_contrato
```

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/buscar` | Búsqueda unificada: texto libre + filtros + cursor |
| GET | `/licitacion/{id}` | Detalle completo (criterios, solvencia, lotes, docs) |
| GET | `/empresa/{nif}` | Perfil de empresa con stats agregadas |
| GET | `/organo/{id}` | Perfil de órgano con stats |
| GET | `/similares/{id}` | Licitaciones similares (CPV + importe) |
| GET | `/catalogos/{tipo}` | Valores válidos para filtros |

## Stack

- **API**: FastAPI + asyncpg + PostgreSQL 16
- **ETL**: Ingestión de feeds ATOM CODICE (hourly cron)
- **Búsqueda**: tsvector español + pg_trgm para fuzzy
- **Deploy**: Docker Compose + Caddy (auto-HTTPS) en Hetzner

## Landing

Página estática en `site/`, servida como Worker de assets estáticos en Cloudflare (`wrangler.jsonc`, Worker `licit`) y desplegada por `.github/workflows/pages.yml` en cada push a `main` que toque `site/`. Necesita los secrets `CLOUDFLARE_API_TOKEN` y `CLOUDFLARE_ACCOUNT_ID`.

```bash
npx wrangler deploy
```

## Deploy de la API

Manual (`workflow_dispatch` en `.github/workflows/deploy.yml`).


1. Crear A record DNS: `api.licit.es → <IP del servidor>`
2. Rellenar variables en `deploy/cloud-init.yml`
3. Crear servidor e insertar cloud-init
4. Tras boot, seed inicial:

```bash
ssh licit@<ip>
cd licit/deploy
docker compose exec etl-cron sh -c \
  "cd /app && PYTHONPATH=src uv run python -m etl.handlers.feed_reader --seed"
```

## Desarrollo local

```bash
cp .env.example .env
uv sync
PYTHONPATH=src uv run pytest tests/
PYTHONPATH=src uv run uvicorn api.main:app --reload
```
