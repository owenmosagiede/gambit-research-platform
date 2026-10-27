"""Offline, stopped-service cutover fixtures; no production approval or access."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT/'deploy'))
import program_cutover as cutover
from research.contracts import canonical, digest, ref
from runtime.execution_compatibility import make_proposal, install_approval
from test_execution_compatibility import synthetic_approval
from test_release_workflow import artifact, FakeMachine
from test_research_runtime import Adapter, KernelSpy, intent, profile
from runtime.research_jobs import ResearchJobs


class StoppedMachine(FakeMachine):
    def __init__(self, base):
        super().__init__(base)
        self.states = dict.fromkeys(cutover.release.UNITS, 'inactive')
        self.intake_running = False
        self.cohort = [{'request_id': '01234567-1234-4234-8234-012345678901',
                       'canonical_request_id': '01234567-1234-4234-8234-012345678901',
                       'intent_sha256': '1'*64, 'scientific_identity': '2'*64,
                       'submission_sha256': '3'*64, 'committed_trials': []}]
    def snapshot(self, manifest_bytes):
        return {'manifest_sha256': cutover.sha(manifest_bytes), 'cohort': deepcopy(self.cohort),
                'states': {'terminal': 'succeeded', 'pending': 'queued'},
                'authority': cutover.authority_inventory(self.root)}
    def quiescent(self, manifest_sha256):
        if self.intake_running or any(v != 'inactive' for v in self.states.values()):
            raise RuntimeError('Drain and finish intake first')
    def publish_approval(self, approval):
        install_approval(self.root, approval)


class CutoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.m = StoppedMachine(Path(self.tmp.name))
        (self.m.root/'src/runtime').mkdir(parents=True)
        self.code = self.m.root/'src/runtime/example.py'; self.code.write_bytes(b'old executor\n')
        self.history = self.m.root/'storage/catalog/trial_ledger/records/preserved.json'
        self.history.parent.mkdir(parents=True); self.history.write_bytes(b'preserved historical authority')
        self.files = {'src/runtime/example.py': b'new executor\n'}
        self.release_manifest = artifact(self.files)
        self.old = cutover.implementation_at(self.m.root)
        self.manifest_bytes = canonical({'fixture': 'frozen program', 'global_pins': {
            'implementation_digest': digest(self.old), 'implementation_fingerprint': self.old['fingerprint']}})
        self.code.write_bytes(self.files['src/runtime/example.py'])
        self.new = cutover.implementation_at(self.m.root)
        self.code.write_bytes(b'old executor\n')
        self.tests_bytes = canonical({'schema': 'gambit_release_checks_v1', 'success': True,
            'commit': self.release_manifest['commit'], 'dirty_checkout': False, 'production_data_used': False})
        self.equivalence_bytes = canonical({'isolated_fixture': True, 'exact_equal': True})
        self.proposal = make_proposal(manifest_sha256=cutover.sha(self.manifest_bytes), operator_sha256='b'*64,
            from_implementation=self.old, to_implementation=self.new, cohort=self.m.cohort,
            evidence={'tests_sha256': cutover.sha(self.tests_bytes),
                      'equivalence_sha256': cutover.sha(self.equivalence_bytes)},
            source_archive_sha256='e'*64, target_archive_sha256='f'*64)
        self.approval = synthetic_approval(self.proposal)
    def plan(self):
        return cutover.make_plan(self.m, self.manifest_bytes, self.release_manifest,
                                 self.files, self.approval, 'f'*64)
    def apply(self, expected=None):
        return cutover.apply(self.m, self.manifest_bytes, self.release_manifest,
            self.files, self.approval, 'f'*64, expected or self.plan()['plan_sha256'])
    def test_queued_cutover_preserves_authority_and_never_starts_or_stops_services(self):
        before = self.m.snapshot(self.manifest_bytes)
        self.m.jobs = ['queued request']
        with self.assertRaisesRegex(RuntimeError, 'Queued or running'):
            self.m.idle() # Ordinary deployment still refuses backlog.
        result = self.apply()
        self.assertEqual(result['status'], 'installed_stopped')
        self.assertEqual(self.code.read_bytes(), b'new executor\n')
        self.assertEqual(self.m.snapshot(self.manifest_bytes), before)
        self.assertEqual(self.m.events, [])
        self.assertEqual(cutover.implementation_at(self.m.root), self.new)
        self.assertEqual(len(list((self.m.root/'storage/catalog/operations/execution_compatibility/approvals').glob('*.json'))), 1)
    def test_inert_proposal_cannot_install(self):
        self.approval = self.proposal
        with self.assertRaises(Exception): self.apply('0'*64)
        self.assertEqual(self.code.read_bytes(), b'old executor\n')
    def test_approval_namespace_is_readable_and_writable_by_existing_worker_identity(self):
        from types import SimpleNamespace
        import os
        account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
        with patch('pwd.getpwnam', return_value=account), patch.object(cutover.os, 'chown') as chown:
            cutover.Machine.publish_approval(self.m, self.approval)
        base = self.m.root/'storage/catalog/operations/execution_compatibility'
        for suffix in ('', 'approvals', 'attempts', 'trial_intents'):
            directory = base/suffix
            self.assertEqual(directory.stat().st_mode & 0o777, 0o750)
            chown.assert_any_call(directory, account.pw_uid, account.pw_gid)
        path = base/'approvals'/(self.approval['id']+'.json')
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        chown.assert_any_call(path, account.pw_uid, account.pw_gid)
    def test_full_intake_and_safe_drain_are_required(self):
        self.m.intake_running = True
        with self.assertRaisesRegex(RuntimeError, 'Drain'): self.apply()
        self.m.intake_running = False; self.m.states[cutover.release.UNITS[1]] = 'active'
        with self.assertRaisesRegex(RuntimeError, 'Drain'): self.apply()
        self.assertEqual(self.m.events, [])
    def test_changed_cohort_code_manifest_archive_or_plan_blocks_before_writes(self):
        expected = self.plan()['plan_sha256']
        self.m.cohort[0]['committed_trials'] = [{'id':'TRIAL_'+'0'*64, 'version':'1.0.0', 'content_sha256':'1'*64}]
        with self.assertRaisesRegex(RuntimeError, 'cohort'): self.apply(expected)
        self.m.cohort = deepcopy(self.proposal['cohort'])
        self.code.write_bytes(b'unreviewed executor')
        with self.assertRaisesRegex(RuntimeError, 'implementation'): self.apply(expected)
        self.code.write_bytes(b'old executor\n')
        for kwargs in ({'manifest_bytes':b'{}'}, {'archive_sha256':'0'*64}):
            args = dict(machine=self.m, manifest_bytes=self.manifest_bytes,
                release_manifest=self.release_manifest, files=self.files, approval=self.approval, archive_sha256='f'*64)
            with self.assertRaisesRegex(RuntimeError, 'manifest or release'): cutover.make_plan(**dict(args, **kwargs))
        with self.assertRaisesRegex(RuntimeError, 'plan changed'): self.apply('0'*64)
        self.assertEqual(self.code.read_bytes(), b'old executor\n')
    def test_pending_registry_runtime_or_removal_changes_still_block(self):
        self.files['config/research_execution.json'] = b'changed scientific policy'
        self.release_manifest = artifact(self.files)
        with self.assertRaisesRegex(RuntimeError, 'blockers'): self.plan()
    def test_backup_and_all_existing_publication_locks_are_required(self):
        paths = [self.m.backup/'backup.lock'] + [self.m.root/'storage/catalog/operations'/(v+'.lock')
            for v in cutover.release.LOCKS] + [self.m.root/'storage/temporary'/v
            for v in ('feature-store-publication.lock', 'target-store-publication.lock', 'lineage-packs-index.lock')]
        for path in paths:
            with self.subTest(lock=path.name), ExitStack() as stack:
                cutover.release.guard(stack, path)
                with self.assertRaisesRegex(RuntimeError, 'owns'): self.apply()
        status = self.m.backup/'status.json'; record = json.loads(status.read_text())
        record['finished_at'] = (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        status.write_text(json.dumps(record))
        with self.assertRaisesRegex(RuntimeError, 'backup'): self.apply()
    def test_failed_install_restores_code_only_and_preserves_history(self):
        self.m.fail_write = True
        before = self.history.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'write failure'): self.apply()
        record = json.loads(next(self.m.state.glob('*/receipt.json')).read_text())
        self.assertEqual(record['status'], 'rolled_back_stopped')
        self.assertEqual(self.code.read_bytes(), b'old executor\n')
        self.assertEqual(self.history.read_bytes(), before)
        self.assertFalse(self.m.events)
    def test_recovery_refuses_after_any_new_authority_and_does_not_erase_records(self):
        result = self.apply()
        new_trial = self.history.with_name('new-trial.json'); new_trial.write_text('new immutable outcome')
        with self.assertRaisesRegex(RuntimeError, 'Research advanced'):
            cutover.recover(self.m, self.manifest_bytes, result['release_id'])
        self.assertEqual(new_trial.read_text(), 'new immutable outcome')
        self.assertEqual(self.code.read_bytes(), b'new executor\n')
    def test_execution_intents_and_provenance_prevent_unsafe_rollback(self):
        result = self.apply()
        directory = self.m.root/'storage/catalog/operations/execution_compatibility/trial_intents/request'
        directory.mkdir(parents=True); intent_path = directory/'intent.json'
        intent_path.write_text('exact new trial identity')
        with self.assertRaisesRegex(RuntimeError, 'Research advanced'):
            cutover.recover(self.m, self.manifest_bytes, result['release_id'])
        self.assertIn(str(intent_path.relative_to(self.m.root)), cutover.authority_inventory(self.m.root))
    def test_another_overlapping_approval_blocks_but_exact_retry_remains_safe(self):
        install_approval(self.m.root, self.approval)
        self.plan() # An exact retry is allowed after a failed, restored installation.
        changed = deepcopy(self.proposal); changed['evidence']['tests_sha256'] = '0'*64
        from runtime.execution_compatibility import _seal
        changed = _seal('EXECPROPOSAL', {k:v for k,v in changed.items() if k!='id'})
        self.approval = synthetic_approval(changed)
        with self.assertRaisesRegex(RuntimeError, 'overlapping'): self.plan()
        self.assertEqual(len(list((self.m.root/'storage/catalog/operations/execution_compatibility/approvals').glob('*.json'))), 1)
    def test_recovery_before_new_authority_restores_exact_old_code(self):
        result = self.apply()
        recovered = cutover.recover(self.m, self.manifest_bytes, result['release_id'])
        self.assertEqual(recovered['status'], 'rolled_back_stopped')
        self.assertEqual(cutover.implementation_at(self.m.root), self.old)
        self.assertFalse(self.m.events)
    def test_exact_passing_checks_and_equivalence_evidence_required(self):
        args = [self.approval, self.release_manifest, self.tests_bytes, self.equivalence_bytes]
        cutover.check_evidence(*args)
        for index in (2,3):
            changed = list(args); changed[index] += b' '
            with self.assertRaisesRegex(RuntimeError, 'evidence differs'): cutover.check_evidence(*changed)
        changed = deepcopy(self.release_manifest); changed['commit'] = 'b'*40
        with self.assertRaisesRegex(RuntimeError, 'exact commit'):
            cutover.check_evidence(self.approval, changed, self.tests_bytes, self.equivalence_bytes)
    def test_proposal_pins_archives_and_cohort_but_grants_no_approval(self):
        old_files = {'src/runtime/example.py': b'old executor\n'}
        proposed = cutover.propose(self.m, self.manifest_bytes, self.release_manifest, self.files,
            operator_sha256='b'*64, source_manifest=artifact(old_files), source_files=old_files,
            source_archive_sha256='e'*64, target_archive_sha256='f'*64,
            checks_bytes=self.tests_bytes, equivalence_bytes=self.equivalence_bytes)
        self.assertEqual(proposed, self.proposal)
        self.assertFalse((self.m.root/'storage/catalog/operations/execution_compatibility').exists())
        self.assertEqual(self.code.read_bytes(), b'old executor\n')
        old_files['src/runtime/example.py'] = b'wrong old archive'
        with self.assertRaisesRegex(RuntimeError, 'Source archive'):
            cutover.propose(self.m, self.manifest_bytes, self.release_manifest, self.files,
                operator_sha256='b'*64, source_manifest=artifact(old_files), source_files=old_files,
                source_archive_sha256='e'*64, target_archive_sha256='f'*64,
                checks_bytes=self.tests_bytes, equivalence_bytes=self.equivalence_bytes)
    def test_original_archive_and_frozen_operator_are_explicitly_verified(self):
        raw = b'isolated operator'
        from runtime.execution_compatibility import _seal
        p = dict(self.proposal, operator_sha256=cutover.sha(raw))
        approved = synthetic_approval(_seal('EXECPROPOSAL', {k:v for k,v in p.items() if k!='id'}))
        source = {'src/runtime/example.py': b'old executor\n'}
        args = dict(source_manifest=artifact(source), source_files=source,
                    source_archive_sha256='e'*64, operator_bytes=raw)
        cutover.check_original_release(self.m, approved, **args)
        for changed in ({'source_archive_sha256':'0'*64}, {'operator_bytes':b'changed operator'}):
            with self.assertRaisesRegex(RuntimeError, 'differs from approval'):
                cutover.check_original_release(self.m, approved, **dict(args, **changed))
    def test_authority_directory_symlink_cannot_hide_history(self):
        target = self.m.root/'storage/catalog/hidden'; target.mkdir()
        (self.m.root/'storage/catalog/trial_ledger/alias').symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'symlink'): cutover.authority_inventory(self.m.root)

    def test_review_captures_once_and_saves_inert_retrievable_package(self):
        source = {'src/runtime/example.py': b'old executor\n'}
        with patch.object(self.m, 'snapshot', wraps=self.m.snapshot) as capture:
            result = cutover.review(self.m, self.manifest_bytes, self.release_manifest, self.files,
                operator_sha256='b'*64, source_manifest=artifact(source), source_files=source,
                source_archive_sha256='e'*64, target_archive_sha256='f'*64,
                checks_bytes=self.tests_bytes, equivalence_bytes=self.equivalence_bytes)
            self.assertEqual(capture.call_count, 1)
        folder = Path(result['directory'])
        self.assertEqual(json.loads((folder/'proposal.json').read_text()), self.proposal)
        self.assertEqual(json.loads((folder/'snapshot.json').read_text()), self.m.snapshot(self.manifest_bytes))
        self.assertEqual((folder/'before/src/runtime/example.py').read_bytes(), b'old executor\n')
        self.assertEqual(json.loads((folder/'receipt.json').read_text()), result)
        self.assertFalse(result['approval_created']); self.assertFalse(result['code_installed'])
        self.assertFalse((self.m.root/'storage/catalog/operations/execution_compatibility').exists())
        self.assertEqual(self.code.read_bytes(), b'old executor\n')
        self.assertEqual(self.m.events, [])

    def test_review_requires_drained_services_recent_backup_and_all_locks(self):
        source = {'src/runtime/example.py': b'old executor\n'}
        def review():
            return cutover.review(self.m, self.manifest_bytes, self.release_manifest, self.files,
                operator_sha256='b'*64, source_manifest=artifact(source), source_files=source,
                source_archive_sha256='e'*64, target_archive_sha256='f'*64,
                checks_bytes=self.tests_bytes, equivalence_bytes=self.equivalence_bytes)
        self.m.states['gambit-worker.service'] = 'active'
        with self.assertRaisesRegex(RuntimeError, 'Drain'): review()
        self.m.states['gambit-worker.service'] = 'inactive'
        for path in [self.m.state/'control.lock', self.m.backup/'backup.lock'] + [
                self.m.root/'storage/catalog/operations'/(name+'.lock') for name in cutover.release.LOCKS] + [
                self.m.root/'storage/temporary'/name for name in
                ('feature-store-publication.lock', 'target-store-publication.lock', 'lineage-packs-index.lock')]:
            with self.subTest(path=path), ExitStack() as guards:
                cutover.release.guard(guards, path)
                with self.assertRaisesRegex(RuntimeError, 'owns'): review()
        backup = self.m.backup/'status.json'; data = json.loads(backup.read_text())
        data['finished_at'] = (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        backup.write_text(json.dumps(data))
        with self.assertRaisesRegex(RuntimeError, 'backup'): review()
        self.assertFalse((self.m.state/'reviews').exists())

    def test_bounded_inventory_never_walks_data_catalogs_or_payloads(self):
        # Data volume must not change deployment work. Even a directory walker
        # touching these namespaces is a failure, not just reading their bytes.
        excluded = ('lineage', 'lineage_packs', 'feature_store', 'target_store', 'snapshots')
        for name in excluded:
            path = self.m.root/'storage/catalog'/name/'large-data'; path.mkdir(parents=True)
            (path/'manifest.json').write_bytes(b'not research authority')
        payload = self.m.root/'storage/payloads/sha256/opaque'; payload.mkdir(parents=True)
        (payload/'data.json').write_bytes(b'not research authority')
        walk = Path.rglob
        def restricted(path, pattern):
            relative = path.relative_to(self.m.root).as_posix()
            self.assertIn(relative, cutover.AUTHORITY_ROOTS)
            return walk(path, pattern)
        with patch.object(Path, 'rglob', restricted):
            before = cutover.authority_inventory(self.m.root)
        for name in excluded:
            (self.m.root/'storage/catalog'/name/'new.json').write_bytes(b'new data metadata')
        self.assertEqual(before, cutover.authority_inventory(self.m.root))
        self.assertIn(self.history.relative_to(self.m.root).as_posix(), before)

    def test_scoped_inventory_detects_new_changed_deleted_research_authority(self):
        before = cutover.authority_inventory(self.m.root)
        for name in cutover.AUTHORITY_ROOTS:
            with self.subTest(namespace=name):
                # Artifact manifests retain payload hashes without opening payloads.
                suffix = 'ARTIFACT_fixture/manifest.json' if name.endswith('trial_artifacts') else 'fixture.json'
                path = self.m.root/name/suffix; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'new research authority')
                self.assertNotEqual(before, cutover.authority_inventory(self.m.root))
                first = cutover.authority_inventory(self.m.root)
                path.write_bytes(b'changed research authority')
                self.assertNotEqual(first, cutover.authority_inventory(self.m.root))
                path.unlink()
                self.assertEqual(before, cutover.authority_inventory(self.m.root))


class CatalogCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'config').mkdir()
        (self.root/'config/research_execution.json').write_text(json.dumps(profile()))
        class FrozenAdapter(Adapter):
            def resolve_plan(self, root, intent, profile):
                value = super().resolve_plan(root, intent, profile)
                value['scope'] = {'reference': value['scope'], 'membership_snapshot': {'frozen': True}}
                value['plan_id'] = 'PLAN_'+digest(value)
                return value
        self.adapter = FrozenAdapter(); self.jobs = ResearchJobs(self.root, adapter=self.adapter, kernels=KernelSpy())
        self.request = intent(); self.jobs.submit(self.request)
        self.original = self.jobs._submission(self.request['request_id'])
        plan = self.original['frozen_plan']
        self.entry = {'request_id': self.request['request_id'], 'intent': self.original['intent'],
            'recipe_reference': plan['recipe'], 'scope_reference': plan['scope']['reference'],
            'membership_snapshot': plan['scope']['membership_snapshot'], 'periods': plan['periods']}
    def snapshot(self, entries=None):
        # Shared full scientific-pin validator is tested separately against the
        # complete contract; these minimal fixtures isolate queue transactions.
        with patch.object(cutover, 'frozen_metadata', return_value=({}, {})), patch(
                'runtime.program_intake_compatibility.validate_entry_binding'):
            return cutover.capture(self.root, canonical({'entries': entries or [self.entry]}))
    def test_capture_is_read_only_and_pending_identity_is_exact(self):
        before = {p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        value = self.snapshot()
        self.assertEqual(value['cohort'][0]['submission_sha256'], self.original['record_sha256'])
        self.assertEqual(value['states'][self.request['request_id']]['status'], 'queued')
        self.assertEqual(before, {p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
    def test_partial_orphan_trial_is_pinned_even_without_result_link(self):
        self.adapter.fail_horizon = 7; self.jobs.run_pending_once()
        value = self.snapshot()
        self.assertEqual(value['states'][self.request['request_id']]['status'], 'failed')
        trials = list((self.root/'storage/catalog/trial_ledger/records').glob('TRIAL_*.json'))
        self.assertEqual(len(trials), 1)
        expected = ref(self.jobs.store.get('trial', trials[0].stem))
        self.assertEqual(value['cohort'][0]['committed_trials'], [expected])
        # Proof inventory does not depend on reconstructible jobs/result links.
        with patch.object(cutover, 'authority_inventory', return_value={}):
            self.assertEqual(self.snapshot()['cohort'][0]['committed_trials'], [expected])
    def test_missing_intake_active_execution_and_unknown_backlog_block(self):
        missing = dict(self.entry, request_id='01234567-1234-4234-8234-012345678901')
        with self.assertRaisesRegex(RuntimeError, 'complete intake'): self.snapshot([self.entry, missing])
        self.jobs._update(self.request['request_id'], status='p1')
        with self.assertRaisesRegex(RuntimeError, 'Drain'): self.snapshot()
        self.jobs._update(self.request['request_id'], status='queued')
        other = intent(direction='NEGATIVE'); self.jobs.submit(other)
        with self.assertRaisesRegex(RuntimeError, 'outside'): self.snapshot()
        self.jobs._submission_path(other['request_id']).unlink()
        with self.assertRaisesRegex(RuntimeError, 'Incomplete intake reservation'): self.snapshot()
    def test_orphan_event_or_projection_blocks_without_repair(self):
        rid = '01234567-1234-4234-8234-012345678901'
        path = self.jobs._job_path(rid); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}')
        before = path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'Orphan'): self.snapshot()
        self.assertEqual(path.read_bytes(), before)
    def test_alias_and_frozen_membership_changes_block(self):
        changed = dict(self.entry, expected_existing_request_id='01234567-1234-4234-8234-012345678901')
        with self.assertRaisesRegex(RuntimeError, 'alias'): self.snapshot([changed])
        changed = dict(self.entry, membership_snapshot={'frozen': False})
        with self.assertRaisesRegex(RuntimeError, 'manifest bindings'): self.snapshot([changed])
    def test_partial_prepared_mismatch_and_orphan_artifact_corruption_block(self):
        self.adapter.fail_horizon = 7; self.jobs.run_pending_once()
        path = next((self.root/'storage/catalog/trial_ledger/records').glob('TRIAL_*.json'))
        old = self.jobs.store.get('trial', path.stem)
        malformed = deepcopy(old['scientific_key']); malformed['prepared']['members'].reverse()
        # Deliberate corruption in a disposable test store, never migration code.
        path.unlink(); bad = self.jobs.store.put('trial', malformed, old['body'])
        with self.assertRaisesRegex(RuntimeError, 'Partial prepared'): self.snapshot()
        self.jobs.store.path('trial', bad['id']).unlink()
        self.jobs.store.put('trial', old['scientific_key'], old['body'])
        artifact = old['body']['artifact_manifests'][0]
        manifest_path = self.root/'storage/catalog/trial_artifacts'/artifact['id']/'manifest.json'
        value = json.loads(manifest_path.read_text()); value['members'] = []
        manifest_path.write_text(json.dumps(value))
        with self.assertRaisesRegex(RuntimeError, 'artifact manifest'): self.snapshot()
    def test_partial_p2_discovery_effect_mismatch_blocks(self):
        load = self.adapter.load_phase
        def interrupted(root, plan, prepared, phase, horizon, **kwargs):
            if phase == 'P2' and horizon == 7: raise RuntimeError('isolated interruption')
            return load(root, plan, prepared, phase, horizon, **kwargs)
        with patch.object(self.adapter, 'load_phase', side_effect=interrupted): self.jobs.run_pending_once()
        trials = [self.jobs.store.get('trial', p.stem) for p in
                  (self.root/'storage/catalog/trial_ledger/records').glob('TRIAL_*.json')]
        trial = next(t for t in trials if t['scientific_key']['stage'] == 'P2')
        key = deepcopy(trial['scientific_key']); key['discovery_effect'] = '1234'
        self.jobs.store.path('trial', trial['id']).unlink()
        self.jobs.store.put('trial', key, trial['body'])
        with self.assertRaisesRegex(RuntimeError, 'Partial P2 discovery'): self.snapshot()
    def test_events_and_historical_records_are_authority_but_caches_are_not(self):
        snapshot = self.snapshot()
        self.assertTrue(any('/attempts/' in p and '/events/' in p for p in snapshot['authority']))
        self.assertTrue(any('/experiment_intake/requests/' in p for p in snapshot['authority']))
        self.assertFalse(any('/operations/jobs/' in p for p in snapshot['authority']))
    def test_capture_calls_complete_currency_binding_validator(self):
        from test_program_intake_compatibility import binding_fixture
        manifest, entry, packet, catalog, targets = binding_fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root/'config').mkdir()
            (root/'config/research_execution.json').write_text(json.dumps(packet['research_spec']))
            class CompleteAdapter(Adapter):
                def resolve_plan(self, root, intent, profile): return deepcopy(packet['frozen_plan'])
            jobs = ResearchJobs(root, adapter=CompleteAdapter())
            jobs.submit(dict(entry['intent'], request_id=entry['request_id']))
            with patch.object(cutover, 'frozen_metadata', return_value=(catalog, targets)):
                observed = cutover.capture(root, canonical(manifest))
                self.assertEqual(observed['cohort'][0]['request_id'], entry['request_id'])
                manifest['global_pins']['knowledge_cutoff'] = '2026-09-01'
                with self.assertRaisesRegex(ValueError, 'Frozen program binding'):
                    cutover.capture(root, canonical(manifest))


if __name__ == '__main__': unittest.main()
