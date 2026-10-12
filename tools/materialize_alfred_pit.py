#!/usr/bin/env python3
"""Materialize, query or rebuild the bounded ALFRED PIT store without network access."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from data.alfred_pit import materialize,query,rebuild_index

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('build');commands.add_parser('rebuild-index')
    q=commands.add_parser('query');q.add_argument('--snapshot-id',required=True);q.add_argument('--as-of',required=True);q.add_argument('--observation-date')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    if root.name!='research_platform': parser.error('Run from research_platform only')
    try:
        if args.command=='build': result=materialize(root)
        elif args.command=='rebuild-index': result=rebuild_index(root)
        else: result=query(root,args.snapshot_id,args.as_of,args.observation_date)
    except (ValueError,KeyError,OSError) as exc:
        parser.exit(1,'PIT operation failed: '+str(exc)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
