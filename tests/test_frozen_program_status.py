"""Staged monitoring verifies saved metadata, never artifacts or execution."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from frozen_program_status import MetadataVerifier, merge_checkpoint
from research.contracts import HORIZONS, canonical, digest, ref, ResearchConflict
from research.store import ResearchStore
from runtime import execution_compatibility as compat
from runtime.experiment_identity import scientific_key
from test_program_intake_compatibility import binding_fixture, RID
from test_execution_compatibility import synthetic_implementation, synthetic_approval, successor_proposal

ATTEMPT = '00000000-0000-0000-0000-000000000003'
HISTORICAL = '00000000-0000-0000-0000-000000000002'


def fixture(root, *, mode='mixed', mutation=None):
    manifest, row, packet, catalog, targets = deepcopy(binding_fixture())
    old, new, historic = (synthetic_implementation(name) for name in ('old', 'new', 'historic'))
    requested = historic if mode == 'historical' else old
    original = dict(packet, request_id=HISTORICAL if mode == 'historical' else RID, implementation=requested)
    original['record_sha256'] = digest(original)
    store = ResearchStore(root); links = []; old_trials = []; new_trials = []
    plan = packet['frozen_plan']
    for h in HORIZONS:
        body = {'recipe': plan['recipe'], 'scope': plan['scope'], 'mode': plan['mode'],
                'target_family': 'price_return', 'horizon': h, 'horizon_unit': 'scheduled_weekdays',
                'members': [m['instrument_id'] for m in plan['members']],
                'targets': [m['targets'][str(h)]['definition'] for m in plan['members']],
                'expected_direction': 'POSITIVE', 'feature_application': plan['feature_application']}
        relationship = store.put('relationship', body, body)
        stages = {}
        for phase in ('P1', 'P2'):
            executor = requested if mode in ('old', 'historical') or (mode == 'mixed' and phase == 'P1') else new
            if mutation == 'wrong_executor' and h == 1 and phase == 'P2':
                executor = synthetic_implementation('unapproved')
            impl = store.put('implementation', executor, executor)
            key = {'relationship': ref(relationship), 'stage': phase, 'horizon': h,
                   'research_spec': ref(original['research_spec']), 'period': plan['periods'][phase],
                   'prepared': {'phase': phase, 'period': plan['periods'][phase],
                                'members': [{'instrument_id': m['instrument_id'], 'materializations': [], 'unavailable': []}
                                            for m in plan['members']]},
                   'targets': [{'instrument': m['instrument_id'], 'binding': m['targets'][str(h)]} for m in plan['members']],
                   'implementation': ref(impl), 'input_digest': digest('saved fixed numerical input'),
                   'discovery_trial': ref(stages['P1']) if phase == 'P2' else None,
                   'discovery_effect': '1' if phase == 'P2' else None}
            if mutation == 'period' and h == 1 and phase == 'P2':
                key['period'] = {'start_inclusive': '1900-01-01', 'end_exclusive': '1901-01-01'}
            if mutation == 'targets' and h == 1 and phase == 'P2':
                key['targets'][0]['binding'] = {'changed': 'scientific target'}
            value = {'stage': phase, 'mode': 'CS', 'horizon': h, 'expected_direction': 'POSITIVE',
                     'execution_status': 'completed', 'metrics': {'primary_effect': '1'},
                     'sample': {'validation_data_accessed': True}, 'evidence': {'saved': True},
                     'reason_codes': [], 'artifact_manifests': [{'must_never_be_opened': True}]}
            value['admission' if phase == 'P1' else 'decision'] = 'admitted' if phase == 'P1' else 'VALIDATED'
            if mutation == 'direction' and h == 1 and phase == 'P2': value['expected_direction'] = 'NEGATIVE'
            if mutation == 'stage_gate' and h == 1 and phase == 'P2': value['sample']['validation_data_accessed'] = False
            trial = stages[phase] = store.put('trial', key, value)
            (old_trials if executor == requested else new_trials).append(trial)
        p1, p2 = stages['P1'], stages['P2']
        admission = store.put('admission', {'trial': ref(p1)}, {'trial': ref(p1), 'relationship': ref(relationship),
            'decision': 'admitted', 'evidence': p1['body']['evidence'], 'reason_codes': []})
        validation = store.put('validation', {'discovery': ref(p1), 'evaluation': ref(p2)},
            {'relationship': ref(relationship), 'discovery_trial': ref(p1), 'evaluation_trial': ref(p2), 'decision': 'VALIDATED'})
        body = {'relationship': ref(relationship), 'trial_results': [ref(p1), ref(p2)],
                'admission_results': [ref(admission)], 'validation_results': [ref(validation)]}
        links.append(ref(store.put('link', body, body)))
    row['ordinal'] = 1
    if mode == 'historical':
        row.update(expected_existing_request_id=HISTORICAL, expected_existing_scientific_identity=scientific_key(original),
                   expected_existing_result_references=links)
    manifest['global_pins'].update(implementation_digest=digest(old), implementation_fingerprint=old['fingerprint'])
    raw = canonical(manifest) + b'\n'
    proposal = compat.make_proposal(manifest_sha256=sha256(raw).hexdigest(), operator_sha256='a' * 64,
        from_implementation=old, to_implementation=new,
        cohort=[{'request_id': RID, 'canonical_request_id': original['request_id'],
                 'intent_sha256': digest(original['intent']), 'scientific_identity': scientific_key(original),
                 'submission_sha256': original['record_sha256'], 'committed_trials': [ref(t) for t in old_trials]}],
        evidence={'equivalence_sha256': 'b' * 64, 'tests_sha256': 'c' * 64},
        source_archive_sha256='d' * 64, target_archive_sha256='e' * 64)
    approval = synthetic_approval(proposal); compat.install_approval(root, approval)
    events = [{'request_id': original['request_id'], 'job': {'request_id': original['request_id'], 'attempt_id': ATTEMPT}}]
    if new_trials:
        compat.record_execution(root, approval, original, new, ATTEMPT)
        for trial in new_trials:
            # A malformed executor is deliberately saved without a valid intent.
            if store.resolve('implementation', trial['scientific_key']['implementation'])['body'] == new:
                compat.record_trial_intent(store, approval, original, trial['scientific_key'])
    journal = {'schema': 'experiment_intake_v1', 'request_id': RID, 'canonical_request_id': original['request_id'],
               'intent': original['intent'], 'scientific_identity': scientific_key(original),
               'requested_implementation': old, 'submission': original if mode != 'historical' else None}
    journal['sha256'] = digest(journal)
    receipt = {'schema': 'gambit_finite_intake_receipt_v1', 'manifest_sha256': sha256(raw).hexdigest(),
               **{k: journal[k] for k in ('request_id', 'canonical_request_id', 'scientific_identity')},
               'journal_sha256': journal['sha256']}
    return dict(store=store, manifest_bytes=raw, operator_sha256='a' * 64, approval_reference=ref(approval),
                actual_implementation=new, feature_catalog=catalog, target_metadata=targets), dict(
                original=original, journal=journal, receipt=receipt,
                job={'request_id': original['request_id'], 'status': 'succeeded', 'results': links}, events=events)


class MetadataStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)

    def verify(self, setup, entry):
        store = setup['store']
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with (patch.object(store, 'verify_artifact', side_effect=AssertionError('numerical artifact read forbidden')),
                patch.object(store, 'put', side_effect=AssertionError('research publication forbidden'))):
            result = MetadataVerifier(**setup).verify_entry(RID, **entry)
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        return result

    def test_old_new_mixed_and_older_historical_alias_are_read_only(self):
        for mode in ('old', 'new', 'mixed', 'historical'):
            with self.subTest(mode=mode):
                setup, entry = fixture(self.root / mode, mode=mode)
                rows = self.verify(setup, entry)
                self.assertEqual(len(rows), 5)
                self.assertTrue(all(r['terminal'] and r['stage_gates_passed'] for r in rows))
                expected = ['approved_historical_reference', 'approved_new_executor'] if mode == 'mixed' else (
                    ['approved_new_executor'] * 2 if mode == 'new' else ['approved_historical_reference'] * 2)
                self.assertEqual(rows[0]['trial_execution_provenance'], expected)

    def test_successor_reads_mixed_generations_without_relabeling_or_losing_passes(self):
        for mode in ('old', 'new', 'mixed', 'historical'):
            setup, entry = fixture(self.root/mode, mode=mode)
            before = self.verify(setup, entry)
            previous = compat.resolve(setup['store'].root, setup['approval_reference'])
            actual = synthetic_implementation('successor')
            proposal = successor_proposal(setup['store'], previous, entry['original'], actual)
            approved = synthetic_approval(proposal); compat.install_approval(setup['store'].root, approved)
            rows = self.verify(dict(setup, approval_reference=ref(approved), actual_implementation=actual), entry)
            self.assertEqual([{k:v for k,v in r.items() if k != 'trial_execution_provenance'} for r in rows],
                             [{k:v for k,v in r.items() if k != 'trial_execution_provenance'} for r in before])
            self.assertTrue(all(r['trial_execution_provenance'] == ['approved_historical_reference']*2 for r in rows))

    def test_successor_still_checks_predecessor_intents_attempts_and_events(self):
        for missing in ('intent', 'attempt', 'event'):
            setup, entry = fixture(self.root/missing, mode='mixed')
            store = setup['store'];previous = compat.resolve(store.root, setup['approval_reference'])
            actual = synthetic_implementation('successor')
            approved = synthetic_approval(successor_proposal(store, previous, entry['original'], actual))
            compat.install_approval(store.root, approved)
            if missing == 'event': entry['events'] = []
            else:
                folder = 'trial_intents/'+RID if missing == 'intent' else 'attempts'
                next((store.root/compat.BASE/folder).glob('*.json')).unlink()
            with self.subTest(missing=missing), self.assertRaises(ResearchConflict):
                self.verify(dict(setup, approval_reference=ref(approved), actual_implementation=actual), entry)

    def test_no_approval_wrong_manifest_operator_executor_or_cohort_is_rejected(self):
        setup, entry = fixture(self.root)
        for field, value in (('manifest_bytes', setup['manifest_bytes'] + b' '), ('operator_sha256', 'f' * 64),
                             ('actual_implementation', synthetic_implementation('other'))):
            with self.subTest(field=field), self.assertRaises(ResearchConflict):
                self.verify(dict(setup, **{field: value}), entry)
        changed = deepcopy(entry); changed['original']['record_sha256'] = 'f' * 64
        with self.assertRaises(ResearchConflict): self.verify(setup, changed)
        path = next((self.root / compat.BASE / 'approvals').glob('*.json')); path.unlink()
        with self.assertRaises(FileNotFoundError): self.verify(setup, entry)

    def test_new_trial_requires_exact_intent_attempt_and_event_history(self):
        for missing in ('trial_intent', 'execution_attempt', 'events'):
            setup, entry = fixture(self.root / missing)
            if missing == 'events': entry['events'] = []
            else:
                folder = 'trial_intents/' + RID if missing == 'trial_intent' else 'attempts'
                next((setup['store'].root / compat.BASE / folder).glob('*.json')).unlink()
            with self.subTest(missing=missing), self.assertRaises(ResearchConflict): self.verify(setup, entry)

    def test_scientific_target_period_direction_executor_and_stage_gate_fail_closed(self):
        for mutation in ('targets', 'period', 'direction', 'wrong_executor', 'stage_gate'):
            setup, entry = fixture(self.root / mutation, mutation=mutation)
            with self.subTest(mutation=mutation), self.assertRaises(ResearchConflict): self.verify(setup, entry)

    def test_feature_source_and_target_catalog_binding_stays_exact(self):
        setup, entry = fixture(self.root)
        for field in ('feature', 'source_view', 'price_snapshot'):
            changed = deepcopy(setup); changed['store'] = setup['store']
            changed['feature_catalog']['body']['bindings'][0][field] = {'changed': 'scientific reference'}
            with self.subTest(field=field), self.assertRaises(ResearchConflict): self.verify(changed, entry)
        changed = deepcopy(setup); changed['store'] = setup['store']
        symbol = next(iter(changed['target_metadata']))
        changed['target_metadata'][symbol]['1']['definition'] = {'changed': 'target definition'}
        with self.assertRaises(ResearchConflict): self.verify(changed, entry)

    def test_historical_alias_exact_links_and_receipts_cannot_be_relaxed(self):
        setup, entry = fixture(self.root, mode='historical')
        changed = deepcopy(entry); changed['job']['results'] = changed['job']['results'][:-1]
        with self.assertRaises(ResearchConflict): self.verify(setup, changed)
        changed = deepcopy(entry); changed['receipt']['journal_sha256'] = 'f' * 64
        with self.assertRaises(ResearchConflict): self.verify(setup, changed)

    def test_checkpoint_preserves_old_history_across_failed_and_incomplete_reads(self):
        setup, entry = fixture(self.root)
        passes = self.verify(setup, entry)
        old = {'schema': 'momentum_program_heartbeat_v1', 'manifest_sha256': sha256(setup['manifest_bytes']).hexdigest(),
               'observed_at': '2026-10-25T01:00:00+00:00', 'issues': [], 'verified_passes': passes[:1],
               'verified_pass_identity_history': ['RELATIONSHIP_' + 'f' * 64]}
        current = {'schema': 'momentum_program_heartbeat_approved_execution_v1',
                   'manifest_sha256': old['manifest_sha256'], 'execution_compatibility': setup['approval_reference'],
                   'observed_at': '2026-10-25T02:00:00+00:00', 'issues': [], 'planned': 1,
                   'verified_receipts': 1, 'intake_complete': True, 'verified_passes': passes[:2],
                   'rows': [{'receipt_verified': True, 'status': 'p2', 'outcomes': passes[:2]}]}
        before = deepcopy(current)
        merged = merge_checkpoint(current, old)
        self.assertEqual(current, before)
        self.assertTrue(merged['checkpoint_advanced'])
        self.assertEqual(merged['new_passes_since_previous'], passes[1:2])
        self.assertEqual(len(merged['verified_pass_identity_history']), 3)
        for incomplete in (dict(current, issues=[{'error': 'partial read'}], verified_passes=passes),
                           dict(current, rows=[], verified_passes=passes)):
            failed = merge_checkpoint(incomplete, merged)
            self.assertFalse(failed['checkpoint_advanced'])
            self.assertEqual(failed['verified_pass_identity_history'], merged['verified_pass_identity_history'])
            self.assertEqual(failed['last_successful_observed_at'], merged['observed_at'])
            self.assertEqual(failed['new_passes_since_previous'], [])
            resumed = deepcopy(current); resumed['verified_passes'] = passes
            resumed['rows'][0]['outcomes'] = passes
            recovery = merge_checkpoint(resumed, failed)
            self.assertEqual(recovery['new_passes_since_previous'], passes[2:])
        baseline = merge_checkpoint(current)
        self.assertIsNone(baseline['new_passes_since_previous'])
        self.assertEqual(len(baseline['verified_pass_identity_history']), 2)

    def test_successor_checkpoint_keeps_known_passes_across_verified_approval_chain(self):
        setup, entry = fixture(self.root)
        outcomes = self.verify(setup, entry)
        previous_approval = compat.resolve(self.root, setup['approval_reference'])
        successor = synthetic_approval(successor_proposal(setup['store'], previous_approval,
            entry['original'], synthetic_implementation('successor')))
        old = {'schema':'momentum_program_heartbeat_approved_execution_v1',
            'manifest_sha256':sha256(setup['manifest_bytes']).hexdigest(),
            'execution_compatibility':ref(previous_approval), 'observed_at':'before',
            'issues':[], 'verified_passes':outcomes[:1], 'checkpoint_advanced':True}
        current = {'schema':old['schema'], 'manifest_sha256':old['manifest_sha256'],
            'execution_compatibility':ref(successor), 'observed_at':'after',
            'verified_predecessor_approvals':[ref(previous_approval)],
            'issues':[], 'planned':1, 'verified_receipts':1, 'intake_complete':True,
            'verified_passes':outcomes, 'rows':[{'receipt_verified':True,
                'status':'succeeded', 'outcomes':outcomes}]}
        before = deepcopy(old)
        merged = merge_checkpoint(current, old)
        self.assertEqual(old, before)
        self.assertEqual(merged['new_passes_since_previous'], outcomes[1:])
        self.assertEqual(len(merged['verified_pass_identity_history']), 5)
        failed = merge_checkpoint(dict(current, issues=[{'incomplete':'snapshot'}]), old)
        self.assertFalse(failed['checkpoint_advanced'])
        self.assertEqual(failed['verified_pass_identity_history'], [outcomes[0]['relationship']['id']])
        self.assertEqual(failed['last_successful_observed_at'], 'before')
        for refs in ([], [ref(successor)], [ref(previous_approval)]*2,
                     [dict(ref(previous_approval), content_sha256='0'*64)]):
            with self.subTest(refs=refs), self.assertRaises(ResearchConflict):
                merge_checkpoint(dict(current, verified_predecessor_approvals=refs), old)

    def test_checkpoint_refuses_other_program_approval_or_pass_projection(self):
        setup, entry = fixture(self.root)
        passes = self.verify(setup, entry)
        current = {'schema': 'momentum_program_heartbeat_approved_execution_v1',
                   'manifest_sha256': sha256(setup['manifest_bytes']).hexdigest(),
                   'execution_compatibility': setup['approval_reference'], 'observed_at': 'now', 'issues': [],
                   'planned': 1, 'verified_receipts': 1, 'intake_complete': True, 'verified_passes': passes,
                   'rows': [{'receipt_verified': True, 'status': 'succeeded', 'outcomes': passes}]}
        baseline = merge_checkpoint(current)
        for field, value in (('manifest_sha256', 'f' * 64), ('execution_compatibility', {'other': 'approval'})):
            with self.subTest(field=field), self.assertRaises(ResearchConflict):
                merge_checkpoint(dict(current, **{field: value}), baseline)
        changed = deepcopy(current); changed['verified_passes'] = []
        with self.assertRaises(ResearchConflict): merge_checkpoint(changed, baseline)


if __name__ == '__main__': unittest.main()
