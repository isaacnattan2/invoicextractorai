from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ReceiptItem(BaseModel):
    item_id: Optional[str] = None
    item: str
    quantidade: float = Field(ge=0)
    valor_unitario: float = Field(ge=0)
    valor_total: float = Field(ge=0)
    desconto: float = Field(default=0, ge=0)
    ean: Optional[str] = None

    @field_validator("quantidade", "valor_unitario", "valor_total", "desconto", mode="before")
    @classmethod
    def normalize_numeric(cls, v):
        if isinstance(v, str):
            v = v.replace(",", ".")
            v = float(v)
        return abs(float(v)) if v is not None else 0

    @field_validator("item_id", "ean", mode="before")
    @classmethod
    def empty_string_to_none(cls, v):
        if v == "":
            return None
        return v


class ReceiptExtractionResult(BaseModel):
    market_name: Optional[str] = None
    cnpj: Optional[str] = None
    address: Optional[str] = None
    access_key: Optional[str] = None
    issue_date: Optional[str] = None
    purchase_date: Optional[str] = None
    items: List[ReceiptItem]

    @field_validator("market_name", "cnpj", "address", "access_key", "issue_date", "purchase_date", mode="before")
    @classmethod
    def empty_string_to_none(cls, v):
        if v == "":
            return None
        return v
