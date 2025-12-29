from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ReceiptItem(BaseModel):
    item: str
    quantidade: float = Field(ge=0)
    valor_unitario: float = Field(ge=0)
    valor_total: float = Field(ge=0)
    desconto: float = Field(default=0, ge=0)

    @field_validator("quantidade", "valor_unitario", "valor_total", "desconto", mode="before")
    @classmethod
    def normalize_numeric(cls, v):
        if isinstance(v, str):
            v = v.replace(",", ".")
            v = float(v)
        return abs(float(v)) if v is not None else 0


class ReceiptExtractionResult(BaseModel):
    market_name: Optional[str] = None
    purchase_date: Optional[str] = None
    items: List[ReceiptItem]
