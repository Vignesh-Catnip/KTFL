from datetime import datetime, timezone
from sqlalchemy import String, Text, Float, DateTime, ForeignKey, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def now(): return datetime.now(timezone.utc)
class Invoice(Base):
    __tablename__='invoices'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    filename: Mapped[str]=mapped_column(String(255))
    vendor: Mapped[str|None]=mapped_column(String(255))
    invoice_number: Mapped[str|None]=mapped_column(String(100),index=True)
    invoice_date: Mapped[str|None]=mapped_column(String(30))
    po_number: Mapped[str|None]=mapped_column(String(100))
    tax_code: Mapped[str|None]=mapped_column(String(30))
    business_place: Mapped[str|None]=mapped_column(String(100))
    currency: Mapped[str]=mapped_column(String(10),default='INR')
    subtotal: Mapped[float]=mapped_column(Float,default=0)
    tax: Mapped[float]=mapped_column(Float,default=0)
    total: Mapped[float]=mapped_column(Float,default=0)
    confidence: Mapped[float]=mapped_column(Float,default=0)
    status: Mapped[str]=mapped_column(String(40),default='REVIEW',index=True)
    error_message: Mapped[str|None]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)
    lines=relationship('InvoiceLine',back_populates='invoice',cascade='all, delete-orphan')
class InvoiceLine(Base):
    __tablename__='invoice_lines'
    id: Mapped[int]=mapped_column(primary_key=True)
    invoice_id: Mapped[int]=mapped_column(ForeignKey('invoices.id',ondelete='CASCADE'))
    item: Mapped[str]=mapped_column(String(255))
    quantity: Mapped[float]=mapped_column(Float,default=0)
    tax_code: Mapped[str]=mapped_column(String(30),default='')
    amount: Mapped[float]=mapped_column(Float,default=0)
    invoice=relationship('Invoice',back_populates='lines')
class ProcessingRun(Base):
    __tablename__='processing_runs'
    id: Mapped[int]=mapped_column(primary_key=True)
    invoice_id: Mapped[int]=mapped_column(ForeignKey('invoices.id',ondelete='CASCADE'))
    session_id: Mapped[str]=mapped_column(String(80),index=True)
    status: Mapped[str]=mapped_column(String(30),default='RUNNING')
    current_step: Mapped[str]=mapped_column(String(120),default='Bot session started on VM')
    sap_document: Mapped[str|None]=mapped_column(String(80))
    detail: Mapped[dict]=mapped_column(JSON,default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)
class AuditLog(Base):
    __tablename__='audit_logs'
    id: Mapped[int]=mapped_column(primary_key=True)
    invoice_id: Mapped[int|None]=mapped_column(ForeignKey('invoices.id',ondelete='SET NULL'))
    action: Mapped[str]=mapped_column(String(100))
    detail: Mapped[dict]=mapped_column(JSON,default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
