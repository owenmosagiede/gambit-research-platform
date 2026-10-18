"""Isolated batch intake, crash recovery, exact duplicate handling and real kernels."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid

from research.contracts import ResearchConflict, ResearchError, digest
from runtime.research_batches import ResearchBatches, checked, save, semantic_key
from runtime.research_jobs import ResearchJobs
from test_research_runtime import Adapter, KernelSpy, intent, profile


def manifest(**changes):
    r = intent()
    return dict({'batch_id': str(uuid.uuid4()), 'name': 'Synthetic Momentum batch',
        'features': [r['feature']], 'scopes': [intent(mode='TS')['scope'], r['scope']],
        'target_family': 'price_return', 'expected_direction': 'POSITIVE', 'duplicate_policy': 'reuse_exact'}, **changes)


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.root = Path(self.temp.name)
        (self.root/'config').mkdir(); (self.root/'config/research_execution.json').write_text(json.dumps(profile()))
        self.adapter = Adapter(); self.kernels = KernelSpy()
        self.jobs = ResearchJobs(self.root, adapter=self.adapter, kernels=self.kernels)
        self.batches = ResearchBatches(self.jobs)
        self.addCleanup(self.temp.cleanup); self.addCleanup(self.jobs.close)

    def preview(self, request=None):
        m = request or manifest(); self.batches.create(m)
        for _ in range(10):
            self.jobs.run_pending_once()
            status = self.batches.status(m['batch_id'])
            if status['preview_complete']: return m, status
        self.fail('Preview did not complete')

    def approve(self, m, status, exclude=False):
        return self.batches.approve(m['batch_id'], {'preview_sha256': status['preview_sha256'], 'exclude_blocked': exclude})

    def finish(self, bid):
        for _ in range(20):
            self.jobs.run_pending_once()
            s = self.batches.status(bid)
            if s['state']['state'] in ('completed', 'needs_attention'): return s
        self.fail('Batch did not finish')

    def test_preview_counts_frozen_directions_and_no_execution(self):
        m, s = self.preview(manifest(expected_direction='NEGATIVE'))
        self.assertEqual(s['preview_counts'], {'new': 2})
        self.assertEqual(s['estimates']['p1_horizon_evaluations'], 10)
        self.assertEqual(s['estimates']['p2_horizon_evaluations_upper_bound'], 10)
        self.assertIsNone(s['estimates']['sequential_seconds_range'])
        self.assertFalse(self.adapter.preparations); self.assertFalse(self.jobs.list_jobs()['items'])
        self.assertEqual({r['mode'] for r in s['items']}, {'TS', 'CS'})
        self.assertTrue(all(r['intent']['expected_direction'] == 'NEGATIVE' for r in s['items']))
        self.approve(m, s); done = self.finish(m['batch_id'])
        self.assertEqual(done['job_counts'], {'succeeded': 2})
        for item in done['items']:
            original = self.jobs._submission(item['dispatch']['request_id'])
            self.assertEqual(original['frozen_plan']['intent']['expected_direction'], 'NEGATIVE')
            self.assertEqual(len(item['job']['horizons']), 5)

    def test_identical_preview_retry_and_manifest_conflict(self):
        m, s = self.preview()
        self.assertEqual(self.batches.create(m)['preview_sha256'], s['preview_sha256'])
        with self.assertRaises(ResearchConflict): self.batches.create(dict(m, expected_direction='NEGATIVE'))
        with self.assertRaises(ResearchConflict): self.batches.approve(m['batch_id'], {'preview_sha256':'0'*64, 'exclude_blocked':False})
        self.assertFalse(self.jobs.list_jobs()['items'])

    def test_duplicates_in_manifest_and_existing_success_reuse(self):
        m = manifest(); m['features'] *= 2
        m, s = self.preview(m); self.assertEqual(s['input_duplicates'], 2)
        self.approve(m, s); self.finish(m['batch_id'])
        n, t = self.preview(); self.assertEqual(t['preview_counts'], {'reuse': 2})
        self.assertEqual(t['estimates']['new_submissions'], 0)
        self.approve(n, t); done = self.finish(n['batch_id'])
        self.assertEqual(done['state']['state'], 'completed')
        self.assertEqual(len(self.jobs.list_jobs()['items']), 2)
        self.assertTrue(all(i['dispatch']['state']=='linked' for i in done['items']))

    def test_crash_after_enqueue_recovers_original_id(self):
        m, s = self.preview(); self.approve(m, s)
        import runtime.research_batches as module
        original = module.save
        def crash(path, *a, **kw):
            if path.parent.name == 'dispatch': raise OSError('simulated disk failure after durable Submit')
            return original(path, *a, **kw)
        with patch.object(module, 'save', crash): self.jobs.run_pending_once()
        self.assertEqual(len(self.jobs.list_jobs()['items']), 1)
        fresh = ResearchBatches(ResearchJobs(self.root, adapter=self.adapter, kernels=self.kernels))
        self.assertEqual(fresh.status(m['batch_id'])['state']['state'], 'needs_attention')
        fresh.control(m['batch_id'], 'resume')
        done = self.finish(m['batch_id'])
        self.assertEqual(done['job_counts'], {'succeeded':2})
        self.assertEqual(len(self.jobs.list_jobs()['items']), 2)
        self.assertEqual({i['dispatch']['request_id'] for i in done['items']}, {i['request_id'] for i in s['items']})

    def test_pause_resume_preview_and_dispatch_preserve_ids(self):
        m = manifest(); self.batches.create(m); self.batches.control(m['batch_id'], 'pause')
        self.jobs.run_pending_once(); self.assertEqual(self.batches.status(m['batch_id'])['previewed'], 0)
        self.batches.control(m['batch_id'], 'resume')
        m, s = self.preview(m); self.approve(m, s)
        self.jobs.run_pending_once(); self.batches.control(m['batch_id'], 'pause')
        for _ in range(3): self.jobs.run_pending_once()
        self.assertEqual(len(self.jobs.list_jobs()['items']), 1)
        self.batches.control(m['batch_id'], 'resume')
        self.assertEqual(self.finish(m['batch_id'])['job_counts'], {'succeeded': 2})

    def test_crash_after_approval_recovers_without_reapproval(self):
        m, s = self.preview()
        with patch.object(self.batches, '_state', side_effect=OSError('approval state interrupted')):
            with self.assertRaises(OSError): self.approve(m, s)
        self.assertTrue((self.batches.directory(m['batch_id'])/'approval.json').exists())
        self.assertEqual(self.batches.status(m['batch_id'])['state']['state'], 'ready')
        self.assertEqual(self.finish(m['batch_id'])['job_counts'], {'succeeded': 2})

    def test_approval_retry_does_not_unpause(self):
        m, s = self.preview(); self.approve(m, s)
        self.batches.control(m['batch_id'], 'pause')
        self.approve(m, s); self.jobs.run_pending_once()
        self.assertEqual(self.batches.status(m['batch_id'])['state']['state'], 'paused')
        self.assertFalse(self.jobs.list_jobs()['items'])

    def test_invalid_member_requires_explicit_exclusion(self):
        resolve = self.adapter.resolve_plan
        def invalid(root, request, policy):
            if request['scope']['id'] == 'SCOPE_CS': raise ValueError('Missing member; no member was omitted')
            return resolve(root, request, policy)
        self.adapter.resolve_plan = invalid
        m, s = self.preview(); self.assertEqual(s['preview_counts'], {'new':1, 'blocked':1})
        with self.assertRaises(ResearchConflict): self.approve(m, s)
        self.approve(m, s, True)
        self.assertEqual(self.finish(m['batch_id'])['job_counts'], {'succeeded':1, 'excluded':1})

    def test_changed_policy_after_preview_blocks_dispatch(self):
        m, s = self.preview(); self.approve(m, s)
        p = profile(); p['version']='2.0.0'; (self.root/'config/research_execution.json').write_text(json.dumps(p))
        done = self.finish(m['batch_id'])
        self.assertEqual(done['state']['state'], 'needs_attention'); self.assertFalse(self.jobs.list_jobs()['items'])

    def test_changed_code_cannot_approve_or_resume(self):
        m, s = self.preview()
        with patch('runtime.research_batches.implementation', return_value={}):
            with self.assertRaises(ResearchConflict): self.approve(m,s)
            with self.assertRaises(ResearchConflict): self.batches.control(m['batch_id'],'resume')

    def test_duplicate_failed_is_explicit_not_automatic_retry(self):
        m, s = self.preview(); self.approve(m,s); self.jobs.run_pending_once()
        rid = self.jobs.list_jobs()['items'][0]['job']['request_id']; self.jobs.cancel(rid)
        self.finish(m['batch_id'])
        n, t = self.preview()
        self.assertEqual(t['preview_counts'], {'blocked':1, 'reuse':1})
        self.assertIn('DUPLICATE_REQUIRES_REVIEW', str(t['items']))

    def test_racing_batches_deduplicate_under_writer_lock(self):
        m, s = self.preview(); n, t = self.preview()
        self.approve(m,s); self.approve(n,t)
        for _ in range(15): self.jobs.run_pending_once()
        self.assertEqual(len(self.jobs.list_jobs()['items']),2)
        self.assertEqual(self.batches.status(m['batch_id'])['state']['state'], 'completed')
        self.assertEqual(self.batches.status(n['batch_id'])['state']['state'], 'completed')

    def test_tamper_blocks_no_submission(self):
        m,s=self.preview(); self.approve(m,s)
        path=self.batches.directory(m['batch_id'])/'rows/0.json'
        row=json.loads(path.read_text()); row['intent']['expected_direction']='NEGATIVE';path.write_text(json.dumps(row))
        self.jobs.run_pending_once()
        self.assertEqual(checked(path.parent.parent/'state.json')['state'],'needs_attention')
        self.assertFalse(self.jobs.list_jobs()['items'])

    def test_reject_policy_keeps_existing_success_visible_without_rerun(self):
        m, s = self.preview(); self.approve(m, s); self.finish(m['batch_id'])
        n, t = self.preview(manifest(duplicate_policy='reject'))
        self.assertEqual(t['preview_counts'], {'blocked': 2})
        self.assertEqual(t['estimates']['new_submissions'], 0)
        with self.assertRaises(ResearchConflict): self.approve(n, t)
        self.assertEqual(len(self.jobs.list_jobs()['items']), 2)

    def test_previewed_reuse_cannot_turn_into_new_research(self):
        m, s = self.preview(); self.approve(m, s)
        self.jobs.run_pending_once()
        self.batches.control(m['batch_id'], 'pause')
        n = manifest(scopes=[m['scopes'][0]])
        self.batches.create(n); self.batches.advance()
        t = self.batches.status(n['batch_id'])
        self.assertEqual(t['preview_counts'], {'reuse': 1})
        self.approve(n, t)
        self.jobs.cancel(t['items'][0]['existing_request_id'])
        self.batches.advance()
        self.assertEqual(self.batches.status(n['batch_id'])['state']['state'], 'needs_attention')
        self.assertEqual(len(self.jobs.list_jobs()['items']), 1)

    def test_resource_estimates_are_labeled_assumptions(self):
        basis={'description':'Synthetic calibration, not a measured production forecast',
            'seconds_per_experiment':[10,40], 'bytes_per_experiment':[100,200]}
        m,s=self.preview(manifest(estimate_basis=basis))
        self.assertEqual(s['estimates']['sequential_seconds_range'],[20,80])
        self.assertEqual(s['estimates']['additional_bytes_range'],[200,400])
        self.assertEqual(s['estimates']['basis'],basis)
        self.assertGreater(s['estimates']['scheduled_member_rows_upper_bound']['P1'],0)
        with self.assertRaises(ResearchError): self.batches.create(manifest(estimate_basis=dict(basis,seconds_per_experiment=[True,10])))

    def test_bounds_and_explicit_direction(self):
        with self.assertRaises(ResearchError):self.batches.create(manifest(expected_direction='AUTO'))
        with self.assertRaises(ResearchError):self.batches.create(manifest(features=[]))
        m=manifest();m['features']*=2501
        with self.assertRaises(ResearchError):self.batches.create(m)

    def test_real_kernels_p1_p2_scoped_results(self):
        self.jobs.kernels=None
        m,s=self.preview();self.approve(m,s);done=self.finish(m['batch_id'])
        self.assertEqual(done['job_counts'], {'succeeded':2})
        results=self.jobs.store.results_for_recipe(m['features'][0]['id'])
        self.assertEqual(len(results),10)
        self.assertEqual({r['mode'] for r in results},{'TS','CS'})
        self.assertTrue(any(any(t['stage']=='P2' for t in r['results']) for r in results))
        self.assertTrue(list((self.root/'storage/catalog/trial_ledger/records').glob('*.json')))


class StoredBatchTests(unittest.TestCase):
    def test_batch_uses_native_planner_preparation_and_stored_results(self):
        import test_research_end_to_end as fixtures
        fixture = fixtures.StoredResearchEndToEndTests(methodName='runTest')
        self.addCleanup(fixture.doCleanups); fixture.setUp()
        jobs = ResearchJobs(fixture.root); self.addCleanup(jobs.close)
        batches = ResearchBatches(jobs)
        m = manifest(features=[{'id': fixture.recipe['id'], 'version': '1.0.0'}],
                     scopes=[{'id': fixture.scope['id'], 'version': '1.0.0'}])
        batches.create(m); jobs.run_pending_once()
        preview = batches.status(m['batch_id'])
        self.assertEqual(preview['preview_counts'], {'new': 1}, preview)
        self.assertFalse(jobs.store.results_for_recipe(fixture.recipe['id']))
        batches.approve(m['batch_id'], {'preview_sha256': preview['preview_sha256'], 'exclude_blocked': False})
        for _ in range(4): jobs.run_pending_once()
        done = batches.status(m['batch_id'])
        self.assertEqual(done['job_counts'], {'succeeded': 1}, done)
        results = jobs.store.results_for_recipe(fixture.recipe['id'])
        self.assertEqual(len(results), 5)
        self.assertTrue(any(any(t['stage'] == 'P2' for t in r['results']) for r in results))
        n = dict(m, batch_id=str(uuid.uuid4()))
        batches.create(n); jobs.run_pending_once()
        self.assertEqual(batches.status(n['batch_id'])['preview_counts'], {'reuse': 1})
