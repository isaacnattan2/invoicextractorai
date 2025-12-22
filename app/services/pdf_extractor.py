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


def _is_password_related_exception(exc: Exception) -> tuple[bool, bool]:
    """
    Traverse the exception chain to detect password-related errors.
    
    Returns:
        tuple[bool, bool]: (is_password_related, is_incorrect_password)
        - is_password_related: True if the exception is related to PDF password/encryption
        - is_incorrect_password: True if specifically a wrong password error (vs missing password)
    """
    visited = set()
    current = exc
    is_password_related = False
    is_incorrect_password = False
    
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        
        exc_type_name = type(current).__name__
        if exc_type_name == "PDFPasswordIncorrect":
            is_password_related = True
            is_incorrect_password = True
        elif exc_type_name in ("PDFEncryptionError", "PDFTextExtractionNotAllowed"):
            is_password_related = True
        
        error_msg = str(current).lower()
        if "password" in error_msg or "encrypted" in error_msg or "encryption" in error_msg:
            is_password_related = True
            if "incorrect" in error_msg or "wrong" in error_msg or "invalid" in error_msg:
                is_incorrect_password = True
        
        if current.__cause__ is not None:
            current = current.__cause__
        elif current.__context__ is not None:
            current = current.__context__
        else:
            for arg in getattr(current, 'args', ()):
                if isinstance(arg, BaseException) and id(arg) not in visited:
                    current = arg
                    break
            else:
                current = None
    
    return is_password_related, is_incorrect_password


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
        
        is_password_related, is_incorrect_password = _is_password_related_exception(e)
        if is_password_related:
            if password is not None or is_incorrect_password:
                raise PDFPasswordIncorrect("The provided password is incorrect.") from e
            raise PDFPasswordRequired("This PDF is password-protected. Please provide the password.") from e
        raise PDFExtractionError(f"Failed to process PDF: {str(e)}") from e

    if not total_text.strip():
        raise PDFExtractionError(
            "PDF contains no extractable text. "
            "This may be a scanned document or image-based PDF."
        )

    return ExtractedPDF(pages=pages)