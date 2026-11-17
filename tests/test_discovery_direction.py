"""Isolated regression tests for direction selection and momentum continuation."""

from hashlib import sha256
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from api.signal_summaries import _verified_branch
from research.contracts import DISCOVERY_DIRECTION, ResearchError, canonical, digest, ref
from research.direction import continuation_id
from research.schedule import period_for
from research.store import install_bytes
from runtime.research_jobs import ResearchJobs
from test_research_runtime import Adapter, KernelSpy, intent, profile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from ts_momentum_direction_cutover import apply_queued, plan_cutover, write_next_manifest
from ts_momentum_intake import launch


class Kernel(KernelSpy):
    def run_p1(self, rows, **kwargs):
        outcome = super().run_p1(rows, **kwargs)
        outcome['metrics']['primary_effect'] = {1: -1.0, 7: 1.0, 21: -2.0, 63: None, 252: 0.0}[kwargs['horizon']]
        if kwargs['horizon'] in (63, 252):
            outcome['admission'] = 'unresolved' if kwargs['horizon'] == 63 else 'rejected'
        return outcome

    def run_p2(self, rows, **kwargs):
        outcome = super().run_p2(rows, **kwargs)
        outcome['expected_direction'] = kwargs['expected_direction']
        outcome['discovery_effect'] = kwargs['discovery_effect']
        return outcome


