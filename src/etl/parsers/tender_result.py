"""Parser for TenderResult elements including winning parties and contracts."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from lxml import etree

from shared.codice.nif import detect_nif_swap, normalize_nif
from shared.codice.xml_helpers import (
    attr,
    find_all,
    find_children,
    find_first,
    text,
    text_bool,
    text_date,
    text_decimal,
    text_int,
)


@dataclass
class WinningPartyData:
    """Raw winning party data before FK assignment."""

    identifier: str | None = None
    identifier_scheme: str | None = None
    name: str = ""
    nuts_code: str | None = None
    city_name: str | None = None
    postal_zone: str | None = None
    country_code: str | None = None
    company_type_code: str | None = None


@dataclass
class ContractData:
    """Raw contract data before FK assignment."""

    contract_number: str | None = None
    issue_date: date | None = None


@dataclass
class ResultData:
    """Raw tender result data before FK assignment."""

    result_code: str | None = None
    description: str | None = None
    award_date: date | None = None
    received_tender_quantity: int | None = None
    lower_tender_amount: Decimal | None = None
    higher_tender_amount: Decimal | None = None
    sme_awarded_indicator: bool | None = None
    abnormally_low_tenders_indicator: bool | None = None
    start_date: date | None = None
    smes_received_tender_quantity: int | None = None
    eu_nationals_received_quantity: int | None = None
    non_eu_nationals_received_qty: int | None = None
    awarded_owner_nationality_code: str | None = None
    subcontract_rate: Decimal | None = None
    subcontract_description: str | None = None
    awarded_tax_exclusive_amount: Decimal | None = None
    awarded_payable_amount: Decimal | None = None
    awarded_currency_id: str | None = None
    awarded_lot_number: str | None = None


@dataclass
class ResultBundle:
    """Complete parsed output for a single TenderResult."""

    result: ResultData
    winning_parties: list[WinningPartyData] = field(default_factory=list)
    contract: ContractData | None = None


class TenderResultParser:
    def parse(self, folder_elem: etree._Element) -> list[ResultBundle]:
        bundles: list[ResultBundle] = []

        for tr in find_children(folder_elem, "TenderResult"):
            result_data = self._parse_result(tr)
            winning_parties = self._parse_winning_parties(tr)
            contract = self._parse_contract(tr)

            bundles.append(
                ResultBundle(
                    result=result_data,
                    winning_parties=winning_parties,
                    contract=contract,
                )
            )

        return bundles

    def _parse_result(self, tr: etree._Element) -> ResultData:
        awarded_project = find_first(tr, "AwardedTenderedProject")
        legal_monetary = (
            find_first(awarded_project, "LegalMonetaryTotal")
            if awarded_project is not None
            else None
        )
        subcontract = find_first(tr, "SubcontractTerms")

        awarded_currency_id = None
        if legal_monetary is not None:
            for tag in ["TaxExclusiveAmount", "PayableAmount"]:
                elem = find_first(legal_monetary, tag)
                if elem is not None:
                    awarded_currency_id = attr(elem, "currencyID")
                    if awarded_currency_id:
                        break

        return ResultData(
            result_code=text(find_first(tr, "ResultCode")),
            description=text(find_first(tr, "Description")),
            award_date=text_date(find_first(tr, "AwardDate")),
            received_tender_quantity=text_int(find_first(tr, "ReceivedTenderQuantity")),
            lower_tender_amount=text_decimal(find_first(tr, "LowerTenderAmount")),
            higher_tender_amount=text_decimal(find_first(tr, "HigherTenderAmount")),
            sme_awarded_indicator=text_bool(find_first(tr, "SMEAwardedIndicator")),
            abnormally_low_tenders_indicator=text_bool(
                find_first(tr, "AbnormallyLowTendersIndicator")
            ),
            start_date=text_date(find_first(tr, "StartDate")),
            smes_received_tender_quantity=text_int(
                find_first(tr, "SMEsReceivedTenderQuantity")
            ),
            eu_nationals_received_quantity=text_int(
                find_first(tr, "ReceivedForeignEUTendersQuantity")
            ),
            non_eu_nationals_received_qty=text_int(
                find_first(tr, "ReceivedForeignTendersQuantity")
            ),
            awarded_owner_nationality_code=text(
                find_first(tr, "AwardedOwnerNationalityCode")
            ),
            subcontract_rate=text_decimal(find_first(subcontract, "Rate"))
            if subcontract is not None
            else None,
            subcontract_description=text(find_first(subcontract, "Description"))
            if subcontract is not None
            else None,
            awarded_tax_exclusive_amount=text_decimal(
                find_first(legal_monetary, "TaxExclusiveAmount")
            )
            if legal_monetary is not None
            else None,
            awarded_payable_amount=text_decimal(
                find_first(legal_monetary, "PayableAmount")
            )
            if legal_monetary is not None
            else None,
            awarded_currency_id=awarded_currency_id,
            awarded_lot_number=text(
                find_first(awarded_project, "ProcurementProjectLotID")
            )
            if awarded_project is not None
            else None,
        )

    def _parse_winning_parties(self, tr: etree._Element) -> list[WinningPartyData]:
        parties: list[WinningPartyData] = []

        for wp in find_all(tr, "WinningParty"):
            pi = find_first(wp, "PartyIdentification")
            id_elem = find_first(pi, "ID") if pi is not None else None
            raw_identifier = text(id_elem)
            identifier_scheme = attr(id_elem, "schemeName")

            party_name = find_first(wp, "PartyName")
            name = (
                text(find_first(party_name, "Name")) if party_name is not None else None
            )
            if not name:
                name = raw_identifier or ""

            identifier, name = detect_nif_swap(raw_identifier, name)
            identifier = normalize_nif(identifier)
            name = name or ""

            # PLACSP puts the winner's NUTS code in PhysicalLocation and the
            # rest of its address in PhysicalLocation/Address (find_first
            # searches descendants).
            address = find_first(wp, "PhysicalLocation")

            parties.append(
                WinningPartyData(
                    identifier=identifier,
                    identifier_scheme=identifier_scheme,
                    name=name,
                    nuts_code=text(find_first(address, "CountrySubentityCode"))
                    if address is not None
                    else None,
                    city_name=text(find_first(address, "CityName"))
                    if address is not None
                    else None,
                    postal_zone=text(find_first(address, "PostalZone"))
                    if address is not None
                    else None,
                    country_code=text(find_first(address, "IdentificationCode"))
                    if address is not None
                    else None,
                    company_type_code=text(find_first(wp, "CompanyTypeCode")),
                )
            )

        return parties

    def _parse_contract(self, tr: etree._Element) -> ContractData | None:
        contract_elem = find_first(tr, "Contract")
        if contract_elem is None:
            return None

        return ContractData(
            contract_number=text(find_first(contract_elem, "ID")),
            issue_date=text_date(find_first(contract_elem, "IssueDate")),
        )
