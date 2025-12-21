import asyncio
import os
import queue

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sse_starlette.sse import EventSourceResponse

from app.services.job_registry import get_registry
from app.services.processor import start_processing

import re

router = APIRouter()


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    provider: str = Form(default="offline")
):
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only PDF files are accepted."
        )

    if provider not in ("offline", "online"):
        provider = "offline"

    contents = await file.read()
    filename = file.filename or "invoice.pdf"

    registry = get_registry()
    job = registry.create_job(filename=filename, provider=provider, pdf_content=contents)

    start_processing(job.id)

    return RedirectResponse(url="/", status_code=303)


@router.get("/jobs")
async def list_jobs():
    registry = get_registry()
    jobs = registry.get_all_jobs()
    return JSONResponse(content={"jobs": jobs})


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    registry = get_registry()
    success = registry.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel this job")
    return RedirectResponse(url="/", status_code=303)


@router.get("/jobs/{job_id}/download")
async def download_job(job_id: str):
    registry = get_registry()
    job = registry.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if not job.excel_path or not os.path.exists(job.excel_path):
        raise HTTPException(status_code=404, detail="Excel file not available")
    
    base_name = job.filename.rsplit(".", 1)[0] if job.filename else "invoice"

    model_label = job.model_name or job.provider
    excel_filename = f"{base_name}_transactions_{model_label}"
    sanitized_filename = sanitize_filename_part(excel_filename)
    download_filename = f"{sanitized_filename}.xlsx"
    
    return FileResponse(
        path=job.excel_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=download_filename
    )

def sanitize_filename_part(value: str) -> str:
    """
    Makes a string safe to be used as part of a filename.
    Replaces characters that are invalid on Windows/Linux.
    """
    if not value:
        return "unknown_model"

    # Replace . and : explicitly
    value = value.replace(".", "_").replace(":", "_")

    # Optional: remove any remaining unsafe characters
    value = re.sub(r"[^a-zA-Z0-9_\-]", "_", value)

    return value

@router.get("/events")
async def sse_events():
    registry = get_registry()
    subscriber_queue = registry.subscribe()

    async def event_generator():
        try:
            while True:
                try:
                    data = await asyncio.to_thread(subscriber_queue.get, True, 30)
                    yield {"event": "job_update", "data": data}
                except queue.Empty:
                    yield {"event": "ping", "data": ""}
        except GeneratorExit:
            registry.unsubscribe(subscriber_queue)

    return EventSourceResponse(event_generator())
