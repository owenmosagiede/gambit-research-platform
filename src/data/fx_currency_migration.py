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
    root=Path(root).resolve();files={};records={}
    for folder in ('definitions','storage/catalog','config'):
        directory=root/folder
        for path in sorted(directory.rglob('*')):
            relative=path.relative_to(root).as_posix()
            if path.is_symlink():raise ValueError('Migration refuses symbolic links: '+relative)
            if not path.is_file() or relative.startswith(BASE+'/') or path.suffix=='.lock':continue
            # Configuration hashes detect drift; credentials are never parsed or emitted.
            raw=stable_read(path);files[relative]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
            if path.suffix=='.json' and folder!='config':records[relative]=strict_json(raw)
    return files,records


def plan(root,release_ref):
    from data.fx_currency_release import validate_release
    store=FeatureStore(root);release=store.resolve(release_ref)
    validate_release(root,release)
    files,records=_inventory(root);selected=set();blockers=[]
    eligible={p for p in records if p.startswith(CORE+OPERATIONAL)}
    scopes={p:_scopes(r) for p,r in records.items()}
    strings={p:_strings(r) for p,r in records.items()}
    for p in eligible:
        record=records[p]
        if p.startswith(CORE) and record.get('schema_version')!='0.8.0':
            blockers.append('Unsupported historical research schema: '+p)
        if scopes[p]&RETIRED:
            if scopes[p]-RETIRED:blockers.append('Mixed retired/retained Scope ownership: '+p)
            else:selected.add(p)
    for p,r in records.items():
        kind=str(r.get('record_type',''))
        if (p not in eligible and not p.startswith(ARTIFACTS) and p.startswith('storage/catalog/')
                and any(word in kind for word in ('trial','experiment','admission','validation','research_'))
                and (scopes[p]&RETIRED or r.get('schema_version') not in ('0.8.0',))):
            blockers.append('Unsupported historical consumer: '+p)
        if p.startswith('definitions/scopes/') and r.get('id') in RETIRED:selected.add(p)
        if r.get('layer')=='membership' and r.get('definition',{}).get('id') in RETIRED:
            selected.add(p)
    # Propagate request/event/relationship/trial dependencies, never Feature/price ownership.
    while True:
        ids=set().union(*(_identities(records[p]) for p in selected)) if selected else set()
        additions={p for p in eligible-selected if strings[p]&ids}
        for p in additions:
            if scopes[p]-RETIRED:blockers.append('Retained Scope record references retired CS history: '+p)
        additions={p for p in additions if not scopes[p]-RETIRED}
        if not additions:break
        selected|=additions
    # Delete whole old-only batch directories, including checksummed previews/packets.
    batchbase='storage/catalog/operations/research_batches/'
    batches={p[len(batchbase):].split('/')[0] for p in selected if p.startswith(batchbase)}
    for bid in batches:
        prefix=batchbase+bid+'/'
        paths={p for p in records if p.startswith(prefix)}
        if any(scopes[p]-RETIRED for p in paths):blockers.append('Mixed batch must be reconciled explicitly: '+bid)
        else:selected|=paths
    # Shared artifacts are retained; only artifacts exclusively referenced by deleted records qualify.
    removed_refs=set().union(*(strings[p] for p in selected)) if selected else set()
    kept_refs=set().union(*(strings[p] for p in records.keys()-selected if p!=INDEX and not p.startswith(ARTIFACTS)))
    for p,r in records.items():
        if p.startswith(ARTIFACTS) and r.get('id') in removed_refs and r.get('id') not in kept_refs:selected.add(p)
    if INDEX in files:selected.add(INDEX)  # Rebuildable mixed lookup; immutable TS authority is retained.
    # Fail closed for any other research consumer pointing at a deleted identity.
    deleted_ids=set().union(*(_identities(records[p]) for p in selected if p in records))
    for p in records.keys()-selected:
        # The unchanged TS membership policy intentionally embeds the original
        # grouping specification. It is dependency evidence, not CS trial history.
        shared_spec=records[p].get('body',{}).get('kind')=='fixed_fx_scope_specification'
        if not shared_spec and strings[p]&deleted_ids:
            blockers.append('Retained consumer references deletion: '+p)
    # Verify authoritative queue history, not just mutable job summaries.
    from runtime.research_jobs import ResearchJobs,ACTIVE
    jobs=ResearchJobs(root)
    request_ids={Path(p).stem for p in records if p.startswith(('storage/catalog/submissions/','storage/catalog/operations/jobs/'))}
    for rid in sorted(request_ids):
        try:
            job=jobs._read_job(rid)
            if job is None or job['status'] in ACTIVE:blockers.append('Unresolved or active request: '+rid)
        except (ValueError,KeyError,TypeError,OSError):blockers.append('Unverifiable request: '+rid)
    for p,r in records.items():
        if p.startswith(batchbase) and p.endswith('/manifest.json') and p not in selected:
            state_path=p.removesuffix('manifest.json')+'state.json'
            if records.get(state_path,{}).get('state')!='completed':
                blockers.append('Retained unfinished batch requires explicit reconciliation before release: '+p)
    # TS definitions and memberships must exist and remain exactly byte-identical.
    ts={r.get('id') for p,r in records.items() if p.startswith('definitions/scopes/') and r.get('body',{}).get('kind')=='instrument'}
    if ts!=set(PAIR_IDS):blockers.append('All 43 canonical TS Scopes must exist before migration')
    protected={p:files[p] for p,r in records.items() if (p.startswith('definitions/scopes/') and r.get('id') in PAIR_IDS)
        or (r.get('layer')=='membership' and r.get('definition',{}).get('id') in PAIR_IDS)}
    if len(protected)!=86:blockers.append('Each TS Scope requires exactly one retained membership snapshot')
    from data.scopes import resolve_scope
    for symbol in PAIR_IDS:
        try:
            scope=resolve_scope(root,symbol,'1.0.0')
            if scope['kind']!='instrument' or scope['members']!=[symbol]:raise ValueError('TS membership differs')
        except (ValueError,KeyError,TypeError,OSError):blockers.append('Retained TS closure is unverifiable: '+symbol)
    # Only owned, unshared payloads are removed. All other data remains outside this purge.
    removed_blobs=set().union(*(_blobs(records[p]) for p in selected if p in records))
    kept_blobs=set().union(*(_blobs(r) for p,r in records.items() if p not in selected))
    payloads={}
    for sha in sorted(removed_blobs-kept_blobs):
        for path in (Path(root)/'storage/payloads/sha256'/sha[:2]).glob(sha+'.*'):
            if path.is_symlink():raise ValueError('Symlink payload is unsupported')
            raw=stable_read(path)
            if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Deletion payload checksum mismatch')
            payloads[path.relative_to(root).as_posix()]={'sha256':sha,'bytes':len(raw)}
    deletions={p:files[p] for p in sorted(selected)};deletions.update(payloads)
    result={'schema':'fx_currency_deletion_v1','release':release_ref,'inventory':files,'delete':deletions,
        'protected_ts':protected,'retired_scopes':sorted(RETIRED),'blockers':sorted(set(blockers))}
    result['sha256']=digest(result)
    return result


