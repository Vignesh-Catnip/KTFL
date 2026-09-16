"""
Structured logging with auto git push on error.
- backend/logs/app.log  : all INFO+ activity
- backend/logs/error.log: WARNING+ errors only
- On any error: auto_push_logs.bat triggered → logs pushed to GitHub
"""
import logging
import logging.handlers
import subprocess
import threading
from pathlib import Path

_DEFAULT_FIELDS = {"stage": "-", "endpoint": "-", "method": "-", "filename_ctx": "-"}

class _DefaultFieldsFilter(logging.Filter):
    def filter(self, record):
        for k, v in _DEFAULT_FIELDS.items():
            if not hasattr(record, k):
                setattr(record, k, v)
        return True

_is_pushing = False
_push_lock = threading.Lock()

class _AutoPushHandler(logging.Handler):
    """Triggers git push when WARNING or ERROR is logged."""
    def emit(self, record):
        if record.levelno >= logging.WARNING:
            _trigger_push()

def _trigger_push():
    global _is_pushing
    with _push_lock:
        if _is_pushing:
            return
        _is_pushing = True

    def push():
        global _is_pushing
        try:
            # Find the auto_push_logs.bat relative to this file
            # backend/app/logging_config.py → go up 3 levels → project root → scripts/
            project_root = Path(__file__).parent.parent.parent
            script = project_root / "scripts" / "auto_push_logs.bat"
            if script.exists():
                subprocess.Popen(
                    str(script),
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=str(project_root),
                )
        except Exception:
            pass
        finally:
            _is_pushing = False

    threading.Thread(target=push, daemon=True).start()


def setup_logging(log_dir: str = "./logs") -> logging.Logger:
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s stage=%(stage)s endpoint=%(endpoint)s "
        "method=%(method)s file=%(filename_ctx)s logger=%(name)s %(message)s"
    )

    root = logging.getLogger("bfl")
    root.setLevel(logging.INFO)
    root.propagate = False

    if root.handlers:
        return root

    # app.log — all INFO+
    app_h = logging.handlers.RotatingFileHandler(
        log_path / "app.log", maxBytes=5*1024*1024, backupCount=5, encoding="utf-8"
    )
    app_h.setLevel(logging.INFO)
    app_h.setFormatter(fmt)
    app_h.addFilter(_DefaultFieldsFilter())

    # error.log — WARNING+ only
    err_h = logging.handlers.RotatingFileHandler(
        log_path / "error.log", maxBytes=5*1024*1024, backupCount=5, encoding="utf-8"
    )
    err_h.setLevel(logging.WARNING)
    err_h.setFormatter(fmt)
    err_h.addFilter(_DefaultFieldsFilter())

    # console
    con_h = logging.StreamHandler()
    con_h.setLevel(logging.INFO)
    con_h.setFormatter(fmt)
    con_h.addFilter(_DefaultFieldsFilter())

    # auto push on error
    push_h = _AutoPushHandler()
    push_h.setLevel(logging.WARNING)

    root.addHandler(app_h)
    root.addHandler(err_h)
    root.addHandler(con_h)
    root.addHandler(push_h)

    return root

logger = logging.getLogger("bfl")
