from datetime import datetime
from typing import Optional, Union

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.services.job_registry import get_registry
from app.services.receipt_processor import start_receipt_processing

MONGODB_URI = "mongodb://192.168.0.199:27017"
DATABASE_NAME = "invoice_extractor"
COLLECTION_NAME = "ocr_extraction"

router = APIRouter()


class ExtractionImportRequest(BaseModel):
    source: str
    key_sefaz: Optional[str] = None
    ocr_extraction: str
    created_at: str
    hash: Optional[str] = None


def normalize_start_extraction(value: Union[str, bool, int, None]) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    if isinstance(value, str):
        return value.lower() in ("true", "1")
    return False


VALID_PROVIDERS = ["llama3.1:8b", "gpt-4o-mini"]


def normalize_provider(value: Optional[str]) -> str:
    if value is None:
        return "offline"
    if value == "gpt-4o-mini":
        return "online"
    if value == "llama3.1:8b":
        return "offline"
    return "offline"


@router.post("/api/extraction/import")
async def import_extraction(
    request: ExtractionImportRequest,
    start_extraction: Union[str, bool, int] = Query(...),
    provider: Optional[str] = Query(default=None, description="LLM provider: llama3.1:8b or gpt-4o-mini")
):
    if not request.source:
        raise HTTPException(status_code=400, detail="source is required")
    if not request.ocr_extraction:
        raise HTTPException(status_code=400, detail="ocr_extraction is required")
    if not request.created_at:
        raise HTTPException(status_code=400, detail="created_at is required")
    if request.key_sefaz is None and not request.hash:
        raise HTTPException(status_code=400, detail="hash is required when key_sefaz is null")

    should_start_extraction = normalize_start_extraction(start_extraction)

    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        db = client[DATABASE_NAME]
        collection = db[COLLECTION_NAME]

        if request.key_sefaz is not None:
            existing = collection.find_one({"key_sefaz": request.key_sefaz})
        else:
            existing = collection.find_one({"hash": request.hash})

        inserted = False
        if existing is None:
            document = {
                "source": request.source,
                "key_sefaz": request.key_sefaz,
                "ocr_extraction": request.ocr_extraction,
                "created_at": request.created_at
            }
            if request.key_sefaz is None and request.hash:
                document["hash"] = request.hash

            collection.insert_one(document)
            inserted = True

        client.close()

    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    extraction_triggered = False
    if should_start_extraction:
        normalized_provider = normalize_provider(provider)
        registry = get_registry()
        job = registry.create_job_from_text(
            provider=normalized_provider,
            raw_text=request.ocr_extraction
        )
        start_receipt_processing(job.id)
        extraction_triggered = True

    return JSONResponse(
        status_code=200,
        content={
            "received": True,
            "inserted": inserted,
            "extraction_triggered": extraction_triggered
        }
    )
