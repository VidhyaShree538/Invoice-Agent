from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class LineItemSchema(BaseModel):
    description: str
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None

class ValidationFlag(BaseModel):
    type: str
    detail: str

# Response schema returned from POST /api/invoices/upload
class InvoiceUploadResponse(BaseModel):
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    line_items: List[LineItemSchema] = []
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    flags: List[ValidationFlag] = []
    status: str
    file_path: str

# Input schema for POST /api/invoices (saving invoice)
class InvoiceCreate(BaseModel):
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    line_items: List[LineItemSchema] = []
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    file_path: str

# Full Invoice Response Schema
class InvoiceResponse(BaseModel):
    id: int
    created_at: datetime
    file_path: str
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    line_items: List[LineItemSchema] = []
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    flags: List[ValidationFlag] = []
    status: str

    class Config:
        from_attributes = True

# Analytics Response Schema
class VendorSpend(BaseModel):
    vendor_name: str
    total_spend: float

class StatusCounts(BaseModel):
    approved: int
    needs_review: int

class AnalyticsResponse(BaseModel):
    spend_by_vendor: List[VendorSpend]
    status_counts: StatusCounts
