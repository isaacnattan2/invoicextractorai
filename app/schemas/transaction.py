from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Transaction(BaseModel):
    date: str
    description: str
    amount: float = Field(gt=0)
    installment: Optional[str] = None
    currency: str = "BRL"
    page: int
    confidence: float = Field(ge=0.0, le=1.0)
    bank: str = "Unknown"

    @field_validator("amount", mode="before")
    @classmethod
    def normalize_amount(cls, v):
        if isinstance(v, str):
            v = v.replace(",", ".")
            v = float(v)
        return abs(float(v))


class ExtractionResult(BaseModel):
    invoice_due_date: Optional[str] = None
    transactions: List[Transaction]


class UploadResponseWithTransactions(BaseModel):
    message: str
    filename: str
    num_pages: int
    total_characters: int
    transactions: List[Transaction]
