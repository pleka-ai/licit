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

## Matriz de bus

Filas: procesos (hechos). Columnas: dimensiones conformadas que comparten.

| Hecho | Grano | calendario | organo | empresa | cpv | lugar | modalidad | estado | otras |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `licitacion` | expediente (snapshot acumulativo) | ● (13 hitos) | ● | ● adjudicatario principal | ● principal | ● | ● | ● actual | `resultado` principal |
| `lote` | lote; un "objeto único" si no hay lotes | ● | ● | | ● | ● | ● | ● | |
| `adjudicacion` | resultado × adjudicatario | ● (adjudicación, formalización, inicio) | ● | ● | ● | ● | ● | | `resultado` |
| `cambio_estado` | expediente × estado observado | ● | ● | | | | | ● | |
| `modificacion` | modificación de contrato | ● | ● | | | | ● | | |
| `anuncio` | anuncio × medio de publicación | ● | ● | | | | | | `tipo_anuncio` |
| `documento` | documento | ● | ● | | | | | | `tipo_documento` |
| `criterio_adjudicacion` | criterio | ● | ● | | | | ● | | `tipo_criterio` |
| `requisito` | requisito de participación | ● | ● | | | | | | `tipo_requisito` |
| `garantia` | garantía | ● | ● | | | | | | `tipo_garantia` |
| `condicion_ejecucion` | condición especial | ● | ● | | | | | | `tipo_condicion` |
| `clasificacion_exigida` | clasificación exigida | ● | ● | | | | | | |
| `lugar_ejecucion` | lote × ubicación | | ● | | | ● | | | |
| `cpv_licitacion` | puente expediente × CPV | | | | ● | | | | |

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
- **Dimensiones basura.** `modalidad` agrupa los códigos y flags de bajo
  cardinal del procedimiento (tipo, subtipo, procedimiento, tramitación,
  sistema, presentación, regulación armonizada, financiación UE, plataforma),
  solo con las combinaciones observadas.
- **Medidas aditivas.** En `adjudicacion`, si un resultado tiene varios
  adjudicatarios, importes y presupuesto se reparten con `peso`. En
  `cpv_licitacion`, `peso` reparte 1 entre los CPV del expediente.
- **Cabecera/línea.** Los hechos hijos llevan `licitacion_key` (dimensión
  degenerada para cruzar con `licitacion`) y las dimensiones de la cabecera
  (`organo_key`, `fecha_publicacion`…), resueltas una sola vez en
  `stage.expediente_claves`.

## Notas de la fuente

- `fecha_publicacion` es la fecha del primer anuncio publicado o, si es anterior,
  la primera vez que se observó el expediente.
- Solo ~14 % de los resultados traen `award_date`; `fecha_adjudicacion` hereda
  ese hueco de PLACSP.
- Los hitos por estado (`fecha_en_plazo`, `fecha_evaluacion`…) dependen de que
  el ETL haya visto esa versión del expediente.
