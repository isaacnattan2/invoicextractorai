import logging
from datetime import datetime
from typing import List

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.schemas.transaction import Transaction

logger = logging.getLogger(__name__)

MONGODB_URI = "mongodb://localhost:27017"
DATABASE_NAME = "invoice_extractor"
COLLECTION_NAME = "invoice_extractions"


def persist_extraction(
    job_id: str,
    filename: str,
    bank: str,
    transactions: List[Transaction]
) -> bool:
    """
    Persist extracted invoice data to MongoDB.
    
    Returns True if insertion was successful, False otherwise.
    If insertion fails, logs the error with full stack trace but does not raise.
    """
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        db = client[DATABASE_NAME]
        collection = db[COLLECTION_NAME]
        
        document = {
            "job_id": job_id,
            "filename": filename,
            "bank": bank,
            "extracted_at": datetime.utcnow(),
            "transactions": [t.model_dump() for t in transactions]
        }
        
        collection.insert_one(document)
        client.close()
        
        logger.info("Successfully persisted extraction for job_id=%s to MongoDB", job_id)
        return True
        
    except PyMongoError:
        logger.exception("Failed to persist extraction to MongoDB for job_id=%s", job_id)
        return False
    except Exception:
        logger.exception("Unexpected error persisting extraction to MongoDB for job_id=%s", job_id)
        return False
