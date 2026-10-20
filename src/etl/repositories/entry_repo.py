"""EntryRepository — persists a ParsedEntry in a single transaction."""

from __future__ import annotations

import json
import uuid

import asyncpg

from shared.logger import get_logger
from shared.models.contracting_party import ContractingPartyWrite
from shared.models.document_reference import DocumentReferenceWrite
from shared.models.etl import EntryResult
from shared.models.parsed_page import (
    LotGroup,
    NoticeGroup,
    ParsedEntry,
    ResultGroup,
)

logger = get_logger(__name__)

# Child tables deleted on folder re-upsert (document_reference excluded).
_CHILD_TABLES = (
    "contract_modification",
    "valid_notice_info",
    "tender_result",
    "awarding_criteria",
    "financial_guarantee",
    "qualification_requirement",
    "business_classification",
    "execution_condition",
    "cpv_classification",
    "procurement_project_lot",
)

# Columns for contract_folder_status INSERT/UPDATE (excluding id, created_at).
_CFS_COLS = (
    "entry_id",
    "contracting_party_id",
    "title",
    "summary",
    "link",
    "updated",
    "feed_type",
    "contract_folder_id",
    "status_code",
    "name",
    "type_code",
    "sub_type_code",
    "estimated_overall_contract_amount",
    "total_amount",
    "tax_exclusive_amount",
    "currency_id",
    "nuts_code",
    "country_subentity",
    "duration_measure",
    "duration_unit_code",
    "planned_start_date",
    "planned_end_date",
    "option_validity_description",
    "options_description",
    "mix_contract_indicator",
    "procedure_code",
    "urgency_code",
    "submission_method_code",
    "submission_deadline_date",
    "submission_deadline_time",
    "submission_deadline_description",
    "document_availability_end_date",
    "document_availability_end_time",
    "contracting_system_code",
    "part_presentation_code",
    "auction_constraint_indicator",
    "max_lot_presentation_quantity",
    "max_tenderer_awarded_lots_qty",
    "lots_combination_rights",
    "over_threshold_indicator",
    "participation_request_end_date",
    "participation_request_end_time",
    "short_list_limitation_description",
    "short_list_min_quantity",
    "short_list_expected_quantity",
    "short_list_max_quantity",
    "required_curricula_indicator",
    "procurement_legislation_id",
    "variant_constraint_indicator",
    "price_revision_formula",
    "funding_program_code",
    "funding_program_name",
    "funding_program_description",
    "received_appeal_quantity",
    "tender_recipient_endpoint_id",
    "allowed_subcontract_rate",
    "allowed_subcontract_description",
    "national_legislation_code",
    "ted_uuid",
)

# Columns updated on conflict (entry_id is the upsert key).
_CFS_UPDATE_COLS = [c for c in _CFS_COLS if c != "entry_id"]


def _build_cfs_sql() -> str:
    cols = ", ".join(_CFS_COLS)
    placeholders = ", ".join(f"${i}" for i in range(1, len(_CFS_COLS) + 1))
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in _CFS_UPDATE_COLS)
    return (
        f"INSERT INTO contract_folder_status ({cols})"
        f" VALUES ({placeholders})"
        f" ON CONFLICT (entry_id) DO UPDATE SET {sets}"
        " RETURNING id"
    )


_CFS_UPSERT_SQL = _build_cfs_sql()


class PgEntryRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def process_entry(self, entry: ParsedEntry) -> EntryResult:
        async with (
            self._pool.acquire() as conn,
            conn.transaction(),
        ):
            if await self._is_stale(conn, entry):
                logger.debug(
                    "Stale entry skipped: %s",
                    entry.envelope.entry_id,
                )
                return EntryResult(status="stale")

            try:
                party_id = await self._upsert_party(conn, entry.contracting_party)
            except (asyncpg.PostgresError, RuntimeError):
                logger.warning(
                    "Party resolution failed for entry=%s, persisting without party",
                    entry.envelope.entry_id,
                    exc_info=True,
                )
                party_id = None
            folder_id = await self._upsert_folder(conn, entry, party_id)

            # Detach docs from publication_statuses before cascade
            await conn.execute(
                "UPDATE document_reference"
                " SET publication_status_id = NULL"
                " WHERE contract_folder_status_id = $1"
                " AND publication_status_id IS NOT NULL",
                folder_id,
            )

            for table in _CHILD_TABLES:
                await conn.execute(
                    f"DELETE FROM {table} WHERE contract_folder_status_id = $1",
                    folder_id,
                )

            lot_id_map = await self._insert_lots(conn, folder_id, entry.lot_groups)
            await self._insert_results(conn, folder_id, lot_id_map, entry.result_groups)
            await self._insert_folder_children(conn, folder_id, entry)
            await self._insert_notices(conn, folder_id, entry.notice_groups)
            await self._upsert_documents(conn, folder_id, entry.direct_documents)

            await conn.execute(
                "INSERT INTO status_change"
                " (contract_folder_status_id,"
                " status_code, updated)"
                " VALUES ($1, $2, $3)",
                folder_id,
                entry.folder.status_code,
                entry.envelope.updated,
            )

            return EntryResult(status="ok")

    # ----------------------------------------------------------
    # Staleness check
    # ----------------------------------------------------------

    async def _is_stale(
        self,
        conn: asyncpg.Connection,
        entry: ParsedEntry,
    ) -> bool:
        row = await conn.fetchrow(
            "SELECT updated FROM contract_folder_status WHERE entry_id = $1",
            entry.envelope.entry_id,
        )
        if row is None:
            return False
        return bool(entry.envelope.updated <= row["updated"])

    # ----------------------------------------------------------
    # Folder upsert
    # ----------------------------------------------------------

    async def _upsert_folder(
        self,
        conn: asyncpg.Connection,
        entry: ParsedEntry,
        party_id: uuid.UUID | None,
    ) -> uuid.UUID:
        f = entry.folder
        row = await conn.fetchrow(
            _CFS_UPSERT_SQL,
            f.entry_id,
            party_id,
            f.title,
            f.summary,
            f.link,
            f.updated,
            f.feed_type,
            f.contract_folder_id,
            f.status_code,
            f.name,
            f.type_code,
            f.sub_type_code,
            f.estimated_overall_contract_amount,
            f.total_amount,
            f.tax_exclusive_amount,
            f.currency_id,
            f.nuts_code,
            f.country_subentity,
            f.duration_measure,
            f.duration_unit_code,
            f.planned_start_date,
            f.planned_end_date,
            f.option_validity_description,
            f.options_description,
            f.mix_contract_indicator,
            f.procedure_code,
            f.urgency_code,
            f.submission_method_code,
            f.submission_deadline_date,
            f.submission_deadline_time,
            f.submission_deadline_description,
            f.document_availability_end_date,
            f.document_availability_end_time,
            f.contracting_system_code,
            f.part_presentation_code,
            f.auction_constraint_indicator,
            f.max_lot_presentation_quantity,
            f.max_tenderer_awarded_lots_qty,
            f.lots_combination_rights,
            f.over_threshold_indicator,
            f.participation_request_end_date,
            f.participation_request_end_time,
            f.short_list_limitation_description,
            f.short_list_min_quantity,
            f.short_list_expected_quantity,
            f.short_list_max_quantity,
            f.required_curricula_indicator,
            f.procurement_legislation_id,
            f.variant_constraint_indicator,
            f.price_revision_formula,
            f.funding_program_code,
            f.funding_program_name,
            f.funding_program_description,
            f.received_appeal_quantity,
            f.tender_recipient_endpoint_id,
            f.allowed_subcontract_rate,
            f.allowed_subcontract_description,
            f.national_legislation_code,
            f.ted_uuid,
        )
        if row is None:
            # Concurrent upsert race: another transaction committed
            # the row between our conflict check and lock acquisition.
            row = await conn.fetchrow(
                "SELECT id FROM contract_folder_status WHERE entry_id = $1",
                f.entry_id,
            )
        if row is None:
            msg = "RETURNING clause returned no row"
            raise RuntimeError(msg)
        return uuid.UUID(str(row["id"]))

    # ----------------------------------------------------------
    # Contracting party identity resolution
    # ----------------------------------------------------------

    async def _upsert_party(
        self,
        conn: asyncpg.Connection,
        party: ContractingPartyWrite,
    ) -> uuid.UUID:
        for attempt in range(2):
            try:
                async with conn.transaction():
                    return await self._upsert_party_attempt(conn, party)
            except asyncpg.UniqueViolationError:
                if attempt == 0:
                    logger.debug(
                        "Party INSERT race, retrying party=%s",
                        party.platform_id or party.dir3 or party.name,
                    )
                    continue
                raise
        msg = "Unreachable"
        raise RuntimeError(msg)

    async def _upsert_party_attempt(
        self,
        conn: asyncpg.Connection,
        party: ContractingPartyWrite,
    ) -> uuid.UUID:
        # Step 1: platform_id lookup (the true unique key per PLACSP spec)
        pid_row = None
        if party.platform_id:
            pid_row = await conn.fetchrow(
                "SELECT id FROM contracting_party WHERE platform_id = $1",
                party.platform_id,
            )

        # Step 2: dir3 lookup
        dir3_row = None
        if party.dir3:
            dir3_row = await conn.fetchrow(
                "SELECT id FROM contracting_party WHERE dir3 = $1",
                party.dir3,
            )

        # Merge: both lookups hit different rows -> absorb dir3-row into pid-row
        existing = None
        is_merge = False
        if pid_row and dir3_row and pid_row["id"] != dir3_row["id"]:
            is_merge = True
            # guard_updated trigger rejects FK-only updates (no timestamp change),
            # so temporarily disable it for the merge reassignment.
            await conn.execute(
                "ALTER TABLE contract_folder_status DISABLE TRIGGER guard_updated"
            )
            await conn.execute(
                "UPDATE contract_folder_status"
                " SET contracting_party_id = $1"
                " WHERE contracting_party_id = $2",
                pid_row["id"],
                dir3_row["id"],
            )
            await conn.execute(
                "ALTER TABLE contract_folder_status ENABLE TRIGGER guard_updated"
            )
            await conn.execute(
                "DELETE FROM contracting_party WHERE id = $1",
                dir3_row["id"],
            )
            existing = pid_row
        elif pid_row:
            existing = pid_row
        elif dir3_row:
            existing = dir3_row

        # Step 3: name fallback (only bare records with no identifiers)
        if not existing:
            existing = await conn.fetchrow(
                "SELECT id FROM contracting_party"
                " WHERE name = $1"
                " AND dir3 IS NULL"
                " AND platform_id IS NULL",
                party.name,
            )

        hierarchy_json = (
            json.dumps(party.parent_hierarchy) if party.parent_hierarchy else None
        )

        if existing:
            # Merges: incoming entry is authoritative (has both identifiers).
            # Non-merge: prefer the longer (more complete) name variant.
            name_expr = (
                "$2"
                if is_merge
                else "CASE WHEN length($2) > length(name) THEN $2 ELSE name END"
            )
            await conn.execute(
                f"UPDATE contracting_party SET"
                f" name = {name_expr},"
                " dir3=$3, nif=$4,"
                " platform_id=$5, website_uri=$6,"
                " contracting_party_type_code=$7,"
                " activity_code=$8,"
                " buyer_profile_uri=$9,"
                " contact_name=$10,"
                " contact_telephone=$11,"
                " contact_telefax=$12,"
                " contact_email=$13,"
                " city_name=$14, postal_zone=$15,"
                " address_line=$16, country_code=$17,"
                " agent_party_id=$18,"
                " agent_party_name=$19,"
                " parent_hierarchy=$20"
                " WHERE id = $1",
                existing["id"],
                party.name,
                party.dir3,
                party.nif,
                party.platform_id,
                party.website_uri,
                party.contracting_party_type_code,
                party.activity_code,
                party.buyer_profile_uri,
                party.contact_name,
                party.contact_telephone,
                party.contact_telefax,
                party.contact_email,
                party.city_name,
                party.postal_zone,
                party.address_line,
                party.country_code,
                party.agent_party_id,
                party.agent_party_name,
                hierarchy_json,
            )
            return uuid.UUID(str(existing["id"]))

        row = await conn.fetchrow(
            "INSERT INTO contracting_party ("
            " name, dir3, nif, platform_id,"
            " website_uri,"
            " contracting_party_type_code,"
            " activity_code, buyer_profile_uri,"
            " contact_name, contact_telephone,"
            " contact_telefax, contact_email,"
            " city_name, postal_zone,"
            " address_line, country_code,"
            " agent_party_id, agent_party_name,"
            " parent_hierarchy"
            ") VALUES ("
            " $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,"
            " $11,$12,$13,$14,$15,$16,$17,$18,$19"
            ") RETURNING id",
            party.name,
            party.dir3,
            party.nif,
            party.platform_id,
            party.website_uri,
            party.contracting_party_type_code,
            party.activity_code,
            party.buyer_profile_uri,
            party.contact_name,
            party.contact_telephone,
            party.contact_telefax,
            party.contact_email,
            party.city_name,
            party.postal_zone,
            party.address_line,
            party.country_code,
            party.agent_party_id,
            party.agent_party_name,
            hierarchy_json,
        )
        if row is None:
            msg = "RETURNING clause returned no row"
            raise RuntimeError(msg)
        return uuid.UUID(str(row["id"]))

    # ----------------------------------------------------------
    # Child inserts
    # ----------------------------------------------------------

    async def _insert_lots(
        self,
        conn: asyncpg.Connection,
        folder_id: uuid.UUID,
        lot_groups: list[LotGroup],
    ) -> dict[str, uuid.UUID]:
        lot_id_map: dict[str, uuid.UUID] = {}

        for lg in lot_groups:
            lot = lg.lot
            row = await conn.fetchrow(
                "INSERT INTO procurement_project_lot"
                " (contract_folder_status_id, lot_number,"
                " name, total_amount,"
                " tax_exclusive_amount, currency_id,"
                " nuts_code, country_subentity)"
                " VALUES ($1,$2,$3,$4,$5,$6,$7,$8)"
                " RETURNING id",
                folder_id,
                lot.lot_number,
                lot.name,
                lot.total_amount,
                lot.tax_exclusive_amount,
                lot.currency_id,
                lot.nuts_code,
                lot.country_subentity,
            )
            lot_id = row["id"]
            lot_id_map[lot.lot_number] = lot_id

            for cpv in lg.cpv_codes:
                await conn.execute(
                    "INSERT INTO cpv_classification"
                    " (contract_folder_status_id,"
                    " lot_id,"
                    " item_classification_code)"
                    " VALUES ($1, $2, $3)",
                    folder_id,
                    lot_id,
                    cpv.item_classification_code,
                )
            for c in lg.criteria:
                await conn.execute(
                    "INSERT INTO awarding_criteria"
                    " (contract_folder_status_id,"
                    " lot_id,"
                    " criteria_type_code,"
                    " criteria_sub_type_code,"
                    " description,"
                    " weight_numeric, note)"
                    " VALUES ($1,$2,$3,$4,$5,$6,$7)",
                    folder_id,
                    lot_id,
                    c.criteria_type_code,
                    c.criteria_sub_type_code,
                    c.description,
                    c.weight_numeric,
                    c.note,
                )
            for r in lg.requirements:
                await conn.execute(
                    "INSERT INTO qualification_requirement"
                    " (contract_folder_status_id,"
                    " lot_id, origin_type,"
                    " evaluation_criteria_type_code,"
                    " description,"
                    " threshold_quantity,"
                    " personal_situation,"
                    " operating_years_quantity,"
                    " employee_quantity)"
                    " VALUES"
                    " ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
                    folder_id,
                    lot_id,
                    r.origin_type,
                    r.evaluation_criteria_type_code,
                    r.description,
                    r.threshold_quantity,
                    r.personal_situation,
                    r.operating_years_quantity,
                    r.employee_quantity,
                )
            for loc in lg.locations:
                await conn.execute(
                    "INSERT INTO realized_location"
                    " (lot_id, nuts_code,"
                    " country_subentity,"
                    " country_code, city_name,"
                    " postal_zone, street_name)"
                    " VALUES ($1,$2,$3,$4,$5,$6,$7)",
                    lot_id,
                    loc.nuts_code,
                    loc.country_subentity,
                    loc.country_code,
                    loc.city_name,
                    loc.postal_zone,
                    loc.street_name,
                )

        return lot_id_map

    async def _insert_results(
        self,
        conn: asyncpg.Connection,
        folder_id: uuid.UUID,
        lot_id_map: dict[str, uuid.UUID],
        result_groups: list[ResultGroup],
    ) -> None:
        for rg in result_groups:
            r = rg.result
            lot_id = (
                lot_id_map.get(r.awarded_lot_number) if r.awarded_lot_number else None
            )

            row = await conn.fetchrow(
                "INSERT INTO tender_result"
                " (contract_folder_status_id, lot_id,"
                " result_code, description,"
                " award_date,"
                " received_tender_quantity,"
                " lower_tender_amount,"
                " higher_tender_amount,"
                " sme_awarded_indicator,"
                " abnormally_low_tenders_indicator,"
                " start_date,"
                " smes_received_tender_quantity,"
                " eu_nationals_received_quantity,"
                " non_eu_nationals_received_qty,"
                " awarded_owner_nationality_code,"
                " subcontract_rate,"
                " subcontract_description,"
                " awarded_tax_exclusive_amount,"
                " awarded_payable_amount,"
                " awarded_currency_id,"
                " awarded_lot_number)"
                " VALUES"
                " ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,"
                " $11,$12,$13,$14,$15,$16,$17,$18,"
                " $19,$20,$21)"
                " RETURNING id",
                folder_id,
                lot_id,
                r.result_code,
                r.description,
                r.award_date,
                r.received_tender_quantity,
                r.lower_tender_amount,
                r.higher_tender_amount,
                r.sme_awarded_indicator,
                r.abnormally_low_tenders_indicator,
                r.start_date,
                r.smes_received_tender_quantity,
                r.eu_nationals_received_quantity,
                r.non_eu_nationals_received_qty,
                r.awarded_owner_nationality_code,
                r.subcontract_rate,
                r.subcontract_description,
                r.awarded_tax_exclusive_amount,
                r.awarded_payable_amount,
                r.awarded_currency_id,
                r.awarded_lot_number,
            )
            result_id = row["id"]

            for wp in rg.winning_parties:
                await conn.execute(
                    "INSERT INTO winning_party"
                    " (tender_result_id, identifier,"
                    " identifier_scheme, name,"
                    " nuts_code, city_name,"
                    " postal_zone, country_code,"
                    " company_type_code)"
                    " VALUES"
                    " ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
                    result_id,
                    wp.identifier,
                    wp.identifier_scheme,
                    wp.name,
                    wp.nuts_code,
                    wp.city_name,
                    wp.postal_zone,
                    wp.country_code,
                    wp.company_type_code,
                )

            if rg.contract is not None:
                await conn.execute(
                    "INSERT INTO contract"
                    " (tender_result_id,"
                    " contract_number, issue_date)"
                    " VALUES ($1, $2, $3)",
                    result_id,
                    rg.contract.contract_number,
                    rg.contract.issue_date,
                )

    async def _insert_folder_children(
        self,
        conn: asyncpg.Connection,
        folder_id: uuid.UUID,
        entry: ParsedEntry,
    ) -> None:
        for cpv in entry.cpv_folder:
            await conn.execute(
                "INSERT INTO cpv_classification"
                " (contract_folder_status_id,"
                " item_classification_code)"
                " VALUES ($1, $2)",
                folder_id,
                cpv.item_classification_code,
            )
        for c in entry.criteria_folder:
            await conn.execute(
                "INSERT INTO awarding_criteria"
                " (contract_folder_status_id,"
                " criteria_type_code,"
                " criteria_sub_type_code,"
                " description,"
                " weight_numeric, note)"
                " VALUES ($1,$2,$3,$4,$5,$6)",
                folder_id,
                c.criteria_type_code,
                c.criteria_sub_type_code,
                c.description,
                c.weight_numeric,
                c.note,
            )
        for g in entry.guarantees:
            await conn.execute(
                "INSERT INTO financial_guarantee"
                " (contract_folder_status_id,"
                " guarantee_type_code,"
                " amount_rate,"
                " liability_amount, currency_id)"
                " VALUES ($1,$2,$3,$4,$5)",
                folder_id,
                g.guarantee_type_code,
                g.amount_rate,
                g.liability_amount,
                g.currency_id,
            )
        for r in entry.requirements_folder:
            await conn.execute(
                "INSERT INTO qualification_requirement"
                " (contract_folder_status_id,"
                " origin_type,"
                " evaluation_criteria_type_code,"
                " description,"
                " threshold_quantity,"
                " personal_situation,"
                " operating_years_quantity,"
                " employee_quantity)"
                " VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                folder_id,
                r.origin_type,
                r.evaluation_criteria_type_code,
                r.description,
                r.threshold_quantity,
                r.personal_situation,
                r.operating_years_quantity,
                r.employee_quantity,
            )
        for bc in entry.classifications:
            await conn.execute(
                "INSERT INTO business_classification"
                " (contract_folder_status_id,"
                " code_value)"
                " VALUES ($1, $2)",
                folder_id,
                bc.code_value,
            )
        for ec in entry.conditions:
            await conn.execute(
                "INSERT INTO execution_condition"
                " (contract_folder_status_id,"
                " name,"
                " execution_requirement_code,"
                " description)"
                " VALUES ($1,$2,$3,$4)",
                folder_id,
                ec.name,
                ec.execution_requirement_code,
                ec.description,
            )
        for m in entry.modifications:
            await conn.execute(
                "INSERT INTO contract_modification"
                " (contract_folder_status_id,"
                " modification_number,"
                " contract_id, note,"
                " modification_duration_measure,"
                " modification_duration_unit_code,"
                " final_duration_measure,"
                " final_duration_unit_code,"
                " modification_tax_exclusive_amount,"
                " final_tax_exclusive_amount,"
                " currency_id)"
                " VALUES"
                " ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
                folder_id,
                m.modification_number,
                m.contract_id,
                m.note,
                m.modification_duration_measure,
                m.modification_duration_unit_code,
                m.final_duration_measure,
                m.final_duration_unit_code,
                m.modification_tax_exclusive_amount,
                m.final_tax_exclusive_amount,
                m.currency_id,
            )

    async def _insert_notices(
        self,
        conn: asyncpg.Connection,
        folder_id: uuid.UUID,
        notice_groups: list[NoticeGroup],
    ) -> None:
        for ng in notice_groups:
            n = ng.notice
            row = await conn.fetchrow(
                "INSERT INTO valid_notice_info"
                " (contract_folder_status_id,"
                " notice_type_code,"
                " notice_issue_date)"
                " VALUES ($1, $2, $3)"
                " RETURNING id",
                folder_id,
                n.notice_type_code,
                n.notice_issue_date,
            )
            notice_id = row["id"]

            for sg in ng.statuses:
                ps_row = await conn.fetchrow(
                    "INSERT INTO publication_status"
                    " (valid_notice_info_id,"
                    " publication_media_name, issue_date)"
                    " VALUES ($1, $2, $3)"
                    " RETURNING id",
                    notice_id,
                    sg.status.publication_media_name,
                    sg.status.issue_date,
                )
                pub_status_id = ps_row["id"]

                for doc in sg.documents:
                    await conn.execute(
                        "INSERT INTO document_reference"
                        " (contract_folder_status_id,"
                        " publication_status_id,"
                        " source_type, filename,"
                        " uri, document_hash,"
                        " document_type_code)"
                        " VALUES ($1,$2,$3,$4,$5,$6,$7)"
                        " ON CONFLICT"
                        " (contract_folder_status_id,"
                        " source_type, uri)"
                        " DO UPDATE SET"
                        " filename = EXCLUDED.filename,"
                        " document_hash"
                        " = EXCLUDED.document_hash,"
                        " document_type_code"
                        " = EXCLUDED.document_type_code,"
                        " publication_status_id"
                        " = EXCLUDED.publication_status_id",
                        folder_id,
                        pub_status_id,
                        doc.source_type,
                        doc.filename,
                        doc.uri,
                        doc.document_hash,
                        doc.document_type_code,
                    )

    async def _upsert_documents(
        self,
        conn: asyncpg.Connection,
        folder_id: uuid.UUID,
        documents: list[DocumentReferenceWrite],
    ) -> None:
        for doc in documents:
            await conn.execute(
                "INSERT INTO document_reference"
                " (contract_folder_status_id,"
                " source_type, filename, uri,"
                " document_hash,"
                " document_type_code)"
                " VALUES ($1,$2,$3,$4,$5,$6)"
                " ON CONFLICT"
                " (contract_folder_status_id,"
                " source_type, uri)"
                " DO UPDATE SET"
                " filename = EXCLUDED.filename,"
                " document_hash"
                " = EXCLUDED.document_hash,"
                " document_type_code"
                " = EXCLUDED.document_type_code",
                folder_id,
                doc.source_type,
                doc.filename,
                doc.uri,
                doc.document_hash,
                doc.document_type_code,
            )
