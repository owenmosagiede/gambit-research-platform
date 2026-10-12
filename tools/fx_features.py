#!/usr/bin/env python3
"""Register approved FX recipes, list them, or prepare one bounded sample."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from data.alfred_onboarding import strict_json, stable_read
from data.fx_feature_recipes import register_fx_recipes, list_fx_recipes, resolve_fx_binding


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    actions=parser.add_subparsers(dest='action',required=True)
    register=actions.add_parser('register',help='Register the approved daily grids; never materialize Features')
    register.add_argument('--review',type=Path,required=True)
    register.add_argument('--request',type=Path,required=True)
    listing=actions.add_parser('list');listing.add_argument('--instrument');listing.add_argument('--limit',type=int,default=100);listing.add_argument('--offset',type=int,default=0)
    prepare=actions.add_parser('prepare',help='Prepare one explicitly selected bounded verification sample')
    prepare.add_argument('--instrument',required=True);prepare.add_argument('--operator',required=True)
    prepare.add_argument('--parameters',required=True,help='JSON object using existing approved parameter values')
    prepare.add_argument('--start',required=True);prepare.add_argument('--end',required=True)
    prepare.add_argument('--knowledge-cutoff')
    args=parser.parse_args()
    if args.action=='register':result=register_fx_recipes(args.root,review_path=args.review,request_path=args.request)
    elif args.action=='list':result=list_fx_recipes(args.root,args.instrument,args.limit,args.offset)
    else:
        from data.fx_feature_store import prepare_fx_feature
        from datetime import date
        start,end=date.fromisoformat(args.start),date.fromisoformat(args.end)
        if end<start or (end-start).days>=366:parser.error('Verification samples must be an explicit interval of at most 366 calendar days')
        parameters=strict_json(args.parameters)
        binding=resolve_fx_binding(args.root,instrument_id=args.instrument,operator_id=args.operator,parameters=parameters)
        config=strict_json(stable_read(args.root/'config/fx_retrospective_completion.json'))
        result=prepare_fx_feature(args.root,binding['feature'],price_snapshot=binding['price_snapshot'],batch_policy=config['return_policy'],
            knowledge_cutoff=args.knowledge_cutoff or config['knowledge_cutoff'],start=args.start,end=args.end)
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=='__main__':main()
