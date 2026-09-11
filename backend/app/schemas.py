from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
class Line(BaseModel):
    item: str=''; quantity: float=0; tax_code: str=''; amount: float=0
class Extraction(BaseModel):
    vendor: str=''; invoice_number: str=''; invoice_date: str=''; po_number: str=''; tax_code: str=''; business_place: str=''; currency: str='INR'; subtotal: float=0; tax: float=0; total: float=0; confidence: float=0; lines: list[Line]=Field(default_factory=list)
class ReviewUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    vendor: Optional[str]=None; invoice_number: Optional[str]=None; invoice_date: Optional[str]=None; po_number: Optional[str]=None; tax_code: Optional[str]=None; business_place: Optional[str]=None; currency: Optional[str]=None; subtotal: Optional[float]=None; tax: Optional[float]=None; total: Optional[float]=None
