#!/usr/bin/env python3
"""Separately approved code cutover preserving a fully accepted frozen queue.

Never stops or starts services. The operator first finishes intake and drains
execution; ordinary release_server.py continues to reject queued research.
No approval is generated here. Recovery refuses changed research authority.
"""
from contextlib import ExitStack
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import sys
import uuid

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT/'src'))
sys.path.insert(0, str(PROJECT/'tools'))
sys.path.insert(0, str(PROJECT/'deploy'))
import release_server as release
import retired_definitions
from release_bundle import verify, sha, canonical
from research.contracts import digest, ref, HORIZONS, scientific
from research.store import read_json, inside
from runtime.execution_compatibility import validate_approval, install_approval, make_proposal


def implementation_at(root):
    base = Path(root)/'src'
    files = {p.relative_to(base).as_posix(): sha(p.read_bytes())
             for folder in ('research', 'runtime', 'data', 'contracts')
             for p in sorted((base/folder).rglob('*.py'))}
    return {'profile': 'research_execution_0.8', 'files': files,
            'numeric_environment': {'python': sys.version}, 'fingerprint': digest(files)}


# The inventory is deliberately bounded by research authority, not market-data
# volume. Never recurse through the catalog root: lineage/Feature data can dwarf
# the experiment ledger. Unrelated research authority remains a rollback fence.
AUTHORITY_SCOPE = 'frozen_program_research_metadata_v1'
AUTHORITY_ROOTS = (
    'definitions', 'config',
    'storage/catalog/submissions', 'storage/catalog/attempts',
    'storage/catalog/trial_ledger', 'storage/catalog/admission_ledger',
    'storage/catalog/validation_ledger', 'storage/catalog/research_plans',
    'storage/catalog/research_exposure', 'storage/catalog/research_implementations',
    'storage/catalog/trial_artifacts',
    'storage/catalog/signal_library/relationships',
    'storage/catalog/signal_library/research_links',
    'storage/catalog/operations/experiment_intake/requests',
    'storage/catalog/operations/execution_compatibility/attempts',
    'storage/catalog/operations/execution_compatibility/trial_intents',
    'storage/catalog/operations/submission_incidents',
    'storage/catalog/operations/research_batches',
)


def authority_inventory(root):
    """Hash bounded research metadata, never data catalogs or payloads.

    Completed/partial trials, event order, reserved intake and new execution
    authority are still fenced, including research outside the target program.
    Definitions/configuration are preserved. Feature/Target/source/lineage data
    are immutable inputs, verified by the frozen bindings and normal execution
    readers; this code-only deployment cannot write those namespaces.
    """
    root = Path(root)
    result = {}
    for relative in AUTHORITY_ROOTS:
        base = root/relative
        for parent in (base, *base.parents):
            if parent.is_symlink():
                raise RuntimeError('Authority namespace cannot be a symlink')
            if parent == root:
                break
        if not base.exists():
            continue
        if not base.is_dir():
            raise RuntimeError('Authority namespace must be a directory')
        for p in sorted(base.rglob('*')):
            if p.is_symlink():
                raise RuntimeError('Authority path cannot be a symlink')
            if not p.is_file():
                continue
            # An artifact directory can only contribute its manifest. Numerical
            # evidence lives in payload storage and is never part of this read.
            if relative == 'storage/catalog/trial_artifacts' and p.name != 'manifest.json':
                continue
            if not p.resolve().is_relative_to(root.resolve()):
                raise RuntimeError('Authority path is not a regular in-store file')
            result[p.relative_to(root).as_posix()] = sha(p.read_bytes())
    return result


