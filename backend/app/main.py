from pathlib import Path
import uuid
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, text
import httpx
from .config import settings
from .db import Base, engine, get_db
from .models import Invoice, InvoiceLine, AuditLog, ProcessingRun
from .schemas import ReviewUpdate
from .services.ollama import extract_invoice
from .services.validators import validate_extraction
from .services.rpa import run_rpa
from .logging_config import setup_logging

logger = setup_logging()

Base.metadata.create_all(engine)
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

app = FastAPI(title='SAP MIRO Invoice Processing API', version='3.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.cors_origins.split(',') if x.strip()],
    allow_credentials=True, allow_methods=['*'], allow_headers=['*']
)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    level = logger.warning if exc.status_code < 500 else logger.error
    level(str(exc.detail), extra={'stage': 'API', 'endpoint': request.url.path, 'method': request.method})
    detail = exc.detail if isinstance(exc.detail, dict) else {'message': str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={'detail': detail})

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception('Unhandled error', extra={'stage': 'API', 'endpoint': request.url.path, 'method': request.method})
    return JSONResponse(status_code=500, content={'detail': {'message': 'Internal server error. Please try again.'}})

@app.get('/health')
async def health():
    db_ok = 'ok'
    try:
        with engine.connect() as c: c.execute(text('SELECT 1'))
    except Exception as e:
        db_ok = 'unavailable'
        logger.error(f'DB health check failed: {e}', extra={'stage': 'DATABASE', 'endpoint': '/health', 'method': 'GET'})
    ollama_ok = 'skipped (demo mode)'
    if settings.extraction_mode == 'ollama':
        try:
            async with httpx.AsyncClient(timeout=3, trust_env=False) as c:
                r = await c.get(f"{settings.ollama_url.rstrip('/')}/api/tags")
                ollama_ok = 'ok' if r.status_code < 400 else f'unavailable (HTTP {r.status_code})'
        except Exception as e:
            ollama_ok = 'unavailable'
    return {'status': 'ok', 'extraction_mode': settings.extraction_mode, 'ollama_model': settings.ollama_model, 'database': db_ok, 'ollama': ollama_ok}

def serialize(inv: Invoice) -> dict:
    return {
        'id': inv.id, 'filename': inv.filename,
        'vendor': inv.vendor, 'invoice_number': inv.invoice_number,
        'invoice_date': inv.invoice_date, 'po_number': inv.po_number,
        'gstin': inv.gstin, 'hsn_sac': inv.hsn_sac,
        'vendor_code': inv.vendor_code, 'tax_code': inv.tax_code,
        'business_place': inv.business_place, 'currency': inv.currency,
        'subtotal': inv.subtotal, 'cgst': inv.cgst, 'sgst': inv.sgst,
        'igst': inv.igst, 'tax': inv.tax, 'total': inv.total,
        'confidence': inv.confidence, 'status': inv.status,
        'error_message': inv.error_message,
        'created_at': inv.created_at.isoformat() if inv.created_at else None,
        'lines': [{'id': l.id, 'item': l.item, 'quantity': l.quantity,
                   'rate': l.rate, 'tax_code': l.tax_code, 'amount': l.amount}
                  for l in (inv.lines or [])]
    }