class DirectionTests(TestCase):
    def setUp(self):
        fixture = TemporaryDirectory()
        self.addCleanup(fixture.cleanup)
        self.root = Path(fixture.name)
        install_bytes(self.root / 'config/research_execution.json', canonical(profile()) + b'\n')
        self.adapter = Adapter()
        self.kernel = Kernel()
        self.jobs = ResearchJobs(self.root, adapter=self.adapter, kernels=self.kernel)
        self.addCleanup(self.jobs.close)

    def test_admitted_sign_is_distinct_per_horizon(self):
        row = intent(mode='TS', direction=DISCOVERY_DIRECTION)
        self.jobs.submit(row)
        self.jobs.run_pending_once()
        job = self.jobs.get(row['request_id'])
        self.assertEqual(job['status'], 'succeeded', job)
        self.assertEqual([h.get('discovery_direction') for h in job['horizons']],
                         ['NEGATIVE', 'POSITIVE', 'NEGATIVE', None, None])
        self.assertEqual([h['p2_status'] for h in job['horizons']],
                         ['VALIDATED', 'VALIDATED', 'VALIDATED', 'not_admitted', 'not_admitted'])
        for link_ref in job['results']:
            link = self.jobs.store.resolve('link', link_ref)
            relation, trials, _, decisions, sign = _verified_branch(self.jobs.store, link, include_direction=True)
            if decisions:
                self.assertEqual(decisions[0]['body']['direction_binding']['direction'], sign)
                self.assertEqual(trials[1]['body']['expected_direction'], sign)
                access = self.jobs.store.find('exposure', {
                    'request_id': row['request_id'], 'attempt_id': job['attempt_id'],
                    'phase': 'P2', 'horizon': relation['body']['horizon']})
                self.assertEqual(access['body']['direction_binding'], decisions[0]['body']['direction_binding'])
                self.assertEqual(trials[1]['scientific_key']['period'],
                                 period_for(self.jobs._submission(row['request_id'])['frozen_plan'],
                                            'P2', relation['body']['horizon']))
        self.assertEqual([h for stage, h in self.adapter.loads if stage == 'P2'], [1, 7, 21])

    def setup_skipped(self):
        row = intent(mode='TS')
        self.jobs.submit(row)
        self.jobs.run_pending_once()
        job = self.jobs.get(row['request_id'])
        self.assertEqual(job['status'], 'succeeded', job)
        skipped = {}
        for link_ref in job['results']:
            link = self.jobs.store.resolve('link', link_ref)['body']
            horizon = self.jobs.store.resolve('relationship', link['relationship'])['body']['horizon']
            if horizon in (1, 21):
                skipped[str(horizon)] = link_ref
        child = dict(row, request_id=continuation_id(row['request_id'], followup=True),
                     expected_direction=DISCOVERY_DIRECTION)
        return row, job, child, skipped

    def test_followup_reads_only_missing_p2_and_keeps_parent(self):
        row, job, child, skipped = self.setup_skipped()
        envelope = self.jobs._submission(row['request_id'])
        self.adapter.loads.clear()
        self.adapter.preparations.clear()
        self.kernel.calls.clear()
        self.jobs.submit(child, momentum_parent=row['request_id'], p2_followup=skipped)
        self.jobs.run_pending_once()
        result = self.jobs.get(child['request_id'])
        self.assertEqual(result['status'], 'succeeded', result)
        self.assertEqual(self.adapter.loads, [('P2', 1), ('P2', 21)])
        self.assertEqual(self.adapter.preparations, ['P2'])
        self.assertEqual(self.kernel.calls, self.adapter.loads)
        self.assertEqual(self.jobs.get(row['request_id']), job)
        self.assertEqual(self.jobs._submission(row['request_id']), envelope)
        for link_ref in result['results']:
            link = self.jobs.store.resolve('link', link_ref)
            relation, trials, _, validations, sign = _verified_branch(self.jobs.store, link, include_direction=True)
            earlier = self.jobs.store.resolve('link', skipped[str(relation['body']['horizon'])])['body']
            self.assertEqual(ref(trials[0]), earlier['trial_results'][0])
            self.assertEqual(validations[0]['body']['direction_binding']['prior_decision'], earlier['validation_results'][0])
            self.assertEqual(sign, 'NEGATIVE')
        self.assertFalse(self.jobs.submit(child, momentum_parent=row['request_id'], p2_followup=skipped)[1])

    def test_p2_access_blocks_followup(self):
        row, job, child, skipped = self.setup_skipped()
        self.jobs.store.put('exposure', {'request_id': row['request_id'], 'attempt_id': job['attempt_id'],
                                         'phase': 'P2', 'horizon': 1}, {'event': 'sample_access_started'})
        self.jobs.submit(child, momentum_parent=row['request_id'], p2_followup=skipped)
        self.adapter.loads.clear()
        self.jobs.run_pending_once()
        result = self.jobs.get(child['request_id'])
        self.assertEqual(result['status'], 'blocked', result)
        self.assertEqual(self.adapter.loads, [])

    def test_followup_executor_change_requires_exact_approval_and_reuses_parent_p1(self):
        from runtime import execution_compatibility as compatibility
        from runtime.experiment_identity import scientific_key
        from runtime.research_jobs import implementation
        from test_execution_compatibility import synthetic_approval, synthetic_implementation
        row, parent_job, child, skipped = self.setup_skipped()
        self.jobs.submit(child, momentum_parent=row['request_id'], p2_followup=skipped)
        submission = self.jobs._submission(child['request_id'])
        old = implementation()
        new = synthetic_implementation('isolated reviewed followup executor')
        self.adapter.loads.clear()
        self.kernel.calls.clear()
        with patch('runtime.research_jobs.implementation', return_value=new):
            self.jobs.run_pending_once()
        blocked = self.jobs.get(child['request_id'])
        self.assertEqual(blocked['status'], 'blocked')
        self.assertEqual(blocked['blockers'][0]['code'], 'IMPLEMENTATION_CHANGED')
        self.assertEqual(self.adapter.loads, [])
        proposal = compatibility.make_proposal(
            manifest_sha256='a' * 64, operator_sha256='b' * 64,
            from_implementation=old, to_implementation=new,
            cohort=[{'request_id': child['request_id'], 'canonical_request_id': child['request_id'],
                'intent_sha256': digest(submission['intent']), 'scientific_identity': scientific_key(submission),
                'submission_sha256': submission['record_sha256'], 'committed_trials': []}],
            evidence={'equivalence_sha256': 'c' * 64, 'tests_sha256': 'd' * 64},
            source_archive_sha256='e' * 64, target_archive_sha256='f' * 64)
        compatibility.install_approval(self.root, synthetic_approval(proposal))
        with patch('runtime.research_jobs.implementation', return_value=new):
            self.jobs.resume(child['request_id'])
            self.jobs.run_pending_once()
        result = self.jobs.get(child['request_id'])
        self.assertEqual(result['status'], 'succeeded', result)
        self.assertEqual(self.adapter.loads, [('P2', 1), ('P2', 21)])
        self.assertEqual(self.kernel.calls, self.adapter.loads)
        self.assertEqual(self.jobs.get(row['request_id']), parent_job)

    def test_cutover_replaces_only_unstarted_and_selects_skipped_p2(self):
        old, _, _, _ = self.setup_skipped()
        queued = dict(intent(mode='TS'), feature={'id': 'FEATURE_RECIPE_' + 'b'*64, 'version': '1.0.0'})
        self.jobs.submit(queued)
        staged = dict(queued, request_id=intent()['request_id'], scope={'id': 'SCOPE_BBB_TS', 'version': '1.0.0'})
        schedule = {'id': 'TEST', 'version': '1.0.0'}
        manifest = self.root / 'manifest.json'
        checkpoint = self.root / 'checkpoint.json'
        install_bytes(manifest, canonical({'program': 'GAMBIT_TS_MOMENTUM_20261111',
                                           'schedule': ref(schedule), 'entries': [old, queued, staged]}) + b'\n')
        install_bytes(checkpoint, canonical({'manifest_sha256': sha256(manifest.read_bytes()).hexdigest(),
                                             'next_index': 2, 'created': 2, 'existing': 0, 'blocked': []}) + b'\n')
        with patch('ts_momentum_direction_cutover.load_schedule', return_value=schedule):
            preview = plan_cutover(self.root, manifest, checkpoint, preview=True)
            review = plan_cutover(self.root, manifest, checkpoint)
        with self.assertRaises(ResearchError):
            apply_queued(self.root, preview)
        self.assertEqual(review['original_states'], {'succeeded': 1, 'queued': 1})
        self.assertEqual(set(review['followups'][0]['skipped']), {'1', '21'})
        self.assertEqual(len(review['staged']), 1)
        replacement = review['queued'][0]['child']['request_id']
        original = self.jobs._submission(queued['request_id'])
        with patch('ts_momentum_direction_cutover.ResearchJobs', return_value=self.jobs):
            apply_queued(self.root, review)
            apply_queued(self.root, review)
        self.assertEqual(self.jobs.get(queued['request_id'])['superseded_by'], replacement)
        self.assertEqual(self.jobs._submission(queued['request_id']), original)
        self.assertEqual(self.jobs.get(replacement)['status'], 'queued')
        next_manifest = self.root / 'next.json'
        next_checkpoint = self.root / 'next-checkpoint.json'
        write_next_manifest(manifest, next_manifest, review)
        with (patch('ts_momentum_intake.load_schedule', return_value=schedule),
              patch('ts_momentum_intake.ResearchJobs', return_value=self.jobs)):
            launch(self.root, next_manifest, next_checkpoint, count=1)
        child = review['followups'][0]['child']['request_id']
        self.assertEqual(self.jobs.get(child)['status'], 'queued')
        self.assertEqual(set(self.jobs._submission(child)['p2_followup']['skipped']), {'1', '21'})
        with self.assertRaises(ResearchError):
            self.jobs.resume(queued['request_id'])
    def test_review_rejects_a_live_request(self):
        row = intent(mode='TS')
        self.jobs.submit(row)
        self.jobs._update(row['request_id'], status='p1', stage='P1')
        schedule = {'id': 'TEST', 'version': '1.0.0'}
        manifest = self.root / 'manifest.json'
        checkpoint = self.root / 'checkpoint.json'
        install_bytes(manifest, canonical({'program': 'GAMBIT_TS_MOMENTUM_20261111',
                                           'schedule': ref(schedule), 'entries': [row]}) + b'\n')
        install_bytes(checkpoint, canonical({'manifest_sha256': sha256(manifest.read_bytes()).hexdigest(),
                                             'next_index': 1, 'created': 1, 'existing': 0, 'blocked': []}) + b'\n')
        with patch('ts_momentum_direction_cutover.load_schedule', return_value=schedule):
            with self.assertRaisesRegex(ResearchError, 'Drain the active job'):
                plan_cutover(self.root, manifest, checkpoint)
            preview = plan_cutover(self.root, manifest, checkpoint, preview=True)
        self.assertEqual(preview['original_states'], {'p1': 1})
        self.assertEqual(preview['queued'], [])
        self.assertEqual(self.jobs.get(row['request_id'])['status'], 'p1')

    def test_cutover_cli_reaches_preview_with_one_root_option(self):
        script = Path(__file__).resolve().parents[1] / 'tools/ts_momentum_direction_cutover.py'
        result = subprocess.run([sys.executable, '-B', str(script), 'preview', '--root', str(self.root),
                                 '--manifest', str(self.root/'missing-roster.json'),
                                 '--checkpoint', str(self.root/'missing-checkpoint.json')],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn('missing-roster.json', result.stderr)
        self.assertIn('FileNotFoundError', result.stderr)
