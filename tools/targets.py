#!/usr/bin/env python3
"""Local explicit return Target commands; no provider downloads or implicit latest."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from data.alfred_onboarding import strict_json
from data.targets.service import (create_target,preflight_request,materialize,list_targets,
                                 get_definition,list_materializations,retrieve_target)
from data.targets.store import TargetStore
from data.targets.contracts import create_policy


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    commands=parser.add_subparsers(dest='command',required=True)
    for command in ('register-policy','create','preflight','materialize','refresh'):
        item=commands.add_parser(command)
        item.add_argument('--file',required=True,type=Path,help='Exact policy/body or materialization request JSON')
    listing=commands.add_parser('list')
    listing.add_argument('--instrument-id')
    listing.add_argument('--horizon-amount')
    listing.add_argument('--horizon-unit')
    for command in ('definition','materializations','get'):
        item=commands.add_parser(command)
        item.add_argument('--target-id',required=True)
        if command=='get':
            item.add_argument('--materialization-id',required=True)
            item.add_argument('--start-inclusive')
            item.add_argument('--end-exclusive')
            item.add_argument('--range-precision',choices=['date','utc_timestamp'])
            item.add_argument('--training-cutoff')
            item.add_argument('--cutoff-precision',choices=['date','utc_timestamp'])
    args=parser.parse_args()
    body=strict_json(args.file.read_bytes()) if hasattr(args,'file') else None
    if args.command=='register-policy':
        record=create_policy(body['body'],body.get('display_name','Return Target policy'))
        store=TargetStore(args.root);store.verify_closure([record['body']])
        with store.writer():store.install_record(record)
        result=record
    elif args.command=='create':result=create_target(args.root,body['body'],body.get('display_name','Return Target'))
    elif args.command=='preflight':
        value=preflight_request(args.root,body)
        result={key:value[key] for key in ('definition','state','source_eligibility')}
    elif args.command in ('materialize','refresh'):result=materialize(args.root,body)
    elif args.command=='list':
        from api.target_library import list_target_library
        result=list_target_library(args.root,args.instrument_id,args.horizon_amount,args.horizon_unit)
    elif args.command=='definition':result=get_definition(args.root,args.target_id)
    elif args.command=='materializations':result=list_materializations(args.root,args.target_id)
    else:
        from api.target_library import get_target_detail
        result=get_target_detail(args.root,args.target_id,args.materialization_id,
             training_cutoff=args.training_cutoff,cutoff_precision=args.cutoff_precision,
             start_inclusive=args.start_inclusive,end_exclusive=args.end_exclusive,range_precision=args.range_precision)
    print(json.dumps(result,sort_keys=True,indent=2,allow_nan=False))


if __name__=='__main__':
    main()
