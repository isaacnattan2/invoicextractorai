import os
import tempfile
import threading
from io import BytesIO

from app.services.bank_identifier import identify_bank
from app.services.excel_generator import generate_excel
from app.services.expense_extractor import ExtractionError, extract_expenses
from app.services.job_registry import JobStatus, get_registry
from app.services.pdf_extractor import PDFExtractionError, extract_text_from_pdf


def process_job(job_id: str):
    registry = get_registry()
    job = registry.get_job(job_id)
    
    if not job or not job.pdf_content:
        registry.set_job_error(job_id, "Job not found or PDF content missing")
        return

    if registry.is_job_cancelled(job_id):
        return

    registry.update_job_status(job_id, JobStatus.PROCESSING, progress=0)

    try:
        file_stream = BytesIO(job.pdf_content)
        extracted_pdf = extract_text_from_pdf(file_stream)
        registry.update_job_progress(job_id, 20)
    except PDFExtractionError as e:
        registry.set_job_error(job_id, f"PDF extraction failed: {str(e)}")
        return

    if registry.is_job_cancelled(job_id):
        return

    registry.update_job_progress(job_id, 50)

    if registry.is_job_cancelled(job_id):
        return

    try:
        bank_result = identify_bank(extracted_pdf, provider=job.provider)
    except Exception as e:
        bank_result = type('BankResult', (), {'name': 'Unknown'})()

    if registry.is_job_cancelled(job_id):
        return

    try:
        extraction_result = extract_expenses(extracted_pdf, provider=job.provider)
    except ExtractionError as e:
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
        excel_file = generate_excel(extraction_result.transactions)
        
        temp_dir = os.path.join(tempfile.gettempdir(), "invoicextractor")
        os.makedirs(temp_dir, exist_ok=True)
        
        base_name = job.filename.rsplit(".", 1)[0] if job.filename else "invoice"
        excel_filename = f"{base_name}_{job_id}_transactions.xlsx"
        excel_path = os.path.join(temp_dir, excel_filename)
        
        with open(excel_path, "wb") as f:
            f.write(excel_file.getvalue())
        
        registry.set_job_completed(job_id, excel_path)
    except Exception as e:
        registry.set_job_error(job_id, f"Excel generation failed: {str(e)}")


def start_processing(job_id: str):
    thread = threading.Thread(target=process_job, args=(job_id,), daemon=True)
    thread.start()
