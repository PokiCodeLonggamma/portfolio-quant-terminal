"""Single source of logging config — call `get_logger(__name__)` everywhere."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_CONFIGURED = False


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    fmt = "%(asctime)s %(levelname)-7s %(name)s :: %(message)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    logs_dir = Path(__file__).resolve().parents[2] / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(logs_dir / "quant_terminal.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(fmt))
    root.addHandler(file_handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure_root()
    return logging.getLogger(name)
