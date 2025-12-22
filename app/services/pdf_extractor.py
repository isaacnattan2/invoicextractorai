import re
from typing import BinaryIO, Optional, List

import pdfplumber

from app.schemas.pdf import ExtractedPDF, PageContent


# ==========================
# Exceptions
# ==========================

class PDFExtractionError(Exception):
    """
    Generic PDF extraction error.

    The original exception is preserved via exception chaining (__cause__).
    """

    def __init__(self, message: str, *, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause


class PDFPasswordRequired(Exception):
    """Raised when a PDF is password-protected and requires a password to open."""
    pass


class PDFPasswordIncorrect(Exception):
    """Raised when the provided password is incorrect."""
    pass


# ==========================
# Helpers
# ==========================

def normalize_text(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'\r', '\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def _is_password_error(exc: Exception) -> bool:
    """
    Heuristic to detect password/encryption-related errors coming
    from pdfplumber / pdfminer.
    """
    msg = str(exc).lower()
    return "password" in msg or "encrypted" in msg


# ==========================
# Main Extraction Logic
# ==========================

def extract_text_from_pdf(
    file: BinaryIO,
    password: Optional[str] = None
) -> ExtractedPDF:
    pages: List[PageContent] = []
    total_text: str = ""

    try:
        with pdfplumber.open(file, password=password) as pdf:
            if not pdf.pages:
                raise PDFExtractionError("PDF file contains no pages")

            for page_number, page in enumerate(pdf.pages, start=1):
                raw_text = page.extract_text() or ""
                normalized_text = normalize_text(raw_text)

                total_text += normalized_text

                pages.append(
                    PageContent(
                        page_number=page_number,
                        text=normalized_text
                    )
                )

    except pdfplumber.pdfminer.pdfparser.PDFSyntaxError as e:
        raise PDFExtractionError(
            "Invalid PDF file format",
            cause=e
        ) from e

    except Exception as e:
        # Re-raise known domain exceptions untouched
        if isinstance(e, (PDFExtractionError, PDFPasswordRequired, PDFPasswordIncorrect)):
            raise

        # Password / encryption handling
        if _is_password_error(e):
            if password:
                raise PDFPasswordIncorrect(
                    "The provided password is incorrect."
                ) from e

            raise PDFPasswordRequired(
                "This PDF is password-protected. Please provide the password."
            ) from e

        # Generic failure
        raise PDFExtractionError(
            "Failed to process PDF",
            cause=e
        ) from e

    # Validate extracted content
    if not total_text.strip():
        raise PDFExtractionError(
            "PDF contains no extractable text. "
            "This may be a scanned document or image-based PDF."
        )

    return ExtractedPDF(pages=pages)
