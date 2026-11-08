#!/usr/bin/env python3
"""Explicit, bounded chart backfill from saved evidence. No research execution."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from read_model.chart_evidence import build


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--max-trials',type=int,default=4);p.add_argument('--seconds',type=int,default=30)
    p.add_argument('--watch-seconds',type=int)
    a=p.parse_args()
    if a.watch_seconds is not None and a.watch_seconds<60:p.error('Minimum refresh interval is 60 seconds')
    while True:
        result=build(a.root,a.output,max_trials=a.max_trials,seconds=a.seconds)
        print(json.dumps(result),flush=True)
        if a.watch_seconds is None:return 1 if result['issues'] else 0
        time.sleep(a.watch_seconds)

if __name__=='__main__':raise SystemExit(main())