def capture(root, manifest_bytes):
    """Read immutable envelopes/events; never repair projections or publish."""
    from runtime.research_jobs import ResearchJobs, ACTIVE
    from runtime.experiment_identity import IdentityIndex, scientific_key
    from runtime.program_intake_compatibility import validate_entry_binding
    root = Path(root)
    manifest = json.loads(manifest_bytes)
    entries = manifest['entries']
    ids = [r['request_id'] for r in entries]
    if len(ids) != len(set(ids)):
        raise RuntimeError('Duplicate manifest request')
    jobs = ResearchJobs(root, start_worker=False)
    index = IdentityIndex(jobs)
    events = jobs._event_snapshot()
    catalog, targets = frozen_metadata(root, manifest)
    # Include committed trials even if a crash preceded link/event publication.
    by_relationship = {}
    trial_folder = root/'storage/catalog/trial_ledger/records'
    for path in sorted(trial_folder.glob('TRIAL_*.json')):
        trial = jobs.store.get('trial', path.stem)
        by_relationship.setdefault(trial['scientific_key']['relationship']['id'], []).append(trial)
    cohort, states = [], {}
    for entry in entries:
        journal = index.journal(entry['request_id'])
        if journal is None:
            raise RuntimeError('Wait for complete intake before this cutover')
        cid = journal['canonical_request_id']
        if cid != entry.get('expected_existing_request_id', entry['request_id']):
            raise RuntimeError('Frozen historical alias differs')
        original = jobs._submission(cid)
        job = jobs._read_job(cid, events)
        if job is None or job['status'] in ACTIVE - {'queued'}:
            raise RuntimeError('Drain active execution before capturing the cutover')
        if (original['intent'] != entry['intent'] or journal['intent'] != entry['intent']
                or journal['scientific_identity'] != scientific_key(original)):
            raise RuntimeError('Frozen cohort identity differs')
        if ((cid == entry['request_id'] and journal.get('submission') != original)
                or (cid != entry['request_id'] and journal.get('submission') not in (None, original))):
            raise RuntimeError('Frozen journal submission differs from canonical envelope')
        if jobs._incident_path(jobs._submission_path(cid)).exists():
            raise RuntimeError('Resolve submission integrity incident before cutover')
        validate_entry_binding(manifest, entry, original, feature_catalog=catalog, target_metadata=targets)
        if entry.get('expected_existing_request_id') and (
                job['status'] != 'succeeded' or job['results'] != entry['expected_existing_result_references']
                or scientific_key(original) != entry['expected_existing_scientific_identity']):
            raise RuntimeError('Frozen historical results differ')
        plan = original['frozen_plan']
        if (plan['recipe'] != entry['recipe_reference']
                or plan['scope']['reference'] != entry['scope_reference']
                or plan['scope']['membership_snapshot'] != entry['membership_snapshot']
                or plan['periods'] != entry['periods']):
            raise RuntimeError('Frozen manifest bindings differ')
        refs = {}
        for h in HORIZONS:
            relation = {'recipe': plan['recipe'], 'scope': plan['scope'], 'mode': plan['mode'],
                'target_family': 'price_return', 'horizon': h, 'horizon_unit': 'scheduled_weekdays',
                'members': [m['instrument_id'] for m in plan['members']],
                'targets': [m['targets'][str(h)]['definition'] for m in plan['members']],
                'expected_direction': plan['intent']['expected_direction']}
            if 'feature_application' in plan:
                relation['feature_application'] = plan['feature_application']
            for trial in by_relationship.get('RELATIONSHIP_' + digest(relation), []):
                key = trial['scientific_key']; phase = key['stage']
                expected_targets = [{'instrument': m['instrument_id'], 'binding': m['targets'][str(h)]} for m in plan['members']]
                if (phase in ('P1', 'P2') and key['period'] == plan['periods'][phase] and key['targets'] == scientific(expected_targets)
                        and key['research_spec'] == {'id': original['research_spec']['id'],
                            'version': original['research_spec']['version'], 'content_sha256': digest(original['research_spec'])}):
                    relationship = jobs.store.find('relationship', relation)
                    if (key['horizon'] != h or relationship is None
                            or relationship['body'] != scientific(relation) or key['relationship'] != ref(relationship)):
                        raise RuntimeError('Committed trial relationship or horizon differs')
                    refs[trial['id']] = ref(trial)
        if job['status'] != 'succeeded':
            seen = set()
            for binding in refs.values():
                trial = jobs.store.resolve('trial', binding); key = trial['scientific_key']
                pair = key['stage'], key['horizon']
                if pair in seen or jobs.store.resolve('implementation', key['implementation'])['body'] != original['implementation']:
                    raise RuntimeError('Ambiguous or unexpected executor in partial trial closure')
                seen.add(pair)
                prepared = key['prepared']
                if (prepared['phase'] != key['stage'] or prepared['period'] != plan['periods'][key['stage']]
                        or [m['instrument_id'] for m in prepared['members']] != [m['instrument_id'] for m in plan['members']]):
                    raise RuntimeError('Partial prepared membership or period differs')
                if key['stage'] == 'P1':
                    if key['discovery_trial'] is not None or key['discovery_effect'] is not None:
                        raise RuntimeError('Partial P1 unexpectedly refers to discovery')
                else:
                    if key['discovery_trial'] not in refs.values():
                        raise RuntimeError('Partial P2 discovery chain differs')
                    discovery = jobs.store.resolve('trial', key['discovery_trial'])
                    if (discovery['scientific_key']['stage'] != 'P1' or
                            discovery['scientific_key']['relationship'] != key['relationship'] or
                            discovery['scientific_key']['horizon'] != key['horizon'] or
                            discovery['body']['admission'] != 'admitted' or
                            key['discovery_effect'] != discovery['body']['metrics']['primary_effect']):
                        raise RuntimeError('Partial P2 discovery chain differs')
        for binding in refs.values():
            verify_trial_artifact_metadata(jobs.store, jobs.store.resolve('trial', binding))
        verify_result_metadata(jobs.store, job, refs)
        cohort.append({'request_id': entry['request_id'], 'canonical_request_id': cid,
            'intent_sha256': digest(entry['intent']), 'scientific_identity': scientific_key(original),
            'submission_sha256': original['record_sha256'],
            'committed_trials': [refs[k] for k in sorted(refs)]})
        states[cid] = {'status': job['status'], 'sequence': job['sequence'],
                       'results': job.get('results', []), 'plan': job.get('plan')}
    # Unknown queued work must not be carried across a scoped program migration.
    known = {r['canonical_request_id'] for r in cohort}
    names = {p.stem for p in (root/'storage/catalog/submissions').glob('*.json')}
    names.update(p.stem for p in (root/'storage/catalog/operations/jobs').glob('*.json'))
    names.update(k for k in events if k is not None)
    for path in (index.base/'requests').glob('*.json'):
        journal = index.journal(path.stem)
        if not journal or not jobs._submission_path(journal['canonical_request_id']).is_file():
            raise RuntimeError('Incomplete intake reservation outside captured publication')
        cid = journal['canonical_request_id']; names.add(cid)
        original = jobs._submission(cid)
        if (journal['intent'] != original['intent'] or journal['scientific_identity'] != scientific_key(original)
                or journal.get('submission') not in (None, original)):
            raise RuntimeError('Intake journal differs from canonical publication')
    for rid in names:
        if not jobs._submission_path(rid).is_file() or jobs._incident_path(jobs._submission_path(rid)).exists():
            raise RuntimeError('Orphan or unresolved submission integrity evidence')
        job = jobs._read_job(rid, events)
        if job is None:
            raise RuntimeError('Submission lacks authoritative execution events')
        if rid not in known and job['status'] in ACTIVE:
            raise RuntimeError('Unapproved active request outside the frozen program')
    from data.legacy_batch_evidence import pending
    if pending(root):
        raise RuntimeError('Unapproved legacy batch remains pending')
    result = {'authority_scope': AUTHORITY_SCOPE, 'manifest_sha256': sha(manifest_bytes), 'cohort': cohort,
              'states': states, 'authority': authority_inventory(root)}
    result['snapshot_sha256'] = digest(result)
    return result


