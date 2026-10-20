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
PLACSP ──► GitHub Actions: Postgres efímero + parser (src/etl), esquema fiel a CODICE
             ├─ etl.yml (cron diario): ventana de 730 días, estado pg_dump en R2
             └─ historico.yml (una vez): años archivados 2017+, en paralelo
                    │ export.raw: tablas del parser → Parquet con claves naturales
                    ▼
           parquet/raw/  (export.compact: un único histórico deduplicado)
                    │ export.modelo: warehouse/ (SQLMesh sobre DuckDB)
                    ▼
           parquet/modelo/  modelo dimensional: hechos + dimensiones + agregados
                    ├─► licit.es/explorar (DuckDB-WASM)
                    └─► D1 (export.d1, por diferencias) ──► api.licit.es

Worker "licit" (worker/): api.licit.es (API + Swagger), licit.es (site/ + /data)
```

- **Capas.** `schema/` (Postgres) es el staging del parser, fiel a CODICE.
  `export.raw` lo publica como Parquet con claves naturales (`entry_id`, número
  de lote, ordinales de parseo), porque cada Postgres efímero genera uuids
  distintos. `export.compact` funde la ventana diaria con los años archivados:
  cada expediente conserva su versión más reciente con sus hijos y la unión de
  todos los estados observados.
- **Modelo dimensional.** `warehouse/` es un proyecto SQLMesh que sigue a Kimball.
  Las entidades son dimensiones (`licitacion`, `lote`, `organo`, `empresa`,
  `cpv`, `lugar`, `documento`, `criterio_adjudicacion`…) y los procesos son
  hechos con las claves de todas ellas (`ciclo_licitacion`, snapshot
  acumulativo de la tramitación; `presupuesto_lote`; `adjudicacion`;
  `cambio_estado`; `modificacion`; `anuncio`), más agregados. La matriz de bus y
  las convenciones están en [warehouse/README.md](warehouse/README.md). Los
  audits (grano, claves, integridad referencial) bloquean la publicación.
- **Ids estables.** Claves sustitutas deterministas (md5 de la clave de negocio)
  e ids públicos `md5('licitacion:' || entry_id)` y `md5('organo:' || …)`, así
  que cada reconstrucción genera los mismos ids.
- **D1.** `worker/schema.sql` es la parte de la estrella que usa la API (la fila
  de `licitacion` va unida a su `ciclo_licitacion`), más la vista
  `licitacion_api` con las columnas planas de siempre. `export.d1` compara
  el modelo de hoy con el último cargado (`state/modelo-d1/` en R2) y solo envía
  upserts y borrados; sin modelo previo hace una carga completa en orden
  cronológico, de modo que "más recientes primero" es un recorrido inverso por
  rowid. `export.derived` precalcula catálogos y estadísticas. El Worker cachea
  respuestas 1 h en el edge y corre junto a D1 (smart placement).
- **Coste.** D1 dentro de lo incluido en Workers Paid; `scripts/d1-load.sh` falla
  si la base supera `D1_MAX_BYTES` (4,5 GB) para no generar coste de almacenamiento.

### Puesta en marcha

1. Secrets: `CLOUDFLARE_API_TOKEN` (Workers + D1 edit), `CLOUDFLARE_ACCOUNT_ID`,
   `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`. Variable opcional `D1_DATABASE`
   (por defecto `licit-api`).
2. Ventana reciente: *Actions → ETL*, modo `semilla`, años `2025 2026`.
3. Histórico: *Actions → Historico* (por defecto 2017–2024). Su último job funde
   los años, construye el modelo y lo carga en R2 y D1.
4. El cron diario mantiene todo al día. El Worker se despliega con `site.yml`.

### Migración al modelo dimensional

El esquema de D1 no es compatible con el anterior (tabla plana), y el histórico
raw no existe todavía. Una vez:

1. Crear una base D1 nueva y vacía (`wrangler d1 create licit-modelo`), poner su
   id en `wrangler.jsonc` y la variable de repositorio `D1_DATABASE=licit-modelo`.
2. Lanzar *ETL* en modo `semilla` (o esperar al cron): genera `parquet/raw/` de la
   ventana, el modelo y, al no haber `state/modelo-d1/`, una carga completa.
3. Lanzar *Historico* con todos los años: añade 2017–2024 al histórico raw y D1
   recibe la diferencia.
4. Desplegar el Worker (`site.yml`) y, cuando todo responda, borrar en R2 los
   prefijos antiguos `parquet/todo/`, `parquet/reciente/` y `parquet/historico/`,
   y la base D1 anterior.

## Desarrollo local

```bash
cp .env.example .env
uv sync
docker compose -f docker-compose.dev.yml up -d
PYTHONPATH=src uv run pytest tests/
```

Modelo a partir de un Postgres local con datos (`DATABASE_URL`):

```bash
PYTHONPATH=src uv run python -m export.raw out/raw
PYTHONPATH=src uv run python -m export.compact out/todo out/raw
PYTHONPATH=src uv run python -m export.modelo out/modelo out/todo
uv run sqlmesh -p warehouse test
```
