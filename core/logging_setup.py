"""Rotating log configuration for the Screenrecord Manager daemon."""

import logging
import logging.handlers
import os
import sys
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LOG_DIR = os.environ.get(
    "SCREENRECORD_LOG_DIR", os.path.join(PROJECT_ROOT, ".data", "logs")
)
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_FLAG = "_screenrecord_logging_configured"


def setup_logging(
    level: int = logging.INFO,
    log_dir: Optional[str] = None,
    filename: str = "daemon.log",
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
    console: Optional[bool] = None,
) -> logging.Logger:
    """Configure process-wide logging with size-based rotation (idempotent)."""
    root = logging.getLogger()
    if getattr(root, _FLAG, False):
        return root

    root.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT)
    target_dir = log_dir or DEFAULT_LOG_DIR
    log_path = os.path.join(target_dir, filename)

    try:
        os.makedirs(target_dir, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
    except OSError as exc:
        # An unwritable log directory must never take the service down.
        sys.stderr.write(f"Warning: cannot open log file {log_path}: {exc}\n")

    if console is None:
        console = sys.stderr.isatty()
    if console:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        root.addHandler(stream)

    setattr(root, _FLAG, True)
    return root