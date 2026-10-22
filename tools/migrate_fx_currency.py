#!/usr/bin/env python3
"""Explicit offline currency migration: stage, inspect plan, apply exact digest."""
import argparse,json,logging
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from data.alfred_onboarding import strict_json,stable_read
from data.transformations.identity import reference
from data.fx_currency_release import stage
from data.fx_currency_migration import plan,apply,verify_applied,check_staged_request
from data.fx_migration_manifest import install_manifest

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('stage');s.add_argument('--request',type=Path,required=True);s.add_argument('--output',type=Path,required=True)
    s=sub.add_parser('plan');s.add_argument('--release',type=Path,required=True);s.add_argument('--output',type=Path,required=True)
    s=sub.add_parser('resume-plan');s.add_argument('--release',type=Path,required=True);s.add_argument('--request',type=Path,required=True);s.add_argument('--output',type=Path,required=True)
    s=sub.add_parser('verify');s.add_argument('--manifest',type=Path,required=True)
    s=sub.add_parser('apply');s.add_argument('--manifest',type=Path,required=True);s.add_argument('--expected-sha256',required=True);s.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.command!='verify':logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    if a.command=='stage':
        request=strict_json(stable_read(a.request))
        result=stage(a.root,request['source_snapshots'],request['return_policy'],request['request_text'])
        result=reference(result)
    elif a.command in ('plan','resume-plan'):
        release=strict_json(stable_read(a.release))
        if a.command=='resume-plan':check_staged_request(a.root,release,strict_json(stable_read(a.request)))
        result=plan(a.root,release)
    elif a.command=='verify':result=verify_applied(a.root,strict_json(stable_read(a.manifest)))
    else:result=apply(a.root,strict_json(stable_read(a.manifest)),a.expected_sha256)
    if getattr(a,'output',None):install_manifest(a.output,result)
    else:print(json.dumps(result,indent=2))

if __name__=='__main__':main()
