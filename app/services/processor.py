import asyncio
import os
import tempfile
from io import BytesIO

from typing import Optional

from app.services.bank_identifier import identify_bank
from app.services.excel_generator import generate_excel
from app.services.expense_extractor import ExtractionError, extract_expenses, combine_pages_text, build_llm_prompt
from app.services.job_registry import JobStatus, get_registry
from app.services.pdf_extractor import PDFExtractionError, PDFPasswordRequired, PDFPasswordIncorrect, extract_text_from_pdf
from app.services.rag_loader import load_knowledge_for_issuer
from app.services.mongodb_persistence import persist_extraction

import re
from typing import Iterable

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

logger = logging.getLogger(__name__)

sensitive_keywords = ["Isaac", "Nattan", "Silva", "Palmeira", "Lucimara", "Oliveira", "Moura", 
                              "Avenida", "Central", "Olaria", "casa", "Sinai", "Sergipe", "Brasil",     # "Aracaju",
                              "49092693", "49092-693", "49.092-693", "04138896538", "041.388.965-38", 
                              "036.220.335-09", "03622033509"]


def _extract_pdf_text(pdf_content: bytes, password: Optional[str] = None):
    file_stream = BytesIO(pdf_content)
    return extract_text_from_pdf(file_stream, password=password)


def _write_excel_file(excel_file, excel_path: str):
    with open(excel_path, "wb") as f:
        f.write(excel_file.getvalue())

def removePersonalInformation(
    text: str,
    sensitive_keywords: Iterable[str],
    placeholder: str = "[REDACTED]"
) -> str:
    if not text or not sensitive_keywords:
        return text

    sanitized = text

    # Ordena por tamanho para evitar substituições parciais
    keywords = sorted(
        (k for k in sensitive_keywords if k),
        key=len,
        reverse=True
    )

    for keyword in keywords:
        escaped = re.escape(keyword)

        sanitized = re.sub(
            escaped,
            placeholder,
            sanitized,
            flags=re.IGNORECASE
        )

    return sanitized

async def process_job(job_id: str):
    registry = get_registry()
    
    try:
        job = registry.get_job(job_id)
        
        if not job or not job.pdf_content:
            registry.set_job_error(job_id, "Job not found or PDF content missing")
            return

        if registry.is_job_cancelled(job_id):
            return

        registry.update_job_status(job_id, JobStatus.PROCESSING, progress=0)

        try:
            extracted_pdf = await asyncio.to_thread(_extract_pdf_text, job.pdf_content)
        except PDFPasswordRequired as e:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_password_required(job_id, str(e))
            return
        except PDFPasswordIncorrect as e:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_password_required(job_id, str(e))
            return
        except PDFExtractionError as e:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_error(job_id, f"PDF extraction failed: {str(e)}")
                logger.exception("PDF extraction failed")
                raise
            return

        if registry.is_job_cancelled(job_id):
            return

        registry.update_job_progress(job_id, 20)

        # remove sensitive personal information
        for page in extracted_pdf.pages:
            page.text = removePersonalInformation(page.text, sensitive_keywords)

        combined_text = combine_pages_text(extracted_pdf)

        if registry.is_job_cancelled(job_id):
            return

        registry.update_job_progress(job_id, 30)

        try:
            bank_result = await asyncio.to_thread(identify_bank, extracted_pdf, job.provider)
        except Exception:
            bank_result = type('BankResult', (), {'name': 'Unknown'})()

        if registry.is_job_cancelled(job_id):
            return

        knowledge = load_knowledge_for_issuer(bank_result.name)
        llm_prompt = build_llm_prompt(combined_text, knowledge)
        registry.set_job_details(job_id, combined_text, llm_prompt)

        registry.update_job_progress(job_id, 50)

        try:
            extraction_result = await asyncio.to_thread(extract_expenses, extracted_pdf, job.provider, bank_result.name)
        except ExtractionError as e:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_error(job_id, f"LLM extraction failed: {str(e)}")
            return

        if registry.is_job_cancelled(job_id):
            return

        registry.update_job_progress(job_id, 80)

        for transaction in extraction_result.transactions:
            transaction.bank = bank_result.name

        if registry.is_job_cancelled(job_id):
            return

        await asyncio.to_thread(
            persist_extraction,
            job_id,
            job.filename,
            bank_result.name,
            extraction_result.transactions,
            extraction_result.invoice_due_date
        )

        try:
            excel_file = await asyncio.to_thread(generate_excel, extraction_result.transactions, extraction_result.invoice_due_date)
            
            temp_dir = os.path.join(tempfile.gettempdir(), "invoicextractor")
            os.makedirs(temp_dir, exist_ok=True)
            
            base_name = job.filename.rsplit(".", 1)[0] if job.filename else "invoice"
            model_label = job.model_name or job.provider
            excel_filename = f"{base_name}_{job_id}_transactions_{model_label}.xlsx"
            excel_path = os.path.join(temp_dir, excel_filename)
            
            await asyncio.to_thread(_write_excel_file, excel_file, excel_path)
            
            if not registry.is_job_cancelled(job_id):
                registry.set_job_completed(job_id, excel_path)
        except Exception as e:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_error(job_id, f"Excel generation failed: {str(e)}")
    except Exception as e:
        try:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_error(job_id, f"Processing failed: {str(e)}")
        except Exception:
            pass


