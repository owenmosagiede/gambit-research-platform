"""Reviewed, hash-bound deletion of retired CS research; no general garbage collector.

The user explicitly superseded historical retention for these 18 Scopes only.
The manifest stores paths and hashes, never copies of deleted definitions/results.
Services must be stopped; locks and the maintenance marker also guard new code.
"""
from contextlib import ExitStack
import os
from pathlib import Path
import hashlib
import re
from data.alfred_onboarding import strict_json,stable_read
from data.scopes import UNIVERSES,PAIR_IDS
from data.transformations.fx_currency import SCOPE_IDS
from data.feature_store import FeatureStore
from data.targets.store import TargetStore
from research.store import lock,install_bytes,inside,FOLDERS
from research.contracts import canonical,digest,ResearchBlocked
from data.fx_migration_manifest import manifest_digest,install_manifest
from data.fx_migration_index import file_commitment

RETIRED={r[0] for r in UNIVERSES}
BASE='storage/catalog/operations/fx_currency_migration'
MARKER=BASE+'/in_progress.json'
CORE=tuple('storage/catalog/'+v+'/' for k,v in FOLDERS.items() if k!='implementation')
OPERATIONAL=('storage/catalog/submissions/','storage/catalog/attempts/',
    'storage/catalog/operations/jobs/','storage/catalog/operations/experiment_intake/requests/','storage/catalog/operations/experiment_intake/receipts/',
    'storage/catalog/operations/research_batches/','storage/catalog/operations/submission_incidents/')
ARTIFACTS='storage/catalog/trial_artifacts/'
INDEX='storage/catalog/operations/experiment_intake/index.json'


def check_intake(root,intent=None):
    if inside(root,MARKER).exists():
        raise ResearchBlocked([{'code':'CURRENCY_MIGRATION_IN_PROGRESS','message':'Currency migration must finish before research resumes.'}])
    from data.fx_currency_catalog import active_release
    if intent and intent.get('scope',{}).get('id') in RETIRED and active_release(root):
        raise ResearchBlocked([{'code':'RETIRED_SCOPE','message':'This legacy CS universe has been permanently removed.'}])


def _strings(value):
    if isinstance(value,str):return {value}
    if isinstance(value,list):return set().union(*(_strings(v) for v in value)) if value else set()
    if isinstance(value,dict):return set().union(*(_strings(v) for v in value.values())) if value else set()
    return set()


def _scopes(value):
    if isinstance(value,dict):
        found={value['id']} if isinstance(value.get('id'),str) and value.get('id') in RETIRED|set(PAIR_IDS)|set(SCOPE_IDS) else set()
        for key in ('scope','scope_id'):
            candidate=value.get(key)
            if isinstance(candidate,str) and candidate:found.add(candidate)
            elif isinstance(candidate,dict) and isinstance(candidate.get('id'),str):found.add(candidate['id'])
        return found|set().union(*(_scopes(v) for v in value.values())) if value else found
    if isinstance(value,list):return set().union(*(_scopes(v) for v in value)) if value else set()
    return set()


def _identities(value):
    if not isinstance(value,dict):return set()
    # Only ownership keys: source/Feature references are not ownership.
    return {value[k] for k in ('id','request_id','canonical_request_id','attempt_id','batch_id')
            if isinstance(value.get(k),str)}


def _blobs(value):
    found=set()
    if isinstance(value,dict):
        for key in ('blob_sha256','sha256'):
            sha=value.get(key)
            if isinstance(sha,str) and re.fullmatch('[0-9a-f]{64}',sha):found.add(sha)
        for item in value.values():found|=_blobs(item)
    elif isinstance(value,list):
        for item in value:found|=_blobs(item)
    return found


def _inventory(root):
    from data.fx_migration_index import inventory,Records
    files=inventory(root)
    return files,Records(root,files)


