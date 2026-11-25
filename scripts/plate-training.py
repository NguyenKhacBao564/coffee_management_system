#!/usr/bin/env python3
"""Local-only detector preparation CLI. Uses an isolated training environment."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'edge-agent'))
from offline_vision.fine_tune.cli import main
if __name__=='__main__':main()
