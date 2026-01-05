import asyncio
import os
import tempfile

from app.services.job_registry import JobStatus, get_registry
from app.services.receipt_extractor import ReceiptExtractionError, extract_receipt_items, build_receipt_llm_prompt
from app.services.segmented_receipt_extractor import SegmentedExtractionError, extract_receipt_segmented
from app.services.receipt_excel_generator import generate_receipt_excel
from app.services.receipt_persistence import persist_receipt_extraction

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

logger = logging.getLogger(__name__)


def _write_excel_file(excel_file, excel_path: str):
    with open(excel_path, "wb") as f:
        f.write(excel_file.getvalue())


async def process_receipt_job(job_id: str):
    registry = get_registry()
    
    try:
        job = registry.get_job(job_id)
        
        if not job or not job.extracted_text:
            registry.set_job_error(job_id, "Job not found or receipt text content missing")
            return

        if registry.is_job_cancelled(job_id):
            return

        registry.update_job_status(job_id, JobStatus.PROCESSING, progress=0)

        raw_text = job.extracted_text

        if registry.is_job_cancelled(job_id):
            return

        registry.update_job_progress(job_id, 20)

        llm_prompt = build_receipt_llm_prompt(raw_text)
        registry.set_job_details(job_id, raw_text, llm_prompt)

        registry.update_job_progress(job_id, 30)

        try:
            if job.enable_segmented_extraction:
                extraction_result = await asyncio.to_thread(
                    extract_receipt_segmented,
                    raw_text,
                    job.provider,
                    job.enable_segment_chunking,
                    job.segment_chunk_size
                )
            else:
                extraction_result = await asyncio.to_thread(extract_receipt_items, raw_text, job.provider)
        except (ReceiptExtractionError, SegmentedExtractionError) as e:
            if not registry.is_job_cancelled(job_id):
                registry.set_job_error(job_id, f"LLM extraction failed: {str(e)}")
            return

        if registry.is_job_cancelled(job_id):
            return

        registry.update_job_progress(job_id, 70)

        if registry.is_job_cancelled(job_id):
            return

        await asyncio.to_thread(
            persist_receipt_extraction,
            job_id,
            extraction_result.market_name,
            extraction_result.cnpj,
            extraction_result.address,
            extraction_result.access_key,
            extraction_result.issue_date,
            extraction_result.items
        )

        registry.update_job_progress(job_id, 85)

        try:
            excel_file = await asyncio.to_thread(
                generate_receipt_excel,
                extraction_result.items,
                extraction_result.market_name,
                extraction_result.cnpj,
                extraction_result.address,
                extraction_result.access_key,
                extraction_result.issue_date
            )
            
            temp_dir = os.path.join(tempfile.gettempdir(), "invoicextractor")
            os.makedirs(temp_dir, exist_ok=True)
            
            base_name = "receipt"
            model_label = job.model_name or job.provider
            excel_filename = f"{base_name}_{job_id}_items_{model_label}.xlsx"
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


def start_receipt_processing(job_id: str):
    asyncio.create_task(process_receipt_job(job_id))
