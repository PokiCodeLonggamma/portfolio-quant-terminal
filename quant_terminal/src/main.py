"""Launcher.

Standard project run:
    cp .env.example .env
    pip install -e .
    python -m src.main

This module bootstraps a Streamlit subprocess on `app.py` so the user has a
single, consistent entry-point.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "app.py"


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    if not APP_FILE.exists():
        sys.stderr.write(f"[quant-terminal] app.py missing at {APP_FILE}\n")
        return 1

    port = os.getenv("STREAMLIT_SERVER_PORT", "8501")
    address = os.getenv("STREAMLIT_SERVER_ADDRESS", "localhost")

    # Hand off to streamlit's CLI. `streamlit.web.cli` exposes a `main()` we
    # can invoke directly without spawning a separate process.
    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit", "run", str(APP_FILE),
        "--server.port", port,
        "--server.address", address,
        "--browser.gatherUsageStats", "false",
    ]
    return int(stcli.main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
