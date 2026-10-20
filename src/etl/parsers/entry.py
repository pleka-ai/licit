"""EntryParser — orchestrates all sub-parsers for a single ATOM entry."""

import uuid
from dataclasses import asdict
from datetime import datetime

from lxml import etree

from etl.parsers.contracting_party import ContractingPartyParser
from etl.parsers.document import DocumentParser
from etl.parsers.lot import LotBundle, LotParser
from etl.parsers.modification import ModificationParser
from etl.parsers.procurement_project import (
    FolderProjectFields,
    ProcurementProjectParser,
)
from etl.parsers.tender_result import ResultBundle, TenderResultParser
from etl.parsers.tendering_process import TenderingProcessFields, TenderingProcessParser
from etl.parsers.tendering_terms import (
    TenderingTermsBundle,
    TenderingTermsFields,
    TenderingTermsParser,
)
from etl.parsers.valid_notice_info import ValidNoticeInfoParser
from shared.codice.xml_helpers import find_child, find_first, text
from shared.models.awarding_criteria import AwardingCriteriaWrite
from shared.models.business_classification import BusinessClassificationWrite
from shared.models.contract import ContractWrite
from shared.models.contract_folder_status import ContractFolderStatusWrite
from shared.models.contract_modification import ContractModificationWrite
from shared.models.cpv_classification import CpvClassificationWrite
from shared.models.document_reference import DocumentReferenceWrite
from shared.models.execution_condition import ExecutionConditionWrite
from shared.models.financial_guarantee import FinancialGuaranteeWrite
from shared.models.parsed_page import (
    EntryEnvelope,
    LotGroup,
    NoticeGroup,
    ParsedEntry,
    PublicationStatusGroup,
    ResultGroup,
)
from shared.models.procurement_project_lot import ProcurementProjectLotWrite
from shared.models.publication_status import PublicationStatusWrite
from shared.models.qualification_requirement import QualificationRequirementWrite
from shared.models.realized_location import RealizedLocationWrite
from shared.models.status_change import StatusChangeWrite
from shared.models.tender_result import TenderResultWrite
from shared.models.valid_notice_info import ValidNoticeInfoWrite
from shared.models.winning_party import WinningPartyWrite

_PLACEHOLDER = uuid.UUID(int=0)


