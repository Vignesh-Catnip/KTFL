"""
Invoice extraction via Ollama vision model.
Supports PDF (via PyMuPDF) and images (JPG/PNG).
8K context window. trust_env=False to bypass corporate proxy.
"""
import base64, json, re
from pathlib import Path
import httpx
from fastapi import HTTPException
from ..config import settings
from .demo_extractor import demo_extract

SUPPORTED_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}
SUPPORTED_PDF_EXTS = {'.pdf'}

SYSTEM_PROMPT = """You are an invoice data extraction engine.

Read the invoice image carefully and extract ALL visible fields.

Return ONLY a valid JSON object. No markdown, no code fences, no explanation.
If a value is not visible, return empty string "" for text or 0 for numbers.
Never invent values. Dates must be YYYY-MM-DD format. Amounts must be plain numbers only.

Return exactly this JSON structure:
{
  "vendor": "",
  "invoice_number": "",
  "invoice_date": "",
  "po_number": "",
  "gstin": "",
  "hsn_sac": "",
  "vendor_code": "",
  "tax_code": "",
  "business_place": "",
  "currency": "INR",
  "subtotal": 0,
  "cgst": 0,
  "sgst": 0,
  "igst": 0,
  "tax": 0,
  "total": 0,
  "confidence": 0,
  "lines": [
    {"item": "", "quantity": 0, "rate": 0, "tax_code": "", "amount": 0}
  ]
}

Field definitions:
- vendor: supplier/bill-from company name (NOT the buyer/consignee)
- invoice_number: the invoice's own reference/bill number
- invoice_date: date the invoice was issued (YYYY-MM-DD)
- po_number: purchase order number if shown
- gstin: vendor's GST Identification Number (e.g. 29AAACK7315D1ZQ)
- hsn_sac: HSN or SAC code of the main item/service
- vendor_code: vendor code if printed on the invoice
- tax_code: tax classification code if shown
- business_place: plant, site or business place if shown
- currency: ISO currency code (default INR)
- subtotal: taxable value / amount before tax
- cgst: CGST amount
- sgst: SGST amount
- igst: IGST amount
- tax: total tax (cgst + sgst + igst combined)
- total: final invoice total payable
- confidence: your confidence 0.0-1.0 that extraction is complete and correct
- lines: all line items with item description, quantity, rate per unit, tax code, line amount
"""

def _to_float(v) -> float:
    if v is None: return 0.0
    if isinstance(v, (int, float)): return float(v)
    cleaned = re.sub(r'[^0-9.\-]', '', str(v).replace(',', ''))
    try: return float(cleaned) if cleaned else 0.0
    except: return 0.0

def _extract_json(raw: str) -> dict:
    if not raw or not raw.strip():
        raise ValueError("Ollama returned empty response")
    text = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL | re.IGNORECASE).strip()
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text).strip()
    try: return json.loads(text)
    except: pass
    s, e = text.find('{'), text.rfind('}')
    if s == -1 or e == -1 or e <= s:
        raise ValueError("No JSON found in Ollama response")
    try: return json.loads(text[s:e+1])
    except Exception as ex:
        raise ValueError(f"JSON parse failed: {ex}")

def _normalize_lines(raw) -> list[dict]:
    if not isinstance(raw, list): return []
    result = []
    for x in raw:
        if not isinstance(x, dict): continue
        result.append({
            'item': str(x.get('item') or x.get('description') or x.get('name') or '').strip(),
            'quantity': _to_float(x.get('quantity') or x.get('qty')),
            'rate': _to_float(x.get('rate') or x.get('unit_price') or x.get('price')),
            'tax_code': str(x.get('tax_code') or x.get('hsn') or '').strip(),
            'amount': _to_float(x.get('amount') or x.get('total') or x.get('line_total')),
        })
    return result

