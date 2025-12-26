import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pymongo import MongoClient
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

MONGODB_URI = "mongodb://localhost:27017"
DATABASE_NAME = "invoice_extractor"
COLLECTION_NAME = "invoice_extractions"

router = APIRouter()


@router.get("/invoices")
async def query_invoices(
    start_date: Optional[str] = Query(
        default=None,
        description="Start date filter (YYYY-MM-DD). If omitted with end_date, defaults to last 3 months."
    ),
    end_date: Optional[str] = Query(
        default=None,
        description="End date filter (YYYY-MM-DD). Cannot be used alone without start_date."
    ),
    bank: Optional[str] = Query(
        default=None,
        description="Filter by bank name (exact match)."
    ),
    description: Optional[str] = Query(
        default=None,
        description="Filter by transaction description (partial, case-insensitive match)."
    )
):
    """
    Query invoice data from MongoDB with optional filtering.
    
    Date filter rules:
    - Both start_date and end_date: Return invoices within inclusive date range
    - Only start_date: Return all invoices from start_date forward
    - Neither: Default to last 3 months
    - Only end_date: REJECTED (HTTP 400)
    
    Optional filters:
    - bank: Filter by bank name
    - description: Partial/contains match on transaction descriptions (case-insensitive)
    """
    if end_date is not None and start_date is None:
        raise HTTPException(
            status_code=400,
            detail="Filtering by end_date alone is not allowed. Please provide start_date or omit both date parameters."
        )
    
    try:
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start_dt = datetime.utcnow() - timedelta(days=90)
        
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
        else:
            end_dt = None
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format. Use YYYY-MM-DD. Error: {str(e)}"
        )
    
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        db = client[DATABASE_NAME]
        collection = db[COLLECTION_NAME]
        
        query = {}
        
        if end_dt:
            query["extracted_at"] = {
                "$gte": start_dt,
                "$lte": end_dt
            }
        else:
            query["extracted_at"] = {"$gte": start_dt}
        
        if bank:
            query["bank"] = bank
        
        cursor = collection.find(query)
        
        results = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            
            if "extracted_at" in doc and isinstance(doc["extracted_at"], datetime):
                doc["extracted_at"] = doc["extracted_at"].isoformat()
            
            if description:
                description_lower = description.lower()
                filtered_transactions = [
                    t for t in doc.get("transactions", [])
                    if description_lower in t.get("description", "").lower()
                ]
                if filtered_transactions:
                    doc["transactions"] = filtered_transactions
                    results.append(doc)
            else:
                results.append(doc)
        
        client.close()
        
        return JSONResponse(content={"invoices": results, "count": len(results)})
        
    except PyMongoError:
        logger.exception("Failed to query invoices from MongoDB")
        raise HTTPException(
            status_code=500,
            detail="Database error occurred while querying invoices."
        )
    except Exception:
        logger.exception("Unexpected error querying invoices from MongoDB")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while querying invoices."
        )
