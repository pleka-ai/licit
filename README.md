# licit

Landing: [licit.es](https://licit.es)

API + ETL para explorar datos de licitaciones de la [Plataforma de Contratación del Sector Público](https://contrataciondelestado.es), cruzadas con el Registro Mercantil que publica el [BORME](https://www.boe.es/diario_borme/).

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
                    │
BORME (BOE) ──► borme.yml (cron diario, años 2009+ a demanda): XML en cache/borme/,
                    │ borme.raw → parquet/raw/borme/<año>/
                    │ export.modelo: warehouse/ (SQLMesh sobre DuckDB)
                    ▼
           parquet/modelo/  modelo de datos: entidades, actividad y resúmenes
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
- **BORME.** `src/borme/` descarga de la API de datos abiertos del BOE el sumario
  de cada día y el XML de la sección A de cada provincia (`borme.download`, con
  caché por año en R2), separa cada anuncio en actos y cargos (`borme.parser`) y
  los escribe en Parquet por año (`borme.raw`). Los años publicados no cambian:
  reprocesar no vuelve a pedir nada al BOE.
- **Modelo de datos.** `warehouse/` es un proyecto SQLMesh con tablas de
  entidades (`licitacion`, `lote`, `organo`, `empresa`, `cpv`, `lugar`,
  `documento`, `criterio_adjudicacion`…), tablas de actividad que llevan las
  claves de todas ellas (`ciclo_licitacion` con los hitos de la tramitación,
  `presupuesto_lote`, `adjudicacion`, `cambio_estado`, `modificacion`,
  `anuncio`), el Registro Mercantil (`sociedad`, `persona`, `acto_registral`,
  `cargo_registral`; `empresa.sociedad_key` enlaza cada adjudicataria con su
  sociedad) y resúmenes. Tablas y convenciones en
  [warehouse/README.md](warehouse/README.md). Los
  audits (grano, claves, integridad referencial) bloquean la publicación.
- **Ids estables.** Claves sustitutas deterministas (md5 de la clave de negocio)
  e ids públicos `md5('licitacion:' || entry_id)` y `md5('organo:' || …)`, así
  que cada reconstrucción genera los mismos ids.
- **D1.** `worker/schema.sql` son las tablas del modelo que usa la API (la fila
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
   `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`. Variables: `D1_DATABASE` (base
   D1, también en `wrangler.jsonc`) y, opcional, `R2_BUCKET` (por defecto
   `s3://licit-data`; otra ruta sirve para ensayar sin tocar los datos reales).
2. Histórico: *Actions → Historico*, modo `todo` (por defecto 2017–2024), y
   *Actions → BORME* con los años `2009 … 2026`.
3. Ventana reciente: *Actions → ETL*, modo `semilla`, años `2025 2026`.
4. El cron diario mantiene todo al día. El Worker se despliega con `site.yml`.

### Etapas y reintentos

Cada etapa deja su resultado en R2, así que un fallo se reintenta desde ahí sin
repetir lo anterior:

| Etapa | Resultado en R2 | Reintento |
|---|---|---|
| Ingesta de un año archivado | `parquet/raw/historico/<año>/` (+ `version.txt`) | *Historico*, modo `ingestar` |
| Ingesta diaria (Postgres) | `parquet/raw/reciente/`, `state/licit.dump` | *ETL*, modo `diario` |
| Histórico raw y modelo | `parquet/raw/todo/`, `parquet/modelo/` | *ETL* `publicar` o *Historico* `consolidar` |
| Carga en D1 | D1 + `state/modelo-d1/` (solo tras cargar bien) | igual que la anterior |
| BORME de un año | `cache/borme/<año>.tar.zst`, `parquet/raw/borme/<año>/` | *BORME* con ese año |

- **Años ya ingeridos.** `scripts/version-parser.sh` es un hash del parser, los
  modelos, el esquema y el export raw. Un año publicado con la misma versión no
  se vuelve a ingerir (salvo con `forzar`); solo hace falta reingerir cuando
  cambia el parser.
- **Archivos de PLACSP.** Los zips anuales se guardan en `cache/placsp/` y se
  descargan de PLACSP una sola vez (`feed_reader --zip-dir`).
- **Ensayo.** `scripts/ensayo-pipeline.sh` ejecuta los mismos scripts que los
  workflows (`modelo.sh`, `d1-sql.sh`, `d1-load.sh`) sobre los fixtures: parser,
  raw, modelo, carga completa y por diferencias en un D1 local y la API en
  `wrangler dev`. Corre en cada PR, junto con `actionlint`.

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