def plan(root,release_ref,*,retirement=None):
    from data.fx_currency_release import validate_release
    store=FeatureStore(root);release=store.resolve(release_ref)
    from data.fx_migration_index import MigrationIndex
    from data.fx_preparation_retirement import watch_options
    with MigrationIndex(root,**watch_options(retirement)) as index:
        result=_plan_indexed(root,release_ref,index,retirement=retirement)
        if not result["blockers"]:validate_release(root,release)
        return result


def _plan_indexed(root,release_ref,index,*,retirement=None):
    files,records=index.files,index.records;selected=set();blockers=[]
    from data.fx_batch_reconciliation import reconcile
    replacements,reconciled,batch_blockers=reconcile(Path(root),files,records,RETIRED,set(PAIR_IDS))
    blockers.extend(batch_blockers)
    # Ownership is evaluated against the reviewed retained-TS operational view.
    # The inventory continues to pin the ORIGINAL bytes until apply.
    index.replace(replacements)
    eligible={p for p in records if p.startswith(CORE+OPERATIONAL)}
    for p in eligible:
        record=records[p];scope=index.scope(p)
        if p.startswith(CORE) and record.get('schema_version')!='0.8.0':
            blockers.append('Unsupported historical research schema: '+p)
        if scope&RETIRED:
            if scope-RETIRED:blockers.append('Mixed retired/retained Scope ownership: '+p)
            else:selected.add(p)
    for p,r in index.metadata():
        kind=str(r.get('record_type',''))
        if (p not in eligible and not p.startswith(ARTIFACTS) and p.startswith('storage/catalog/')
                and any(word in kind for word in ('trial','experiment','admission','validation','research_'))
                and (index.scope(p)&RETIRED or r.get('schema_version') not in ('0.8.0',))):
            blockers.append('Unsupported historical consumer: '+p)
        if p.startswith('definitions/scopes/') and r.get('id') in RETIRED:selected.add(p)
        if r.get('layer')=='membership' and r.get('definition',{}).get('id') in RETIRED:
            selected.add(p)
    # Propagate request/event/relationship/trial dependencies, never Feature/price ownership.
    while True:
        index.select(selected)
        additions=index.related() & (eligible-selected)
        for p in additions:
            if index.scope(p)-RETIRED:blockers.append('Retained Scope record references retired CS history: '+p)
        additions={p for p in additions if not index.scope(p)-RETIRED}
        if not additions:break
        selected|=additions
    # Delete whole old-only batch directories, including checksummed previews/packets.
    batchbase='storage/catalog/operations/research_batches/'
    batches={p[len(batchbase):].split('/')[0] for p in selected if p.startswith(batchbase)}
    for bid in batches:
        prefix=batchbase+bid+'/'
        if prefix in reconciled:continue
        paths={p for p in records if p.startswith(prefix)}
        if any(index.scope(p)-RETIRED for p in paths):blockers.append('Mixed batch must be reconciled explicitly: '+bid)
        else:selected|=paths
    preparation=set()
    if retirement is not None:
        from data.fx_preparation_retirement import retirement_selection
        preparation,retirement_blockers=retirement_selection(root,index,retirement)
        blockers.extend(retirement_blockers);selected.update(preparation)
    # Shared artifacts are retained; only artifacts exclusively referenced by deleted records qualify.
    index.select(selected)
    artifacts=set()
    for p,r in index.metadata():
        if (p.startswith(ARTIFACTS) and index.referenced(r.get('id'),True,ARTIFACTS,INDEX,excluded_paths=preparation)
                and not index.referenced(r.get('id'),False,ARTIFACTS,INDEX)):artifacts.add(p)
    selected.update(artifacts)
    if INDEX in files:selected.add(INDEX)  # Rebuildable mixed lookup; immutable TS authority is retained.
    # Fail closed for any other research consumer pointing at a deleted identity.
    index.select(selected)
    for p,r in index.metadata():
        if p not in selected and not r['_body_is_mapping']:
            raise ValueError('Unsupported retained record body: '+p)
    for p in index.related():
        # The unchanged TS membership policy intentionally embeds the original
        # grouping specification. It is dependency evidence, not CS trial history.
        value=records[p]
        shared_spec=isinstance(value,dict) and isinstance(value.get('body',{}),dict) and value.get('body',{}).get('kind')=='fixed_fx_scope_specification'
        if not shared_spec:
            blockers.append('Retained consumer references deletion: '+p)
    # Verify authoritative queue history, not just mutable job summaries.
    from runtime.research_jobs import ResearchJobs,ACTIVE
    jobs=ResearchJobs(root)
    request_ids={Path(p).stem for p in records if p.startswith(('storage/catalog/submissions/','storage/catalog/operations/jobs/'))}
    for p,r in index.metadata():
        if p.startswith('storage/catalog/operations/experiment_intake/requests/') and p not in selected:
            if isinstance(r.get('canonical_request_id'),str):request_ids.add(r['canonical_request_id'])
            else:blockers.append('Unverifiable retained intake reservation: '+p)
    for rid in sorted(request_ids):
        try:
            job=jobs._read_job(rid)
            if job is None or job['status'] in ACTIVE:blockers.append('Unresolved or active request: '+rid)
        except (ValueError,KeyError,TypeError,OSError):blockers.append('Unverifiable request: '+rid)
    for p,r in index.metadata():
        if p.startswith(batchbase) and p.endswith('/manifest.json') and p not in selected:
            state_path=p.removesuffix('manifest.json')+'state.json'
            if records.get(state_path,{}).get('state')!='completed':
                blockers.append('Retained unfinished batch requires explicit reconciliation before release: '+p)
    # TS definitions and memberships must exist and remain exactly byte-identical.
    ts={r.get('id') for p,r in index.metadata() if p.startswith('definitions/scopes/') and r.get('body',{}).get('kind')=='instrument'}
    if ts!=set(PAIR_IDS):blockers.append('All 43 canonical TS Scopes must exist before migration')
    protected={p:files[p] for p,r in index.metadata() if (p.startswith('definitions/scopes/') and r.get('id') in PAIR_IDS)
        or (r.get('layer')=='membership' and r.get('definition',{}).get('id') in PAIR_IDS)}
    if len(protected)!=86:blockers.append('Each TS Scope requires exactly one retained membership snapshot')
    from data.scopes import resolve_scope
    for symbol in PAIR_IDS:
        try:
            scope=resolve_scope(root,symbol,'1.0.0')
            if scope['kind']!='instrument' or scope['members']!=[symbol]:raise ValueError('TS membership differs')
        except (ValueError,KeyError,TypeError,OSError):blockers.append('Retained TS closure is unverifiable: '+symbol)
    # Only owned, unshared payloads are removed. All other data remains outside this purge.
    payloads={}
    for sha in index.removed_blobs(excluded_paths=preparation):
        for path in (Path(root)/'storage/payloads/sha256'/sha[:2]).glob(sha+'.*'):
            if path.is_symlink():raise ValueError('Symlink payload is unsupported')
            binding=file_commitment(path)
            if binding['sha256']!=sha:raise ValueError('Deletion payload checksum mismatch')
            payloads[path.relative_to(root).as_posix()]=binding
    deletions={p:files[p] for p in sorted(selected)};deletions.update(payloads)
    result={'schema':'fx_currency_deletion_v2','release':release_ref,'inventory':files,'delete':deletions,
        'replace':replacements,
        'protected_ts':protected,'retired_scopes':sorted(RETIRED),'blockers':sorted(set(blockers))}
    if retirement is not None:result['preparation_retirement']=retirement
    result['sha256']=manifest_digest(result)
    return result