def verify_result_metadata(store, job, trial_refs):
    """Verify saved reference closure; payload verification remains at execution."""
    for binding in job.get('results', []):
        link = store.resolve('link', binding)['body']
        store.resolve('relationship', link['relationship'])
        for trial_ref in link['trial_results']:
            if trial_ref not in trial_refs.values():
                raise RuntimeError('Job-linked trial is outside frozen committed closure')
            store.resolve('trial', trial_ref)
        for kind, field in (('admission', 'admission_results'), ('validation', 'validation_results')):
            for decision_ref in link.get(field, []):
                decision = store.resolve(kind, decision_ref)['body']
                if decision['relationship'] != link['relationship']:
                    raise RuntimeError('Historical decision relationship differs')


def verify_trial_artifact_metadata(store, trial):
    for artifact_ref in trial['body']['artifact_manifests']:
        artifact = read_json(inside(store.root, 'storage/catalog/trial_artifacts/' + artifact_ref['id'] + '/manifest.json'))
        if (ref(artifact) != artifact_ref or artifact['id'] != 'ARTIFACT_' +
                digest({k:v for k,v in artifact.items() if k != 'id'}) or
                artifact['scientific_key_sha256'] != digest(trial['scientific_key'])):
            raise RuntimeError('Historical artifact manifest reference differs')


def frozen_metadata(root, manifest):
    """Resolve immutable catalogs once; no numerical artifact/observation reads."""
    from data.feature_store import FeatureStore
    from data.targets.store import TargetStore
    from runtime.research_jobs import ResearchJobs
    from runtime.experiment_identity import IdentityIndex
    pins = manifest['global_pins']
    catalog = FeatureStore(root).resolve(pins['feature_catalog'])
    targets = TargetStore(root)
    # All envelopes must have the same exact profile reference (validated for
    # every entry below). Resolve that profile's Target metadata once, rather
    # than rereading 371 journals and rehashing the same Target records for
    # every recipe. A later differing profile is still rejected by capture.
    jobs = ResearchJobs(root); index = IdentityIndex(jobs)
    journal = index.journal(manifest['entries'][0]['request_id'])
    if journal is None:
        raise RuntimeError('Wait for complete intake before this cutover')
    packet = jobs._submission(journal['canonical_request_id'])
    profile = packet['research_spec']
    if (ref(profile) != pins['research_spec'] or
            digest(profile['target_selection']) != pins['source_and_target_pins_sha256']):
        raise RuntimeError('Frozen Target profile differs from manifest')
    found = {}
    for member, horizons in profile['target_selection']['materializations'].items():
        found[member] = {horizon: targets.resolve(binding) for horizon, binding in horizons.items()}
    return catalog, found


