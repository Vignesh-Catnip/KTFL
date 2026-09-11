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

Base.metadata.create_all(engine); Path(settings.upload_dir).mkdir(parents=True,exist_ok=True)
app=FastAPI(title='SAP MIRO Invoice Processing API',version='3.0.0')
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings.cors_origins.split(',') if x.strip()],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Client-facing message stays as-is (already sanitized at raise sites).
    # Server-side we additionally log it with the processing stage so it's
    # traceable in logs/error.log.
    level = logger.warning if exc.status_code < 500 else logger.error
    level(str(exc.detail), extra={'stage': 'API', 'endpoint': request.url.path, 'method': request.method})
    detail = exc.detail if isinstance(exc.detail, dict) else {'message': str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={'detail': detail})

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception('Unhandled server error', extra={'stage': 'API', 'endpoint': request.url.path, 'method': request.method})
    return JSONResponse(status_code=500, content={'detail': {'message': 'Internal server error. Please try again or contact support.'}})

@app.get('/health')
async def health():
    db_status = 'ok'
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:
        db_status = 'unavailable'
        logger.error(f'PostgreSQL health check failed: {exc}', extra={'stage': 'DATABASE', 'endpoint': '/health', 'method': 'GET'})
    ollama_status = 'skipped (demo mode)'
    if settings.extraction_mode == 'ollama':
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{settings.ollama_url.rstrip('/')}/api/tags")
                ollama_status = 'ok' if r.status_code < 400 else f'unavailable (HTTP {r.status_code})'
        except Exception as exc:
            ollama_status = 'unavailable'
            logger.error(f'Ollama health check failed: {exc}', extra={'stage': 'OLLAMA', 'endpoint': '/health', 'method': 'GET'})
    return {'status':'ok','extraction_mode':settings.extraction_mode,'ollama_model':settings.ollama_model,'rpa_mode':settings.rpa_mode,'database':db_status,'ollama':ollama_status}
def serialize(i):
    return {'id':i.id,'filename':i.filename,'vendor':i.vendor,'invoice_number':i.invoice_number,'invoice_date':i.invoice_date,'po_number':i.po_number,'tax_code':i.tax_code,'business_place':i.business_place,'currency':i.currency,'subtotal':i.subtotal,'tax':i.tax,'total':i.total,'confidence':i.confidence,'status':i.status,'error_message':i.error_message,'created_at':i.created_at.isoformat() if i.created_at else None,'lines':[{'id':l.id,'item':l.item,'quantity':l.quantity,'tax_code':l.tax_code,'amount':l.amount} for l in i.lines]}
@app.post('/api/invoices/upload')
async def upload_invoice(file: UploadFile=File(...),db:Session=Depends(get_db)):
    stage_ctx={'endpoint':'/api/invoices/upload','method':'POST','filename_ctx':file.filename or '-'}
    logger.info('Upload received', extra={'stage':'UPLOAD', **stage_ctx})
    allowed_types={'application/pdf','image/png','image/jpeg','image/jpg'}
    allowed_exts={'.pdf','.png','.jpg','.jpeg'}
    ext=Path(file.filename or '').suffix.lower()
    if not file.filename:
        logger.warning('Upload rejected: missing filename', extra={'stage':'FILE_VALIDATION', **stage_ctx})
        raise HTTPException(400,'File name is required')
    if file.content_type not in allowed_types and ext not in allowed_exts:
        logger.warning(f'Upload rejected: unsupported type (content_type={file.content_type!r}, ext={ext!r})', extra={'stage':'FILE_VALIDATION', **stage_ctx})
        raise HTTPException(400,'Unsupported file type. Please upload PDF, JPG, JPEG, or PNG.')
    content=await file.read()
    if not content:
        logger.warning('Upload rejected: empty file', extra={'stage':'FILE_VALIDATION', **stage_ctx})
        raise HTTPException(400,'Uploaded file is empty')
    if len(content)>settings.max_file_size_mb*1024*1024:
        logger.warning('Upload rejected: file too large', extra={'stage':'FILE_VALIDATION', **stage_ctx})
        raise HTTPException(413,f'File exceeds {settings.max_file_size_mb} MB')
    safe=f'{uuid.uuid4().hex}_{Path(file.filename).name}'; path=Path(settings.upload_dir)/safe; path.write_bytes(content)
    try:
        try:
            data=await extract_invoice(str(path))
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception('Invoice extraction pipeline failed', extra={'stage':'INVOICE_EXTRACTION', **stage_ctx})
            raise HTTPException(500,'Invoice extraction failed. Please try again or contact support.') from exc
        if not data.get('invoice_number') or not data.get('vendor'):
            logger.warning('Extraction incomplete: missing vendor/invoice_number', extra={'stage':'INVOICE_EXTRACTION', **stage_ctx})
            raise HTTPException(422,'Vendor and invoice number could not be reliably extracted')
        duplicate=db.scalar(select(Invoice).where(Invoice.invoice_number==data['invoice_number'],Invoice.vendor==data['vendor']))
        if duplicate: raise HTTPException(409,f'Duplicate invoice detected. Existing invoice ID: {duplicate.id}')
        errors=validate_extraction(type('Obj',(),data)())
        try:
            inv=Invoice(filename=file.filename,vendor=data['vendor'],invoice_number=data['invoice_number'],invoice_date=data['invoice_date'],po_number=data['po_number'],tax_code=data['tax_code'],business_place=data['business_place'],currency=data['currency'],subtotal=data['subtotal'],tax=data['tax'],total=data['total'],confidence=data['confidence'],status='EXCEPTION' if errors else 'REVIEW',error_message='; '.join(errors) if errors else None)
            db.add(inv); db.flush()
            for l in data['lines']: db.add(InvoiceLine(invoice_id=inv.id,**l))
            db.add(AuditLog(invoice_id=inv.id,action='UPLOAD_AND_EXTRACT',detail={'mode':settings.extraction_mode,'errors':errors}))
            db.commit(); db.refresh(inv)
        except HTTPException:
            raise
        except Exception as exc:
            db.rollback()
            logger.exception('Database insertion failed', extra={'stage':'DATABASE', **stage_ctx})
            raise HTTPException(503,'Could not save invoice. Database unavailable, please try again shortly.') from exc
        logger.info(f'Upload processed successfully, invoice_id={inv.id}, status={inv.status}', extra={'stage':'UPLOAD', **stage_ctx})
        return serialize(inv)
    finally:
        try:path.unlink()
        except OSError:pass
