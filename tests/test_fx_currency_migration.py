"""Deletion ownership, drift, shared data, and interruption recovery safeguards."""
from pathlib import Path
import tempfile
import unittest
import json
import uuid
from copy import deepcopy
from unittest.mock import patch
from data.fx_currency_catalog import add
from data.feature_store import FeatureStore
from data.fx_currency_migration import plan,apply,RETIRED,MARKER
from data.transformations.identity import reference
from research.store import ResearchStore,install_bytes
from research.contracts import canonical,ref,digest
from test_scopes import fixture,files

class CurrencyDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();fixture(self.root)
        self.release=add(FeatureStore(self.root),'onboarding_evidence',{'kind':'fx_currency_release'})
        self.validation=patch('data.fx_currency_release.validate_release',return_value=self.release)
        self.validation.start();self.addCleanup(self.validation.stop)
        self.store=ResearchStore(self.root)
        self.old=self.store.put('relationship',{'scope':{'id':'FX_G10','version':'1.0.0'}},{})
        self.ts=self.store.put('relationship',{'scope':{'id':'EURUSD','version':'1.0.0'}},{})
        self.artifact=self.store.artifact({'owner':'old'},{'rows':[1,2,3]})
        self.trial=self.store.put('trial',{'relationship':ref(self.old)},{'artifact_manifests':[ref(self.artifact)]})
        self.ts_trial=self.store.put('trial',{'relationship':ref(self.ts)},{})
    def preview(self):return plan(self.root,reference(self.release))
    def put(self,path,value):install_bytes(self.root/path,canonical(value)+b'\n')

    def completed_batch(self, ts_first=False):
        from legacy_batch_fixture import ArchivedBatchFixture
        from runtime.research_jobs import ResearchJobs
        from test_research_runtime import Adapter, KernelSpy, profile, intent
        class CanonicalAdapter(Adapter):
            def resolve_plan(self, root, request, policy):
                synthetic=deepcopy(request)
                mode='TS' if request['scope']['id']=='EURUSD' else 'CS'
                synthetic['scope']['id']='SCOPE_'+mode
                plan=super().resolve_plan(root,synthetic,policy)
                plan['intent']=request;plan['scope']['id']=request['scope']['id']
                plan.pop('plan_id');plan['plan_id']='PLAN_'+digest(plan)
                return plan
        (self.root/'config').mkdir(exist_ok=True)
        (self.root/'config/research_execution.json').write_text(json.dumps(profile()))
        jobs=ResearchJobs(self.root,adapter=CanonicalAdapter(),kernels=KernelSpy())
        self.addCleanup(jobs.close)
        batches=ArchivedBatchFixture(jobs);bid=str(uuid.uuid4())
        scopes=['EURUSD','FX_G10'] if ts_first else ['FX_G10','EURUSD']
        request={'batch_id':bid,'name':'Synthetic mixed completed batch',
            'features':[intent()['feature']], 'scopes':[{'id':s,'version':'1.0.0'} for s in scopes],
            'target_family':'price_return','expected_direction':'POSITIVE','duplicate_policy':'reuse_exact'}
        batches.install_completed(request)
        self.assertEqual(batches.status(bid)['state']['state'],'completed')
        return batches,bid

    def test_completed_mixed_batch_preserves_ts_bytes_and_read_only_history(self):
        from research.contracts import ResearchConflict
        from runtime.research_batches import ResearchBatches
        batches,bid=self.completed_batch()  # TS index 1 must NOT be renumbered.
        base=f'storage/catalog/operations/research_batches/{bid}/'
        before=files(self.root);manifest=self.preview()
        self.assertEqual(manifest['blockers'],[])
        self.assertEqual(set(manifest['replace']),{base+'manifest.json'})
        replacement=manifest['replace'][base+'manifest.json']
        self.assertEqual(replacement['reconciliation']['retained_indices'],[1])
        self.assertIn(base+'rows/0.json',manifest['delete'])
        self.assertIn(base+'dispatch/0.json',manifest['delete'])
        for p in replacement['reconciliation']['retained_files']:
            self.assertNotIn(p,manifest['delete'])
        apply(self.root,manifest,manifest['sha256'])
        after=files(self.root)
        for p in manifest['inventory']:
            if p not in manifest['delete'] and p not in manifest['replace']:
                self.assertEqual(before[p],after[p],p)
        status=batches.status(bid)
        self.assertTrue(status['read_only']);self.assertFalse(status['approved'])
        self.assertEqual(status['job_counts'],{'succeeded':1})
        self.assertEqual(status['items'][0]['index'],1)
        self.assertEqual(status['items'][0]['intent']['scope']['id'],'EURUSD')
        with self.assertRaisesRegex(ResearchConflict,'retired'):ResearchBatches(batches.jobs)
        self.assertTrue(apply(self.root,manifest,manifest['sha256'])['reused'])

    def test_mixed_reconciliation_rejects_unfinished_or_corrupt_evidence(self):
        from legacy_batch_fixture import save
        batches,bid=self.completed_batch(ts_first=True);directory=batches.directory(bid)
        original=(directory/'state.json').read_bytes()
        save(directory/'state.json',{'state':'paused'},mutable=True)
        self.assertTrue(any('completed before reconciliation' in b for b in self.preview()['blockers']))
        (directory/'state.json').write_bytes(original)
        (directory/'approval.json').write_text('{}')
        self.assertTrue(any('corrupt batch evidence' in b for b in self.preview()['blockers']))

    def test_mixed_reconciliation_rejects_unknown_files_and_forged_dispatch(self):
        from legacy_batch_fixture import save
        from data.legacy_batch_evidence import checked
        batches,bid=self.completed_batch();directory=batches.directory(bid)
        extra=directory/'extra.json';extra.write_text('{}')
        self.assertTrue(any('Unknown or missing batch files' in b for b in self.preview()['blockers']))
        extra.unlink()
        dispatch=checked(directory/'dispatch/1.json');dispatch['request_id']=str(uuid.uuid4())
        save(directory/'dispatch/1.json',dispatch,mutable=True)
        self.assertTrue(any('original request' in b for b in self.preview()['blockers']))

    def test_reconciled_manifest_forgery_and_retained_row_drift_are_rejected(self):
        batches,bid=self.completed_batch();manifest=self.preview()
        path=next(iter(manifest['replace']))
        manifest['replace'][path]['request']['name']='Forged'
        manifest['sha256']=digest({k:v for k,v in manifest.items() if k!='sha256'})
        with self.assertRaisesRegex(ValueError,'changed'):apply(self.root,manifest,manifest['sha256'])
        manifest=self.preview()
        (batches.directory(bid)/'rows/1.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'changed'):apply(self.root,manifest,manifest['sha256'])

    def test_interrupted_reconciliation_resumes_with_original_ts_evidence(self):
        import data.fx_currency_migration as migration
        batches,bid=self.completed_batch();manifest=self.preview();original=migration.install_bytes
        target=batches.directory(bid)/'manifest.json'
        def interrupted(path,raw,**kwargs):
            result=original(path,raw,**kwargs)
            if path==target:raise OSError('interrupted after replacement')
            return result
        with patch.object(migration,'install_bytes',side_effect=interrupted):
            with self.assertRaisesRegex(OSError,'after replacement'):apply(self.root,manifest,manifest['sha256'])
        self.assertTrue((self.root/MARKER).exists())
        self.assertTrue(apply(self.root,manifest,manifest['sha256'])['completed'])
        self.assertEqual(batches.status(bid)['job_counts'],{'succeeded':1})

    def test_only_old_cs_history_and_owned_artifacts_are_selected(self):
        manifest=self.preview();self.assertEqual(manifest['blockers'],[])
        deleted=manifest['delete']
        self.assertIn(str(self.store.path('relationship',self.old['id']).relative_to(self.root)),deleted)
        self.assertIn(str(self.store.path('trial',self.trial['id']).relative_to(self.root)),deleted)
        self.assertNotIn(str(self.store.path('trial',self.ts_trial['id']).relative_to(self.root)),deleted)
        for scope in RETIRED:self.assertIn('definitions/scopes/'+scope+'/1.0.0.json',deleted)
        self.assertEqual(len(manifest['protected_ts']),86)
        self.assertTrue(any(p.startswith('storage/payloads/') for p in deleted))

    def test_shared_artifact_and_payload_survive(self):
        self.store.put('trial',{'relationship':ref(self.ts),'shared':True},{'artifact_manifests':[ref(self.artifact)]})
        deleted=self.preview()['delete']
        self.assertNotIn('storage/catalog/trial_artifacts/'+self.artifact['id']+'/manifest.json',deleted)
        for member in self.artifact['members']:
            self.assertFalse(any(member['blob_sha256'] in p for p in deleted))

    def test_mixed_batch_is_a_blocker(self):
        self.put('storage/catalog/operations/research_batches/batch/manifest.json',{'schema':'research_batch_v1','intents':[
            {'scope':{'id':'FX_G10','version':'1.0.0'}},{'scope':{'id':'EURUSD','version':'1.0.0'}}]})
        self.assertTrue(any('Mixed' in b for b in self.preview()['blockers']))

    def test_retained_unfinished_batch_blocks_release(self):
        self.put('storage/catalog/operations/research_batches/batch/manifest.json',{'schema':'research_batch_v1','intents':[
            {'scope':{'id':'EURUSD','version':'1.0.0'}}]})
        self.assertTrue(any('unfinished batch' in b for b in self.preview()['blockers']))

    def test_unknown_historical_schema_blocks_deletion(self):
        self.put('storage/catalog/trial_ledger/records/unknown.json',{'schema_version':'0.1.0','scope':{'id':'FX_G10'}})
        self.assertTrue(any('Unsupported historical' in b for b in self.preview()['blockers']))

    def test_retained_drift_aborts_before_any_deletion(self):
        manifest=self.preview();self.put('definitions/new.json',{'changed':True});before=files(self.root)
        with self.assertRaisesRegex(ValueError,'changed'):apply(self.root,manifest,manifest['sha256'])
        after=files(self.root)
        self.assertEqual({k:v for k,v in after.items() if not k.endswith('.lock')},{k:v for k,v in before.items() if not k.endswith('.lock')})

    def test_self_hashed_forged_deletion_is_not_authorized(self):
        manifest=self.preview();p=str(self.store.path('trial',self.ts_trial['id']).relative_to(self.root))
        manifest['delete'][p]=manifest['inventory'][p]
        manifest['sha256']=digest({k:v for k,v in manifest.items() if k!='sha256'})
        with self.assertRaisesRegex(ValueError,'changed'):apply(self.root,manifest,manifest['sha256'])
        self.assertTrue((self.root/p).exists())

    def test_symlink_is_rejected(self):
        (self.root/'definitions/link.json').symlink_to(self.root/'definitions/scopes/EURUSD/1.0.0.json')
        with self.assertRaisesRegex(ValueError,'symbolic'):self.preview()

    def test_apply_removes_history_and_is_idempotent(self):
        manifest=self.preview();result=apply(self.root,manifest,manifest['sha256'])
        self.assertTrue(result['completed']);self.assertFalse((self.root/MARKER).exists())
        self.assertTrue(self.store.path('trial',self.ts_trial['id']).exists())
        for p in manifest['delete']:self.assertFalse((self.root/p).exists())
        self.assertTrue(apply(self.root,manifest,manifest['sha256'])['reused'])

    def test_interruption_after_activation_resumes_without_restoring_old_data(self):
        from data.fx_currency_catalog import activate
        manifest=self.preview()
        def interrupted(root,release):
            activate(root,release)
            raise OSError('simulated power loss after activation')
        with patch('data.fx_currency_catalog.activate',side_effect=interrupted):
            with self.assertRaisesRegex(OSError,'power loss'):apply(self.root,manifest,manifest['sha256'])
        self.assertTrue((self.root/MARKER).exists())
        result=apply(self.root,manifest,manifest['sha256'])
        self.assertTrue(result['completed']);self.assertFalse((self.root/MARKER).exists())
        self.assertTrue(self.store.path('trial',self.ts_trial['id']).exists())

    def test_old_intake_receipts_follow_deleted_requests(self):
        request='a0000000-0000-4000-8000-000000000001'
        journal='storage/catalog/operations/experiment_intake/requests/'+request+'.json'
        receipt='storage/catalog/operations/experiment_intake/receipts/'+request+'.json'
        self.put(journal,{'request_id':request,'intent':{'scope':{'id':'FX_G10','version':'1.0.0'}}})
        self.put(receipt,{'request_id':request,'canonical_request_id':request})
        manifest=self.preview()
        self.assertIn(journal,manifest['delete']);self.assertIn(receipt,manifest['delete'])

    def test_unhandled_retained_consumer_blocks_deletion(self):
        self.put('storage/catalog/signal_library/entries/shared.json',{'record_type':'signal_library_entry','research_result':ref(self.trial)})
        self.assertTrue(any('Retained consumer' in b for b in self.preview()['blockers']))

    def test_current_worker_diagnostic_still_blocks_unreviewed_retirement(self):
        from data.legacy_batch_evidence import checked
        batches,bid=self.completed_batch()
        row=next(row for row in batches._rows(batches.directory(bid)) if row['intent']['scope']['id']=='FX_G10')
        dispatch=checked(batches.directory(bid)/'dispatch'/f"{row['index']}.json")
        jobs=batches.jobs
        jobs._diagnostic('RESEARCH_ATTEMPT_PERFORMANCE',request_id=dispatch['request_id'],
                         performance={'schema':'isolated operational timing fixture','wall_seconds':'1'})
        path=f'storage/catalog/operations/worker_events/{jobs.session_id}/{jobs.diagnostic_sequence}.json'
        original=(self.root/path).read_bytes();manifest=self.preview()
        self.assertIn('Retained consumer references deletion: '+path,manifest['blockers'])
        self.assertNotIn(path,manifest['delete'])
        with self.assertRaisesRegex(ValueError,'unblocked deletion manifest'):
            apply(self.root,manifest,manifest['sha256'])
        self.assertEqual((self.root/path).read_bytes(),original)
        self.assertTrue(jobs._submission_path(dispatch['request_id']).is_file())


    def test_batch_mixing_retired_and_new_currency_scope_is_not_deleted(self):
        path='storage/catalog/operations/research_batches/mixed/manifest.json'
        self.put(path,{'schema':'research_batch_v1','intents':[
            {'scope':{'id':'FX_G10','version':'1.0.0'}},{'scope':{'id':'FX_CCY_VS_USD','version':'1.0.0'}}]})
        manifest=self.preview()
        self.assertTrue(any('Mixed' in b for b in manifest['blockers']))
        self.assertNotIn(path,manifest['delete'])

    def test_maintenance_marker_blocks_resume_recovery_and_batch_api_stays_retired(self):
        from runtime.research_jobs import ResearchJobs
        from runtime.research_batches import ResearchBatches
        from research.contracts import ResearchBlocked,ResearchConflict
        self.put(MARKER,{'sha256':'interrupted'})
        jobs=ResearchJobs(self.root)
        with self.assertRaises(ResearchBlocked):jobs.resume('a0000000-0000-4000-8000-000000000001')
        with self.assertRaises(ResearchBlocked):jobs.get('a0000000-0000-4000-8000-000000000001')
        self.assertEqual(jobs._pending(),[])
        with self.assertRaisesRegex(ResearchConflict,'retired'):ResearchBatches(jobs)

    def test_uncommitted_retained_intake_reservation_blocks_migration(self):
        request='a0000000-0000-4000-8000-000000000001'
        self.put('storage/catalog/operations/experiment_intake/requests/'+request+'.json',
            {'request_id':request,'canonical_request_id':request,'intent':{'scope':{'id':'EURUSD','version':'1.0.0'}}})
        self.assertIn('Unverifiable request: '+request,self.preview()['blockers'])