class Machine(release.Machine):
    def snapshot(self, manifest_bytes):
        return capture(self.root, manifest_bytes)

    def publish_approval(self, approval):
        # The release runs as root; the existing worker runs as gambit. Keep
        # this new operational namespace writable/readable by that identity.
        # Never chown the research store or modify historical records.
        import pwd
        account = pwd.getpwnam('gambit')
        from runtime.execution_compatibility import BASE
        for suffix in ('', '/approvals', '/attempts', '/trial_intents'):
            directory = release.safe_target(self.root, BASE + suffix)
            directory.mkdir(exist_ok=True, parents=True)
            os.chown(directory, account.pw_uid, account.pw_gid)
            os.chmod(directory, 0o750)
        install_approval(self.root, approval)
        path = release.safe_target(self.root, BASE + '/approvals/' + approval['id'] + '.json')
        os.chown(path, account.pw_uid, account.pw_gid)
        os.chmod(path, 0o640)

    def quiescent(self, manifest_sha256):
        if any(self.status(u) != 'inactive' for u in release.UNITS):
            raise RuntimeError('Web and all worker processes must be stopped after safe drain')
        # systemd inactive and the locks below fence workers; additionally rule
        # out the original standalone program intake process and descendants.
        proc = Path('/proc')
        if not proc.is_dir():
            raise RuntimeError('Linux process inventory is required for live cutover')
        ancestors = {os.getpid()}
        parent = os.getppid()
        while parent and parent not in ancestors:
            ancestors.add(parent)
            values = (proc/str(parent)/'status').read_text().splitlines()
            parent = int(next(v.split()[1] for v in values if v.startswith('PPid:')))
        for p in proc.iterdir():
            if not p.name.isdigit() or int(p.name) in ancestors:
                continue
            try:
                command = (p/'cmdline').read_bytes()
            except FileNotFoundError:
                continue
            if manifest_sha256.encode() in command:
                raise RuntimeError('Program intake process is still present; allow it to finish')


def check_retirement_evidence(retirement, equivalence_bytes, proposal=None):
    """Bind the optional historical exception to the human-reviewed evidence."""
    if equivalence_bytes is None:
        if retirement is not None:
            raise RuntimeError('Retirement requires the reviewed release evidence index')
        return
    evidence = json.loads(equivalence_bytes)
    binding = evidence.get('retirement_context') if isinstance(evidence, dict) else None
    if retirement is None:
        if binding is not None:
            raise RuntimeError('Reviewed retirement context must not be omitted')
        return
    if (evidence.get('schema') != 'frozen_program_release_evidence_v1'
            or binding != retirement.binding):
        raise RuntimeError('Retirement context differs from reviewed release evidence')
    if proposal is not None and (
            sha(equivalence_bytes) != proposal['evidence']['equivalence_sha256']
            or retirement.source_sha256 != proposal['source_archive_sha256']
            or retirement.target_sha256 != proposal['target_archive_sha256']):
        raise RuntimeError('Retirement evidence or archives differ from approval')


def code_plan(root, manifest, files, archive_sha256, retirement=None):
    if retirement is None:
        return release.plan(root, manifest, files)
    return retirement.code_plan(root, manifest, files, archive_sha256)


def check_evidence(approval, release_manifest, checks_bytes, equivalence_bytes, retirement=None):
    """The human review pins both evidence files, not just the archive name."""
    evidence = approval['proposal']['evidence']
    if (sha(checks_bytes) != evidence['tests_sha256']
            or sha(equivalence_bytes) != evidence['equivalence_sha256']):
        raise RuntimeError('Approved test or equivalence evidence differs')
    checks = json.loads(checks_bytes)
    if (checks.get('schema') != 'gambit_release_checks_v1' or checks.get('success') is not True
            or checks.get('commit') != release_manifest['commit']
            or checks.get('dirty_checkout') is not False or checks.get('production_data_used') is not False):
        raise RuntimeError('Clean passing release checks for this exact commit are required')
    check_retirement_evidence(retirement, equivalence_bytes, approval['proposal'])


