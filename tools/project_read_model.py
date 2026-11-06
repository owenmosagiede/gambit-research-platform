#!/usr/bin/env python3
"""Explicit serving-only backfill/refresh; never schedules or executes research."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from read_model.projector import build, cleanup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--watch-seconds', type=int, help='Explicit opt-in continuous refresh, minimum 30 seconds')
    parser.add_argument('--retention-seconds', type=int, default=3600)
    args = parser.parse_args()
    if args.watch_seconds is not None and args.watch_seconds < 30: parser.error('Refresh interval must be at least 30 seconds')
    if not 1 <= args.timeout <= 3600 or args.retention_seconds < 300: parser.error('Invalid time bounds')
    while True:
        try:
            if (args.output/'current.json').exists(): cleanup(args.output,retention_seconds=args.retention_seconds)
            result=build(args.root,args.output,timeout=args.timeout)
            print(json.dumps(result,sort_keys=True),flush=True)
        except Exception as exc:
            print(json.dumps({'published':False,'error_type':type(exc).__name__,'research_unchanged':True}),flush=True)
            if args.watch_seconds is None: return 1
        if args.watch_seconds is None: return 0
        time.sleep(args.watch_seconds)

if __name__ == '__main__': raise SystemExit(main())
