import base64
import json
import re
from pathlib import Path

import httpx
from fastapi import HTTPException

from ..config import settings
from .demo_extractor import demo_extract


SYSTEM_PROMPT = """
You are an accounts-payable invoice extraction engine.

Read the provided invoice image carefully.

Return ONLY one valid JSON object.
Do not return markdown.
Do not return code fences.
Do not return explanations.
Do not return reasoning.
Do not invent values.

If a value cannot be found, return an empty string.
If a numeric value cannot be found, return 0.

Dates should be YYYY-MM-DD when possible.
Currency should be an ISO currency code.
All amounts must be numeric values only.

Extract the invoice information using exactly this structure:

{
  "vendor": "",
  "invoice_number": "",
  "invoice_date": "",
  "po_number": "",
  "tax_code": "",
  "business_place": "",
  "currency": "INR",
  "subtotal": 0,
  "tax": 0,
  "total": 0,
  "confidence": 0,
  "lines": [
    {
      "item": "",
      "quantity": 0,
      "tax_code": "",
      "amount": 0
    }
  ]
}

Rules:
- vendor = supplier/vendor name
- invoice_number = invoice number
- invoice_date = invoice date
- po_number = purchase order/reference number
- tax_code = invoice tax code if available
- business_place = plant/business place/section if available
- subtotal = subtotal before tax
- tax = total tax amount
- total = final invoice total
- confidence = number between 0 and 1
- lines = all invoice line items
- quantity must be numeric
- amount must be numeric
- Do not calculate or invent values when the invoice does not contain them.
"""


def _to_float(value):
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value)

    text = text.replace(",", "")

    cleaned = re.sub(r"[^0-9.\-]", "", text)

    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def _normalize(data):
    if not isinstance(data, dict):
        data = {}

    invoice = data.get("invoice")

    if isinstance(invoice, dict):
        inv = invoice
    else:
        inv = data

    raw_lines = (
        inv.get("lines")
        or inv.get("line_items")
        or inv.get("items")
        or []
    )

    lines = []

    if isinstance(raw_lines, list):
        for item in raw_lines:
            if not isinstance(item, dict):
                continue

            quantity_value = item.get("quantity")

            if quantity_value is None:
                quantity_value = item.get("qty")

            amount_value = item.get("amount")

            if amount_value is None:
                amount_value = item.get("total")

            if amount_value is None:
                amount_value = item.get("line_total")

            lines.append(
                {
                    "item": str(
                        item.get("item")
                        or item.get("description")
                        or item.get("name")
                        or ""
                    ).strip(),
                    "quantity": _to_float(quantity_value),
                    "tax_code": str(
                        item.get("tax_code")
                        or item.get("tax")
                        or ""
                    ).strip(),
                    "amount": _to_float(amount_value),
                }
            )

    total_value = inv.get("total")

    if total_value is None:
        total_value = inv.get("grand_total")

    subtotal_value = inv.get("subtotal")

    if subtotal_value is None:
        subtotal_value = inv.get("sub_total")

    tax_value = inv.get("tax")

    if tax_value is None:
        tax_value = inv.get("tax_amount")

    total = _to_float(total_value)
    subtotal = _to_float(subtotal_value)
    tax = _to_float(tax_value)

    if subtotal == 0 and lines:
        subtotal = sum(line["amount"] for line in lines)

    if total == 0 and lines:
        total = subtotal + tax

    confidence = _to_float(inv.get("confidence"))

    confidence = max(
        0.0,
        min(1.0, confidence)
    )

    return {
        "vendor": str(
            inv.get("vendor")
            or inv.get("supplier")
            or inv.get("vendor_name")
            or ""
        ).strip(),

        "invoice_number": str(
            inv.get("invoice_number")
            or inv.get("invoiceNumber")
            or inv.get("invoice_no")
            or ""
        ).strip(),

        "invoice_date": str(
            inv.get("invoice_date")
            or inv.get("invoiceDate")
            or inv.get("date")
            or ""
        ).strip(),

        "po_number": str(
            inv.get("po_number")
            or inv.get("poNumber")
            or inv.get("po")
            or ""
        ).strip(),

        "tax_code": str(
            inv.get("tax_code")
            or inv.get("taxCode")
            or ""
        ).strip(),

        "business_place": str(
            inv.get("business_place")
            or inv.get("businessPlace")
            or ""
        ).strip(),

        "currency": str(
            inv.get("currency")
            or "INR"
        ).strip(),

        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "confidence": confidence,
        "lines": lines,
    }


def _image_base64(path):
    file_path = Path(path)

    if not file_path.exists():
        raise HTTPException(
            404,
            f"Invoice file not found: {file_path}"
        )

    try:
        image_bytes = file_path.read_bytes()
    except OSError as exc:
        raise HTTPException(
            500,
            f"Could not read invoice image: {exc}"
        ) from exc

    if not image_bytes:
        raise HTTPException(
            400,
            "Invoice image is empty"
        )

    return [
        base64.b64encode(image_bytes).decode("utf-8")
    ]


