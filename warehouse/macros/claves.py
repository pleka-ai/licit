"""Surrogate keys for the dimensional model.

Keys are deterministic: the same business key always yields the same BIGINT,
so every daily rebuild, the D1 diff sync and the explorer agree on them
without a key-mapping table. They keep 52 bits so they survive a round trip
through JavaScript numbers (the Worker reads D1 rows as JS numbers); the
uniqueness audits on every dimension and fact catch the unlikely collision.
Reserved members follow the Kimball convention of never leaving a foreign key
NULL.
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
    """BIGINT surrogate key of ``namespace`` + business key ``parts``.

    Returns NULL when every part is NULL, so callers can coalesce to a
    reserved member.
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
    """Like ``@clave`` but falls back to the 'desconocido' member (0)."""
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
