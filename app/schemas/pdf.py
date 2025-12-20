from typing import List

from pydantic import BaseModel


class PageContent(BaseModel):
    page_number: int
    text: str


class ExtractedPDF(BaseModel):
    pages: List[PageContent]


class UploadResponse(BaseModel):
    message: str
    filename: str
    num_pages: int
    total_characters: int
