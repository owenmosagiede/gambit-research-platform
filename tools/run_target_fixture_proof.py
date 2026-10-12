#!/usr/bin/env python3
"""Persist a synthetic proof through production Target APIs in isolated fixture storage."""
import argparse
from copy import deepcopy
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(PROJECT/'src'),str(PROJECT/'tests')]
from target_persistence_fixture import persistence_fixture,refresh_fixture
from data.targets.service import materialize,retrieve_target,list_targets
from data.transformations.identity import canonical_bytes


def run(root):
    root=Path(root).resolve()
    if root==PROJECT or not root.is_relative_to(PROJECT/'tests/fixtures'):
        raise ValueError('Proof output must be isolated beneath this project tests/fixtures directory')
    setup=persistence_fixture(root,selection='pinned_later')
    request=setup['request'];request['knowledge_cutoff']='2024-01-05'
    pending_request=deepcopy(request);pending_request['knowledge_cutoff']='2024-01-03'
    pending=materialize(root,pending_request)
    initial=materialize(root,request)
    original=retrieve_target(root,initial['target_id'],initial['materialization']['id'])
    assert Decimal(original['observations'][0]['value'])==Decimal(121)/Decimal(100)-1
    source=setup['fixture']['sources']['instrument']
    correction=deepcopy(source['series']['observations'][2])
    correction.update(value='125',available_at='2024-01-08',vintage_id='CORRECTION_1')
    source['series']['observations'].append(correction)
    refreshed=refresh_fixture(root,setup);refreshed['request']['knowledge_cutoff']='2024-01-09'
    corrected=materialize(root,refreshed['request'])
    duplicate=materialize(root,refreshed['request'])
    assert duplicate['reused'] and duplicate['materialization']==corrected['materialization']
    old_again=retrieve_target(root,initial['target_id'],initial['materialization']['id'])
    assert old_again['observations']==original['observations']
    early=retrieve_target(root,corrected['target_id'],corrected['materialization']['id'],training_cutoff='2024-01-07',cutoff_precision='date')
    later=retrieve_target(root,corrected['target_id'],corrected['materialization']['id'],training_cutoff='2024-01-09',cutoff_precision='date')
    assert early['observations']==[] and later['observations'][0]['value']=='0.25'
    command=[sys.executable,str(PROJECT/'tools/targets.py'),'--root',str(root),'get',
             '--target-id',initial['target_id'],'--materialization-id',initial['materialization']['id']]
    completed=subprocess.run(command,capture_output=True,text=True,check=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    fresh=json.loads(completed.stdout)
    assert fresh['observations']==original['observations']
    report={'proof_type':'isolated_synthetic_canonical_investment_source','production_target_created':False,
            'target_id':initial['target_id'],'pending':pending,'initial':initial,'corrected':corrected,
            'initial_value':'0.21','corrected_value':'0.25','interval':{'entry':'2024-01-02','exit':'2024-01-04'},
            'correction_available_at':'2024-01-08','historical_cutoff_before_correction_selected_count':0,
            'historical_cutoff_after_correction_selected_count':1,'fresh_process_retrieval':'passed',
            'identical_request_reused':duplicate['reused'],'original_materialization_unchanged':True,
            'catalog_target_count':list_targets(root)['target_count'],
            'operand_locator_count':len(original['operand_lineage'][0]['operands'])}
    (root/'proof.json').write_bytes(canonical_bytes(report)+b'\n')
    (root/'request_initial.json').write_bytes(canonical_bytes(request)+b'\n')
    (root/'request_corrected.json').write_bytes(canonical_bytes(refreshed['request'])+b'\n')
    (root/'README.md').write_text('# Persisted synthetic return Target proof\n\nThis isolated store uses the production Target service. It is not a production market dataset.\n\nSee `proof.json`, exact requests, `definitions/targets/`, and `storage/catalog/target_store/`.\nThe main platform Target catalog does not enumerate this fixture store.\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=PROJECT/'tests/fixtures/target_return_proof')
    args=parser.parse_args()
    print(json.dumps(run(args.root),indent=2,sort_keys=True))
