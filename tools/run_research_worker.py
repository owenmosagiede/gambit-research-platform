#!/usr/bin/env python3
"""Run research independently of the web server. SIGTERM finishes the current submission."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from services.research_worker import run_service

if __name__ == '__main__':
    try:
        raise SystemExit(run_service(Path(__file__).resolve().parents[1]))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
