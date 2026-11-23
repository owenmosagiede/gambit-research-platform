#!/usr/bin/env python3
"""Explicit plan/apply for four frozen panel packages; never launches research."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from data import panel_import as panels
from data.transformations.identity import canonical_bytes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['plan','apply'])
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--batch',type=Path,required=True)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--plan-sha256')
    args=parser.parse_args()
    if args.action=='plan':
        names={'macro':'gambit-seven-macro-panels.zip','common':'gambit-ten-common-panels.zip',
            'etf':'gambit-cross-asset-etf-panels.zip','expansion':'gambit-market-expansion.zip'}
        packages=[panels.package_plan(args.batch/'data/extracted'/folder,kind,args.batch/'archives'/names[kind])
            for kind,(folder,_) in panels.FILES.items()]
        value=panels.make_plan(packages)
        from research.store import install_bytes
        install_bytes(args.plan,canonical_bytes(value)+b'\n')
        print(json.dumps({'plan_sha256':value['plan_sha256'],'packages':[
            {'package':p['package'],'eligible_field_projections':len(p['projections']),
             'frozen_max_asof':p['frozen_max_asof']} for p in packages]},indent=2))
    else:
        from research.panel_features import install_profile
        value=json.loads(args.plan.read_text())
        # Policy installation is part of this explicit migration, separate from
        # normal application deployment. The base Research Spec is preserved.
        receipt=panels.install(args.root,value,args.plan_sha256)
        receipt['alignment']=install_profile(args.root)
        print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