def start_processing(job_id: str):
    asyncio.create_task(process_job(job_id))


async def process_text_job(job_id: str):
    """Process a job created from raw text input, bypassing PDF extraction."""
    registry = get_registry()
    
    try:
        job = registry.get_job(job_id)
        
        if not job or not job.extracted_text:
            registry.set_job_error(job_id, "Job not found or text content missing")
            return

        if registry.is_job_cancelled(job_id):
            return

        registry.update_job_status(job_id, JobStatus.PROCESSING, progress=0)

        # Skip PDF extraction - text is already available
        # Create an ExtractedPDF-like structure with the text as a single page
        from app.schemas.pdf import ExtractedPDF, PageContent
        
        raw_text = job.extracted_text
        
        # Remove sensitive personal information
        sanitized_text = removePersonalInformation(raw_text, sensitive_keywords)
        
        # Create a single-page structure
        extracted_pdf = ExtractedPDF(pages=[PageContent(page_number=1, text=sanitized_text)])

        if registry.is_job_cancelled(job_id):
            return

        registry.update_job_progress(job_id, 20)

        combined_text = combine_pages_text(extracted_pdf)

        if registry.is_job_cancelled(job_id):
            return

        registry.update_job_progress(job_id, 30)

        try:
            bank_result = await asyncio.to_thread(identify_bank, extracted_pdf, job.provider)
        except Exception:
            bank_result = type('BankResult', (), {'name': 'Unknown'})()

        if registry.is_job_cancelled(job_id):
            return

        knowledge = load_knowledge_for_issuer(bank_result.name)
        llm_prompt = build_llm_prompt(combined_text, knowledge)
        registry.set_job_details(job_id, combined_text, llm_prompt)

        registry.update_job_progress(job_id, 50)

        try:
            extraction_result = await asyncio.to_thread(extract_expenses, extracted_pdf, job.provider, bank_result.name)
        except ExtractionError as e:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_error(job_id, f"LLM extraction failed: {str(e)}")
            return

        if registry.is_job_cancelled(job_id):
            return

        registry.update_job_progress(job_id, 80)

        for transaction in extraction_result.transactions:
            transaction.bank = bank_result.name

        if registry.is_job_cancelled(job_id):
            return

        await asyncio.to_thread(
            persist_extraction,
            job_id,
            job.filename,
            bank_result.name,
            extraction_result.transactions,
            extraction_result.invoice_due_date
        )

        try:
            excel_file = await asyncio.to_thread(generate_excel, extraction_result.transactions, extraction_result.invoice_due_date)
            
            temp_dir = os.path.join(tempfile.gettempdir(), "invoicextractor")
            os.makedirs(temp_dir, exist_ok=True)
            
            base_name = job.filename.rsplit(".", 1)[0] if job.filename else "text_input"
            model_label = job.model_name or job.provider
            excel_filename = f"{base_name}_{job_id}_transactions_{model_label}.xlsx"
            excel_path = os.path.join(temp_dir, excel_filename)
            
            await asyncio.to_thread(_write_excel_file, excel_file, excel_path)
            
            if not registry.is_job_cancelled(job_id):
                registry.set_job_completed(job_id, excel_path)
        except Exception as e:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_error(job_id, f"Excel generation failed: {str(e)}")
    except Exception as e:
        try:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_error(job_id, f"Processing failed: {str(e)}")
        except Exception:
            pass