def check_original_release(machine, approval, *, source_manifest, source_files,
                           source_archive_sha256, operator_bytes, retirement=None):
    proposal = approval['proposal']
    if (source_archive_sha256 != proposal['source_archive_sha256']
            or sha(operator_bytes) != proposal['operator_sha256']):
        raise RuntimeError('Frozen source archive or intake operator differs from approval')
    prior = code_plan(machine.root, source_manifest, source_files, source_archive_sha256, retirement)
    if prior['changes'] or prior['blockers']:
        raise RuntimeError('Installed code differs from the approved original archive')


def _proposal_bundle(machine, manifest_bytes, release_manifest, files, *, operator_sha256,
            source_manifest, source_files, source_archive_sha256, target_archive_sha256,
            checks_bytes, equivalence_bytes, retirement=None):
    """Construct a reviewable, inert proposal only at the quiescent boundary.

    This does not install an approval, change a queue, or alter the manifest.
    The source archive proves the complete installed code, not an assumed tag.
    """
    machine.quiescent(sha(manifest_bytes))
    check_retirement_evidence(retirement, equivalence_bytes)
    prior = code_plan(machine.root, source_manifest, source_files, source_archive_sha256, retirement)
    future = code_plan(machine.root, release_manifest, files, target_archive_sha256, retirement)
    if prior['changes'] or prior['blockers'] or future['blockers']:
        raise RuntimeError('Source archive or proposed code plan differs from the reviewed migration')
    old = implementation_at(machine.root)
    pins = json.loads(manifest_bytes)['global_pins']
    if (pins['implementation_digest'] != digest(old)
            or pins['implementation_fingerprint'] != old['fingerprint']):
        raise RuntimeError('Installed source does not match the original frozen executor')
    new_files = {name[4:]: sha(raw) for name, raw in files.items() if name.startswith('src/')
                 and name[4:].split('/')[0] in {'research', 'runtime', 'data', 'contracts'}
                 and name.endswith('.py')}
    new = dict(old, files=new_files, fingerprint=digest(new_files))
    snapshot = machine.snapshot(manifest_bytes)
    proposal = make_proposal(manifest_sha256=sha(manifest_bytes), operator_sha256=operator_sha256,
        from_implementation=old, to_implementation=new, cohort=snapshot['cohort'],
        evidence={'tests_sha256': sha(checks_bytes), 'equivalence_sha256': sha(equivalence_bytes)},
        source_archive_sha256=source_archive_sha256, target_archive_sha256=target_archive_sha256)
    check_evidence({'proposal': proposal}, release_manifest, checks_bytes, equivalence_bytes, retirement)
    return {'proposal': proposal, 'snapshot': snapshot, 'code_plan': future}


def propose(machine, manifest_bytes, release_manifest, files, **evidence):
    return _proposal_bundle(machine, manifest_bytes, release_manifest, files, **evidence)['proposal']


def review(machine, manifest_bytes, release_manifest, files, **evidence):
    """One fresh capture under maintenance locks; persist before returning.

    Never grants approval or installs code. A disconnected client can retrieve
    the durable package instead of repeating the capture. Apply still performs
    a fresh check at its own boundary; this is not a reusable bypass token.
    """
    with ExitStack() as guards:
        release.guard(guards, machine.state/'control.lock')
        release.guard(guards, machine.backup/'backup.lock')
        machine.quiescent(sha(manifest_bytes)); machine.backup_ready()
        _locks(guards, machine); machine.quiescent(sha(manifest_bytes))
        print('Capturing frozen cohort and bounded research metadata once', file=sys.stderr, flush=True)
        bundle = _proposal_bundle(machine, manifest_bytes, release_manifest, files, **evidence)
        proposal, snapshot, code = bundle['proposal'], bundle['snapshot'], bundle['code_plan']
        # Each completed review gets its own immutable package. Nothing is
        # installed under the application, including execution approval.
        folder = machine.state/'reviews'/('review-' + uuid.uuid4().hex)
        if (machine.state/'reviews').is_symlink():
            raise RuntimeError('Review directory cannot be a symlink')
        folder.mkdir(mode=0o700, parents=True, exist_ok=False)
        before = []
        for row in code['changes']:
            if row['before'] is not None:
                raw = release.safe_target(machine.root, row['path']).read_bytes()
                if sha(raw) != row['before']:
                    raise RuntimeError('Code changed during review')
                release.atomic(folder/'before'/row['path'], raw, mode=0o600)
            before.append({'path': row['path'], 'sha256': row['before']})
        for name, value in bundle.items():
            release.atomic(folder/(name+'.json'), canonical(value), mode=0o600)
        result = {'schema': 'frozen_program_review_package_v1', 'directory': str(folder),
            'commit': release_manifest['commit'], 'proposal': ref(proposal),
            'snapshot_sha256': digest(snapshot),
            'authority_scope': snapshot.get('authority_scope'),
            'cohort_count': len(snapshot['cohort']),
            'authority_records': len(snapshot['authority']), 'before_images': before,
            'checks_sha256': proposal['evidence']['tests_sha256'],
            'equivalence_sha256': proposal['evidence']['equivalence_sha256'],
            'approval_created': False, 'code_installed': False}
        release.atomic(folder/'receipt.json', canonical(result), mode=0o600)
        print('Review package saved: '+str(folder), file=sys.stderr, flush=True)
        return result