def _normalize(data) -> dict:
    if not isinstance(data, dict): data = {}
    inv = data.get('invoice') if isinstance(data.get('invoice'), dict) else data
    lines = _normalize_lines(inv.get('lines') or inv.get('line_items') or inv.get('items') or [])
    subtotal = _to_float(inv.get('subtotal') or inv.get('sub_total') or inv.get('taxable_value'))
    cgst = _to_float(inv.get('cgst') or inv.get('cgst_amount'))
    sgst = _to_float(inv.get('sgst') or inv.get('sgst_amount'))
    igst = _to_float(inv.get('igst') or inv.get('igst_amount'))
    tax = _to_float(inv.get('tax') or inv.get('tax_amount'))
    total = _to_float(inv.get('total') or inv.get('grand_total') or inv.get('invoice_total'))
    # Auto-derive missing values
    if tax == 0: tax = cgst + sgst + igst
    if subtotal == 0 and lines: subtotal = sum(l['amount'] for l in lines)
    if total == 0: total = subtotal + tax
    return {
        'vendor': str(inv.get('vendor') or inv.get('supplier') or '').strip(),
        'invoice_number': str(inv.get('invoice_number') or inv.get('bill_no') or inv.get('invoice_no') or '').strip(),
        'invoice_date': str(inv.get('invoice_date') or inv.get('date') or inv.get('bill_date') or '').strip(),
        'po_number': str(inv.get('po_number') or inv.get('po') or inv.get('buyer_order_no') or '').strip(),
        'gstin': str(inv.get('gstin') or inv.get('gst_number') or '').strip(),
        'hsn_sac': str(inv.get('hsn_sac') or inv.get('hsn') or inv.get('sac') or '').strip(),
        'vendor_code': str(inv.get('vendor_code') or '').strip(),
        'tax_code': str(inv.get('tax_code') or '').strip(),
        'business_place': str(inv.get('business_place') or inv.get('plant') or '').strip(),
        'currency': str(inv.get('currency') or 'INR').strip() or 'INR',
        'subtotal': subtotal,
        'cgst': cgst,
        'sgst': sgst,
        'igst': igst,
        'tax': tax,
        'total': total,
        'confidence': max(0.0, min(1.0, _to_float(inv.get('confidence')))),
        'lines': lines,
    }

def _pdf_to_images(path: Path) -> list[str]:
    try:
        import fitz
    except ImportError as e:
        raise HTTPException(500, "PyMuPDF required for PDF extraction") from e
    try:
        doc = fitz.open(str(path))
    except Exception as e:
        raise HTTPException(400, f"Cannot open PDF: {e}") from e
    images = []
    try:
        if doc.page_count == 0:
            raise HTTPException(400, "PDF has no pages")
        limit = max(1, int(settings.ollama_max_pages))
        zoom = fitz.Matrix(1.6, 1.6)
        for i in range(min(doc.page_count, limit)):
            pix = doc[i].get_pixmap(matrix=zoom, alpha=False)
            images.append(base64.b64encode(pix.tobytes("png")).decode())
    finally:
        doc.close()
    if not images:
        raise HTTPException(400, "No pages rendered from PDF")
    return images

def _file_to_images(path: Path) -> list[str]:
    ext = path.suffix.lower()
    if ext in SUPPORTED_PDF_EXTS:
        return _pdf_to_images(path)
    if ext in SUPPORTED_IMAGE_EXTS:
        data = path.read_bytes()
        if not data:
            raise HTTPException(400, "Image file is empty")
        return [base64.b64encode(data).decode()]
    raise HTTPException(400, "Unsupported file type. Please upload PDF, JPG, JPEG, or PNG.")

async def _call_ollama(images: list[str]) -> str:
    endpoint = f"{settings.ollama_url.rstrip('/')}/api/generate"
    payload = {
        "model": settings.ollama_model,
        "prompt": SYSTEM_PROMPT,
        "stream": False,
        "think": False,
        "keep_alive": "30m",
        "images": images,
        "options": {"num_ctx": 8192, "num_predict": 4096},
    }
    try:
        async with httpx.AsyncClient(
            timeout=settings.ollama_timeout,
            trust_env=False,  # bypass corporate proxy for localhost Ollama
        ) as client:
            resp = await client.post(endpoint, json=payload)
    except httpx.TimeoutException as e:
        raise HTTPException(504, f"Ollama timed out after {settings.ollama_timeout}s. Increase OLLAMA_TIMEOUT.") from e
    except httpx.RequestError as e:
        raise HTTPException(502, f"Cannot connect to Ollama at {settings.ollama_url}: {e}") from e

    if resp.status_code >= 400:
        try: msg = resp.json().get('error', resp.text)
        except: msg = resp.text
        raise HTTPException(502, f"Ollama returned HTTP {resp.status_code}: {msg}")

    try: body = resp.json()
    except: raise HTTPException(502, "Ollama returned invalid JSON response")

    raw = (body.get('response') or body.get('thinking') or '').strip()
    if not raw:
        raise HTTPException(502, f"Ollama returned empty response (done_reason={body.get('done_reason','unknown')})")
    return raw

async def extract_invoice(file_path: str) -> dict:
    if settings.extraction_mode == 'demo':
        return demo_extract(file_path)
    if settings.extraction_mode != 'ollama':
        raise HTTPException(500, "EXTRACTION_MODE must be 'demo' or 'ollama'")
    path = Path(file_path)
    images = _file_to_images(path)
    try:
        raw = await _call_ollama(images)
        parsed = _extract_json(raw)
        return _normalize(parsed)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(502, f"Cannot parse Ollama response: {e}") from e
    except Exception as e:
        raise HTTPException(500, f"Extraction error: {e}") from e
