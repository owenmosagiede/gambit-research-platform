"""Online, read-only catalog diagnostic. Never an apply manifest or replay cache."""
from pathlib import Path
import hashlib
import os
import time
import uuid
from data.fx_migration_index import MigrationIndex,inventory,HEARTBEAT
from data.fx_migration_manifest import manifest_digest
from data.fx_currency_migration import _plan_indexed,MARKER
from data.fx_preparation_retirement import watch_options,runtime_blockers


def idle_heartbeat(root):
    """Only a healthy idle projection with no diagnostic/reference fields may vary.

    This is not an event-history exclusion: submissions, attempts, batch state,
    and all other operational records remain in the hash-bound inventory.
    """
    from data.alfred_onboarding import stable_read,strict_json
    path=Path(root)/HEARTBEAT
    if path.is_symlink() or not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('Unsafe worker heartbeat path: '+HEARTBEAT)
    for attempt in range(3):
        try:raw=stable_read(path);break
        except ValueError as exc:
            if str(exc)!='source changed during bounded read' or attempt==2:raise
    try:
        value=strict_json(raw)
        if not isinstance(value,dict) or set(value)!={'workspace','pid','session_id','monotonic_ns','health'}:raise ValueError()
        h=value['health']
        if (value['workspace']!=str(Path(root).resolve()) or type(value['pid']) is not int or value['pid']<=0
                or str(uuid.UUID(value['session_id']))!=value['session_id'] or type(value['monotonic_ns']) is not int
                or not 0<=time.monotonic_ns()-value['monotonic_ns']<=15_000_000_000
                or not isinstance(h,dict) or set(h)!={'healthy','state','worker_alive','supervisor_alive','restart_count','restart_limit','last_error','last_diagnostic'}
                or any(h[k] is not True for k in ('healthy','worker_alive','supervisor_alive')) or h['state']!='idle'
                or h['last_error'] is not None or h['last_diagnostic'] is not None
                or type(h['restart_count']) is not int or type(h['restart_limit']) is not int
                or not 0<=h['restart_count']<=h['restart_limit']):raise ValueError()
        os.kill(value['pid'],0)
    except (ValueError,TypeError,KeyError,AttributeError,OSError) as exc:
        raise ValueError('Worker heartbeat must be healthy, idle, fresh, and contain no unreviewed fields or diagnostics: '+HEARTBEAT) from exc
    return {'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'pid':value['pid'],'session_id':value['session_id']}


def catalog_preflight(root,release_ref,*,retirement=None):
    root=Path(root).resolve()
    report={'schema':'fx_currency_catalog_preflight_v1','diagnostic_only':True,
        'scientific_validation_performed':False,'apply_authorized':False,'release':release_ref,
        'blockers':[]}
    try:
        if (root/MARKER).exists():raise ValueError('Migration already in progress')
        from data.feature_store import FeatureStore
        if FeatureStore(root).resolve(release_ref)['body'].get('kind')!='fx_currency_release':
            raise ValueError('Expected staged currency release')
        first=idle_heartbeat(root)
        report['volatile_projection']={'path':HEARTBEAT,'before':first,'reason':'One-second health heartbeat; strict healthy-idle schema, no dependency-bearing diagnostics'}
        with MigrationIndex(root,online=True,**watch_options(retirement)) as index:
            result=_plan_indexed(root,release_ref,index,retirement=retirement)
            report.update(inventory_files=len(index.files),inventory_sha256=manifest_digest(index.files),
                candidate_deletions=len(result['delete']),candidate_replacements=len(result['replace']),
                protected_ts_files=len(result['protected_ts']),blockers=result['blockers'],
                preparation_files_selected=sum(p.startswith(retirement['prefix']) for p in result['delete']) if retirement else 0,
                preparation_dependencies=[{'path':p,'reference':v} for p,v in index.dependencies()
                    if retirement and not p.startswith(retirement['prefix'])])
            # Online writers are allowed. Drift means this diagnostic is not a
            # stable catalog view and must be explained before scientific replay.
            if inventory(root,online=True)!=index.files:report['blockers'].append('Catalog changed during online preflight; repeat on a stable view')
            last=idle_heartbeat(root);report['volatile_projection']['after']=last
            if (first['pid'],first['session_id'])!=(last['pid'],last['session_id']):
                report['blockers'].append('Worker restarted during online preflight; repeat on a stable view')
            if retirement:report['blockers'].extend(runtime_blockers())
    except (ValueError,KeyError,TypeError,OSError) as exc:
        report['blockers'].append(type(exc).__name__+': '+str(exc))
    report['blockers']=sorted(set(report['blockers']))
    report['catalog_ready']=not report['blockers']
    return report
