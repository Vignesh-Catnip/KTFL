import io
import os

os.environ.setdefault("EXTRACTION_MODE", "demo")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_bfl.db")
os.environ.setdefault("UPLOAD_DIR", "./test_uploads")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


def test_upload_rejects_unsupported_type():
    r = client.post(
        "/api/invoices/upload",
        files={"file": ("invoice.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert r.status_code == 400
    assert "Unsupported file type" in r.json()["detail"]["message"]


def test_upload_rejects_empty_file():
    r = client.post(
        "/api/invoices/upload",
        files={"file": ("invoice.pdf", io.BytesIO(b""), "application/pdf")},
    )
    assert r.status_code == 400
    assert "empty" in r.json()["detail"]["message"].lower()


def test_upload_demo_pdf_succeeds():
    pdf_bytes = b"%PDF-1.4 fake minimal content for demo mode"
    r = client.post(
        "/api/invoices/upload",
        files={"file": ("invoice.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["vendor"]
    assert body["invoice_number"]
    assert len(body["lines"]) > 0


def test_upload_duplicate_is_rejected():
    # demo_extractor always returns the same invoice_number/vendor, so a
    # second upload (after test_upload_demo_pdf_succeeds) must be flagged
    # as a duplicate rather than silently creating a second record.
    png_bytes = b"\x89PNG\r\n\x1a\nfakepngbytes"
    r = client.post(
        "/api/invoices/upload",
        files={"file": ("invoice.png", io.BytesIO(png_bytes), "image/png")},
    )
    assert r.status_code == 409
