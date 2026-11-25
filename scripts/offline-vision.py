#!/usr/bin/env python3
"""Local D05a CLI entry point, intentionally independent of FastAPI/DB."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "edge-agent"))
from offline_vision.cli import main

raise SystemExit(main())
