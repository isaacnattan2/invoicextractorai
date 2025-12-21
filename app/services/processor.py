import asyncio
import os
import tempfile
from io import BytesIO

from app.services.bank_identifier import identify_bank
from app.services.excel_generator import generate_excel
from app.services.expense_extractor import ExtractionError, extract_expenses, combine_pages_text, build_llm_prompt
from app.services.job_registry import JobStatus, get_registry
from app.services.pdf_extractor import PDFExtractionError, extract_text_from_pdf


def _extract_pdf_text(pdf_content: bytes):
    file_stream = BytesIO(pdf_content)
    return extract_text_from_pdf(file_stream)


def _write_excel_file(excel_file, excel_path: str):
    with open(excel_path, "wb") as f:
        f.write(excel_file.getvalue())


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
        except PDFExtractionError as e:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_error(job_id, f"PDF extraction failed: {str(e)}")
            return

        if registry.is_job_cancelled(job_id):
            return

        registry.update_job_progress(job_id, 20)

        combined_text = combine_pages_text(extracted_pdf)
        llm_prompt = build_llm_prompt(combined_text)
        registry.set_job_details(job_id, combined_text, llm_prompt)

        if registry.is_job_cancelled(job_id):
            return

        registry.update_job_progress(job_id, 50)

        try:
            bank_result = await asyncio.to_thread(identify_bank, extracted_pdf, job.provider)
        except Exception:
            bank_result = type('BankResult', (), {'name': 'Unknown'})()

        if registry.is_job_cancelled(job_id):
            return

        try:
            extraction_result = await asyncio.to_thread(extract_expenses, extracted_pdf, job.provider)
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

        try:
            excel_file = await asyncio.to_thread(generate_excel, extraction_result.transactions)
            
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