def make_plan(machine, manifest_bytes, release_manifest, files, approval, archive_sha256,
              *, retirement=None, equivalence_bytes=None):
    validate_approval(approval)
    proposal = approval['proposal']
    check_retirement_evidence(retirement, equivalence_bytes, proposal)
    if retirement is not None:
        # Repeat the complete source comparison under apply's maintenance locks.
        prior = code_plan(machine.root, retirement.source_manifest, retirement.source_files,
                          retirement.source_sha256, retirement)
        if prior['changes'] or prior['blockers']:
            raise RuntimeError('Installed code differs from the approved original archive')
    from runtime.execution_compatibility import approvals
    rows = proposal['cohort']
    rids = {r['request_id'] for r in rows}; canonical_ids = {r['canonical_request_id'] for r in rows}
    for prior in approvals(machine.root):
        if prior == approval or prior['proposal']['to_implementation'] != proposal['to_implementation']:
            continue
        old_rows = prior['proposal']['cohort']
        if rids & {r['request_id'] for r in old_rows} or canonical_ids & {r['canonical_request_id'] for r in old_rows}:
            raise RuntimeError('An overlapping execution approval already exists; explicit reconciliation required')
    if sha(manifest_bytes) != proposal['manifest_sha256'] or archive_sha256 != proposal['target_archive_sha256']:
        raise RuntimeError('Approved manifest or release archive differs')
    pins = json.loads(manifest_bytes)['global_pins']
    if (pins['implementation_digest'] != digest(proposal['from_implementation'])
            or pins['implementation_fingerprint'] != proposal['from_implementation']['fingerprint']):
        raise RuntimeError('Frozen manifest implementation differs from approval')
    snapshot = machine.snapshot(manifest_bytes)
    if snapshot['cohort'] != proposal['cohort']:
        raise RuntimeError('Approved cohort or committed trial references changed; refresh proposal')
    if implementation_at(machine.root) != proposal['from_implementation']:
        raise RuntimeError('Installed implementation differs from approval')
    expected = proposal['to_implementation']['files']
    prospective = dict(proposal['from_implementation']['files'])
    for name, data in files.items():
        if name.startswith('src/') and name[4:].split('/')[0] in {'research', 'runtime', 'data', 'contracts'} and name.endswith('.py'):
            prospective[name[4:]] = sha(data)
    if prospective != expected or proposal['to_implementation']['numeric_environment'] != {'python': sys.version}:
        raise RuntimeError('Release implementation or Python differs from approval')
    code = code_plan(machine.root, release_manifest, files, archive_sha256, retirement)
    if code['blockers']:
        raise RuntimeError('Code plan has registry/runtime/removal blockers')
    result = {'schema': 'frozen_program_cutover_plan_v1', 'approval': ref(approval),
        'archive_sha256': archive_sha256, 'manifest_sha256': proposal['manifest_sha256'],
        'source_archive_sha256': proposal['source_archive_sha256'], 'operator_sha256': proposal['operator_sha256'],
        'code': code, 'snapshot': snapshot,
        'restart_automatic': False, 'requires_complete_intake_and_safe_drain': True}
    if retirement is not None:
        result.update(schema='frozen_program_cutover_plan_v2',
                      retirement_context=retirement.binding,
                      equivalence_sha256=sha(equivalence_bytes))
    result['plan_sha256'] = digest(result)
    return result


def _locks(stack, machine):
    for name in release.LOCKS:
        release.guard(stack, machine.root/'storage/catalog/operations'/(name+'.lock'))
    # Preserve Feature-before-lineage lock order.
    for name in ('feature-store-publication.lock', 'target-store-publication.lock', 'lineage-packs-index.lock'):
        release.guard(stack, machine.root/'storage/temporary'/name)


