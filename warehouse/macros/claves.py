"""Surrogate keys for the dimensional model.

Keys are deterministic: the same business key always yields the same BIGINT,
so every daily rebuild, the D1 diff sync and the explorer agree on them
without a key-mapping table. Reserved members follow the Kimball convention
of never leaving a foreign key NULL.
"""

from __future__ import annotations

from sqlglot import exp
from sqlmesh import macro
from sqlmesh.core.macros import MacroEvaluator

DESCONOCIDO = 0
NO_APLICA = -1


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
            this=exp.func("md5_number_lower", joined), expression=exp.Literal.number(1)
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


MODALIDAD_COLUMNS = (
    "type_code",
    "sub_type_code",
    "procedure_code",
    "urgency_code",
    "contracting_system_code",
    "submission_method_code",
    "part_presentation_code",
    "over_threshold_indicator",
    "auction_constraint_indicator",
    "variant_constraint_indicator",
    "mix_contract_indicator",
    "national_legislation_code",
    "funding_program_code",
    "feed_type",
)


@macro()
def modalidad_key(
    evaluator: MacroEvaluator, alias: exp.Expression | None = None
) -> exp.Expression:
    """Key of the ``modalidad`` junk dimension from folder columns.

    Every column is part of the key (NULLs included), so the dimension and the
    facts compute it the same way from ``stage.contract_folder_status``.
    """
    table = alias.name if alias is not None else None
    parts = [
        exp.func(
            "coalesce",
            exp.cast(exp.column(c, table=table), "text"),
            exp.Literal.string("∅"),
        )
        for c in MODALIDAD_COLUMNS
    ]
    return clave(evaluator, exp.Literal.string("modalidad"), *parts)
