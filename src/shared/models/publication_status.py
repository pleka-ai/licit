import uuid
from datetime import date

from pydantic import BaseModel


class PublicationStatusWrite(BaseModel):
    valid_notice_info_id: uuid.UUID
    publication_media_name: str | None = None
    issue_date: date | None = None


class PublicationStatusRead(PublicationStatusWrite):
    id: uuid.UUID
