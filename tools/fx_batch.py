#!/usr/bin/env python3
"""Execute or inspect the bounded 18-source/43-instrument FX batch; no downloads."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from data.alfred_onboarding import strict_json,stable_read,sha
from data.fx_onboarding import onboard,read_source
from data.fx_pipeline import register_and_construct,list_instruments
from data.feature_store import FeatureStore
from data.fx_records import read_rows
from data.targets.fx import materialize
from data.transformations.identity import canonical_bytes,digest,reference


class _ReadOnlyImplementationProbe:
    """Run the authoritative implementation fingerprint without publishing files."""
    def __init__(self):self.io=self
    def blob(self,data,fmt='json',role='evidence',rows=None):
        return {'role':role,'blob_sha256':sha(data),'format':fmt,'byte_count':len(data),'row_count':rows}
    def install_record(self,record):return reference(record)


def reuse_completed_targets(root, construction, policy_bundle, cached_run):
    """Fail-closed reuse of an explicitly supplied, fully completed prior run.

    This verifies immutable identity and every closure payload checksum. It does
    not replace independent calculation verification or reselect source history.
    No record, payload, source, policy or code change is silently tolerated.
    """
    from data.targets.store import TargetStore,TargetStoreError
    from data.targets.contracts import create_policy
    from data.targets.fx import (_approved_policy,_price_snapshot,_schedule,_definition,
        validate_manifest,validate_alignment_evidence)
    from data.targets.service import _implementation
    from data.transformations.contracts import normalize_time
    store=TargetStore(root)
    policy=_approved_policy(store,policy_bundle['return_policy'])
    validate_alignment_evidence(store,policy_bundle['alignment_policy'])
    cutoff=normalize_time(policy_bundle['knowledge_cutoff'],'date')
    if not isinstance(cached_run,dict) or cached_run.get('blockers')!=[]:
        raise TargetStoreError('Reuse requires an explicitly completed prior run')
    if cached_run.get('construction',{}).get('completion')!=construction['completion']:
        raise TargetStoreError('Cached and active construction completion differ')
    completion=store.resolve(construction['completion']);body=completion.get('body',{})
    if body.get('kind')!='fx_universe_completion' or body.get('alignment_policy')!=policy_bundle['alignment_policy']:
        raise TargetStoreError('Active completion differs from the approved price alignment')
    items=construction['instruments']
    if not isinstance(items,list) or not items or [item['registration'] for item in items]!=body['instruments']:
        raise TargetStoreError('Active instrument entries differ from their immutable completion')
    symbols=[item['instrument_id'] for item in items]
    if len(set(symbols))!=len(symbols):raise TargetStoreError('Repeated active instrument')
    for item in items:
        registration=store.resolve(item['registration'])
        if registration['body'].get('kind')!='fx_instrument_registration' or dict(registration['body'],registration=item['registration'])!=item or item.get('price_snapshot') is None:
            raise TargetStoreError('Active instrument is not its populated immutable registration')
    outputs=cached_run.get('targets')
    if not isinstance(outputs,list) or len(outputs)!=len(items)*len(policy['horizons']):
        raise TargetStoreError('Cached run does not contain every instrument and horizon exactly once')
    by_target={};materializations=set()
    for output in outputs:
        if set(output)!={'target_id','materialization','reused','row_count','status_counts','reason_counts'} or type(output['reused']) is not bool:
            raise TargetStoreError('Invalid completed Target result')
        manifest=validate_manifest(store.resolve(output['materialization']))
        if output['target_id']!=manifest['definition']['id'] or output['target_id'] in by_target or manifest['id'] in materializations:
            raise TargetStoreError('Repeated or mismatched Target/materialization in cached run')
        for field in ('row_count','status_counts','reason_counts'):
            if canonical_bytes(output[field])!=canonical_bytes(manifest[field]):raise TargetStoreError('Cached Target summary differs from its immutable manifest')
        if manifest['input_key']['batch_policy']!=policy or manifest['input_key']['knowledge_cutoff']!=cutoff:
            raise TargetStoreError('Cached return policy or knowledge cutoff differs')
        by_target[output['target_id']]=(output,manifest);materializations.add(manifest['id'])
    result=[];implementations={}
    calculation=create_policy({'kind':'return_calculation','calculation_version':'1.0.0','arithmetic':'decimal_50_then_binary64_guard'})
    for item in items:
        snapshot,_=_price_snapshot(store,item['price_snapshot'],policy,verify_rows=False)
        if snapshot['body']['instrument_id']!=item['instrument_id']:
            raise TargetStoreError('Active price snapshot belongs to another instrument')
        config,anchors,schedule_policy=_schedule(store,policy,snapshot['body']['coverage']['start'],snapshot['body']['coverage']['end'],install=False)
        zone=config['timezone']
        if zone not in implementations:implementations[zone]=_implementation(_ReadOnlyImplementationProbe(),calculation,config)
        for horizon in policy['horizons']:
            expected=_definition(store,snapshot,policy,horizon,schedule_policy,install=False)
            match=by_target.pop(expected['id'],None)
            if match is None:raise TargetStoreError('Cached Target is missing the expected instrument and horizon definition')
            output,manifest=match;key=manifest['input_key']
            if (manifest['definition']!=reference(expected) or manifest['price_snapshot']!=item['price_snapshot']
                    or key['schedule_sha256']!=digest(config) or key['anchors_sha256']!=digest(anchors)
                    or manifest['implementation']!=implementations[zone]):
                raise TargetStoreError('Cached Target source, definition, schedule or current implementation differs')
            schedule=strict_json(store.payload(manifest['schedule']))
            if schedule!={'schedule':config,'anchors':anchors}:
                raise TargetStoreError('Cached schedule payload differs from the approved grid')
            store.verify_closure([manifest])
            result.append(dict(deepcopy(output),reused=True))
    if by_target:raise TargetStoreError('Cached run has unexpected Target definitions')
    store.verify_closure([completion])
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT)
    commands=parser.add_subparsers(dest='command',required=True)
    for command in ('onboard','run'):
        item=commands.add_parser(command);item.add_argument('--legacy-root',type=Path,required=True);item.add_argument('--audit',type=Path,required=True)
        if command=='run':item.add_argument('--approved-policy',type=Path)
    item=commands.add_parser('construct');item.add_argument('--completion',type=Path,required=True);item.add_argument('--approved-policy',type=Path);item.add_argument('--preserve-construction',type=Path);item.add_argument('--jobs',type=int,choices=(1,2,3),default=1)
    item=commands.add_parser('returns');item.add_argument('--completion',type=Path,required=True);item.add_argument('--approved-policy',type=Path,required=True);item.add_argument('--jobs',type=int,choices=(1,2,3),default=1)
    for name in ('construct','returns'):
        commands.choices[name].add_argument('--reuse-completed-run',type=Path,
            help='Verify and reuse every exact Target manifest from this completed run; reject any mismatch')
    commands.add_parser('list')
    item=commands.add_parser('source');item.add_argument('--snapshot-id',required=True)
    item=commands.add_parser('prices');item.add_argument('--instrument-id',required=True)
    args=parser.parse_args();store=FeatureStore(args.root)
    if args.command=='list':result=list_instruments(args.root)
    elif args.command=='source':
        record=strict_json(stable_read(store.path('storage/catalog/snapshots/'+args.snapshot_id+'/manifest.json')))
        result=read_source(args.root,reference(record))
    elif args.command=='prices':
        entry=next((i for i in list_instruments(args.root) if i['instrument_id']==args.instrument_id),None)
        if entry is None or entry['price_snapshot'] is None:raise ValueError('Instrument has no stored constructed prices')
        manifest=store.resolve(entry['price_snapshot']);result={'manifest':manifest,'observations':read_rows(store,manifest['body']['members'])}
    else:
        if args.command in ('onboard','run'):
            result=onboard(args.root,args.legacy_root,args.audit,migration_time=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ'))
            print(json.dumps({'event':'source_onboarding_complete','source_count':result['source_count'],'row_count':result['row_count'],'reused':result['reused']}) ,file=sys.stderr,flush=True)
        else:
            result=strict_json(stable_read(args.completion))
            if 'scientific' in result:result=dict(result['scientific'],completion_path=str(args.completion))
        if args.command!='onboard':
            policy=strict_json(stable_read(args.approved_policy)) if args.approved_policy else None
            preserved=None
            if args.command=='construct' and args.preserve_construction:
                saved=strict_json(stable_read(args.preserve_construction))
                preserved=saved['construction']['completion'] if 'construction' in saved else saved
            if args.command=='returns':
                saved=store.resolve(reference(result) if result.get('record_type') else result)
                if saved.get('body',{}).get('kind')!='fx_universe_completion' or saved['body']['alignment_policy']!=policy['alignment_policy']:
                    raise ValueError('Exact completed universe matching the approved alignment is required')
                store.verify_closure([saved])
                items=[]
                for binding in saved['body']['instruments']:
                    record=store.resolve(binding)
                    if record['body'].get('kind')!='fx_instrument_registration' or record['body'].get('price_snapshot') is None:
                        raise ValueError('Return-only resume requires stored instrument prices')
                    items.append({'registration':binding,**record['body']})
                from data.transformations.fx import INSTRUMENTS
                if len(items)!=43 or {item['instrument_id'] for item in items}!=set(INSTRUMENTS):raise ValueError('Incomplete stored universe')
                construction={'completion':reference(saved),'instruments':items}
            else:
                construction=register_and_construct(args.root,result,alignment_policy=policy['alignment_policy'] if policy else None,preserve_completion=preserved)
            print(json.dumps({'event':'price_construction_complete','instruments':len(construction['instruments'])}),file=sys.stderr,flush=True)
            targets=[]
            reuse=getattr(args,'reuse_completed_run',None)
            if reuse:
                if not policy:raise ValueError('Completed-run reuse requires an explicit approved policy')
                targets=reuse_completed_targets(args.root,construction,policy,strict_json(stable_read(reuse)))
                print(json.dumps({'event':'completed_targets_verified_reused','variants':len(targets)}),file=sys.stderr,flush=True)
            elif policy:
                jobs=getattr(args,'jobs',1)
                if jobs==1:
                    for item in construction['instruments']:
                        if item['price_snapshot']:
                            outputs=materialize(args.root,item['price_snapshot'],policy['return_policy'],knowledge_cutoff=policy['knowledge_cutoff'])
                            targets+=outputs;print(json.dumps({'event':'targets_complete','instrument':item['instrument_id'],'variants':len(outputs)}),file=sys.stderr,flush=True)
                else:
                    # Independent instruments share immutable blobs and the same
                    # existing publication lock; output order remains canonical.
                    from concurrent.futures import ProcessPoolExecutor,as_completed
                    with ProcessPoolExecutor(max_workers=jobs,max_tasks_per_child=1) as pool:
                        futures={pool.submit(materialize,args.root,item['price_snapshot'],policy['return_policy'],
                            knowledge_cutoff=policy['knowledge_cutoff']):item['instrument_id'] for item in construction['instruments'] if item['price_snapshot']}
                        completed={}
                        for future in as_completed(futures):
                            symbol=futures[future];completed[symbol]=future.result()
                            print(json.dumps({'event':'targets_complete','instrument':symbol,'variants':len(completed[symbol])}),file=sys.stderr,flush=True)
                        targets=[output for item in construction['instruments'] for output in completed.get(item['instrument_id'],[])]
            result={'onboarding':result,'construction':construction,'targets':targets,
                'blockers':[] if policy else ['RETURN_HORIZONS_AND_SCHEDULE_UNAPPROVED','RETROSPECTIVE_CROSS_ALIGNMENT_UNAPPROVED']}
    print(json.dumps(result,sort_keys=True,indent=2,allow_nan=False))

if __name__=='__main__':main()
