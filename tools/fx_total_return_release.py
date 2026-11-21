#!/usr/bin/env python3
"""Explicit idle-only migration; never enqueue a research experiment.

The ordinary source release happens first. This separate data migration binds
the new model to exact existing spot materializations, then publishes one config
pointer last. Admissions stay closed throughout and after activation.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from data import fx_funding
from data.targets import fx_total
from data.targets.store import TargetStore
from data.transformations.identity import reference
from data.verified_inputs import execution_inputs
from research.store import read_json,lock,install_bytes
from research.contracts import canonical,digest
from research.schedule import load_schedule

ACTIVE={'queued','resolving','preparing','p1','p2'}

def idle(root):
    """Require each current projection to match its immutable committed event."""
    found=[]
    directory=root/'storage/catalog/operations/jobs'
    inventory={p.name:p.stat().st_mtime_ns for p in directory.glob('*.json')}
    for name in inventory:
        job=read_json(directory/name)
        event=read_json(root/f"storage/catalog/attempts/{job['attempt_id']}/events/RESEVENT_{job['event_sha256']}.json")
        if digest(event)!=job['event_sha256'] or dict(event['job'],sequence=event['sequence'],event_sha256=job['event_sha256'])!=job:
            raise ValueError('Cannot verify native research queue; migration blocked')
        if job['request_id']+'.json'!=name or job['status'] not in ACTIVE|{'succeeded','failed','blocked','cancelled'}:
            raise ValueError('Unknown or inconsistent queue state; migration blocked')
        if job['status'] in ACTIVE:found.append(job['request_id'])
    if inventory!={p.name:p.stat().st_mtime_ns for p in directory.glob('*.json')}:
        raise ValueError('Research queue changed during the idle check')
    if found:raise ValueError(f'Migration requires an empty accepted queue; {len(found)} requests remain active')

def migrate(root,bis_raw,sora_raw,*,apply=False):
    root=Path(root).resolve()
    if not (root/'config/research_execution.json').is_file():raise ValueError('A native research workspace is required')
    idle(root)
    # Resolve the existing scientific authority; never choose a lexical latest.
    from research.contracts import load_profile
    profile=load_profile(root);selection=profile['target_selection']
    pins=selection.get('materializations',{})
    if not pins or selection.get('selection_scope')!='registered_fx_registry':
        raise ValueError('An exact registered pair/spot Target map is required')
    horizons=(load_schedule(root) or {}).get('horizons',[1,7,21,63])
    pairs=sorted(p for p in pins if len(p)==6 and p[:3] in fx_funding.SUPPORTED and p[3:] in fx_funding.SUPPORTED)
    result={'operation':'fx_benchmark_total_return_migration_v1','pairs':pairs,'horizons':horizons,
            'excluded_pairs':sorted(set(pins)-set(pairs)),'research_admissions_reopened':False,
            'research_jobs_created':0,'apply':apply,'bis_sha256':sha256(bis_raw).hexdigest(),
            'sora_sha256':sha256(sora_raw).hexdigest(),'funding_model':reference(fx_total.policy())}
    if not apply:return result
    marker=Path('/etc/gambit/research-admissions-closed')
    if not marker.is_file():raise ValueError('Close production admissions before this separately reviewed migration')
    if (root/'config/fx_total_return.json').exists():raise ValueError('A total-return release already exists; an explicit versioned upgrade plan is required')
    with lock(root,'research-executor',nonblocking=True) as available:
        if not available:raise ValueError('Research executor is active; no inputs installed')
        with lock(root,'research-writer'):
            idle(root)
            binding=fx_funding.install(root,bis_raw,sora_raw);maps={};store=TargetStore(root)
            with execution_inputs(root,'fx-total-return-migration-v1',max_bytes=512*1024*1024):
                for pair in pairs:
                    maps[pair]={}
                    for horizon in horizons:
                        pin=pins[pair][str(horizon)]
                        if not isinstance(pin,dict):raise ValueError('Every spot input must be an exact content reference')
                        record=store.resolve(pin)
                        if reference(record)!=pin:raise ValueError('Spot input binding differs')
                        maps[pair][str(horizon)]=fx_total.materialize(root,pin,binding)
            config={'schema':'fx_total_return_release_v1','funding_model':reference(fx_total.policy()),
                    'funding_snapshot':binding,'materializations':maps}
            # Pointer last: partial Target publications are inert until all
            # selected pairs/horizons completed and this immutable config exists.
            install_bytes(root/'config/fx_total_return.json',canonical(config)+b'\n')
            result.update(funding_snapshot=binding,materializations=maps,config_sha256=digest(config))
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--bis',type=Path,required=True);parser.add_argument('--sora',type=Path,required=True)
    parser.add_argument('--bis-sha256',required=True);parser.add_argument('--sora-sha256',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();bis=args.bis.read_bytes();sora=args.sora.read_bytes()
    if sha256(bis).hexdigest()!=args.bis_sha256 or sha256(sora).hexdigest()!=args.sora_sha256:
        raise SystemExit('Primary-source checksum differs from the reviewed capture')
    print(json.dumps(migrate(args.root,bis,sora,apply=args.apply),indent=2))

if __name__=='__main__':main()
