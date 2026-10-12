#!/usr/bin/env python3
"""Fetch, onboard and query the full available CES0500000003 ALFRED archive."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from data.alfred_full_acquisition import acquire
from data.alfred_full_history import materialize, query, rebuild_index

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    build=sub.add_parser('build');build.add_argument('--acquisition-dir',type=Path,required=True)
    build.add_argument('--fetch',action='store_true',help='Fetch fresh evidence with the existing local provider credential before building')
    q=sub.add_parser('query');q.add_argument('--snapshot-id',required=True);q.add_argument('--as-of',required=True);q.add_argument('--observation-date')
    sub.add_parser('rebuild-index')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    if root.name!='research_platform':parser.error('Run from research_platform only')
    try:
        if args.command=='build':
            if args.fetch:acquire(args.acquisition_dir,root.parent/'Data/.env.local')
            result=materialize(root,args.acquisition_dir)
        elif args.command=='query':result=query(root,args.snapshot_id,args.as_of,args.observation_date)
        else:result=rebuild_index(root)
    except (ValueError,KeyError,OSError) as exc:
        parser.exit(1,'Full-history operation failed: '+str(exc)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
