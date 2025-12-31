import hashlib
import json
import logging
from datetime import datetime
from typing import List, Optional

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.schemas.receipt import ReceiptItem

logger = logging.getLogger(__name__)

MONGODB_URI = "mongodb://192.168.0.199:27017"
DATABASE_NAME = "invoice_extractor"
COLLECTION_NAME = "receipt_extractions"


def _normalize_string(s: str) -> str:
    if not s:
        return ""
    return " ".join(s.strip().split())


def _normalize_amount(amount: float) -> str:
    return f"{amount:.2f}"


def _item_to_canonical_tuple(item: ReceiptItem) -> tuple:
    return (
        _normalize_string(item.item),
        _normalize_amount(item.quantidade),
        _normalize_amount(item.valor_total),
    )


def generate_receipt_content_hash(
    items: List[ReceiptItem],
    market_name: Optional[str] = None,
    purchase_date: Optional[str] = None
) -> str:
    canonical_tuples = [_item_to_canonical_tuple(item) for item in items]
    sorted_tuples = sorted(canonical_tuples)
    
    hash_data = {
        "market_name": _normalize_string(market_name) if market_name else "",
        "purchase_date": _normalize_string(purchase_date) if purchase_date else "",
        "items": sorted_tuples
    }
    
    serialized = json.dumps(hash_data, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    content_hash = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
    
    return content_hash


def persist_receipt_extraction(
    job_id: str,
    market_name: Optional[str],
    purchase_date: Optional[str],
    items: List[ReceiptItem]
) -> bool:
    try:
        content_hash = generate_receipt_content_hash(items, market_name, purchase_date)
        
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        db = client[DATABASE_NAME]
        collection = db[COLLECTION_NAME]
        
        existing = collection.find_one({"content_hash": content_hash})
        if existing:
            logger.info(
                "Skipping duplicate receipt insertion for job_id=%s, content_hash=%s already exists",
                job_id, content_hash
            )
            client.close()
            return True
        
        document = {
            "content_hash": content_hash,
            "job_id": job_id,
            "market_name": market_name,
            "purchase_date": purchase_date,
            "extracted_at": datetime.utcnow(),
            "items": [item.model_dump() for item in items]
        }
        
        collection.insert_one(document)
        client.close()
        
        logger.info(
            "Successfully persisted receipt extraction for job_id=%s, content_hash=%s to MongoDB",
            job_id, content_hash
        )
        return True
        
    except PyMongoError:
        logger.exception("Failed to persist receipt extraction to MongoDB for job_id=%s", job_id)
        return False
    except Exception:
        logger.exception("Unexpected error persisting receipt extraction to MongoDB for job_id=%s", job_id)
        return False
