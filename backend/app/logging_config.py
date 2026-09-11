"""Structured server-side logging.

Writes to logs/app.log (all INFO+ records) and logs/error.log (WARNING+),
both rotated so they don't grow unbounded on the Windows server.

Log records are expected to carry `stage` (e.g. UPLOAD, PDF_PROCESSING,
OLLAMA, DATABASE) and optionally `endpoint`/`method`/`filename` via the
`extra=` kwarg, e.g.:

    logger.error("PDF conversion failed", extra={
        "stage": "PDF_PROCESSING", "endpoint": "/api/invoices/upload",
        "method": "POST", "filename": file.filename,
    })

Never pass secrets, credentials, or full invoice content into log calls.
"""
import logging
import logging.handlers
from pathlib import Path

_DEFAULT_FIELDS = {"stage": "-", "endpoint": "-", "method": "-", "filename_ctx": "-"}


class _DefaultFieldsFilter(logging.Filter):
    """Fills in missing structured fields so the formatter never KeyErrors."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, default in _DEFAULT_FIELDS.items():
            if not hasattr(record, key):
                setattr(record, key, default)
        return True


def setup_logging(log_dir: str = "./logs") -> logging.Logger:
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s stage=%(stage)s endpoint=%(endpoint)s "
        "method=%(method)s file=%(filename_ctx)s logger=%(name)s %(message)s"
    )

    # Note: we use `filename_ctx` (not `filename`) for the invoice file name
    # because logging.LogRecord already has a built-in `filename` attribute
    # (the source .py file of the log call), and passing `filename=...` via
    # `extra=` raises "Attempt to overwrite 'filename' in LogRecord".

    root = logging.getLogger("bfl")
    root.setLevel(logging.INFO)
    root.propagate = False

    if root.handlers:
        # Avoid duplicate handlers if setup_logging() runs twice (e.g. --reload)
        return root

    app_handler = logging.handlers.RotatingFileHandler(
        log_path / "app.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(fmt)
    app_handler.addFilter(_DefaultFieldsFilter())

    error_handler = logging.handlers.RotatingFileHandler(
        log_path / "error.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(fmt)
    error_handler.addFilter(_DefaultFieldsFilter())

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)
    console_handler.addFilter(_DefaultFieldsFilter())

    root.addHandler(app_handler)
    root.addHandler(error_handler)
    root.addHandler(console_handler)

    return root


logger = logging.getLogger("bfl")
