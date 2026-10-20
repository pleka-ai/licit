"""Tests for ValidNoticeInfoParser."""

from datetime import date
from pathlib import Path

import pytest

from etl.parsers.valid_notice_info import ValidNoticeInfoParser
from shared.codice.xml_helpers import find_first, get_entries, parse_xml

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _folder_elem(fixture: str) -> object:
    root = parse_xml(_load(fixture))
    entries = get_entries(root)
    return find_first(entries[0], "ContractFolderStatus")


@pytest.fixture
def parser() -> ValidNoticeInfoParser:
    return ValidNoticeInfoParser()


class TestFullEntryNotices:
    def test_returns_two_notices(self, parser: ValidNoticeInfoParser) -> None:
        folder = _folder_elem("full_entry.xml")
        bundle = parser.parse(folder)
        assert len(bundle.notices) == 2

    def test_first_notice_type(self, parser: ValidNoticeInfoParser) -> None:
        folder = _folder_elem("full_entry.xml")
        bundle = parser.parse(folder)
        assert bundle.notices[0].notice_type_code == "DOC_CN"

    def test_first_notice_date(self, parser: ValidNoticeInfoParser) -> None:
        folder = _folder_elem("full_entry.xml")
        bundle = parser.parse(folder)
        assert bundle.notices[0].notice_issue_date == date(2024, 6, 1)

    def test_second_notice_type(self, parser: ValidNoticeInfoParser) -> None:
        folder = _folder_elem("full_entry.xml")
        bundle = parser.parse(folder)
        assert bundle.notices[1].notice_type_code == "DOC_CAN_ADJ"

    def test_first_notice_has_two_statuses(self, parser: ValidNoticeInfoParser) -> None:
        folder = _folder_elem("full_entry.xml")
        bundle = parser.parse(folder)
        assert len(bundle.notices[0].publication_statuses) == 2

    def test_first_status_media_name(self, parser: ValidNoticeInfoParser) -> None:
        folder = _folder_elem("full_entry.xml")
        bundle = parser.parse(folder)
        status = bundle.notices[0].publication_statuses[0]
        assert status.publication_media_name == "Perfil del Contratante"

    def test_second_status_media_name(self, parser: ValidNoticeInfoParser) -> None:
        folder = _folder_elem("full_entry.xml")
        bundle = parser.parse(folder)
        status = bundle.notices[0].publication_statuses[1]
        assert status.publication_media_name == "BOE"


class TestPublicationDocuments:
    def test_first_status_has_one_document(self, parser: ValidNoticeInfoParser) -> None:
        folder = _folder_elem("full_entry.xml")
        bundle = parser.parse(folder)
        docs = bundle.notices[0].publication_statuses[0].documents
        assert len(docs) == 1

    def test_document_source_type(self, parser: ValidNoticeInfoParser) -> None:
        folder = _folder_elem("full_entry.xml")
        bundle = parser.parse(folder)
        doc = bundle.notices[0].publication_statuses[0].documents[0]
        assert doc.source_type == "PUBLICATION"

    def test_document_filename(self, parser: ValidNoticeInfoParser) -> None:
        folder = _folder_elem("full_entry.xml")
        bundle = parser.parse(folder)
        doc = bundle.notices[0].publication_statuses[0].documents[0]
        assert doc.filename == "anuncio_licitacion.pdf"

    def test_document_uri(self, parser: ValidNoticeInfoParser) -> None:
        folder = _folder_elem("full_entry.xml")
        bundle = parser.parse(folder)
        doc = bundle.notices[0].publication_statuses[0].documents[0]
        assert "anuncio.pdf" in doc.uri

    def test_document_type_code(self, parser: ValidNoticeInfoParser) -> None:
        folder = _folder_elem("full_entry.xml")
        bundle = parser.parse(folder)
        doc = bundle.notices[0].publication_statuses[0].documents[0]
        assert doc.document_type_code == "2"

    def test_boe_status_has_no_documents(self, parser: ValidNoticeInfoParser) -> None:
        folder = _folder_elem("full_entry.xml")
        bundle = parser.parse(folder)
        docs = bundle.notices[0].publication_statuses[1].documents
        assert docs == []


class TestMinimalEntry:
    def test_no_notices(self, parser: ValidNoticeInfoParser) -> None:
        folder = _folder_elem("minimal_entry.xml")
        bundle = parser.parse(folder)
        assert bundle.notices == []


class TestPublicationDates:
    """Live feeds date each publication, not the notice itself."""

    _XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
  xmlns:cac-place-ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2"
  xmlns:cbc-place-ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2"
  xmlns:cbc="urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2">
  <entry><cac-place-ext:ContractFolderStatus>
    <cac-place-ext:ValidNoticeInfo>
      <cbc-place-ext:NoticeTypeCode>DOC_CN</cbc-place-ext:NoticeTypeCode>
      <cac-place-ext:AdditionalPublicationStatus>
        <cbc-place-ext:PublicationMediaName>DOUE</cbc-place-ext:PublicationMediaName>
        <cac-place-ext:AdditionalPublicationDocumentReference>
          <cbc:IssueDate>2026-10-21</cbc:IssueDate>
        </cac-place-ext:AdditionalPublicationDocumentReference>
      </cac-place-ext:AdditionalPublicationStatus>
      <cac-place-ext:AdditionalPublicationStatus>
        <cbc-place-ext:PublicationMediaName>Perfil</cbc-place-ext:PublicationMediaName>
        <cac-place-ext:AdditionalPublicationDocumentReference>
          <cbc:IssueDate>2026-10-20</cbc:IssueDate>
        </cac-place-ext:AdditionalPublicationDocumentReference>
      </cac-place-ext:AdditionalPublicationStatus>
    </cac-place-ext:ValidNoticeInfo>
  </cac-place-ext:ContractFolderStatus></entry>
</feed>"""

    def _notice(self, parser: ValidNoticeInfoParser):  # type: ignore[no-untyped-def]
        entry = get_entries(parse_xml(self._XML))[0]
        return parser.parse(find_first(entry, "ContractFolderStatus")).notices[0]

    def test_each_publication_keeps_its_date(
        self, parser: ValidNoticeInfoParser
    ) -> None:
        dates = [s.issue_date for s in self._notice(parser).publication_statuses]
        assert dates == [date(2026, 10, 21), date(2026, 10, 20)]

    def test_notice_date_is_first_publication(
        self, parser: ValidNoticeInfoParser
    ) -> None:
        assert self._notice(parser).notice_issue_date == date(2026, 10, 20)
