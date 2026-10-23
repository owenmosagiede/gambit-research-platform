"""Online, read-only catalog diagnostic. Never an apply manifest or replay cache."""
from pathlib import Path
from data.fx_migration_index import MigrationIndex,inventory
from data.fx_migration_manifest import manifest_digest
from data.fx_currency_migration import _plan_indexed,MARKER
from data.fx_preparation_retirement import watch_options,runtime_blockers


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
        with MigrationIndex(root,**watch_options(retirement)) as index:
            result=_plan_indexed(root,release_ref,index,retirement=retirement)
            report.update(inventory_files=len(index.files),inventory_sha256=manifest_digest(index.files),
                candidate_deletions=len(result['delete']),candidate_replacements=len(result['replace']),
                protected_ts_files=len(result['protected_ts']),blockers=result['blockers'],
                preparation_files_selected=sum(p.startswith(retirement['prefix']) for p in result['delete']) if retirement else 0,
                preparation_dependencies=[{'path':p,'reference':v} for p,v in index.dependencies()
                    if retirement and not p.startswith(retirement['prefix'])])
            # Online writers are allowed. Drift means this diagnostic is not a
            # stable catalog view and must be explained before scientific replay.
            if inventory(root)!=index.files:report['blockers'].append('Catalog changed during online preflight; repeat on a stable view')
            if retirement:report['blockers'].extend(runtime_blockers())
    except (ValueError,KeyError,TypeError,OSError) as exc:
        report['blockers'].append(type(exc).__name__+': '+str(exc))
    report['blockers']=sorted(set(report['blockers']))
    report['catalog_ready']=not report['blockers']
    return report
