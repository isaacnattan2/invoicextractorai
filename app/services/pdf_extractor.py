import re
from typing import BinaryIO, Optional

import pdfplumber

from app.schemas.pdf import ExtractedPDF, PageContent


class PDFExtractionError(Exception):
    pass


class PDFPasswordRequired(Exception):
    """Raised when a PDF is password-protected and requires a password to open."""
    pass


class PDFPasswordIncorrect(Exception):
    """Raised when the provided password is incorrect."""
    pass


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'\r', '\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    return text


def extract_text_from_pdf(file: BinaryIO, password: Optional[str] = None) -> ExtractedPDF:
    pages = []
    total_text = ""

    try:
        with pdfplumber.open(file, password=password) as pdf:
            if len(pdf.pages) == 0:
                raise PDFExtractionError("PDF file contains no pages")

            for page_num, page in enumerate(pdf.pages, start=1):
                raw_text = page.extract_text() or ""
                normalized_text = normalize_text(raw_text)
                total_text += normalized_text

                pages.append(PageContent(
                    page_number=page_num,
                    text=normalized_text
                ))

    except pdfplumber.pdfminer.pdfparser.PDFSyntaxError:
        raise PDFExtractionError("Invalid PDF file format")
    except Exception as e:
        if isinstance(e, (PDFExtractionError, PDFPasswordRequired, PDFPasswordIncorrect)):
            raise
        error_msg = str(e).lower()
        if "password" in error_msg or "encrypted" in error_msg:
            if password is not None:
                raise PDFPasswordIncorrect("The provided password is incorrect.")
            raise PDFPasswordRequired("This PDF is password-protected. Please provide the password.")
        raise PDFExtractionError(f"Failed to process PDF: {str(e)}")

    if not total_text.strip():
        raise PDFExtractionError(
            "PDF contains no extractable text. "
            "This may be a scanned document or image-based PDF."
        )

    return ExtractedPDF(pages=pages)
