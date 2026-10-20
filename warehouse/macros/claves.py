"""Keys of the warehouse tables.

Keys are deterministic: the same business key always yields the same BIGINT,
so every daily rebuild, the D1 diff sync and the explorer agree on them
without a key-mapping table. They keep 52 bits so they survive a round trip
through JavaScript numbers (the Worker reads D1 rows as JS numbers); the
uniqueness audits on every table catch the unlikely collision.
Keys 0 (unknown) and -1 (not applicable) are placeholder rows, so a key column
is never NULL.
"""

from __future__ import annotations

from sqlglot import exp
from sqlmesh import macro
from sqlmesh.core.macros import MacroEvaluator

DESCONOCIDO = 0
NO_APLICA = -1
# md5_number_lower is 64 bits; shifting by 12 leaves 52 (JS-safe integers).
KEY_SHIFT = 12


@macro()
def clave(
    evaluator: MacroEvaluator, namespace: exp.Expression, *parts: exp.Expression
) -> exp.Expression:
    """BIGINT key of ``namespace`` + business key ``parts``.

    Returns NULL when every part is NULL, so callers can coalesce to a
    placeholder row.
    """
    del evaluator
    joined = exp.func(
        "concat_ws",
        exp.Literal.string("|"),
        namespace,
        *[exp.cast(p, "text") for p in parts],
    )
    hashed = exp.cast(
        exp.BitwiseRightShift(
            this=exp.func("md5_number_lower", joined),
            expression=exp.Literal.number(KEY_SHIFT),
        ),
        "bigint",
    )
    any_part = exp.or_(
        *[exp.Not(this=exp.Is(this=p.copy(), expression=exp.Null())) for p in parts]
    )
    return exp.If(this=any_part, true=hashed, false=exp.Null())


@macro()
def clave_o(
    evaluator: MacroEvaluator, namespace: exp.Expression, *parts: exp.Expression
) -> exp.Expression:
    """Like ``@clave`` but falls back to the 'desconocido' row (0)."""
    return exp.func(
        "coalesce", clave(evaluator, namespace, *parts), exp.Literal.number(DESCONOCIDO)
    )


@macro()
def raw(evaluator: MacroEvaluator, table: exp.Expression) -> exp.Expression:
    """``read_parquet`` over one table of the compacted raw set."""
    base = str(evaluator.var("raw_path")).rstrip("/")
    name = table.name
    return exp.func("read_parquet", exp.Literal.string(f"{base}/{name}.parquet"))


@macro()
def borme(evaluator: MacroEvaluator, table: exp.Expression) -> exp.Expression:
    """``read_parquet`` over one BORME raw table, every year directory at once."""
    base = str(evaluator.var("borme_path")).rstrip("/")
    return exp.func(
        "read_parquet",
        exp.Literal.string(f"{base}/*/{table.name}.parquet"),
        exp.EQ(this=exp.column("union_by_name"), expression=exp.true()),
    )


# Legal forms, longest first, as they appear spelled out or abbreviated once
# punctuation is gone ("S.L.U." -> "S L U"). Both sides of a name match (PLACSP
# winners and BORME companies) reduce them to the same token.
_LEGAL_FORMS: tuple[tuple[str, str], ...] = (
    ("SOCIEDAD LIMITADA NUEVA EMPRESA", "SLNE"),
    ("SOCIEDAD LIMITADA PROFESIONAL", "SLP"),
    ("SOCIEDAD LIMITADA LABORAL", "SLL"),
    ("SOCIEDAD LIMITADA UNIPERSONAL", "SLU"),
    ("SOCIEDAD ANONIMA UNIPERSONAL", "SAU"),
    ("SOCIEDAD ANONIMA LABORAL", "SAL"),
    ("SOCIEDAD LIMITADA", "SL"),
    ("SOCIEDAD ANONIMA", "SA"),
    ("SOCIEDAD COOPERATIVA", "SCOOP"),
    ("S COOP", "SCOOP"),
    ("S L N E", "SLNE"),
    ("S L P", "SLP"),
    ("S L L", "SLL"),
    ("S L U", "SLU"),
    ("S A U", "SAU"),
    ("S A L", "SAL"),
    ("S L", "SL"),
    ("S A", "SA"),
    ("U T E", "UTE"),
)
LEGAL_FORM_TOKENS: tuple[str, ...] = (
    "SLNE",
    "SLP",
    "SLL",
    "SLU",
    "SAU",
    "SAL",
    "SL",
    "SA",
    "SCOOP",
)


@macro()
def nombre_normalizado(
    evaluator: MacroEvaluator, value: exp.Expression
) -> exp.Expression:
    """Comparison form of a company or person name.

    Uppercase, no accents, punctuation to spaces, legal forms to one token:
    'Indra Sistemas, S.A.' and 'INDRA SISTEMAS SOCIEDAD ANONIMA' both become
    'INDRA SISTEMAS SA'.
    """
    del evaluator

    # Padded with spaces so every form matches as whole words.
    def replace(text: exp.Expression, pattern: str, replacement: str) -> exp.Expression:
        return exp.RegexpReplace(
            this=text,
            expression=exp.Literal.string(pattern),
            replacement=exp.Literal.string(replacement),
            modifiers=exp.Literal.string("g"),
        )

    upper = exp.Upper(this=exp.func("strip_accents", exp.cast(value, "text")))
    text: exp.Expression = exp.func(
        "concat",
        exp.Literal.string(" "),
        replace(upper, "[^A-Z0-9]+", " "),
        exp.Literal.string(" "),
    )
    for long, short in _LEGAL_FORMS:
        text = replace(text, f" {long} ", f" {short} ")
    return exp.func("nullif", exp.func("trim", text), exp.Literal.string(""))


@macro()
def forma_juridica(
    evaluator: MacroEvaluator, normalized: exp.Expression
) -> exp.Expression:
    """Legal-form token at the end of a normalized name, NULL if none."""
    del evaluator
    pattern = r"(?:^| )(" + "|".join(LEGAL_FORM_TOKENS) + r")$"
    extract = exp.RegexpExtract(
        this=normalized,
        expression=exp.Literal.string(pattern),
        group=exp.Literal.number(1),
    )
    return exp.func("nullif", extract, exp.Literal.string(""))


@macro()
def fecha(evaluator: MacroEvaluator, value: exp.Expression) -> exp.Expression:
    """Cast to DATE, dropping implausible values (PLACSP has years like 0201)."""
    del evaluator
    as_date = exp.cast(value, "date")
    plausible = exp.Between(
        this=as_date.copy(),
        low=exp.cast(exp.Literal.string("1990-01-01"), "date"),
        high=exp.cast(exp.Literal.string("2100-12-31"), "date"),
    )
    return exp.If(this=plausible, true=as_date)


@macro()
def texto(evaluator: MacroEvaluator, value: exp.Expression) -> exp.Expression:
    """Trimmed text, NULL when empty."""
    del evaluator
    return exp.func(
        "nullif", exp.func("trim", exp.cast(value, "text")), exp.Literal.string("")
    )


@macro()
def etiqueta(
    evaluator: MacroEvaluator, code_list: exp.Expression, code: exp.Expression
) -> exp.Expression:
    """Description of ``code`` in a CODICE list, falling back to the code."""
    del evaluator
    lookup = (
        exp.select("description")
        .from_("stage.codice_code")
        .where(
            exp.and_(
                exp.EQ(this=exp.column("list"), expression=code_list),
                exp.EQ(this=exp.column("code"), expression=code.copy()),
            )
        )
        .limit(1)
    )
    return exp.func("coalesce", exp.Subquery(this=lookup), code)
