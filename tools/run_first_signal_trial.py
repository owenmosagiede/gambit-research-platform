#!/usr/bin/env python3
"""Offline first Feature trial and exact Signal retrieval; no fetch or UI routes."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from data.alfred_onboarding import strict_json, stable_read
from data.first_signal_trial import run_trial
from data.feature_store import retrieve_signal


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    commands=parser.add_subparsers(dest='command',required=True)
    run=commands.add_parser('run');run.add_argument('--request',type=Path,default=ROOT/'config/first_signal_trial.json')
    retrieve=commands.add_parser('get');retrieve.add_argument('--signal-id',required=True);retrieve.add_argument('--materialization-id');retrieve.add_argument('--include-observations',action='store_true')
    args=parser.parse_args()
    if args.command=='run':result=run_trial(args.root,strict_json(stable_read(args.request)))
    else:
        result=retrieve_signal(args.root,args.signal_id,args.materialization_id)
        if not args.include_observations:
            result['observation_count']=len(result.pop('observations'));result['operand_count']=len(result.pop('operands'))
    print(json.dumps(result,sort_keys=True,indent=2,allow_nan=False))


if __name__=='__main__':main()