def apply(machine, manifest_bytes, release_manifest, files, approval, archive_sha256, expected_plan,
          *, retirement=None, equivalence_bytes=None):
    """Already-approved, already-quiescent migration only. Never grants approval."""
    validate_approval(approval)
    with ExitStack() as guards:
        release.guard(guards, machine.state/'control.lock')
        release.guard(guards, machine.backup/'backup.lock')
        machine.quiescent(sha(manifest_bytes)); machine.backup_ready()
        _locks(guards, machine)
        machine.quiescent(sha(manifest_bytes))
        pending = [p for p in machine.state.glob('*/receipt.json')
                   if json.loads(p.read_text()).get('status') in {'installing','rollback_required'}]
        if pending:
            raise RuntimeError('Recover unfinished release first')
        plan = make_plan(machine, manifest_bytes, release_manifest, files, approval, archive_sha256,
                         retirement=retirement, equivalence_bytes=equivalence_bytes)
        if plan['plan_sha256'] != expected_plan:
            raise RuntimeError('Reviewed cutover plan changed')
        rid = 'program-' + release_manifest['commit'] + '-' + uuid.uuid4().hex[:12]
        folder = machine.state/rid; folder.mkdir(exist_ok=False)
        record = dict(plan, release_id=rid, status='installing', changes=plan['code']['changes'],
                      started_at=datetime.now(timezone.utc).isoformat())
        if retirement is not None:
            retirement.persist(folder/'retirement')
            release.atomic(folder/'release-evidence.json', equivalence_bytes, mode=0o600)
        for row in record['changes']:
            if row['before'] is not None:
                target = folder/'before'/row['path']; target.parent.mkdir(parents=True, exist_ok=True)
                data = release.safe_target(machine.root, row['path']).read_bytes()
                if sha(data) != row['before']:
                    raise RuntimeError('Code changed while preparing before-images')
                release.atomic(target, data, mode=0o600)
        release.atomic(folder/'receipt.json', canonical(record), mode=0o600)
        try:
            machine.publish_approval(approval)
            for row in record['changes']:
                machine.write(release.safe_target(machine.root, row['path']), files[row['path']])
            for row in record['changes']:
                if sha((machine.root/row['path']).read_bytes()) != row['after']:
                    raise RuntimeError('Installed code checksum differs')
            if machine.snapshot(manifest_bytes) != plan['snapshot']:
                raise RuntimeError('Research authority changed during cutover')
            if implementation_at(machine.root) != approval['proposal']['to_implementation']:
                raise RuntimeError('Installed executor differs from approval')
            if retirement is not None:
                retirement.revalidate(machine.root)
            record['status'] = 'installed_stopped'
        except BaseException:
            # Data changes require inspection, not a cosmetic code rollback.
            record['status'] = 'rollback_required'
            try:
                if machine.snapshot(manifest_bytes) == plan['snapshot']:
                    if retirement is not None:
                        retirement.revalidate(machine.root)
                    release.restore(machine, folder, record)
                    if retirement is not None:
                        retirement.revalidate(machine.root)
                    if machine.snapshot(manifest_bytes) != plan['snapshot']:
                        raise RuntimeError('Research authority changed during code restoration')
                    record['status'] = 'rolled_back_stopped'
            except BaseException:
                pass # Keep the recoverable receipt and services stopped.
            release.atomic(folder/'receipt.json', canonical(record), mode=0o600)
            raise
        record['finished_at'] = datetime.now(timezone.utc).isoformat()
        release.atomic(folder/'receipt.json', canonical(record), mode=0o600)
        return record