@app.post('/api/invoices/upload')
async def upload_invoice(file: UploadFile = File(...), db: Session = Depends(get_db)):
    ctx = {'stage': 'UPLOAD', 'endpoint': '/api/invoices/upload', 'method': 'POST', 'filename_ctx': file.filename or '-'}
    logger.info('Upload received', extra=ctx)

    allowed_types = {'application/pdf', 'image/png', 'image/jpeg', 'image/jpg'}
    allowed_exts = {'.pdf', '.png', '.jpg', '.jpeg'}
    fname = file.filename or ''
    ext = Path(fname).suffix.lower()

    if not fname:
        raise HTTPException(400, 'File name is required')
    if file.content_type not in allowed_types and ext not in allowed_exts:
        raise HTTPException(400, 'Unsupported file type. Please upload PDF, JPG, JPEG, or PNG.')

    content = await file.read()
    if not content:
        raise HTTPException(400, 'Uploaded file is empty')
    if len(content) > settings.max_file_size_mb * 1024 * 1024:
        raise HTTPException(413, f'File exceeds {settings.max_file_size_mb} MB')

    safe = f'{uuid.uuid4().hex}_{Path(fname).name}'
    path = Path(settings.upload_dir) / safe
    path.write_bytes(content)

    try:
        try:
            data = await extract_invoice(str(path))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception('Extraction failed', extra={**ctx, 'stage': 'INVOICE_EXTRACTION'})
            raise HTTPException(500, 'Invoice extraction failed. Please try again.') from e

        if not data.get('invoice_number') or not data.get('vendor'):
            raise HTTPException(422, 'Vendor and invoice number could not be extracted')

        dup = db.scalar(select(Invoice).where(
            Invoice.invoice_number == data['invoice_number'],
            Invoice.vendor == data['vendor']
        ))
        if dup:
            raise HTTPException(409, f'Duplicate invoice detected. Existing invoice ID: {dup.id}')

        errors = validate_extraction(type('O', (), data)())

        try:
            inv = Invoice(
                filename=fname,
                vendor=data['vendor'],
                invoice_number=data['invoice_number'],
                invoice_date=data['invoice_date'],
                po_number=data['po_number'],
                gstin=data.get('gstin', ''),
                hsn_sac=data.get('hsn_sac', ''),
                vendor_code=data.get('vendor_code', ''),
                tax_code=data['tax_code'],
                business_place=data['business_place'],
                currency=data['currency'],
                subtotal=data['subtotal'],
                cgst=data.get('cgst', 0),
                sgst=data.get('sgst', 0),
                igst=data.get('igst', 0),
                tax=data['tax'],
                total=data['total'],
                confidence=data['confidence'],
                status='EXCEPTION' if errors else 'REVIEW',
                error_message='; '.join(errors) if errors else None,
            )
            db.add(inv)
            db.flush()
            for l in data['lines']:
                db.add(InvoiceLine(
                    invoice_id=inv.id,
                    item=l.get('item', ''),
                    quantity=l.get('quantity', 0),
                    rate=l.get('rate', 0),
                    tax_code=l.get('tax_code', ''),
                    amount=l.get('amount', 0),
                ))
            db.add(AuditLog(invoice_id=inv.id, action='UPLOAD_AND_EXTRACT',
                            detail={'mode': settings.extraction_mode, 'errors': errors}))
            db.commit()
            db.refresh(inv)
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.exception('DB insert failed', extra={**ctx, 'stage': 'DATABASE'})
            raise HTTPException(503, 'Could not save invoice. Database unavailable.') from e

        logger.info(f'Upload success id={inv.id} status={inv.status}', extra=ctx)
        return serialize(inv)
    finally:
        try: path.unlink()
        except: pass

@app.get('/api/invoices')
def list_invoices(status: str = '', search: str = '', db: Session = Depends(get_db)):
    q = select(Invoice).order_by(Invoice.created_at.desc())
    if status:
        q = q.where(Invoice.status == status)
    if search:
        like = f'%{search}%'
        q = q.where(or_(Invoice.vendor.ilike(like), Invoice.invoice_number.ilike(like), Invoice.po_number.ilike(like)))
    return [serialize(i) for i in db.scalars(q).all()]

@app.get('/api/invoices/{invoice_id}')
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv: raise HTTPException(404, 'Invoice not found')
    return serialize(inv)

@app.patch('/api/invoices/{invoice_id}')
def update_invoice(invoice_id: int, body: ReviewUpdate, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv: raise HTTPException(404, 'Invoice not found')
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(inv, k, v)
    db.add(AuditLog(invoice_id=inv.id, action='MANUAL_EDIT', detail=body.model_dump(exclude_none=True)))
    db.commit(); db.refresh(inv)
    return serialize(inv)

@app.post('/api/invoices/{invoice_id}/send-back')
def send_back(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv: raise HTTPException(404, 'Invoice not found')
    inv.status = 'EXCEPTION'
    db.add(AuditLog(invoice_id=inv.id, action='SEND_BACK', detail={}))
    db.commit(); return {'status': 'ok'}

@app.post('/api/invoices/{invoice_id}/approve')
def approve(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv: raise HTTPException(404, 'Invoice not found')
    inv.status = 'APPROVED'
    import uuid as _uuid
    session_id = str(_uuid.uuid4())
    run = ProcessingRun(invoice_id=inv.id, session_id=session_id, status='RUNNING',
                        detail={'steps': ['Bot session started', 'Processing invoice']})
    db.add(run)
    db.add(AuditLog(invoice_id=inv.id, action='APPROVED', detail={'session': session_id}))
    db.commit(); db.refresh(run)
    return {'status': 'ok', 'session_id': session_id, 'run_id': run.id}

@app.get('/api/invoices/{invoice_id}/processing')
def processing_status(invoice_id: int, db: Session = Depends(get_db)):
    run = db.scalar(select(ProcessingRun).where(ProcessingRun.invoice_id == invoice_id).order_by(ProcessingRun.created_at.desc()))
    if not run: raise HTTPException(404, 'No processing run found')
    return {'id': run.id, 'session_id': run.session_id, 'status': run.status,
            'current_step': run.current_step, 'sap_document': run.sap_document, 'detail': run.detail}
