#!/usr/bin/env python3
"""Run research independently of the web server. SIGTERM finishes the current submission."""
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from services.research_worker import run_service

if __name__ == '__main__':
    try:
        root = Path(__file__).resolve().parents[1]
        lane_count = os.environ.get("GAMBIT_RESEARCH_WORKERS", "1")
        if lane_count == "1":
            raise SystemExit(run_service(root))
        if lane_count == "2":
            from services.two_workers import ParallelResearchJobs
            raise SystemExit(run_service(root, jobs_factory=ParallelResearchJobs))
        raise RuntimeError("GAMBIT_RESEARCH_WORKERS must be 1 or 2")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
