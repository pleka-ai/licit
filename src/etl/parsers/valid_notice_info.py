"""Parser for ValidNoticeInfo elements including publication statuses and docs."""

from dataclasses import dataclass, field
from datetime import date

from lxml import etree

from etl.parsers.document import DocumentData
from shared.codice.xml_helpers import (
    find_all,
    find_children,
    find_first,
    text,
    text_date,
)


@dataclass
class PublicationStatusData:
    """Raw publication status data before FK assignment."""

    publication_media_name: str | None = None
    issue_date: date | None = None
    documents: list[DocumentData] = field(default_factory=list)


@dataclass
class NoticeData:
    """Raw notice data before FK assignment."""

    notice_type_code: str | None = None
    notice_issue_date: date | None = None
    publication_statuses: list[PublicationStatusData] = field(default_factory=list)


@dataclass
class NoticeBundle:
    """Complete parsed output from ValidNoticeInfo elements."""

    notices: list[NoticeData] = field(default_factory=list)


class ValidNoticeInfoParser:
    def parse(self, folder_elem: etree._Element) -> NoticeBundle:
        notices: list[NoticeData] = []

        for vni in find_children(folder_elem, "ValidNoticeInfo"):
            notice_type = text(find_first(vni, "NoticeTypeCode"))
            statuses = self._parse_statuses(vni)

            # PLACSP dates each publication (AdditionalPublicationDocumentReference/
            # IssueDate); NoticeIssueDate is rarely present. The notice date is
            # its own if given, else its first publication.
            published = [s.issue_date for s in statuses if s.issue_date is not None]
            notice_date = text_date(find_first(vni, "NoticeIssueDate")) or (
                min(published) if published else None
            )

            notices.append(
                NoticeData(
                    notice_type_code=notice_type,
                    notice_issue_date=notice_date,
                    publication_statuses=statuses,
                )
            )

        return NoticeBundle(notices=notices)

    def _parse_statuses(self, vni: etree._Element) -> list[PublicationStatusData]:
        statuses: list[PublicationStatusData] = []

        for aps in find_all(vni, "AdditionalPublicationStatus"):
            media_name = text(find_first(aps, "PublicationMediaName"))

            documents = self._parse_pub_documents(aps)
            dates = [
                d
                for ref in find_all(aps, "AdditionalPublicationDocumentReference")
                if (d := text_date(find_first(ref, "IssueDate"))) is not None
            ]

            statuses.append(
                PublicationStatusData(
                    publication_media_name=media_name,
                    issue_date=min(dates) if dates else None,
                    documents=documents,
                )
            )

        return statuses

    def _parse_pub_documents(self, aps: etree._Element) -> list[DocumentData]:
        docs: list[DocumentData] = []

        for ref in find_all(aps, "AdditionalPublicationDocumentReference"):
            ext_ref = find_first(ref, "ExternalReference")
            uri = text(find_first(ext_ref, "URI")) if ext_ref is not None else None
            filename_elem = (
                find_first(ext_ref, "FileName") if ext_ref is not None else None
            )
            filename = text(filename_elem) or text(find_first(ref, "ID"))

            docs.append(
                DocumentData(
                    source_type="PUBLICATION",
                    filename=filename,
                    uri=uri,
                    document_type_code=text(find_first(ref, "DocumentTypeCode")),
                )
            )

        return docs