class EntryParser:
    def __init__(self) -> None:
        self._party = ContractingPartyParser()
        self._project = ProcurementProjectParser()
        self._process = TenderingProcessParser()
        self._terms = TenderingTermsParser()
        self._lot = LotParser(self._project, self._terms)
        self._result = TenderResultParser()
        self._document = DocumentParser()
        self._modification = ModificationParser()
        self._notice = ValidNoticeInfoParser()

    def parse(
        self,
        entry_elem: etree._Element,
        feed_type: str,
    ) -> ParsedEntry:
        envelope = self._parse_envelope(entry_elem, feed_type)
        cfs_elem = find_first(entry_elem, "ContractFolderStatus")
        if cfs_elem is None:
            msg = "Missing ContractFolderStatus in entry"
            raise ValueError(msg)

        contracting_party = self._party.parse(cfs_elem)
        project_fields = self._project.parse_folder(cfs_elem)
        process_fields = self._process.parse(cfs_elem)
        terms_bundle = self._terms.parse(cfs_elem, is_lot=False)

        status_code = text(find_child(cfs_elem, "ContractFolderStatusCode"))
        if not status_code:
            msg = "Missing ContractFolderStatusCode"
            raise ValueError(msg)

        contract_folder_id = text(find_child(cfs_elem, "ContractFolderID"))
        ted_uuid = text(find_first(cfs_elem, "UUID"))

        folder = _build_folder(
            envelope,
            project_fields,
            process_fields,
            terms_bundle.scalar_fields,
            {
                "status_code": status_code,
                "contract_folder_id": contract_folder_id,
                "ted_uuid": ted_uuid,
            },
        )

        lot_groups = self._collect_lot_groups(cfs_elem)

        (
            cpv_folder,
            criteria_folder,
            guarantees,
            requirements_folder,
            classifications,
            conditions,
        ) = _collect_folder_terms(
            project_fields,
            terms_bundle,
        )

        result_groups = self._collect_result_groups(cfs_elem)

        direct_documents = self._collect_documents(cfs_elem)
        notice_groups = self._collect_notice_groups(cfs_elem)

        modifications = self._collect_modifications(cfs_elem)

        status_changes = [
            StatusChangeWrite(
                contract_folder_status_id=_PLACEHOLDER,
                status_code=status_code,
                updated=envelope.updated,
            )
        ]

        return ParsedEntry(
            envelope=envelope,
            folder=folder,
            contracting_party=contracting_party,
            lot_groups=lot_groups,
            result_groups=result_groups,
            cpv_folder=cpv_folder,
            criteria_folder=criteria_folder,
            guarantees=guarantees,
            requirements_folder=requirements_folder,
            classifications=classifications,
            conditions=conditions,
            direct_documents=direct_documents,
            notice_groups=notice_groups,
            modifications=modifications,
            status_changes=status_changes,
        )

    def _parse_envelope(
        self,
        entry_elem: etree._Element,
        feed_type: str,
    ) -> EntryEnvelope:
        entry_id = text(find_first(entry_elem, "id"))
        if not entry_id:
            msg = "Missing <id> in ATOM entry"
            raise ValueError(msg)

        updated_str = text(find_first(entry_elem, "updated"))
        if not updated_str:
            msg = "Missing <updated> in ATOM entry"
            raise ValueError(msg)
        updated = datetime.fromisoformat(updated_str)

        link_elem = find_first(entry_elem, "link")
        link = link_elem.get("href") if link_elem is not None else None

        return EntryEnvelope(
            entry_id=entry_id,
            title=text(find_first(entry_elem, "title")),
            summary=text(find_first(entry_elem, "summary")),
            link=link,
            updated=updated,
            feed_type=feed_type,
        )

    def _collect_lot_groups(
        self,
        cfs_elem: etree._Element,
    ) -> list[LotGroup]:
        return [_lot_group(lb) for lb in self._lot.parse(cfs_elem)]

    def _collect_result_groups(
        self,
        cfs_elem: etree._Element,
    ) -> list[ResultGroup]:
        return [_result_group(rb) for rb in self._result.parse(cfs_elem)]

    def _collect_documents(
        self,
        cfs_elem: etree._Element,
    ) -> list[DocumentReferenceWrite]:
        return [
            DocumentReferenceWrite(
                contract_folder_status_id=_PLACEHOLDER,
                source_type=d.source_type,
                filename=d.filename,
                uri=d.uri,
                document_hash=d.document_hash,
                document_type_code=d.document_type_code,
            )
            for d in self._document.parse(cfs_elem)
        ]

    def _collect_notice_groups(
        self,
        cfs_elem: etree._Element,
    ) -> list[NoticeGroup]:
        bundle = self._notice.parse(cfs_elem)
        groups: list[NoticeGroup] = []

        for nd in bundle.notices:
            notice = ValidNoticeInfoWrite(
                contract_folder_status_id=_PLACEHOLDER,
                notice_type_code=nd.notice_type_code,
                notice_issue_date=nd.notice_issue_date,
            )
            status_groups: list[PublicationStatusGroup] = []
            for ps in nd.publication_statuses:
                status = PublicationStatusWrite(
                    valid_notice_info_id=_PLACEHOLDER,
                    publication_media_name=ps.publication_media_name,
                    issue_date=ps.issue_date,
                )
                docs = [
                    DocumentReferenceWrite(
                        contract_folder_status_id=_PLACEHOLDER,
                        publication_status_id=_PLACEHOLDER,
                        source_type=doc.source_type,
                        filename=doc.filename,
                        uri=doc.uri,
                        document_type_code=doc.document_type_code,
                    )
                    for doc in ps.documents
                ]
                status_groups.append(
                    PublicationStatusGroup(status=status, documents=docs)
                )
            groups.append(NoticeGroup(notice=notice, statuses=status_groups))

        return groups

    def _collect_modifications(
        self,
        cfs_elem: etree._Element,
    ) -> list[ContractModificationWrite]:
        return [
            ContractModificationWrite(
                contract_folder_status_id=_PLACEHOLDER,
                modification_number=m.modification_number,
                contract_id=m.contract_id,
                note=m.note,
                modification_duration_measure=m.modification_duration_measure,
                modification_duration_unit_code=m.modification_duration_unit_code,
                final_duration_measure=m.final_duration_measure,
                final_duration_unit_code=m.final_duration_unit_code,
                modification_tax_exclusive_amount=m.modification_tax_exclusive_amount,
                final_tax_exclusive_amount=m.final_tax_exclusive_amount,
                currency_id=m.currency_id,
            )
            for m in self._modification.parse(cfs_elem)
        ]


