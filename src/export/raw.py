"""Export the parser's Postgres tables to Parquet, re-keyed by natural keys.

Each ephemeral Postgres (the daily window, every archived year) assigns its own
random uuids, so the raw export replaces them with PLACSP natural keys:

* a folder is its ``entry_id``;
* a lot is ``(entry_id, lot_number)``;
* any other child is ``(entry_id, n)``, where ``n`` is the row's position in
  parse order (``ctid``), and references between children become those
  ordinals (``result_n``, ``notice_n``, ``publication_n``);
* a contracting party is ``organo_ref``, the identity the parser resolves
  (``platform_id``, else ``dir3``, else the name).

The tables keep the parser's (CODICE) names and columns: this is the
warehouse's source layer, not a presentation model. ``export.compact`` merges
several raw exports into one history and ``warehouse/`` builds the model.

Usage::

    PYTHONPATH=src uv run python -m export.raw <out_dir>
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from shared.config import Settings
from shared.logger import get_logger

logger = get_logger(__name__)

# Natural key of a contracting party; also seeds the public organo id.
ORGANO_REF = "coalesce(cp.platform_id, cp.dir3, cp.name)"

_ENTRY = "f.entry_id"
_FOLDER = "JOIN contract_folder_status f ON f.id = x.contract_folder_status_id"
_LOT = "LEFT JOIN procurement_project_lot l ON l.id = x.lot_id"


def _ordinal(table: str) -> str:
    """Parse-order position of a child row within its folder."""
    return (
        f"(SELECT id, row_number() OVER (PARTITION BY contract_folder_status_id"
        f" ORDER BY ctid) AS n FROM {table})"
    )


RAW_TABLES: dict[str, str] = {
    "contract_folder_status": f"""
        SELECT f.entry_id, f.title, f.summary, f.link, f.updated, f.feed_type,
               f.contract_folder_id, f.status_code, {ORGANO_REF} AS organo_ref,
               f.name, f.type_code, f.sub_type_code,
               f.estimated_overall_contract_amount, f.total_amount,
               f.tax_exclusive_amount, f.currency_id, f.nuts_code,
               f.country_subentity, f.duration_measure, f.duration_unit_code,
               f.planned_start_date, f.planned_end_date,
               f.option_validity_description, f.options_description,
               f.mix_contract_indicator, f.procedure_code, f.urgency_code,
               f.submission_method_code, f.submission_deadline_date,
               f.submission_deadline_time::text AS submission_deadline_time,
               f.submission_deadline_description,
               f.document_availability_end_date,
               f.document_availability_end_time::text
                 AS document_availability_end_time,
               f.contracting_system_code, f.part_presentation_code,
               f.auction_constraint_indicator, f.max_lot_presentation_quantity,
               f.max_tenderer_awarded_lots_qty, f.lots_combination_rights,
               f.over_threshold_indicator, f.participation_request_end_date,
               f.participation_request_end_time::text
                 AS participation_request_end_time,
               f.short_list_limitation_description, f.short_list_min_quantity,
               f.short_list_expected_quantity, f.short_list_max_quantity,
               f.required_curricula_indicator, f.procurement_legislation_id,
               f.variant_constraint_indicator, f.price_revision_formula,
               f.funding_program_code, f.funding_program_name,
               f.funding_program_description, f.received_appeal_quantity,
               f.tender_recipient_endpoint_id, f.allowed_subcontract_rate,
               f.allowed_subcontract_description, f.national_legislation_code,
               f.ted_uuid
        FROM contract_folder_status f
        LEFT JOIN contracting_party cp ON cp.id = f.contracting_party_id
    """,
    # One row per party, stamped with the newest folder that references it so
    # compaction can keep the most recent version.
    "contracting_party": f"""
        SELECT {ORGANO_REF} AS organo_ref, max(f.updated) AS updated,
               cp.name, cp.dir3, cp.nif, cp.platform_id, cp.website_uri,
               cp.contracting_party_type_code, cp.activity_code,
               cp.buyer_profile_uri, cp.contact_name, cp.contact_telephone,
               cp.contact_telefax, cp.contact_email, cp.city_name,
               cp.postal_zone, cp.address_line, cp.country_code,
               cp.agent_party_id, cp.agent_party_name,
               cp.parent_hierarchy::text AS parent_hierarchy
        FROM contracting_party cp
        JOIN contract_folder_status f ON f.contracting_party_id = cp.id
        GROUP BY cp.id
    """,
    "procurement_project_lot": f"""
        SELECT {_ENTRY}, x.lot_number, x.name, x.total_amount,
               x.tax_exclusive_amount, x.currency_id, x.nuts_code,
               x.country_subentity
        FROM procurement_project_lot x {_FOLDER}
    """,
    "cpv_classification": f"""
        SELECT {_ENTRY}, o.n, l.lot_number, x.item_classification_code
        FROM cpv_classification x {_FOLDER} {_LOT}
        JOIN {_ordinal("cpv_classification")} o ON o.id = x.id
    """,
    "realized_location": f"""
        SELECT {_ENTRY}, l.lot_number,
               row_number() OVER (PARTITION BY x.lot_id ORDER BY x.ctid) AS n,
               x.nuts_code, x.country_subentity, x.country_code, x.city_name,
               x.postal_zone, x.street_name
        FROM realized_location x
        JOIN procurement_project_lot l ON l.id = x.lot_id
        JOIN contract_folder_status f ON f.id = l.contract_folder_status_id
    """,
    "tender_result": f"""
        SELECT {_ENTRY}, o.n, l.lot_number, x.result_code, x.description,
               x.award_date, x.received_tender_quantity, x.lower_tender_amount,
               x.higher_tender_amount, x.sme_awarded_indicator,
               x.abnormally_low_tenders_indicator, x.start_date,
               x.smes_received_tender_quantity,
               x.eu_nationals_received_quantity, x.non_eu_nationals_received_qty,
               x.awarded_owner_nationality_code, x.subcontract_rate,
               x.subcontract_description, x.awarded_tax_exclusive_amount,
               x.awarded_payable_amount, x.awarded_currency_id,
               x.awarded_lot_number
        FROM tender_result x {_FOLDER} {_LOT}
        JOIN {_ordinal("tender_result")} o ON o.id = x.id
    """,
    "winning_party": f"""
        SELECT {_ENTRY}, r.n AS result_n,
               row_number() OVER (PARTITION BY x.tender_result_id
                                  ORDER BY x.ctid) AS n,
               x.identifier, x.identifier_scheme, x.name, x.nuts_code,
               x.city_name, x.postal_zone, x.country_code, x.company_type_code
        FROM winning_party x
        JOIN tender_result t ON t.id = x.tender_result_id
        JOIN {_ordinal("tender_result")} r ON r.id = t.id
        JOIN contract_folder_status f ON f.id = t.contract_folder_status_id
    """,
    "contract": f"""
        SELECT {_ENTRY}, r.n AS result_n, x.contract_number, x.issue_date
        FROM contract x
        JOIN tender_result t ON t.id = x.tender_result_id
        JOIN {_ordinal("tender_result")} r ON r.id = t.id
        JOIN contract_folder_status f ON f.id = t.contract_folder_status_id
    """,
    "awarding_criteria": f"""
        SELECT {_ENTRY}, o.n, l.lot_number, x.criteria_type_code,
               x.criteria_sub_type_code, x.description, x.weight_numeric, x.note
        FROM awarding_criteria x {_FOLDER} {_LOT}
        JOIN {_ordinal("awarding_criteria")} o ON o.id = x.id
    """,
    "financial_guarantee": f"""
        SELECT {_ENTRY}, o.n, x.guarantee_type_code, x.amount_rate,
               x.liability_amount, x.currency_id
        FROM financial_guarantee x {_FOLDER}
        JOIN {_ordinal("financial_guarantee")} o ON o.id = x.id
    """,
    "qualification_requirement": f"""
        SELECT {_ENTRY}, o.n, l.lot_number, x.origin_type,
               x.evaluation_criteria_type_code, x.description,
               x.threshold_quantity, x.personal_situation,
               x.operating_years_quantity, x.employee_quantity
        FROM qualification_requirement x {_FOLDER} {_LOT}
        JOIN {_ordinal("qualification_requirement")} o ON o.id = x.id
    """,
    "business_classification": f"""
        SELECT {_ENTRY}, o.n, x.code_value
        FROM business_classification x {_FOLDER}
        JOIN {_ordinal("business_classification")} o ON o.id = x.id
    """,
    "execution_condition": f"""
        SELECT {_ENTRY}, o.n, x.name, x.execution_requirement_code, x.description
        FROM execution_condition x {_FOLDER}
        JOIN {_ordinal("execution_condition")} o ON o.id = x.id
    """,
    "valid_notice_info": f"""
        SELECT {_ENTRY}, o.n, x.notice_type_code, x.notice_issue_date
        FROM valid_notice_info x {_FOLDER}
        JOIN {_ordinal("valid_notice_info")} o ON o.id = x.id
    """,
    "publication_status": f"""
        SELECT {_ENTRY}, v.n AS notice_n,
               row_number() OVER (PARTITION BY x.valid_notice_info_id
                                  ORDER BY x.ctid) AS n,
               x.publication_media_name
        FROM publication_status x
        JOIN valid_notice_info vi ON vi.id = x.valid_notice_info_id
        JOIN {_ordinal("valid_notice_info")} v ON v.id = vi.id
        JOIN contract_folder_status f ON f.id = vi.contract_folder_status_id
    """,
    "document_reference": f"""
        SELECT {_ENTRY}, o.n, v.n AS notice_n, p.n AS publication_n,
               x.source_type, x.filename, x.uri, x.document_hash,
               x.document_type_code
        FROM document_reference x {_FOLDER}
        JOIN {_ordinal("document_reference")} o ON o.id = x.id
        LEFT JOIN (
          SELECT id, valid_notice_info_id, row_number() OVER (
            PARTITION BY valid_notice_info_id ORDER BY ctid) AS n
          FROM publication_status) p ON p.id = x.publication_status_id
        LEFT JOIN {_ordinal("valid_notice_info")} v
          ON v.id = p.valid_notice_info_id
    """,
    "contract_modification": f"""
        SELECT {_ENTRY}, o.n, x.modification_number, x.contract_id, x.note,
               x.modification_duration_measure, x.modification_duration_unit_code,
               x.final_duration_measure, x.final_duration_unit_code,
               x.modification_tax_exclusive_amount, x.final_tax_exclusive_amount,
               x.currency_id
        FROM contract_modification x {_FOLDER}
        JOIN {_ordinal("contract_modification")} o ON o.id = x.id
    """,
    "status_change": f"""
        SELECT DISTINCT {_ENTRY}, x.status_code, x.updated
        FROM status_change x {_FOLDER}
    """,
}

# CODICE code lists, one table per list in Postgres (cat_*), one long table here.
CODE_LISTS: tuple[str, ...] = (
    "status_code",
    "type_code",
    "sub_type_code",
    "procedure_code",
    "urgency_code",
    "result_code",
    "contracting_system",
    "nuts",
    "cpv",
    "contracting_authority_type",
    "activity_code",
    "country_code",
    "awarding_criteria_type",
    "awarding_criteria_sub_type",
    "evaluation_criteria_type",
    "declaration_type",
    "funding_program",
    "national_legislation",
    "guarantee_type",
    "execution_requirement",
    "part_presentation",
    "submission_method",
    "notice_type",
    "document_type",
)

RAW_TABLES["codice_code"] = " UNION ALL ".join(
    f"SELECT '{name}' AS list, code, description FROM cat_{name}" for name in CODE_LISTS
)

_COPY_OPTS = "FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 250000"


def export(out_dir: Path, database_url: str) -> dict[str, object]:
    """Copy every raw table to ``out_dir`` and return the manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    con.execute("INSTALL postgres; LOAD postgres;")
    dsn = database_url.replace("'", "''")
    con.execute(f"ATTACH '{dsn}' AS pg (TYPE postgres, READ_ONLY)")

    tables: dict[str, dict[str, int | str]] = {}
    for name, sql in RAW_TABLES.items():
        path = out_dir / f"{name}.parquet"
        escaped = sql.replace("'", "''")
        con.execute(
            f"COPY (SELECT * FROM postgres_query('pg', '{escaped}')) "
            f"TO '{path}' ({_COPY_OPTS})"
        )
        row = con.execute(f"SELECT count(*) FROM '{path}'").fetchone()
        tables[name] = {
            "file": path.name,
            "rows": int(row[0]) if row else 0,
            "bytes": path.stat().st_size,
        }
        logger.info("Exported raw table=%s rows=%s", name, tables[name]["rows"])

    manifest: dict[str, object] = {
        "generado": datetime.now(UTC).isoformat(),
        "tablas": tables,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    return manifest


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    out_dir = Path(args[0] if args else "out/raw")
    export(out_dir, Settings().database_url)


if __name__ == "__main__":
    main()
