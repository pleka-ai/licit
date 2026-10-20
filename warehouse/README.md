# Warehouse

Modelo de datos de licit, construido con SQLMesh sobre DuckDB a partir de dos
capas raw: las licitaciones (las tablas del parser de PLACSP exportadas por
`export.raw` y fusionadas en un histórico por `export.compact`) y el Registro
Mercantil (`borme.raw`: la sección A del BORME desde 2009, un directorio por
año).

```
raw (CODICE, claves naturales)  →  stage (tipado, limpio)  →  modelo  →  resumen
```

```bash
RAW_PATH=out/raw BORME_PATH=out/borme WAREHOUSE_DB=/tmp/w.duckdb uv run sqlmesh -p warehouse plan --auto-apply
uv run sqlmesh -p warehouse test
PYTHONPATH=src uv run python -m export.modelo out/modelo out/raw out/borme   # construir y publicar Parquet
```

## Tablas

`models/entidades/`: aquello por lo que se pregunta. Una fila por cosa.

| Tabla | Una fila por |
|---|---|
| `licitacion` | licitación (expediente): título, enlaces, estado actual, tipo, procedimiento, tramitación, financiación, duración y condiciones del pliego |
| `lote` | lote; las licitaciones sin lotes tienen un lote "0" (objeto único) |
| `organo` | órgano de contratación, con su jerarquía administrativa |
| `empresa` | adjudicataria (por NIF) |
| `cpv` | código CPV, con división, grupo, clase y categoría |
| `lugar` | territorio NUTS, con país, comunidad y provincia |
| `documento` | pliego, anexo o anuncio publicado |
| `criterio_adjudicacion`, `requisito`, `garantia`, `condicion_ejecucion`, `clasificacion_exigida`, `lugar_ejecucion` | término del pliego de una licitación o lote |
| `cpv_licitacion` | CPV de una licitación o de sus lotes (`es_principal`, `peso`) |
| `sociedad` | sociedad del Registro Mercantil (BORME), por hoja registral: nombre actual, forma jurídica, constitución, capital, domicilio, objeto social y situación |
| `persona` | persona física o jurídica con cargos en el BORME, por nombre normalizado (enlazada con su `sociedad` si es una) |
| `estado`, `resultado`, `calendario` | estado del ciclo, resultado de adjudicación, día |

`models/actividad/`: lo que pasa con ellas, con importes, recuentos y fechas.
Cada tabla lleva las claves de todo lo que le aplica, aunque se pudieran
deducir de la licitación, para consultarla sin rodeos.

| Tabla | Una fila por | licitacion | lote | organo | empresa | cpv | lugar | estado | resultado | fechas |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `ciclo_licitacion` | licitación | ● | | ● | ● principal | ● principal | ● | ● actual | ● principal | 13 hitos |
| `presupuesto_lote` | lote | ● | ● | ● | | ● | ● | ● | | publicación, límite |
| `adjudicacion` | resultado × adjudicatario | ● | ● | ● | ● | ● | ● | | ● | adjudicación, formalización, inicio |
| `cambio_estado` | estado observado | ● | | ● | | ● | ● | ● | | momento |
| `modificacion` | modificación de contrato | ● | | ● | | ● | ● | | | publicación |
| `anuncio` | anuncio × medio | ● | | ● | | ● | ● | | | anuncio, publicación |
| `acto_registral` | acto inscrito en el BORME | | | | | | | | | publicación, inscripción |
| `cargo_registral` | movimiento de un cargo en el BORME | | | | | | | | | publicación |

`acto_registral` y `cargo_registral` llevan `sociedad_key` (y el segundo
`persona_key`); `empresa.sociedad_key` une el Registro Mercantil con las
licitaciones.

`models/resumenes/`: tablas pequeñas precalculadas para el explorador, entre
ellas `cargo_vigente` (último movimiento de cada persona en cada cargo cuando es
un nombramiento) y `adjudicataria_registro` (cada adjudicataria con su sociedad,
cargos en vigor y días entre su constitución y su primera adjudicación).

## Convenciones

- **Claves deterministas.** `<tabla>_key` es un BIGINT derivado de md5 del
  nombre de la tabla y la clave de negocio (macro `@clave`). La misma clave de
  negocio da siempre la misma clave, así que el ETL diario, la carga de D1 por
  diferencias y el explorador coinciden sin tabla de mapeo.
- **Ninguna clave nula.** Las tablas referenciadas tienen filas `0` =
  desconocido y `-1` = no aplica (p. ej. `empresa -1` = "Sin adjudicatario" en
  resultados desiertos). Lo comprueban los audits `clave_existe` y `rol_existe`.
- **Fechas.** `calendario` se cruza por la propia fecha. En `ciclo_licitacion`,
  un hito nulo significa que aún no se ha alcanzado.
- **Ids públicos estables.** `licitacion.id = md5('licitacion:' || entry_id)` y
  `organo.id = md5('organo:' || referencia)`, las mismas fórmulas que usaba la
  API, así que los enlaces existentes siguen funcionando.
- **Versión vigente.** `licitacion`, `organo` y `empresa` guardan los datos de
  su publicación más reciente; el histórico de estados está en `cambio_estado`.
- **Etiquetas dentro.** Los códigos CODICE se resuelven a etiquetas en la propia
  tabla (p. ej. `licitacion.tipo_contrato_codigo` y `licitacion.tipo_contrato`).
- **Importes que suman.** En `adjudicacion`, si un resultado tiene varios
  adjudicatarios, importes y presupuesto se reparten con `peso`. En
  `cpv_licitacion`, `peso` reparte 1 entre los CPV de la licitación.
- **Claves compartidas.** Las claves de cada licitación (`organo_key`,
  `cpv_key`, `lugar_key`, `fecha_publicacion`…) se resuelven una sola vez en
  `stage.expediente_claves` y las copian todas las tablas de actividad.

## Notas de la fuente

### BORME

- El BORME no publica NIF ni DNI. Una sociedad se identifica por su hoja
  registral (registro provincial y número, p. ej. `M 374639`; por su nombre si
  falta, menos del 1 %), y una persona por su nombre normalizado: dos homónimos
  son la misma `persona`.
- `empresa.sociedad_key` se fija cuando alguno de los nombres de la adjudicataria
  en PLACSP, normalizado (mayúsculas, sin acentos ni puntuación, forma jurídica
  abreviada: «S.A.», «SA» y «SOCIEDAD ANONIMA» son `SA`), coincide con los de una
  sola sociedad. Las UTE no se inscriben y nunca se enlazan.
- Una sociedad que cambia de provincia abre hoja en otro registro y aparece como
  otra `sociedad`.
- Los cargos se publican con unas 270 etiquetas distintas («Adm. Unico»,
  «ADM.UNICO»…); `cargo_tipo` las agrupa.

### PLACSP

- `fecha_publicacion` es la fecha del primer anuncio publicado o, si es anterior,
  la primera vez que se observó el expediente.
- Solo ~14 % de los resultados traen `award_date`; `fecha_adjudicacion` hereda
  ese hueco de PLACSP.
- Los hitos por estado (`fecha_en_plazo`, `fecha_evaluacion`…) dependen de que
  el ETL haya visto esa versión del expediente.