def apply(root,manifest,expected_sha256):
    if (manifest.get('sha256')!=expected_sha256 or manifest_digest({k:v for k,v in manifest.items() if k!='sha256'})!=expected_sha256
            or manifest.get('schema')!='fx_currency_deletion_v2' or manifest.get('blockers')):
        raise ValueError('A complete, unchanged, unblocked deletion manifest is required')
    from data.fx_currency_release import validate_release
    from data.fx_currency_catalog import activate
    marker=inside(root,MARKER);done=inside(root,BASE+'/completed.json')
    if done.exists():
        if strict_json(stable_read(done))!={'sha256':expected_sha256,'release':manifest['release']}:raise ValueError('Another migration already completed')
        if marker.exists():
            if strict_json(stable_read(marker))!={'sha256':expected_sha256}:raise ValueError('Completion marker differs')
            marker.unlink()
        return {'completed':True,'reused':True}
    with ExitStack() as stack:
        for name in ('batch-writer','research-executor','research-writer'):
            if not stack.enter_context(lock(root,name,nonblocking=True)):raise ValueError('Stop active writers before migration')
        stack.enter_context(FeatureStore(root).writer());stack.enter_context(TargetStore(root).writer())
        release=FeatureStore(root).resolve(manifest['release'])
        if manifest.get('preparation_retirement'):
            from data.fx_preparation_retirement import runtime_blockers
            if runtime_blockers():raise ValueError('Preparation runtime must be inactive before retirement')
        if marker.exists():
            validate_release(root,release)
            if strict_json(stable_read(marker))!={'sha256':expected_sha256}:raise ValueError('Another migration is in progress')
        else:
            # Recompute eligibility as well as hashes; a caller cannot forge a broader deletion list.
            if plan(root,manifest['release'],retirement=manifest.get('preparation_retirement'))!=manifest:raise ValueError('Deletion plan or inventory changed; re-plan')
        from data.fx_migration_index import inventory
        files=inventory(root)
        changed=set(manifest['delete'])|set(manifest['replace'])
        expected={p:v for p,v in manifest['inventory'].items() if p not in changed}
        actual={p:v for p,v in files.items() if p not in changed}
        # Activation may have committed immediately before an interrupted completion receipt.
        from data.fx_currency_catalog import ACTIVE,active_release
        if marker.exists() and ACTIVE in actual and ACTIVE not in expected:
            if reference_for_active(root)==manifest['release']:actual.pop(ACTIVE)
        if actual!=expected:raise ValueError('Retained inventory changed; migration cannot resume')
        for p,value in manifest['replace'].items():
            raw=canonical(value)+b'\n'
            after={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
            if files.get(p) not in (manifest['inventory'][p],after):
                raise ValueError('Reconciled batch bytes changed: '+p)
        for p,v in manifest['delete'].items():
            path=inside(root,p)
            if (Path(root)/p).is_symlink():raise ValueError('Deletion path became a symlink')
            if path.exists():
                if file_commitment(path)!=v:raise ValueError('Deletion bytes changed: '+p)
        install_bytes(marker,canonical({'sha256':expected_sha256})+b'\n')
        # Recovery retains only hashes of deleted data and the retained-TS view;
        # it never stores copies of discarded CS definitions or research.
        install_manifest(inside(root,BASE+'/manifest.json'),manifest)
        for p,value in sorted(manifest['replace'].items()):
            install_bytes(inside(root,p),canonical(value)+b'\n',mutable=True)
        for p in sorted(manifest['delete']):
            path=inside(root,p)
            if path.exists():
                path.unlink()
                fd=os.open(path.parent,os.O_RDONLY)
                try:os.fsync(fd)
                finally:os.close(fd)
        for p,v in manifest['protected_ts'].items():
            raw=stable_read(inside(root,p))
            if hashlib.sha256(raw).hexdigest()!=v['sha256']:raise ValueError('Retained TS bytes changed')
        activate(root,release)
        install_bytes(done,canonical({'sha256':expected_sha256,'release':manifest['release']})+b'\n')
        marker.unlink()
    return {'completed':True,'deleted_files':len(manifest['delete']),'retained_ts_scopes':43,'active_cs_scopes':7}


def reference_for_active(root):
    from data.fx_currency_catalog import active_release
    from data.transformations.identity import reference
    value=active_release(root)
    return reference(value) if value else None


def check_staged_request(root,release_ref,request):
    """Reuse an existing staged release only with the original frozen inputs."""
    from data.fx_currency_catalog import active_release
    if inside(root,MARKER).exists() or active_release(root):raise ValueError('Existing activation requires recovery')
    store=FeatureStore(root);release=store.resolve(release_ref)
    if release['body'].get('kind')!='fx_currency_release':raise ValueError('Expected currency release')
    catalog=store.resolve(release['body']['price_catalog'])['body']
    if (catalog['source_snapshots']!=request['source_snapshots'] or catalog['return_policy']!=request['return_policy']):
        raise ValueError('Staged release differs from frozen source/policy request')
    # Full scientific replay remains mandatory in plan(); this check is no cache.
    return release


def verify_applied(root,manifest):
    """Verify retained bytes and registry as the application account after apply."""
    from data.fx_migration_index import inventory
    from data.fx_currency_catalog import active_release
    from data.transformations.identity import reference
    from data.scopes import list_scopes
    if manifest_digest({k:v for k,v in manifest.items() if k!='sha256'})!=manifest['sha256'] or manifest['blockers']:
        raise ValueError('Invalid verification manifest')
    if inside(root,MARKER).exists():raise ValueError('Migration is unfinished')
    done=strict_json(stable_read(inside(root,BASE+'/completed.json')))
    if done!={'sha256':manifest['sha256'],'release':manifest['release']}:raise ValueError('Completion receipt differs')
    current=inventory(root);changed=set(manifest['delete'])|set(manifest['replace'])
    for name,expected in manifest['inventory'].items():
        if name not in changed and current.get(name)!=expected:raise ValueError('Retained inventory changed: '+name)
    for name in manifest['delete']:
        if inside(root,name).exists():raise ValueError('Deleted file remains: '+name)
    for name,value in manifest['replace'].items():
        if stable_read(inside(root,name))!=canonical(value)+b'\n':raise ValueError('Replacement differs: '+name)
    release=active_release(root)
    if not release or reference(release)!=manifest['release']:raise ValueError('Active release differs')
    scopes=list_scopes(root);ts=[s for s in scopes['scopes'] if s['kind']=='instrument'];cs=[s for s in scopes['scopes'] if s['kind']=='universe']
    if (scopes['issues'] or len(ts)!=43 or len(cs)!=7 or {s['id'] for s in ts}!=set(PAIR_IDS)
            or any(s['members']!=[s['id']] for s in ts) or {s['id'] for s in cs}!=set(SCOPE_IDS)
            or any(len(s['members'])!=18 for s in cs)):raise ValueError('Final scope membership differs')
    from data.fx_currency_features import records,context
    from data.fx_currency_release import profile_for
    from data.targets.fx import read_materialization
    store,catalog,policy=context(root)
    if len(records(root))!=180 or len(catalog['body']['bindings'])!=22680:raise ValueError('Feature bindings incomplete')
    for binding in catalog['body']['bindings']:store.resolve(binding['feature'])
    targets=profile_for(root,release)['target_selection']['materializations']
    if len(targets)!=126 or sum(len(v) for v in targets.values())!=630:raise ValueError('Target bindings incomplete')
    read_materialization(root,targets[sorted(targets)[0]]['1']['id'])
    return {'completed':True,'active_ts_scopes':43,'active_cs_scopes':7,'retained_files_verified':len(manifest['inventory'])-len(set(manifest['inventory'])&changed),
        'deleted_files_absent':len(manifest['delete']),'feature_bindings_read':22680,'target_bindings':630,'sample_target_read':True,'sha256':manifest['sha256']}