def apply(root,manifest,expected_sha256):
    if (manifest.get('sha256')!=expected_sha256 or digest({k:v for k,v in manifest.items() if k!='sha256'})!=expected_sha256
            or manifest.get('schema')!='fx_currency_deletion_v1' or manifest.get('blockers')):
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
        if marker.exists():
            validate_release(root,release)
            if strict_json(stable_read(marker))!={'sha256':expected_sha256}:raise ValueError('Another migration is in progress')
        else:
            # Recompute eligibility as well as hashes; a caller cannot forge a broader deletion list.
            if plan(root,manifest['release'])!=manifest:raise ValueError('Deletion plan or inventory changed; re-plan')
        files,_=_inventory(root)
        expected={p:v for p,v in manifest['inventory'].items() if p not in manifest['delete']}
        actual={p:v for p,v in files.items() if p not in manifest['delete']}
        # Activation may have committed immediately before an interrupted completion receipt.
        from data.fx_currency_catalog import ACTIVE,active_release
        if marker.exists() and ACTIVE in actual and ACTIVE not in expected:
            if reference_for_active(root)==manifest['release']:actual.pop(ACTIVE)
        if actual!=expected:raise ValueError('Retained inventory changed; migration cannot resume')
        for p,v in manifest['delete'].items():
            path=inside(root,p)
            if (Path(root)/p).is_symlink():raise ValueError('Deletion path became a symlink')
            if path.exists():
                raw=stable_read(path)
                if {'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}!=v:raise ValueError('Deletion bytes changed: '+p)
        install_bytes(marker,canonical({'sha256':expected_sha256})+b'\n')
        # Durable manifest contains hashes only, so recovery never retains old results.
        install_bytes(inside(root,BASE+'/manifest.json'),canonical(manifest)+b'\n')
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