@app.get('/api/invoices')
def list_invoices(status: str|None=Query(None),search: str|None=Query(None),db:Session=Depends(get_db)):
    q=select(Invoice).order_by(Invoice.id.desc())
    if status:q=q.where(Invoice.status==status.upper())
    if search:
        s=f'%{search}%'; q=q.where(or_(Invoice.vendor.ilike(s),Invoice.invoice_number.ilike(s),Invoice.po_number.ilike(s)))
    return [serialize(x) for x in db.scalars(q).unique().all()]
@app.get('/api/invoices/{invoice_id}')
def get_invoice(invoice_id:int,db:Session=Depends(get_db)):
    i=db.get(Invoice,invoice_id)
    if not i: raise HTTPException(404,'Invoice not found')
    return serialize(i)
@app.patch('/api/invoices/{invoice_id}')
def update_invoice(invoice_id:int,payload:ReviewUpdate,db:Session=Depends(get_db)):
    i=db.get(Invoice,invoice_id)
    if not i: raise HTTPException(404,'Invoice not found')
    for k,v in payload.model_dump(exclude_none=True).items(): setattr(i,k,v)
    i.status='REVIEW'; i.error_message=None; db.add(AuditLog(invoice_id=i.id,action='HUMAN_UPDATE',detail=payload.model_dump(exclude_none=True))); db.commit(); db.refresh(i); return serialize(i)
@app.post('/api/invoices/{invoice_id}/send-back')
def send_back(invoice_id:int,db:Session=Depends(get_db)):
    i=db.get(Invoice,invoice_id)
    if not i: raise HTTPException(404,'Invoice not found')
    i.status='EXCEPTION'; i.error_message='Sent back for human correction'; db.add(AuditLog(invoice_id=i.id,action='SEND_BACK',detail={})); db.commit(); return serialize(i)
@app.post('/api/invoices/{invoice_id}/approve')
async def approve(invoice_id:int,db:Session=Depends(get_db)):
    i=db.get(Invoice,invoice_id)
    if not i: raise HTTPException(404,'Invoice not found')
    data=type('Obj',(),{'vendor':i.vendor,'invoice_number':i.invoice_number,'invoice_date':i.invoice_date,'total':i.total,'tax':i.tax,'confidence':i.confidence,'lines':[type('L',(),{'amount':l.amount})() for l in i.lines]})()
    errors=validate_extraction(data)
    if errors: raise HTTPException(422,detail={'message':'Invoice failed validation','errors':errors})
    i.status='PROCESSING'; run=ProcessingRun(invoice_id=i.id,session_id=f'RPA-{uuid.uuid4().hex[:12].upper()}',status='RUNNING',current_step='Bot session started on VM'); db.add(run); db.add(AuditLog(invoice_id=i.id,action='APPROVED',detail={})); db.commit(); db.refresh(run)
    result=await run_rpa(i.id); run.status='COMPLETED' if result['status']=='COMPLETED' else 'FAILED'; run.current_step=result.get('steps', [''])[-1] if result.get('steps') else result.get('message',''); run.sap_document=result.get('sap_document'); run.detail=result; i.status='PROCESSED' if result['status']=='COMPLETED' else 'EXCEPTION'; i.error_message=None if result['status']=='COMPLETED' else result.get('message'); db.add(AuditLog(invoice_id=i.id,action='RPA_RESULT',detail=result)); db.commit(); return {'invoice':serialize(i),'processing':result}
@app.get('/api/invoices/{invoice_id}/processing')
def processing(invoice_id:int,db:Session=Depends(get_db)):
    run=db.scalar(select(ProcessingRun).where(ProcessingRun.invoice_id==invoice_id).order_by(ProcessingRun.id.desc()))
    if not run: raise HTTPException(404,'No processing run found')
    return {'id':run.id,'invoice_id':invoice_id,'session_id':run.session_id,'status':run.status,'current_step':run.current_step,'sap_document':run.sap_document,'detail':run.detail}