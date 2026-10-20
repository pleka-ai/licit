# Warehouse

Modelo dimensional de licit, construido con SQLMesh sobre DuckDB a partir de
la capa raw (las tablas del parser exportadas por `export.raw` y fusionadas en
un histórico por `export.compact`). Sigue el método de Kimball (*The Data
Warehouse Toolkit*): procesos de negocio, grano declarado, dimensiones
conformadas y hechos. Los nombres no llevan prefijos `dim_`/`fact_`: el papel
de cada tabla está en su descripción y en esta página.

```
raw (CODICE, claves naturales)  →  stage (tipado, limpio)  →  modelo (dimensiones + hechos)  →  agregado
```

```bash
RAW_PATH=out/raw WAREHOUSE_DB=/tmp/w.duckdb uv run sqlmesh -p warehouse plan --auto-apply
uv run sqlmesh -p warehouse test
PYTHONPATH=src uv run python -m export.modelo out/modelo out/raw   # construir y publicar Parquet
```

## Entidades y hechos

Las **dimensiones** son las entidades por las que alguien pregunta a una API de
licitaciones: la licitación y sus lotes, quién contrata y quién gana, qué se
compra y dónde, y los documentos y condiciones de cada licitación.

| Dimensión | Una fila por |
|---|---|
| `licitacion` | licitación (expediente): título, enlaces, estado actual, tipo, procedimiento, tramitación, financiación, duración y condiciones del pliego |
| `lote` | lote; las licitaciones sin lotes tienen un lote "0" (objeto único) |
| `organo` | órgano de contratación, con su jerarquía administrativa |
| `empresa` | adjudicataria (por NIF) |
| `cpv` | código CPV, con división, grupo, clase y categoría |
| `lugar` | territorio NUTS, con país, comunidad y provincia |
| `documento` | pliego, anexo o anuncio publicado |
| `criterio_adjudicacion`, `requisito`, `garantia`, `condicion_ejecucion`, `clasificacion_exigida`, `lugar_ejecucion` | término del pliego de una licitación o lote |
| `estado`, `resultado`, `calendario` | estado del ciclo, resultado de adjudicación, día |

Los **hechos** son los procesos que se miden. Cada uno lleva las claves de
todas las dimensiones que le aplican, aunque sean deducibles de la licitación:
la redundancia es a propósito, para que cada hecho se consulte sin rodeos.

| Hecho | Grano | licitacion | lote | organo | empresa | cpv | lugar | estado | resultado | fechas |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `ciclo_licitacion` | licitación (snapshot acumulativo) | ● | | ● | ● principal | ● principal | ● | ● actual | ● principal | 13 hitos |
| `presupuesto_lote` | lote | ● | ● | ● | | ● | ● | ● | | publicación, límite |
| `adjudicacion` | resultado × adjudicatario | ● | ● | ● | ● | ● | ● | | ● | adjudicación, formalización, inicio |
| `cambio_estado` | estado observado | ● | | ● | | ● | ● | ● | | momento |
| `modificacion` | modificación de contrato | ● | | ● | | ● | ● | | | publicación |
| `anuncio` | anuncio × medio | ● | | ● | | ● | ● | | | anuncio, publicación |

`cpv_licitacion` es la tabla puente entre `licitacion` y `cpv` (todos los CPV de
la licitación y de sus lotes, con `es_principal` y `peso`).

## Convenciones

- **Claves sustitutas deterministas.** `<dimension>_key` es un BIGINT derivado
  de md5 del espacio de nombres y la clave de negocio (macro `@clave`). La misma
  clave de negocio da siempre la misma clave, así que el ETL diario, la carga
  de D1 por diferencias y el explorador coinciden sin tabla de mapeo.
- **Ninguna clave foránea nula.** Cada dimensión tiene miembros reservados:
  `0` = desconocido y `-1` = no aplica (p. ej. `empresa -1` = "Sin adjudicatario"
  en resultados desiertos). Lo comprueba el audit `clave_existe`.
- **Fechas.** `calendario` está indexado por la propia fecha (clave inteligente,
  como recomienda Kimball para el tiempo) y la usan todos los roles de fecha. En
  el snapshot acumulativo, un hito nulo significa que aún no se ha alcanzado.
- **Ids públicos estables.** `licitacion.id = md5('licitacion:' || entry_id)` y
  `organo.id = md5('organo:' || referencia)`, las mismas fórmulas que usaba la
  API, así que los enlaces existentes siguen funcionando.
- **SCD tipo 1.** `organo` y `empresa` guardan los atributos de su aparición
  más reciente; el histórico de cambios de estado vive en `cambio_estado`.
- **Dimensiones aplanadas.** Los códigos CODICE se resuelven a etiquetas dentro
  de cada dimensión (p. ej. `licitacion.tipo_contrato_codigo` y
  `licitacion.tipo_contrato`), sin tablas de códigos aparte.
- **Medidas aditivas.** En `adjudicacion`, si un resultado tiene varios
  adjudicatarios, importes y presupuesto se reparten con `peso`. En
  `cpv_licitacion`, `peso` reparte 1 entre los CPV del expediente.
- **Claves compartidas.** Las claves de cada licitación (`organo_key`,
  `cpv_key`, `lugar_key`, `fecha_publicacion`…) se resuelven una sola vez en
  `stage.expediente_claves` y todos los hechos las copian. Los roles
  (`adjudicatario_key` → `empresa`) se validan con el audit `rol_existe`.

## Notas de la fuente

- `fecha_publicacion` es la fecha del primer anuncio publicado o, si es anterior,
  la primera vez que se observó el expediente.
- Solo ~14 % de los resultados traen `award_date`; `fecha_adjudicacion` hereda
  ese hueco de PLACSP.
- Los hitos por estado (`fecha_en_plazo`, `fecha_evaluacion`…) dependen de que
  el ETL haya visto esa versión del expediente.
