import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from app.database import Base

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    file_path = Column(String, nullable=False)
    vendor_name = Column(String, nullable=False)
    invoice_number = Column(String, nullable=False)
    invoice_date = Column(String, nullable=True)
    due_date = Column(String, nullable=True)
    line_items_json = Column(Text, nullable=False)  # JSON-encoded array of items
    subtotal = Column(Float, nullable=True)
    tax = Column(Float, nullable=True)
    total = Column(Float, nullable=True)
    flags_json = Column(Text, nullable=False)        # JSON-encoded array of flags
    status = Column(String, nullable=False)          # "approved" or "needs_review"