def _build_folder(
    envelope: EntryEnvelope,
    project: FolderProjectFields,
    process: TenderingProcessFields,
    terms_scalars: TenderingTermsFields | None,
    cfs_fields: dict[str, str | None],
) -> ContractFolderStatusWrite:
    terms_dict = asdict(terms_scalars) if terms_scalars is not None else {}

    return ContractFolderStatusWrite(
        entry_id=envelope.entry_id,
        title=envelope.title,
        summary=envelope.summary,
        link=envelope.link,
        updated=envelope.updated,
        feed_type=envelope.feed_type,
        contract_folder_id=cfs_fields.get("contract_folder_id"),
        status_code=cfs_fields.get("status_code", ""),
        name=project.name,
        type_code=project.type_code,
        sub_type_code=project.sub_type_code,
        estimated_overall_contract_amount=project.estimated_overall_contract_amount,
        total_amount=project.total_amount,
        tax_exclusive_amount=project.tax_exclusive_amount,
        currency_id=project.currency_id,
        nuts_code=project.nuts_code,
        country_subentity=project.country_subentity,
        duration_measure=project.duration_measure,
        duration_unit_code=project.duration_unit_code,
        planned_start_date=project.planned_start_date,
        planned_end_date=project.planned_end_date,
        option_validity_description=project.option_validity_description,
        options_description=project.options_description,
        mix_contract_indicator=project.mix_contract_indicator,
        procedure_code=process.procedure_code,
        urgency_code=process.urgency_code,
        submission_method_code=process.submission_method_code,
        submission_deadline_date=process.submission_deadline_date,
        submission_deadline_time=process.submission_deadline_time,
        submission_deadline_description=process.submission_deadline_description,
        document_availability_end_date=process.document_availability_end_date,
        document_availability_end_time=process.document_availability_end_time,
        contracting_system_code=process.contracting_system_code,
        part_presentation_code=process.part_presentation_code,
        auction_constraint_indicator=process.auction_constraint_indicator,
        max_lot_presentation_quantity=process.max_lot_presentation_quantity,
        max_tenderer_awarded_lots_qty=process.max_tenderer_awarded_lots_qty,
        lots_combination_rights=process.lots_combination_rights,
        over_threshold_indicator=process.over_threshold_indicator,
        participation_request_end_date=process.participation_request_end_date,
        participation_request_end_time=process.participation_request_end_time,
        short_list_limitation_description=process.short_list_limitation_description,
        short_list_min_quantity=process.short_list_min_quantity,
        short_list_expected_quantity=process.short_list_expected_quantity,
        short_list_max_quantity=process.short_list_max_quantity,
        ted_uuid=cfs_fields.get("ted_uuid"),
        **terms_dict,
    )


def _collect_folder_terms(
    project: FolderProjectFields,
    terms: TenderingTermsBundle,
) -> tuple[
    list[CpvClassificationWrite],
    list[AwardingCriteriaWrite],
    list[FinancialGuaranteeWrite],
    list[QualificationRequirementWrite],
    list[BusinessClassificationWrite],
    list[ExecutionConditionWrite],
]:
    cpv_folder = [
        CpvClassificationWrite(
            contract_folder_status_id=_PLACEHOLDER,
            item_classification_code=code,
        )
        for code in (project.cpv_codes or [])
    ]

    criteria_folder = [
        AwardingCriteriaWrite(
            contract_folder_status_id=_PLACEHOLDER,
            criteria_type_code=c.criteria_type_code,
            criteria_sub_type_code=c.criteria_sub_type_code,
            description=c.description,
            weight_numeric=c.weight_numeric,
            note=c.note,
        )
        for c in terms.criteria
    ]

    guarantees = [
        FinancialGuaranteeWrite(
            contract_folder_status_id=_PLACEHOLDER,
            guarantee_type_code=g.guarantee_type_code,
            amount_rate=g.amount_rate,
            liability_amount=g.liability_amount,
            currency_id=g.currency_id,
        )
        for g in terms.guarantees
    ]

    requirements_folder = [
        QualificationRequirementWrite(
            contract_folder_status_id=_PLACEHOLDER,
            origin_type=r.origin_type,
            evaluation_criteria_type_code=r.evaluation_criteria_type_code,
            description=r.description,
            threshold_quantity=r.threshold_quantity,
            personal_situation=r.personal_situation,
            operating_years_quantity=r.operating_years_quantity,
            employee_quantity=r.employee_quantity,
        )
        for r in terms.requirements
    ]

    classifications = [
        BusinessClassificationWrite(
            contract_folder_status_id=_PLACEHOLDER,
            code_value=c.code_value,
        )
        for c in terms.classifications
    ]

    conditions = [
        ExecutionConditionWrite(
            contract_folder_status_id=_PLACEHOLDER,
            name=c.name,
            execution_requirement_code=c.execution_requirement_code,
            description=c.description,
        )
        for c in terms.conditions
    ]

    return (
        cpv_folder,
        criteria_folder,
        guarantees,
        requirements_folder,
        classifications,
        conditions,
    )


