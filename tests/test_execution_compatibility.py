"""Synthetic frozen-program execution approvals; never production approval data."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.contracts import canonical, digest, ref, ResearchConflict, ResearchError
from runtime.research_jobs import ResearchJobs, implementation
from runtime.experiment_identity import freeze, scientific_key
from runtime import execution_compatibility as compatibility
from test_research_runtime import Adapter, KernelSpy, intent, profile


def synthetic_implementation(label):
    files = {'runtime/synthetic.py': digest(label)}
    return {'profile': 'synthetic_execution', 'files': files,
            'numeric_environment': {'python': 'synthetic-only'}, 'fingerprint': digest(files)}


def synthetic_approval(proposal):
    # No application API grants approval. This explicit test evidence lives only
    # in temporary isolated fixtures, never in an operator command or release.
    return compatibility._seal('EXECAPPROVAL', {
        'schema': compatibility.APPROVAL_SCHEMA, 'version': '1.0.0',
        'decision': 'equivalent_execution', 'proposal': proposal,
        'approval': {'approved_by': 'synthetic test reviewer',
                     'approved_at': '2026-10-25T12:00:00+00:00',
                     'decision_reference': 'isolated test fixture only'}})


def successor_proposal(store, previous, original, actual):
    trials = [store.get('trial', p.stem) for p in
              sorted((store.root/'storage/catalog/trial_ledger/records').glob('TRIAL_*.json'))]
    prior = previous['proposal']
    return compatibility.make_proposal(manifest_sha256=prior['manifest_sha256'],
        operator_sha256=prior['operator_sha256'], from_implementation=prior['from_implementation'],
        to_implementation=actual, cohort=[dict(prior['cohort'][0], committed_trials=[ref(t) for t in trials])],
        evidence=prior['evidence'], source_archive_sha256='7'*64, target_archive_sha256='8'*64,
        predecessor_approval=previous,
        historical_trial_implementations={t['id']: t['scientific_key']['implementation'] for t in trials})


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.root = Path(self.temp.name)
        (self.root / 'config').mkdir()
        (self.root / 'config/research_execution.json').write_text(json.dumps(profile()))
        self.old = synthetic_implementation('old'); self.new = synthetic_implementation('new')
        self.adapter = Adapter(); self.kernel = KernelSpy()
        self.jobs = ResearchJobs(self.root, adapter=self.adapter, kernels=self.kernel)

    def tearDown(self):
        self.temp.cleanup()

    def submit_old(self, request=None):
        request = request or intent()
        with patch('runtime.research_jobs.implementation', return_value=self.old):
            self.jobs.submit(request)
        return self.jobs._submission(request['request_id'])

    def trials(self):
        return [self.jobs.store.get('trial', p.stem) for p in
                sorted((self.root / 'storage/catalog/trial_ledger/records').glob('*.json'))]

    def proposal(self, original=None, *, request=None, packet=None, committed=None):
        rid = (request or original)['request_id']
        packet = packet or original
        row = {'request_id': rid, 'canonical_request_id': original['request_id'] if original else rid,
               'intent_sha256': digest(packet['intent']), 'scientific_identity': scientific_key(packet),
               'submission_sha256': original['record_sha256'] if original else None,
               'committed_trials': committed if committed is not None else [ref(t) for t in self.trials()]}
        return compatibility.make_proposal(manifest_sha256='a'*64, operator_sha256='b'*64,
            from_implementation=self.old, to_implementation=self.new, cohort=[row],
            evidence={'equivalence_sha256': 'c'*64, 'tests_sha256': 'd'*64},
            source_archive_sha256='e'*64, target_archive_sha256='f'*64)

    def approve(self, proposal):
        approval = synthetic_approval(proposal)
        compatibility.install_approval(self.root, approval)
        return approval

    def run_old(self):
        with patch('runtime.research_jobs.implementation', return_value=self.old):
            self.jobs.run_pending_once()

    def resume_new(self, rid):
        with patch('runtime.research_jobs.implementation', return_value=self.new):
            self.jobs.resume(rid); self.jobs.run_pending_once()

    def test_proposal_is_inert_and_unapproved_queue_blocks(self):
        original = self.submit_old(); proposal = self.proposal(original)
        with self.assertRaises(ResearchConflict): compatibility.install_approval(self.root, proposal)
        self.assertFalse((self.root / compatibility.BASE).exists())
        with patch('runtime.research_jobs.implementation', return_value=self.new):
            self.jobs.run_pending_once()
        job = self.jobs.get(original['request_id'])
        self.assertEqual(job['status'], 'blocked')
        self.assertEqual(job['blockers'][0]['code'], 'IMPLEMENTATION_CHANGED')
        self.assertEqual(self.kernel.calls, [])

    def test_successor_preserves_two_generations_and_unlinked_partial_trials(self):
        for interrupted_phase in ('P1', 'P2'):
            with self.subTest(phase=interrupted_phase):
                # Separate request science so independent fixtures cannot reuse a result.
                if interrupted_phase == 'P2':
                    self.tearDown(); self.setUp()
                original = self.submit_old(); rid = original['request_id']
                self.adapter.fail_horizon = 7; self.run_old()
                first = self.approve(self.proposal(original))
                link = self.jobs._link
                def interrupted(relationship, p1, admission, p2=None, validation=None):
                    selected = p2 if interrupted_phase == 'P2' else p1
                    if selected and selected['scientific_key']['horizon'] == (1 if interrupted_phase == 'P2' else 7):
                        raise RuntimeError('synthetic predecessor publication-before-link interruption')
                    return link(relationship, p1, admission, p2, validation)
                with patch.object(self.jobs, '_link', side_effect=interrupted): self.resume_new(rid)
                self.assertEqual(self.jobs.get(rid)['status'], 'failed')
                saved = {t['id']: canonical(t) for t in self.trials()}
                third = synthetic_implementation('successor')
                proposal = successor_proposal(self.jobs.store, first, original, third)
                second = self.approve(proposal)
                self.assertEqual(compatibility.source_implementation(proposal), self.new)
                self.assertEqual(proposal['from_implementation'], self.old)
                self.adapter.loads.clear()
                with patch('runtime.research_jobs.implementation', return_value=third):
                    self.jobs.resume(rid); self.jobs.run_pending_once()
                self.assertEqual(self.jobs.get(rid)['status'], 'succeeded', self.jobs.get(rid))
                self.assertEqual(len(self.trials()), 10)
                self.assertEqual(len(self.kernel.calls), 10)
                self.assertNotIn(('P1', 1), self.adapter.loads)
                self.assertNotIn(('P1', 7), self.adapter.loads)
                if interrupted_phase == 'P2': self.assertNotIn(('P2', 1), self.adapter.loads)
                for identity, raw in saved.items(): self.assertEqual(canonical(self.jobs.store.get('trial', identity)), raw)
                self.assertEqual(self.jobs._submission(rid), original)
                self.assertEqual(compatibility.resolve(self.root, ref(first)), first)
                self.assertEqual(compatibility.resolve(self.root, ref(second)), second)

    def test_successor_chain_requires_installed_predecessor_and_monotone_exact_pins(self):
        original = self.submit_old(); self.adapter.fail_horizon = 7; self.run_old()
        first = self.approve(self.proposal(original))
        third = synthetic_implementation('third')
        proposal = successor_proposal(self.jobs.store, first, original, third)
        for field in ('manifest_sha256', 'operator_sha256'):
            changed = deepcopy(proposal); changed[field] = '9'*64
            changed = compatibility._seal('EXECPROPOSAL', {k:v for k,v in changed.items() if k != 'id'})
            with self.assertRaises(ResearchConflict): compatibility.validate_proposal(changed)
        for mutation in ('omit_trial', 'omit_executor', 'change_envelope'):
            changed = deepcopy(proposal)
            if mutation == 'omit_trial':
                changed['cohort'][0]['committed_trials'] = []; changed['historical_trial_implementations'] = {}
            elif mutation == 'omit_executor': changed['historical_trial_implementations'] = {}
            else: changed['cohort'][0]['submission_sha256'] = '0'*64
            changed = compatibility._seal('EXECPROPOSAL', {k:v for k,v in changed.items() if k != 'id'})
            with self.subTest(mutation=mutation), self.assertRaises(ResearchConflict): compatibility.validate_proposal(changed)
        path = self.root/compatibility.BASE/'approvals'/(first['id']+'.json')
        raw = path.read_bytes(); path.unlink()
        with self.assertRaises(FileNotFoundError): self.approve(proposal)
        path.write_bytes(raw); second = self.approve(proposal)
        fourth = successor_proposal(self.jobs.store, second, original, synthetic_implementation('fourth'))
        key = next(iter(fourth['historical_trial_implementations']))
        fourth['historical_trial_implementations'][key]['content_sha256'] = '9'*64
        fourth = compatibility._seal('EXECPROPOSAL', {k:v for k,v in fourth.items() if k != 'id'})
        with self.assertRaisesRegex(ResearchConflict, 'relabels'): compatibility.validate_proposal(fourth)

    def test_exact_program_and_implementation_pins_and_append_only_approval(self):
        original = self.submit_old(); approval = self.approve(self.proposal(original))
        binding = ref(approval)
        self.assertEqual(compatibility.resolve(self.root, binding), approval)
        self.assertEqual(compatibility.install_approval(self.root, approval), binding)
        args = dict(manifest_sha256='a'*64, operator_sha256='b'*64, actual_implementation=self.new)
        self.assertEqual(compatibility.for_program(self.root, **args), approval)
        for field, value in [('manifest_sha256', '0'*64), ('operator_sha256','0'*64),
                             ('actual_implementation', synthetic_implementation('other'))]:
            with self.subTest(field=field), self.assertRaises(ResearchConflict):
                compatibility.for_program(self.root, **dict(args, **{field: value}))
        changed = deepcopy(approval); changed['approval']['approved_by'] = 'altered'
        with self.assertRaises(ResearchConflict): compatibility.install_approval(self.root, changed)
        self.assertEqual(compatibility.resolve(self.root, binding), approval)

    def test_partial_p1_reused_without_loading_or_rewriting_and_new_executor_recorded(self):
        original = self.submit_old(); rid = original['request_id']
        self.adapter.fail_horizon = 7; self.run_old()
        self.assertEqual(self.jobs.get(rid)['status'], 'failed')
        old_trials = self.trials(); self.assertEqual(len(old_trials), 1)
        preserved = {p: p.read_bytes() for p in self.root.rglob('*.json')
                     if '/trial_ledger/' in str(p) or '/trial_artifacts/' in str(p) or '/payloads/' in str(p) or
                     '/submissions/' in str(p)}
        self.approve(self.proposal(original)); self.adapter.loads.clear()
        self.resume_new(rid)
        self.assertEqual(self.jobs.get(rid)['status'], 'succeeded', self.jobs.get(rid))
        self.assertNotIn(('P1', 1), self.adapter.loads)
        self.assertEqual(self.kernel.calls.count(('P1', 1)), 1)
        for p, content in preserved.items(): self.assertEqual(p.read_bytes(), content)
        for trial in self.trials():
            expected = self.old if trial['id'] == old_trials[0]['id'] else self.new
            actual = self.jobs.store.resolve('implementation', trial['scientific_key']['implementation'])['body']
            self.assertEqual(actual, expected)
        attempts = list((self.root / compatibility.BASE / 'attempts').glob('*.json'))
        self.assertEqual(len(attempts), 1)
        attempt = json.loads(attempts[0].read_text())
        self.assertEqual(attempt['requested_implementation'], self.old)
        self.assertEqual(attempt['executing_implementation'], self.new)

    def test_unlinked_historical_trial_cannot_be_omitted_to_force_rerun(self):
        original = self.submit_old(); rid = original['request_id']
        # A trial can publish successfully immediately before link publication fails.
        with patch.object(self.jobs, '_link', side_effect=RuntimeError('synthetic link crash')):
            self.run_old()
        self.assertEqual(len(self.trials()), 1)
        self.assertEqual(self.jobs.get(rid).get('results', []), [])
        self.approve(self.proposal(original, committed=[]))
        self.resume_new(rid)
        self.assertEqual(self.kernel.calls, [('P1', 1)])
        job = self.jobs.get(rid)
        self.assertEqual(job['status'], 'failed')
        self.assertIn('omitted from exact approved closure', job['blockers'][0]['message'])

    def test_partial_p2_reuses_all_committed_p1_and_p2_exactly(self):
        original = self.submit_old(); rid = original['request_id']
        load = self.adapter.load_phase
        def failing(root, plan, prepared, phase, horizon, **kw):
            if phase == 'P2' and horizon == 7: raise RuntimeError('synthetic interruption')
            return load(root, plan, prepared, phase, horizon, **kw)
        with patch.object(self.adapter, 'load_phase', side_effect=failing): self.run_old()
        self.assertEqual(len(self.trials()), 6)
        old_refs = [ref(t) for t in self.trials()]
        self.approve(self.proposal(original)); self.adapter.loads.clear(); self.adapter.preparations.clear()
        self.resume_new(rid)
        self.assertEqual(self.jobs.get(rid)['status'], 'succeeded', self.jobs.get(rid))
        self.assertEqual(self.adapter.preparations, ['P2'])
        self.assertEqual(self.adapter.loads, [('P2', h) for h in (7,21,63,252)])
        self.assertTrue(all(ref(self.jobs.store.resolve('trial', r)) == r for r in old_refs))
        self.assertEqual(len(self.kernel.calls), 10)

    def interrupt_new_executor_and_resume_with_changed_preparation(self, phase):
        original = self.submit_old(); rid = original['request_id']
        self.adapter.fail_horizon = 7; self.run_old()
        self.approve(self.proposal(original))
        link = self.jobs._link
        def fail_link(relationship, p1, admission, p2=None, validation=None):
            chosen = p2 if phase == 'P2' else p1
            if chosen and chosen['scientific_key']['horizon'] == (1 if phase == 'P2' else 7):
                raise RuntimeError('synthetic new executor post-publication crash')
            return link(relationship,p1,admission,p2,validation)
        with patch.object(self.jobs, '_link', side_effect=fail_link): self.resume_new(rid)
        self.assertEqual(self.jobs.get(rid)['status'], 'failed')
        completed = [ref(t) for t in self.trials()]
        prepare = self.adapter.prepare_phase
        def changed_inventory(*args, **kwargs):
            prepared = prepare(*args, **kwargs)
            for member in prepared['members']:
                member['materializations'] = [dict(r, id=r['id']+'_new_inventory') for r in member['materializations']]
            return prepared
        self.adapter.loads.clear()
        with patch.object(self.adapter, 'prepare_phase', side_effect=changed_inventory): self.resume_new(rid)
        self.assertEqual(self.jobs.get(rid)['status'], 'succeeded', self.jobs.get(rid))
        self.assertEqual(len(self.kernel.calls), 10)
        self.assertEqual(len(self.trials()), 10)
        self.assertNotIn(('P1', 1), self.adapter.loads)
        self.assertNotIn(('P1', 7), self.adapter.loads)
        if phase == 'P2': self.assertNotIn(('P2', 1), self.adapter.loads)
        self.assertTrue(all(ref(self.jobs.store.resolve('trial', r)) == r for r in completed))

    def test_missing_new_trial_intent_blocks_before_any_preparation_or_rerun(self):
        original = self.submit_old(); rid = original['request_id']
        self.adapter.fail_horizon = 7; self.run_old()
        self.approve(self.proposal(original))
        link = self.jobs._link
        def fail_new_link(relationship, p1, admission, p2=None, validation=None):
            if p1['scientific_key']['horizon'] == 7:
                raise RuntimeError('synthetic post-publication crash')
            return link(relationship,p1,admission,p2,validation)
        with patch.object(self.jobs, '_link', side_effect=fail_new_link): self.resume_new(rid)
        self.assertEqual(self.jobs.get(rid)['status'], 'failed')
        trials = {t['id']:ref(t) for t in self.trials()}
        claims = list((self.root / compatibility.BASE / 'trial_intents' / rid).glob('*.json'))
        self.assertEqual(len(claims), 1)
        claims[0].unlink()  # Simulate lost operational authority in this fixture only.
        before_calls = list(self.kernel.calls)
        self.adapter.preparations.clear(); self.adapter.loads.clear()
        self.resume_new(rid)
        job = self.jobs.get(rid)
        self.assertEqual(job['status'], 'failed')
        self.assertIn('lacks this exact request trial intent', job['blockers'][0]['message'])
        self.assertEqual(self.kernel.calls, before_calls)
        self.assertEqual(self.adapter.preparations, []); self.assertEqual(self.adapter.loads, [])
        self.assertEqual({t['id']:ref(t) for t in self.trials()}, trials)

    def test_new_executor_orphan_p1_reused_after_second_interruption(self):
        self.interrupt_new_executor_and_resume_with_changed_preparation('P1')

    def test_new_executor_orphan_p2_reused_after_second_interruption(self):
        self.interrupt_new_executor_and_resume_with_changed_preparation('P2')

    def test_complete_request_never_reexecutes_and_partial_tampering_fails_closed(self):
        original = self.submit_old(); self.run_old(); calls = list(self.kernel.calls)
        approval = self.approve(self.proposal(original))
        with patch('runtime.research_jobs.implementation', return_value=self.new): self.jobs._run(original['request_id'])
        self.assertEqual(self.kernel.calls, calls)
        trial = self.trials()[0]
        path = self.jobs.store.path('trial', trial['id'])
        trial['body']['metrics']['primary_effect'] = '9000'; path.write_bytes(canonical(trial)+b'\n')
        with self.assertRaises(ResearchError):
            compatibility.committed_trial(self.jobs.store, approval, original, original['frozen_plan'],
                trial['scientific_key']['stage'], trial['scientific_key']['horizon'],
                self.jobs.store.resolve('relationship', trial['scientific_key']['relationship']))

    def test_changed_science_or_envelope_and_ambiguous_approvals_rejected(self):
        original = self.submit_old(); approval = self.approve(self.proposal(original))
        for field in ('intent','frozen_plan','record_sha256'):
            changed = deepcopy(original)
            if field == 'intent': changed[field]['expected_direction'] = 'NEGATIVE'
            elif field == 'frozen_plan': changed[field]['members'].reverse()
            else: changed[field] = '0'*64
            with self.subTest(field=field), self.assertRaises(ResearchConflict):
                compatibility.authorize_execution(self.root, changed, self.new)
        proposal = deepcopy(approval['proposal']); proposal['evidence']['tests_sha256'] = '1'*64
        proposal = compatibility._seal('EXECPROPOSAL', {k:v for k,v in proposal.items() if k!='id'})
        self.approve(proposal)
        with self.assertRaises(ResearchConflict): compatibility.authorize_execution(self.root, original, self.new)

    def test_new_intake_keeps_uuid_science_and_actual_implementation(self):
        request = intent(); packet = freeze(self.jobs, {k:v for k,v in request.items() if k!='request_id'}, self.old)
        approval = self.approve(self.proposal(request=request, packet=packet, committed=[]))
        with patch('runtime.research_jobs.implementation', return_value=self.new):
            self.jobs.submit(request); self.jobs.run_pending_once()
        original = self.jobs._submission(request['request_id'])
        self.assertEqual(original['implementation'], self.new)
        self.assertEqual(scientific_key(original), scientific_key(packet))
        self.assertEqual(original['execution_compatibility'], ref(approval))
        compatibility.validate_cohort_envelope(approval, request['request_id'], original)
        self.assertEqual(self.jobs.get(request['request_id'])['status'], 'succeeded')

    def test_same_implementation_duplicate_cannot_change_approved_canonical_id(self):
        existing = intent()
        with patch('runtime.research_jobs.implementation', return_value=self.new): self.jobs.submit(existing)
        request = intent(); packet = freeze(self.jobs, {k:v for k,v in request.items() if k!='request_id'}, self.old)
        self.approve(self.proposal(request=request, packet=packet, committed=[]))
        with patch('runtime.research_jobs.implementation', return_value=self.new), self.assertRaisesRegex(ResearchConflict,'canonical program request'):
            self.jobs.submit(request)
        self.assertFalse(self.jobs._submission_path(request['request_id']).exists())

    def test_only_pinned_historical_alias_reused_without_new_experiment(self):
        original = self.submit_old(); self.run_old(); before = list(self.kernel.calls)
        alias = intent(); proposal = self.proposal(original, request=alias)
        self.approve(proposal)
        with patch('runtime.research_jobs.implementation', return_value=self.new):
            job, created = self.jobs.submit(alias); self.jobs.run_pending_once()
        self.assertFalse(created); self.assertEqual(job['request_id'], original['request_id'])
        self.assertEqual(self.kernel.calls, before)
        self.assertFalse(self.jobs._submission_path(alias['request_id']).exists())
        unrelated = intent()
        with patch('runtime.research_jobs.implementation', return_value=self.new), self.assertRaises(ResearchConflict):
            self.jobs.submit(unrelated)

    def test_diagnostic_failure_cannot_change_success_or_trial_identity(self):
        original = self.submit_old()
        with patch.object(self.jobs, '_diagnostic', side_effect=RuntimeError('synthetic logging failure')), \
                self.assertLogs('runtime.research_jobs', level='ERROR'):
            self.run_old()
        self.assertEqual(self.jobs.get(original['request_id'])['status'], 'succeeded')
        self.assertTrue(all('performance' not in t['body'] for t in self.trials()))


if __name__ == '__main__': unittest.main()
