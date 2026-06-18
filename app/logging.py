"""Loguru setup: stdout + rotating file sink."""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_LOG_DIR = Path("logs")
_LOG_FILE = _LOG_DIR / "amanda.log"

_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        backtrace=True,
        diagnose=False,
        enqueue=False,
    )
    # Sink de arquivo em JSON estruturado (serialize=True) para ingestão pelo
    # coletor do Hub. stdout permanece legível para operação humana.
    logger.add(
        str(_LOG_FILE),
        level="INFO",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        backtrace=True,
        diagnose=False,
        enqueue=True,
        serialize=True,
    )
    _configured = True


setup_logging()