def _pdf_images(path):
    try:
        import fitz
    except ImportError as exc:
        raise HTTPException(
            500,
            "PyMuPDF is required for PDF extraction"
        ) from exc

    file_path = Path(path)

    if not file_path.exists():
        raise HTTPException(
            404,
            f"Invoice PDF not found: {file_path}"
        )

    try:
        document = fitz.open(str(file_path))
    except Exception as exc:
        raise HTTPException(
            400,
            f"Could not open invoice PDF: {exc}"
        ) from exc

    images = []

    try:
        page_limit = max(
            1,
            int(settings.ollama_max_pages)
        )

        page_count = min(
            len(document),
            page_limit
        )

        for page_number in range(page_count):
            page = document[page_number]

            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(1.4, 1.4),
                alpha=False
            )

            png_bytes = pixmap.tobytes("png")

            images.append(
                base64.b64encode(
                    png_bytes
                ).decode("utf-8")
            )

    except Exception as exc:
        raise HTTPException(
            500,
            f"Could not convert PDF pages to images: {exc}"
        ) from exc

    finally:
        document.close()

    if not images:
        raise HTTPException(
            400,
            "No pages found in invoice PDF"
        )

    return images


def _extract_json(raw_response):
    if not raw_response:
        raise ValueError(
            "Ollama returned an empty response"
        )

    text = raw_response.strip()

    # Remove thinking blocks if present.
    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    ).strip()

    # Remove markdown code fences.
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    text = text.strip()

    # Try direct JSON first.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # If additional text exists, locate the JSON object.
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError(
            "Ollama returned non-JSON output"
        )

    json_text = text[start:end + 1]

    try:
        return json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Ollama JSON parsing failed: {exc}"
        ) from exc


async def extract_invoice(file_path):
    if settings.extraction_mode == "demo":
        return demo_extract(file_path)

    if settings.extraction_mode != "ollama":
        raise HTTPException(
            500,
            "EXTRACTION_MODE must be demo or ollama"
        )

    if not settings.ollama_url:
        raise HTTPException(
            500,
            "OLLAMA_URL is not configured"
        )

    if not settings.ollama_model:
        raise HTTPException(
            500,
            "OLLAMA_MODEL is not configured"
        )

    suffix = Path(file_path).suffix.lower()

    if suffix == ".pdf":
        images = _pdf_images(file_path)
    elif suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        images = _image_base64(file_path)
    else:
        raise HTTPException(
            400,
            "Unsupported invoice file type"
        )

    payload = {
        "model": settings.ollama_model,
        "prompt": SYSTEM_PROMPT,
        "stream": False,
        "think": False,
        "keep_alive": "30m",
        "images": images,
        "options": {
            "num_ctx": 8192,
            "num_predict": 4096
        }
    }

    endpoint = (
        f"{settings.ollama_url.rstrip('/')}"
        "/api/generate"
    )

    try:
        async with httpx.AsyncClient(
            timeout=settings.ollama_timeout
        ) as client:

            response = await client.post(
                endpoint,
                json=payload
            )

        if response.status_code >= 400:
            try:
                error_data = response.json()
                error_message = error_data.get(
                    "error",
                    response.text
                )
            except Exception:
                error_message = response.text

            raise HTTPException(
                502,
                "Ollama API returned HTTP "
                f"{response.status_code}: "
                f"{error_message}"
            )

        try:
            body = response.json()
        except json.JSONDecodeError as exc:
            raise HTTPException(
                502,
                "Ollama returned an invalid API response"
            ) from exc

        raw_response = body.get("response", "") or ""

        # Some Ollama/qwen3-vl builds route output into a separate
        # "thinking" field even when think=False is requested, especially
        # if generation is cut off mid-thought by num_predict. Fall back
        # to it so we don't fail on a technically-empty "response".
        if not raw_response.strip():
            raw_response = body.get("thinking", "") or ""

        if not raw_response.strip():
            done_reason = body.get("done_reason", "unknown")
            raise HTTPException(
                502,
                "Ollama returned an empty response "
                f"(done_reason={done_reason}). The model may need a "
                "higher OLLAMA num_predict, or does not support "
                "think=False for this endpoint — try a non-thinking "
                "vision model or increase num_predict in ollama.py."
            )

        parsed_data = _extract_json(
            raw_response
        )

        normalized_data = _normalize(
            parsed_data
        )

        return normalized_data

    except HTTPException:
        raise

    except httpx.TimeoutException as exc:
        raise HTTPException(
            504,
            "Ollama extraction timed out. "
            "Increase OLLAMA_TIMEOUT if required."
        ) from exc

    except httpx.RequestError as exc:
        raise HTTPException(
            502,
            f"Could not connect to Ollama at "
            f"{settings.ollama_url}: {exc}"
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            502,
            f"Could not parse Ollama extraction: {exc}"
        ) from exc

    except Exception as exc:
        raise HTTPException(
            500,
            f"Unexpected error during Ollama extraction: {exc}",
        ) from exc