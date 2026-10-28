"""Stopped-service cutovers with synthetic, historically retired definitions."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'deploy'))
import program_cutover as cutover
import retired_definitions as retired
from research.contracts import canonical, digest
from runtime.execution_compatibility import make_proposal
from test_execution_compatibility import synthetic_approval
from test_program_cutover import StoppedMachine
from test_retired_definitions import SyntheticRetirement


class RetiredCutoverTests(unittest.TestCase):
    def setUp(self):
        self.f = SyntheticRetirement(self)
        self.m = StoppedMachine(self.f.base)
        self.m.root = self.f.root
        self.code = self.m.root / 'src/runtime/example.py'
        self.history = self.m.root / 'storage/catalog/trial_ledger/records/preserved.json'
        self.history.parent.mkdir(parents=True)
        self.history.write_bytes(b'unchanged synthetic historical authority')
        self.old = cutover.implementation_at(self.m.root)
        self.code.write_bytes(self.f.target_files['src/runtime/example.py'])
        self.new = cutover.implementation_at(self.m.root)
        self.code.write_bytes(self.f.source_files['src/runtime/example.py'])
        self.manifest_bytes = canonical({'fixture': 'frozen program', 'global_pins': {
            'implementation_digest': digest(self.old),
            'implementation_fingerprint': self.old['fingerprint']}})
        self.checks_bytes = canonical({'schema': 'gambit_release_checks_v1', 'success': True,
            'commit': self.f.target_manifest['commit'], 'dirty_checkout': False,
            'production_data_used': False})
        self.index = {'schema': 'frozen_program_release_evidence_v1',
                      'retirement_context': self.f.context.binding,
                      'scientific_evidence': {'synthetic_unchanged_report_sha256': '7'*64}}
        self.equivalence_bytes = canonical(self.index)
        self.proposal = make_proposal(manifest_sha256=cutover.sha(self.manifest_bytes),
            operator_sha256='b'*64, from_implementation=self.old, to_implementation=self.new,
            cohort=self.m.cohort, evidence={'tests_sha256': cutover.sha(self.checks_bytes),
                'equivalence_sha256': cutover.sha(self.equivalence_bytes)},
            source_archive_sha256=self.f.source_sha, target_archive_sha256=self.f.target_sha)
        self.approval = synthetic_approval(self.proposal)

    def plan(self):
        return cutover.make_plan(self.m, self.manifest_bytes, self.f.target_manifest,
            self.f.target_files, self.approval, self.f.target_sha,
            retirement=self.f.context, equivalence_bytes=self.equivalence_bytes)

    def apply(self, expected=None):
        return cutover.apply(self.m, self.manifest_bytes, self.f.target_manifest,
            self.f.target_files, self.approval, self.f.target_sha,
            expected or self.plan()['plan_sha256'], retirement=self.f.context,
            equivalence_bytes=self.equivalence_bytes)

    def propose(self, **changes):
        arguments = dict(operator_sha256='b'*64, source_manifest=self.f.source_manifest,
            source_files=self.f.source_files, source_archive_sha256=self.f.source_sha,
            target_archive_sha256=self.f.target_sha, checks_bytes=self.checks_bytes,
            equivalence_bytes=self.equivalence_bytes, retirement=self.f.context)
        return cutover.propose(self.m, self.manifest_bytes, self.f.target_manifest,
            self.f.target_files, **dict(arguments, **changes))

    def assert_absent(self):
        self.assertTrue(all(not (self.m.root / name).exists() for name in self.f.names))

    def receipt(self):
        path = next(self.m.state.glob('*/receipt.json'))
        return path, json.loads(path.read_bytes())

    def test_proposal_is_inert_and_requires_exact_retirement_index(self):
        before = self.m.snapshot(self.manifest_bytes)
        self.assertEqual(self.propose(), self.proposal)
        self.assertEqual(self.m.snapshot(self.manifest_bytes), before)
        self.assertFalse((self.m.root / 'storage/catalog/operations/execution_compatibility').exists())
        for changes in ({'retirement': None}, {'equivalence_bytes': canonical({})},
                        {'equivalence_bytes': canonical(dict(self.index, schema='wrong'))}):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                self.propose(**changes)
        self.approval = self.proposal
        with self.assertRaises(Exception):
            self.apply('0'*64)
        self.assertEqual(self.code.read_bytes(), b'old executor\n')
        self.assert_absent()

    def test_install_keeps_authority_absences_and_ordinary_deployment_guards(self):
        before = self.m.snapshot(self.manifest_bytes)
        ordinary = cutover.release.plan(self.m.root, self.f.target_manifest, self.f.target_files)
        self.assertEqual(len(ordinary['blockers']), len(self.f.names))
        self.m.jobs = ['queued synthetic request']
        with self.assertRaisesRegex(RuntimeError, 'Queued or running'):
            self.m.idle()
        plan = self.plan()
        self.assertEqual(plan['schema'], 'frozen_program_cutover_plan_v2')
        self.assertEqual(plan['retirement_context'], self.f.context.binding)
        self.assertEqual(plan['code']['blockers'], [])
        self.assertEqual([r['path'] for r in plan['code']['changes']], ['src/runtime/example.py'])
        result = self.apply(plan['plan_sha256'])
        self.assertEqual(result['status'], 'installed_stopped')
        self.assertEqual(self.m.snapshot(self.manifest_bytes), before)
        self.assertEqual(self.code.read_bytes(), b'new executor\n')
        self.assertEqual(self.m.events, [])
        self.assert_absent()

    def test_source_is_rechecked_under_all_maintenance_locks_before_writes(self):
        expected = self.plan()['plan_sha256']
        paths = [self.m.state / 'control.lock', self.m.backup / 'backup.lock']
        paths += [self.m.root / 'storage/catalog/operations' / (name + '.lock')
                  for name in cutover.release.LOCKS]
        paths += [self.m.root / 'storage/temporary' / name for name in
                  ('feature-store-publication.lock', 'target-store-publication.lock', 'lineage-packs-index.lock')]
        original = retired.RetirementContext.code_plan
        checked = []
        def verify_locks(context, root, manifest, files, archive_sha):
            if archive_sha == self.f.source_sha:
                for path in paths:
                    with ExitStack() as stack, self.assertRaisesRegex(RuntimeError, 'owns'):
                        cutover.release.guard(stack, path)
                checked.append(archive_sha)
                self.assertEqual(self.code.read_bytes(), b'old executor\n')
            return original(context, root, manifest, files, archive_sha)
        with patch.object(retired.RetirementContext, 'code_plan', verify_locks):
            self.apply(expected)
        self.assertEqual(checked, [self.f.source_sha])

    def test_evidence_or_absence_changed_after_plan_blocks_before_writes(self):
        expected = self.plan()['plan_sha256']
        path = self.f.evidence['status']; original = path.read_bytes()
        path.write_bytes(original + b' ')
        with self.assertRaisesRegex(RuntimeError, 'checksum'):
            self.apply(expected)
        path.write_bytes(original)
        restored = self.m.root / self.f.names[0]
        restored.parent.mkdir(parents=True)
        restored.write_bytes(self.f.source_files[self.f.names[0]])
        with self.assertRaisesRegex(RuntimeError, 'reappeared'):
            self.apply(expected)
        self.assertEqual(self.code.read_bytes(), b'old executor\n')
        self.assertFalse(list(self.m.state.glob('*/receipt.json')))
        self.assertFalse((self.m.root / 'storage/catalog/operations/execution_compatibility').exists())

    def test_context_index_and_archive_cannot_be_substituted(self):
        expected = self.plan()['plan_sha256']
        original = self.equivalence_bytes
        changed = deepcopy(self.index); changed['retirement_context']['action'] = 'restore_definitions'
        self.equivalence_bytes = canonical(changed)
        with self.assertRaisesRegex(RuntimeError, 'Retirement context'):
            self.apply(expected)
        self.equivalence_bytes = canonical(dict(self.index, extra='unapproved evidence'))
        with self.assertRaisesRegex(RuntimeError, 'differ from approval'):
            self.apply(expected)
        self.equivalence_bytes = original
        self.f.source_path.write_bytes(self.f.target)
        with self.assertRaisesRegex(RuntimeError, 'checksum'):
            self.apply(expected)
        self.assertEqual(self.code.read_bytes(), b'old executor\n')

    def test_original_archive_check_uses_same_retirement_context(self):
        raw = b'synthetic original operator'
        from runtime.execution_compatibility import _seal
        proposal = dict(self.proposal, operator_sha256=cutover.sha(raw))
        approval = synthetic_approval(_seal('EXECPROPOSAL', {k:v for k,v in proposal.items() if k != 'id'}))
        args = dict(source_manifest=self.f.source_manifest, source_files=self.f.source_files,
            source_archive_sha256=self.f.source_sha, operator_bytes=raw)
        with self.assertRaisesRegex(RuntimeError, 'Installed code differs'):
            cutover.check_original_release(self.m, approval, **args)
        cutover.check_original_release(self.m, approval, retirement=self.f.context, **args)
        (self.m.root / 'config/unchanged.json').write_bytes(b'unreviewed policy')
        with self.assertRaisesRegex(RuntimeError, 'Installed code differs'):
            cutover.check_original_release(self.m, approval, retirement=self.f.context, **args)

    def test_failed_install_restores_only_code_and_keeps_absences(self):
        before = self.m.snapshot(self.manifest_bytes)
        self.m.fail_write = True
        with self.assertRaisesRegex(RuntimeError, 'write failure'):
            self.apply()
        _, record = self.receipt()
        self.assertEqual(record['status'], 'rolled_back_stopped')
        self.assertEqual(self.m.snapshot(self.manifest_bytes), before)
        self.assertEqual(self.code.read_bytes(), b'old executor\n')
        self.assertEqual(self.m.events, [])
        self.assert_absent()

    def test_changed_external_evidence_prevents_automatic_rollback(self):
        original_write = self.m.write
        def change_evidence(path, data):
            original_write(path, data)
            evidence = self.f.evidence['status']
            evidence.write_bytes(evidence.read_bytes() + b' ')
            raise RuntimeError('injected failure after evidence changed')
        with patch.object(self.m, 'write', side_effect=change_evidence):
            with self.assertRaisesRegex(RuntimeError, 'injected failure'):
                self.apply()
        _, record = self.receipt()
        self.assertEqual(record['status'], 'rollback_required')
        self.assertEqual(self.code.read_bytes(), b'new executor\n')
        self.assert_absent()

    def test_saved_evidence_supports_recovery_after_original_staging_is_removed(self):
        before = self.m.snapshot(self.manifest_bytes)
        result = self.apply()
        folder = self.m.state / result['release_id']
        self.assertEqual(retired.load_saved(folder / 'retirement').binding, self.f.context.binding)
        self.assertEqual((folder / 'release-evidence.json').read_bytes(), self.equivalence_bytes)
        for path in (*self.f.evidence.values(), self.f.source_path, self.f.target_path):
            path.unlink()
        recovered = cutover.recover(self.m, self.manifest_bytes, result['release_id'])
        self.assertEqual(recovered['status'], 'rolled_back_stopped')
        self.assertEqual(self.code.read_bytes(), b'old executor\n')
        self.assertEqual(self.m.snapshot(self.manifest_bytes), before)
        self.assertEqual(self.m.events, [])
        self.assert_absent()

    def test_recovery_refuses_new_authority_or_reappeared_definition(self):
        result = self.apply()
        new_trial = self.history.with_name('new.json'); new_trial.write_bytes(b'new authority')
        with self.assertRaisesRegex(RuntimeError, 'Research advanced'):
            cutover.recover(self.m, self.manifest_bytes, result['release_id'])
        self.assertEqual(new_trial.read_bytes(), b'new authority')
        new_trial.unlink()
        restored = self.m.root / self.f.names[0]; restored.parent.mkdir(parents=True)
        restored.write_bytes(self.f.source_files[self.f.names[0]])
        with self.assertRaisesRegex(RuntimeError, 'Research advanced'):
            cutover.recover(self.m, self.manifest_bytes, result['release_id'])
        self.assertEqual(self.code.read_bytes(), b'new executor\n')

    def test_recovery_refuses_changed_saved_context_or_evidence(self):
        result = self.apply(); folder = self.m.state / result['release_id']
        context = folder / 'retirement/context.json'; raw = context.read_bytes()
        changed = json.loads(raw); changed['omissions_count'] += 1
        context.write_bytes(canonical(changed))
        with self.assertRaisesRegex(RuntimeError, 'context differs'):
            cutover.recover(self.m, self.manifest_bytes, result['release_id'])
        context.write_bytes(raw)
        status = folder / 'retirement/status.json'; status.write_bytes(status.read_bytes() + b' ')
        with self.assertRaisesRegex(RuntimeError, 'checksum'):
            cutover.recover(self.m, self.manifest_bytes, result['release_id'])
        self.assertEqual(self.code.read_bytes(), b'new executor\n')
        self.assert_absent()

    def test_recovery_binds_saved_index_to_immutable_approval_not_just_receipt(self):
        result = self.apply(); folder = self.m.state / result['release_id']
        evidence = canonical(dict(self.index, added_after_approval=True))
        (folder / 'release-evidence.json').write_bytes(evidence)
        path, record = self.receipt(); record['equivalence_sha256'] = cutover.sha(evidence)
        path.write_bytes(canonical(record))
        with self.assertRaisesRegex(RuntimeError, 'differ from approval'):
            cutover.recover(self.m, self.manifest_bytes, result['release_id'])
        self.assertEqual(self.code.read_bytes(), b'new executor\n')
        self.assert_absent()


if __name__ == '__main__':
    unittest.main()


class SuccessorRetiredCutoverTests(unittest.TestCase):
    setUp = RetiredCutoverTests.setUp
    plan = RetiredCutoverTests.plan
    apply = RetiredCutoverTests.apply

    def test_successor_installs_and_recovers_with_original_retirement_anchor(self):
        from test_retired_definitions import archive_bytes
        from research.contracts import ref
        previous = self.approval
        self.apply()
        source_path, source_sha = self.f.target_path, self.f.target_sha
        self.f.source_manifest, self.f.source_files = self.f.target_manifest, dict(self.f.target_files)
        self.f.target_files['src/runtime/example.py'] = b'third executor\n'
        raw, self.f.target_manifest = archive_bytes(self.f.target_files, 'c'*40)
        next_path = self.f.base/'third.tar.gz'; next_path.write_bytes(raw)
        self.f.target_sha = retired.sha(raw)
        self.f.context = retired.load_context(self.f.evidence, source_path, source_sha,
            next_path, self.f.target_sha, retirement_archive=self.f.source_path)
        self.checks_bytes = canonical({'schema':'gambit_release_checks_v1','success':True,
            'commit':self.f.target_manifest['commit'],'dirty_checkout':False,'production_data_used':False})
        self.equivalence_bytes = canonical(dict(self.index, retirement_context=self.f.context.binding))
        self.code.write_bytes(b'third executor\n'); target = cutover.implementation_at(self.m.root)
        self.code.write_bytes(b'new executor\n')
        self.approval = synthetic_approval(make_proposal(manifest_sha256=cutover.sha(self.manifest_bytes),
            operator_sha256='b'*64, from_implementation=self.old, to_implementation=target,
            cohort=self.m.cohort, evidence={'tests_sha256':cutover.sha(self.checks_bytes),
                'equivalence_sha256':cutover.sha(self.equivalence_bytes)},
            source_archive_sha256=source_sha, target_archive_sha256=self.f.target_sha,
            predecessor_approval=previous, historical_trial_implementations={}))
        snapshot = self.m.snapshot
        def capture(raw):
            result = snapshot(raw)
            if getattr(self.m, 'predecessor_approval', None):
                result.update(predecessor_approval=ref(previous), historical_trial_implementations={})
            return result
        self.m.snapshot = capture
        result = self.apply()
        self.assertEqual(result['status'], 'installed_stopped')
        self.assertEqual(self.code.read_bytes(), b'third executor\n')
        recovered = cutover.recover(self.m, self.manifest_bytes, result['release_id'])
        self.assertEqual(recovered['status'], 'rolled_back_stopped')
        self.assertEqual(self.code.read_bytes(), b'new executor\n')
        self.assertEqual(self.history.read_bytes(), b'unchanged synthetic historical authority')
        self.assertTrue(all(not (self.m.root/name).exists() for name in self.f.names))