def _lot_group(lb: LotBundle) -> LotGroup:
    lot = ProcurementProjectLotWrite(
        contract_folder_status_id=_PLACEHOLDER,
        lot_number=lb.lot_number,
        name=lb.project.name,
        total_amount=lb.project.total_amount,
        tax_exclusive_amount=lb.project.tax_exclusive_amount,
        currency_id=lb.project.currency_id,
        nuts_code=lb.project.nuts_code,
        country_subentity=lb.project.country_subentity,
    )
    cpv_codes = [
        CpvClassificationWrite(
            contract_folder_status_id=_PLACEHOLDER,
            item_classification_code=code,
        )
        for code in lb.cpv_codes
    ]
    criteria = [
        AwardingCriteriaWrite(
            contract_folder_status_id=_PLACEHOLDER,
            criteria_type_code=c.criteria_type_code,
            criteria_sub_type_code=c.criteria_sub_type_code,
            description=c.description,
            weight_numeric=c.weight_numeric,
            note=c.note,
        )
        for c in lb.criteria
    ]
    requirements = [
        QualificationRequirementWrite(
            contract_folder_status_id=_PLACEHOLDER,
            origin_type=r.origin_type,
            evaluation_criteria_type_code=r.evaluation_criteria_type_code,
            description=r.description,
            threshold_quantity=r.threshold_quantity,
            personal_situation=r.personal_situation,
            operating_years_quantity=r.operating_years_quantity,
            employee_quantity=r.employee_quantity,
        )
        for r in lb.requirements
    ]
    locations = [
        RealizedLocationWrite(
            lot_id=_PLACEHOLDER,
            nuts_code=loc.nuts_code,
            country_subentity=loc.country_subentity,
            country_code=loc.country_code,
            city_name=loc.city_name,
            postal_zone=loc.postal_zone,
            street_name=loc.street_name,
        )
        for loc in lb.locations
    ]
    return LotGroup(
        lot=lot,
        cpv_codes=cpv_codes,
        criteria=criteria,
        requirements=requirements,
        locations=locations,
    )


def _result_group(rb: ResultBundle) -> ResultGroup:
    rd = rb.result
    result = TenderResultWrite(
        contract_folder_status_id=_PLACEHOLDER,
        result_code=rd.result_code,
        description=rd.description,
        award_date=rd.award_date,
        received_tender_quantity=rd.received_tender_quantity,
        lower_tender_amount=rd.lower_tender_amount,
        higher_tender_amount=rd.higher_tender_amount,
        sme_awarded_indicator=rd.sme_awarded_indicator,
        abnormally_low_tenders_indicator=rd.abnormally_low_tenders_indicator,
        start_date=rd.start_date,
        smes_received_tender_quantity=rd.smes_received_tender_quantity,
        eu_nationals_received_quantity=rd.eu_nationals_received_quantity,
        non_eu_nationals_received_qty=rd.non_eu_nationals_received_qty,
        awarded_owner_nationality_code=rd.awarded_owner_nationality_code,
        subcontract_rate=rd.subcontract_rate,
        subcontract_description=rd.subcontract_description,
        awarded_tax_exclusive_amount=rd.awarded_tax_exclusive_amount,
        awarded_payable_amount=rd.awarded_payable_amount,
        awarded_currency_id=rd.awarded_currency_id,
        awarded_lot_number=rd.awarded_lot_number,
    )
    winning_parties = [
        WinningPartyWrite(
            tender_result_id=_PLACEHOLDER,
            identifier=wp.identifier,
            identifier_scheme=wp.identifier_scheme,
            name=wp.name,
            nuts_code=wp.nuts_code,
            city_name=wp.city_name,
            postal_zone=wp.postal_zone,
            country_code=wp.country_code,
            company_type_code=wp.company_type_code,
        )
        for wp in rb.winning_parties
    ]
    contract = None
    if rb.contract is not None:
        contract = ContractWrite(
            tender_result_id=_PLACEHOLDER,
            contract_number=rb.contract.contract_number,
            issue_date=rb.contract.issue_date,
        )
    return ResultGroup(
        result=result,
        winning_parties=winning_parties,
        contract=contract,
    )
