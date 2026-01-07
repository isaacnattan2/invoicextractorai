import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import List, Optional

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.schemas.transaction import Transaction

logger = logging.getLogger(__name__)

# Evita duplicação de logs
if not logger.handlers:

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # Handler de arquivo com rotação
    file_handler = RotatingFileHandler(
        filename="app.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    # (Opcional) handler de console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

MONGODB_URI = "mongodb://192.168.0.199:27017"
DATABASE_NAME = "invoice_extractor"
COLLECTION_NAME = "invoice_extractions"


def _normalize_string(s: str) -> str:
    """Normalize a string by stripping and collapsing whitespace."""
    if not s:
        return ""
    return " ".join(s.strip().split())


def _normalize_amount(amount: float) -> str:
    """Normalize amount to 2 decimal places as a string."""
    return f"{amount:.2f}"


def _transaction_to_canonical_tuple(t: Transaction) -> tuple:
    """
    Convert a transaction to a canonical tuple for hashing.
    
    Excludes non-deterministic fields: page, confidence, bank
    These fields can vary between runs even for the same invoice.
    """
    return (
        _normalize_string(t.date),
        _normalize_string(t.description),
        _normalize_amount(t.amount),
        _normalize_string(t.installment or ""),
        _normalize_string(t.currency),
    )


def generate_content_hash(transactions: List[Transaction]) -> str:
    """
    Generate a deterministic SHA-256 hash based on the extracted invoice content.
    
    The hash is:
    - Stable: same content always produces the same hash
    - Order-independent: transactions in different order produce the same hash
    - Excludes non-deterministic fields (page, confidence, bank)
    """
    canonical_tuples = [_transaction_to_canonical_tuple(t) for t in transactions]
    
    sorted_tuples = sorted(canonical_tuples)
    
    serialized = json.dumps(sorted_tuples, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    
    content_hash = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
    
    return content_hash


def persist_extraction(
    job_id: str,
    filename: str,
    bank: str,
    transactions: List[Transaction],
    invoice_due_date: Optional[str] = None
) -> bool:
    """
    Persist extracted invoice data to MongoDB with deduplication.
    
    Uses a deterministic content hash to prevent duplicate insertions.
    If a document with the same content hash already exists, insertion is skipped.
    
    Returns True if insertion was successful or skipped (duplicate), False on error.
    If insertion fails, logs the error with full stack trace but does not raise.
    """
    try:
        content_hash = generate_content_hash(transactions)
        
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        db = client[DATABASE_NAME]
        collection = db[COLLECTION_NAME]
        
        existing = collection.find_one({"content_hash": content_hash})
        if existing:
            logger.info(
                "Skipping duplicate insertion for job_id=%s, content_hash=%s already exists",
                job_id, content_hash
            )
            client.close()
            return True
        
        document = {
            "content_hash": content_hash,
            "job_id": job_id,
            "filename": filename,
            "bank": bank,
            "invoice_due_date": invoice_due_date,
            "extracted_at": datetime.utcnow(),
            "transactions": [t.model_dump() for t in transactions]
        }
        
        collection.insert_one(document)
        client.close()
        
        logger.info(
            "Successfully persisted extraction for job_id=%s, content_hash=%s to MongoDB",
            job_id, content_hash
        )
        return True
        
    except PyMongoError:
        logger.exception("Failed to persist extraction to MongoDB for job_id=%s", job_id)
        return False
    except Exception:
        logger.exception("Unexpected error persisting extraction to MongoDB for job_id=%s", job_id)
        return False