def recover(machine, manifest_bytes, release_id):
    """Restore old code only if no authority advanced; otherwise fail closed."""
    if '/' in release_id or '..' in release_id or not release_id.startswith('program-'):
        raise ValueError('Invalid program release ID')
    folder = machine.state/release_id
    record = read_json(folder/'receipt.json')
    if sha(manifest_bytes) != record['manifest_sha256']:
        raise RuntimeError('Recovery manifest differs')
    with ExitStack() as guards:
        release.guard(guards, machine.state/'control.lock')
        release.guard(guards, machine.backup/'backup.lock')
        machine.quiescent(record['manifest_sha256']); machine.backup_ready(); _locks(guards, machine)
        machine.quiescent(record['manifest_sha256'])
        if machine.snapshot(manifest_bytes) != record['snapshot']:
            raise RuntimeError('Research advanced: retain new records; use reviewed forward repair or reverse compatibility')
        retirement = None
        if record.get('schema') == 'frozen_program_cutover_plan_v2' or 'retirement_context' in record:
            if record.get('schema') != 'frozen_program_cutover_plan_v2':
                raise RuntimeError('Recovery retirement schema differs')
            retirement = retired_definitions.load_saved(folder/'retirement')
            evidence = retired_definitions.trusted_bytes(folder/'release-evidence.json')
            if (retirement.binding != record['retirement_context']
                    or sha(evidence) != record['equivalence_sha256']
                    or retirement.source_sha256 != record['source_archive_sha256']
                    or retirement.target_sha256 != record['archive_sha256']):
                raise RuntimeError('Recovery retirement evidence differs')
            from runtime.execution_compatibility import resolve
            approved = resolve(machine.root, record['approval'])
            check_retirement_evidence(retirement, evidence, approved['proposal'])
            retirement.revalidate(machine.root)
        release.restore(machine, folder, record)
        if retirement is not None:
            retirement.revalidate(machine.root)
        if machine.snapshot(manifest_bytes) != record['snapshot']:
            raise RuntimeError('Research authority changed during code restoration')
        record['status'] = 'rolled_back_stopped'
        release.atomic(folder/'receipt.json', canonical(record), mode=0o600)
        return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('snapshot', 'propose', 'review', 'plan', 'apply', 'recover'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--state', type=Path, default=release.STATE)
    parser.add_argument('--backup', type=Path, default=release.BACKUP)
    parser.add_argument('--approval', type=Path)
    parser.add_argument('--archive', type=Path); parser.add_argument('--sha256')
    parser.add_argument('--checks', type=Path); parser.add_argument('--equivalence', type=Path)
    parser.add_argument('--source-archive', type=Path); parser.add_argument('--source-sha256')
    parser.add_argument('--operator', type=Path); parser.add_argument('--operator-sha256')
    parser.add_argument('--retirement-plan', type=Path)
    parser.add_argument('--retirement-status', type=Path)
    parser.add_argument('--retirement-receipt', type=Path)
    parser.add_argument('--plan-sha256'); parser.add_argument('--release-id')
    args = parser.parse_args(); machine = Machine(args.root, args.state, args.backup)
    retirement = None
    retirement_paths = {'plan': args.retirement_plan, 'status': args.retirement_status,
                        'receipt': args.retirement_receipt}
    if any(retirement_paths.values()):
        if args.action not in ('propose', 'review', 'plan', 'apply') or not all(retirement_paths.values()):
            parser.error('Retirement requires all three exact evidence files for propose, review, plan or apply')
        if not all((args.archive, args.sha256, args.source_archive, args.source_sha256)):
            parser.error('Retirement requires both exact protected archives')
        retirement = retired_definitions.load_context(retirement_paths,
            args.source_archive, args.source_sha256, args.archive, args.sha256)
    raw = args.manifest.read_bytes()
    if args.action == 'snapshot':
        result = machine.snapshot(raw)
    elif args.action == 'recover':
        result = recover(machine, raw, args.release_id)
    elif args.action in ('propose', 'review'):
        if not all((args.archive, args.sha256, args.source_archive, args.source_sha256,
                    args.operator, args.operator_sha256, args.checks, args.equivalence)):
            parser.error('Proposal requires both verified archives, exact original operator, and release evidence')
        if sha(args.operator.read_bytes()) != args.operator_sha256:
            parser.error('Frozen operator checksum differs')
        manifest, files = verify(args.archive, args.sha256)
        source, source_files = verify(args.source_archive, args.source_sha256)
        result = (review if args.action == 'review' else propose)(machine, raw, manifest, files, operator_sha256=args.operator_sha256,
            source_manifest=source, source_files=source_files, source_archive_sha256=args.source_sha256,
            target_archive_sha256=args.sha256, checks_bytes=args.checks.read_bytes(),
            equivalence_bytes=args.equivalence.read_bytes(), retirement=retirement)
    else:
        if not all((args.approval, args.archive, args.sha256, args.checks, args.equivalence,
                    args.source_archive, args.source_sha256, args.operator)):
            parser.error('Exact approval, both archives/checksums, original operator, checks and equivalence evidence required')
        approval = read_json(args.approval); manifest, files = verify(args.archive, args.sha256)
        source, source_files = verify(args.source_archive, args.source_sha256)
        validate_approval(approval)
        equivalence_bytes = args.equivalence.read_bytes()
        check_evidence(approval, manifest, args.checks.read_bytes(), equivalence_bytes, retirement)
        check_original_release(machine, approval, source_manifest=source, source_files=source_files,
            source_archive_sha256=args.source_sha256, operator_bytes=args.operator.read_bytes(), retirement=retirement)
        if args.action == 'plan':
            result = make_plan(machine, raw, manifest, files, approval, args.sha256,
                               retirement=retirement, equivalence_bytes=equivalence_bytes)
        else:
            if not args.plan_sha256:
                parser.error('Apply requires the reviewed cutover plan SHA256')
            result = apply(machine, raw, manifest, files, approval, args.sha256, args.plan_sha256,
                           retirement=retirement, equivalence_bytes=equivalence_bytes)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