def start_processing_text(job_id: str):
    """Start processing a text input job."""
    asyncio.create_task(process_text_job(job_id))


async def process_job_with_password(job_id: str, password: str):
    registry = get_registry()
    
    try:
        job = registry.get_job(job_id)
        
        if not job or not job.pdf_content:
            registry.set_job_error(job_id, "Job not found or PDF content missing")
            return
        
        if job.status != JobStatus.PASSWORD_REQUIRED:
            registry.set_job_error(job_id, "Job is not waiting for password")
            return

        registry.reset_job_for_retry(job_id)

        try:
            extracted_pdf = await asyncio.to_thread(_extract_pdf_text, job.pdf_content, password)
        except PDFPasswordRequired as e:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_password_required(job_id, str(e))
            return
        except PDFPasswordIncorrect as e:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_password_required(job_id, str(e))
            return
        except PDFExtractionError as e:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_error(job_id, f"PDF extraction failed: {str(e)}")
            return

        if registry.is_job_cancelled(job_id):
            return

        registry.update_job_progress(job_id, 20)

        # remove sensitive personal information
        for page in extracted_pdf.pages:
            page.text = removePersonalInformation(page.text, sensitive_keywords)

        combined_text = combine_pages_text(extracted_pdf)

        if registry.is_job_cancelled(job_id):
            return

        registry.update_job_progress(job_id, 30)

        try:
            bank_result = await asyncio.to_thread(identify_bank, extracted_pdf, job.provider)
        except Exception:
            bank_result = type('BankResult', (), {'name': 'Unknown'})()

        if registry.is_job_cancelled(job_id):
            return

        knowledge = load_knowledge_for_issuer(bank_result.name)
        llm_prompt = build_llm_prompt(combined_text, knowledge)
        registry.set_job_details(job_id, combined_text, llm_prompt)

        registry.update_job_progress(job_id, 50)

        try:
            extraction_result = await asyncio.to_thread(extract_expenses, extracted_pdf, job.provider, bank_result.name)
        except ExtractionError as e:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_error(job_id, f"LLM extraction failed: {str(e)}")
            return

        if registry.is_job_cancelled(job_id):
            return

        registry.update_job_progress(job_id, 80)

        for transaction in extraction_result.transactions:
            transaction.bank = bank_result.name

        if registry.is_job_cancelled(job_id):
            return

        await asyncio.to_thread(
            persist_extraction,
            job_id,
            job.filename,
            bank_result.name,
            extraction_result.transactions,
            extraction_result.invoice_due_date
        )

        try:
            excel_file = await asyncio.to_thread(generate_excel, extraction_result.transactions, extraction_result.invoice_due_date)
            
            temp_dir = os.path.join(tempfile.gettempdir(), "invoicextractor")
            os.makedirs(temp_dir, exist_ok=True)
            
            base_name = job.filename.rsplit(".", 1)[0] if job.filename else "invoice"
            model_label = job.model_name or job.provider
            excel_filename = f"{base_name}_{job_id}_transactions_{model_label}.xlsx"
            excel_path = os.path.join(temp_dir, excel_filename)
            
            await asyncio.to_thread(_write_excel_file, excel_file, excel_path)
            
            if not registry.is_job_cancelled(job_id):
                registry.set_job_completed(job_id, excel_path)
        except Exception as e:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_error(job_id, f"Excel generation failed: {str(e)}")
    except Exception as e:
        try:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_error(job_id, f"Processing failed: {str(e)}")
        except Exception:
            pass


def start_processing_with_password(job_id: str, password: str):
    asyncio.create_task(process_job_with_password(job_id, password))
