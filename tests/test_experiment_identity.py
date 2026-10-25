"""Shared route races and durable intake crash boundaries; synthetic stores only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import uuid

from research.contracts import digest, canonical, ResearchConflict
from research.store import install_bytes, lock
from runtime.research_jobs import ResearchJobs, implementation
from runtime.experiment_identity import IdentityIndex, freeze, scientific_key
from test_research_runtime import Adapter, KernelSpy, intent, profile


class IntakeTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'config').mkdir()
        (self.root/'config/research_execution.json').write_text(json.dumps(profile()))
        self.adapter, self.spy = Adapter(), KernelSpy()
        self.jobs = ResearchJobs(self.root, adapter=self.adapter, kernels=self.spy)

    def packet(self, request):
        return freeze(self.jobs, {k: v for k, v in request.items() if k != 'request_id'}, implementation())

    def test_different_ids_concurrent_submissions_create_one_experiment_without_calculation(self):
        request = intent()
        def submit(i):
            jobs = ResearchJobs(self.root, adapter=Adapter(), kernels=KernelSpy())
            r = dict(request, request_id=str(uuid.uuid4()))
            result = jobs.submit(r)
            self.assertFalse(jobs.adapter.preparations)
            self.assertFalse(jobs.kernels.calls)
            return r, result
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(submit, range(12)))
        self.assertEqual(sum(created for _, (_,created) in results), 1)
        ids = {job['request_id'] for _, (job,_) in results}
        self.assertEqual(len(ids), 1)
        self.assertEqual(len(self.jobs.list_jobs()['items']), 1)
        for r, (job,_) in results:
            retry, created = self.jobs.submit(r)
            self.assertFalse(created)
            self.assertEqual(retry['request_id'], job['request_id'])
            self.assertEqual(self.jobs.get(r['request_id'])['request_id'], job['request_id'])
            self.assertEqual(job['submission_receipt']['request_id'], r['request_id'])
        self.assertIn('frozen_plan', self.jobs._submission(next(iter(ids))))

    def test_completed_scientific_rejection_returns_results(self):
        first = intent(direction='NEGATIVE')
        self.jobs.submit(first); self.jobs.run_pending_once()
        count = len(self.spy.calls)
        job, created = self.jobs.submit(dict(first, request_id=str(uuid.uuid4())))
        self.assertFalse(created); self.assertEqual(job['intake_action'], 'view_results')
        self.assertTrue(all(r['p2_status']=='FAILED' for r in job['horizons']))
        self.assertTrue(job['results']); self.jobs.run_pending_once()
        self.assertEqual(len(self.spy.calls), count)

    def test_failure_and_cancellation_offer_recovery_no_new_attempt(self):
        for status in ('failed','cancelled','blocked'):
            with self.subTest(status=status):
                self.jobs = ResearchJobs(self.root, adapter=self.adapter, kernels=self.spy)
                request = intent(direction='NEGATIVE' if status=='failed' else 'POSITIVE', mode='TS' if status=='blocked' else 'CS')
                first, _ = self.jobs.submit(request)
                self.jobs._update(first['request_id'], status=status)
                job, created = self.jobs.submit(dict(request, request_id=str(uuid.uuid4())))
                self.assertFalse(created); self.assertEqual(job['intake_action'],'recover_existing')
                self.assertEqual(job['attempt_id'],first['attempt_id']); self.assertEqual(job['status'],status)
                self.assertTrue(job['resumable'])

    def test_lost_receipt_and_response_preserve_request_binding_after_inputs_change(self):
        first = intent(); a,_=self.jobs.submit(first)
        request = dict(first, request_id=str(uuid.uuid4())); self.jobs.submit(request)
        index=IdentityIndex(self.jobs)
        (index.base/'receipts'/f"{request['request_id']}.json").unlink()
        index.path.unlink()
        with patch.object(self.adapter,'resolve_plan',side_effect=AssertionError('Must not resolve retry')):
            result=self.jobs.get(request['request_id'])
            self.assertEqual(result['request_id'],a['request_id'])
            self.assertEqual(self.jobs.submit(request)[0]['request_id'],a['request_id'])
        with self.assertRaises(ResearchConflict):
            self.jobs.submit(dict(request,expected_direction='NEGATIVE'))

    def test_crash_after_journal_before_envelope_new_uuid_still_reuses_reservation(self):
        r=intent()
        with patch.object(self.jobs,'_ensure_recorded',side_effect=OSError('power loss')):
            with self.assertRaises(OSError):self.jobs.submit(r)
        self.assertFalse(self.jobs._submission_path(r['request_id']).exists())
        fresh=ResearchJobs(self.root,adapter=Adapter(),kernels=self.spy)
        job,created=fresh.submit(dict(r,request_id=str(uuid.uuid4())))
        self.assertFalse(created); self.assertEqual(job['request_id'],r['request_id'])
        fresh.run_pending_once()
        self.assertEqual(fresh.get(r['request_id'])['status'],'succeeded')
        self.assertEqual(len(fresh.list_jobs()['items']),1)

    def test_worker_recovers_publication_without_browser_retry(self):
        r=intent()
        with patch.object(self.jobs,'_ensure_recorded',side_effect=OSError('power loss')):
            with self.assertRaises(OSError):self.jobs.submit(r)
        self.jobs.run_pending_once()
        self.assertEqual(self.jobs.get(r['request_id'])['status'],'succeeded')

    def test_crash_after_envelope_before_first_event(self):
        r=intent()
        with patch.object(self.jobs,'_save',side_effect=OSError('power loss')):
            with self.assertRaises(OSError):self.jobs.submit(r)
        self.jobs.run_pending_once()
        self.assertEqual(self.jobs.get(r['request_id'])['status'],'succeeded')
        self.assertEqual(len(self.jobs.list_jobs()['items']),1)

    def test_changed_inputs_new_identity_and_cache_inventory_does_not_change_identity(self):
        r=intent(); a,_=self.jobs.submit(r)
        resolve=self.adapter.resolve_plan
        def changed(root,intent,policy):
            p=resolve(root,intent,policy);p['members'][0]['price_snapshot']={'id':'changed','version':'1.0.0','content_sha256':'a'*64}
            p['plan_id']='PLAN_'+digest(p);return p
        with patch.object(self.adapter,'resolve_plan',side_effect=changed):
            b,created=self.jobs.submit(dict(r,request_id=str(uuid.uuid4())))
        self.assertTrue(created);self.assertNotEqual(a['request_id'],b['request_id'])
        def cached(root,intent,policy):
            p=resolve(root,intent,policy);p['members'][0]['feature_materializations']=[{'id':'CACHE'}]
            p['plan_id']='PLAN_'+digest(p);return p
        with patch.object(self.adapter,'resolve_plan',side_effect=cached):
            c,created=self.jobs.submit(dict(r,request_id=str(uuid.uuid4())))
        self.assertFalse(created);self.assertEqual(a['request_id'],c['request_id'])

    def test_release_requires_exact_review_and_retains_execution_resume_guard(self):
        r=intent();first,_=self.jobs.submit(r);old=implementation();new=deepcopy(old)
        new['files']['runtime/example.py']='a'*64;new['fingerprint']=digest(new['files'])
        with patch('runtime.research_jobs.implementation',return_value=new):
            with self.assertRaisesRegex(ResearchConflict,'compatibility'):
                self.jobs.submit(dict(r,request_id=str(uuid.uuid4())))
            review={'from':digest(old),'to':digest(new),'decision':'equivalent','evidence':'review-123','tests':['parity-test']}
            with patch('runtime.experiment_identity.release_reviews',return_value=[review]):
                job,created=self.jobs.submit(dict(r,request_id=str(uuid.uuid4())))
                self.assertFalse(created);self.assertEqual(job['request_id'],first['request_id'])
                self.jobs.cancel(first['request_id'])
                self.assertFalse(self.jobs.get(first['request_id'])['resumable'])
                with self.assertRaises(ResearchConflict):self.jobs.resume(first['request_id'])
            review['decision']='different'
            with patch('runtime.experiment_identity.release_reviews',return_value=[review]):
                job,created=self.jobs.submit(dict(r,request_id=str(uuid.uuid4())))
                self.assertTrue(created);self.assertNotEqual(job['request_id'],first['request_id'])
        self.assertEqual(self.jobs._submission(first['request_id'])['implementation'],old)

    def test_unresolved_legacy_history_blocks_even_after_code_change(self):
        r=intent();packet=self.packet(r);packet.pop('frozen_plan')
        original=dict(packet,schema_version='0.8.0',request_id=r['request_id'],created_at='2026-10-01T00:00:00+00:00',intent_fingerprint=digest(packet['intent']))
        original['record_sha256']=digest(original)
        install_bytes(self.jobs._submission_path(r['request_id']),canonical(original)+b'\n')
        with self.assertRaisesRegex(ResearchConflict,'reconciliation'):
            self.jobs.submit(dict(r,request_id=str(uuid.uuid4())))

    def test_index_rebuild_and_warm_lookup_do_not_scan_envelopes(self):
        r=intent();self.jobs.submit(r)
        index=IdentityIndex(self.jobs)
        with patch.object(IdentityIndex,'rebuild',side_effect=AssertionError('Warm lookup scanned history')):
            self.jobs.submit(dict(r,request_id=str(uuid.uuid4())))
        index.path.unlink()
        with lock(self.root,'research-writer'):
            state=index.rebuild()
        self.assertEqual(len(state['entries']),1);self.assertFalse(state['issues'])

    def test_retired_batch_overrides_are_rejected_before_intake(self):
        r=intent()
        before={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        for keyword,value in (('_batch_packet',{}),('_batch_duplicate_policy','reuse_exact'),('_batch_reuse_id',r['request_id'])):
            with self.subTest(keyword=keyword),self.assertRaisesRegex(TypeError,keyword):
                self.jobs.submit(r,**{keyword:value})
        after={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(after,before)
        self.assertEqual(self.adapter.resolve_calls,0)

    def test_changed_phase_target_and_membership_never_reuse_old_science(self):
        request=intent();first,_=self.jobs.submit(request);resolve=self.adapter.resolve_plan
        for field in ('periods','targets','scope'):
            def changed(root,intent,policy):
                plan=deepcopy(resolve(root,intent,policy))
                if field=='periods':plan['periods']['P1']['end_exclusive']='2021-01-01'
                elif field=='targets':plan['members'][0]['targets']['1']['materialization']['content_sha256']='b'*64
                else:plan['scope']['content_sha256']='c'*64
                plan['plan_id']='PLAN_'+digest(plan);return plan
            with patch.object(self.adapter,'resolve_plan',side_effect=changed):
                new,created=self.jobs.submit(dict(request,request_id=str(uuid.uuid4())))
            self.assertTrue(created);self.assertNotEqual(new['request_id'],first['request_id'])

    def test_historical_duplicate_authorities_require_reconciliation(self):
        request=intent();first,_=self.jobs.submit(request)
        original=deepcopy(self.jobs._submission(first['request_id']));original['request_id']=str(uuid.uuid4())
        original.pop('record_sha256');original['record_sha256']=digest(original)
        with lock(self.root,'research-writer'):self.jobs._ensure_recorded(original)
        with self.assertRaisesRegex(ResearchConflict,'reconciliation'):
            self.jobs.submit(dict(request,request_id=str(uuid.uuid4())))
        self.assertEqual(len(self.jobs.list_jobs()['items']),2)
        with lock(self.root,'research-writer'):
            state=IdentityIndex(self.jobs).rebuild(persist=False)
        self.assertEqual(len(state['entries']),2)

    def test_corrupt_journal_is_not_treated_as_missing_receipt(self):
        request=intent();self.jobs.submit(request);index=IdentityIndex(self.jobs)
        path=index.journal_path(request['request_id']);path.write_text('{invalid')
        with self.assertRaises((ValueError,ResearchConflict)):self.jobs.submit(request)
        index.invalidate()
        with self.assertRaisesRegex(ResearchConflict,'reconciliation'):
            self.jobs.submit(dict(request,request_id=str(uuid.uuid4())))
        self.assertFalse(self.adapter.preparations)

    def test_retry_of_unfrozen_historical_uuid_does_not_requeue(self):
        request=intent();packet=self.packet(request);packet.pop('frozen_plan')
        original=dict(packet,schema_version='0.8.0',request_id=request['request_id'],created_at='2026-10-01T00:00:00+00:00',intent_fingerprint=digest(packet['intent']))
        original['record_sha256']=digest(original)
        install_bytes(self.jobs._submission_path(request['request_id']),canonical(original)+b'\n')
        with self.assertRaisesRegex(ResearchConflict,'reconciliation'):self.jobs.submit(request)
        self.jobs.run_pending_once()
        self.assertTrue(self.jobs.get(request['request_id'])['operational_failure'])
        self.assertFalse(self.adapter.preparations)
