"""Real HTTP, independent worker, real statistics, browser-independent batch intake."""
import json
from pathlib import Path
import time
import unittest

from runtime.research_batches import ResearchBatches
from services.research_worker import WebResearchJobs, external_health
from test_research_runtime import Adapter
from test_research_batches import manifest
import test_separate_services as services_fixture
from test_separate_services import worker_main


class BatchHTTPTests(unittest.TestCase):
    setUp = services_fixture.SeparateServicesTests.setUp
    cleanup = services_fixture.SeparateServicesTests.cleanup
    start = services_fixture.SeparateServicesTests.start
    web = services_fixture.SeparateServicesTests.web
    request = services_fixture.SeparateServicesTests.request
    wait = services_fixture.SeparateServicesTests.wait

    def test_approved_batch_finishes_after_initiating_web_process_exits(self):
        worker = self.start(worker_main, self.root); web = self.web()
        self.wait(lambda: external_health(self.root)['healthy'])
        m = manifest()
        code, result = self.request('POST', '/api/batches', m)
        self.assertEqual(code, 202, result)
        path = '/api/batches/' + m['batch_id']
        result = self.wait(lambda: (s if (s := self.request('GET', path)[1]).get('preview_complete') else None))
        self.assertEqual(result['preview_counts'], {'new': 2})
        self.assertFalse(list((self.root/'storage/catalog/trial_ledger/records').glob('*.json')))
        self.assertEqual(self.request('POST', path+'/approve', {'preview_sha256':'0'*64,'exclude_blocked':False})[0],409)
        approval = {'preview_sha256':result['preview_sha256'], 'exclude_blocked':False}
        self.assertEqual(self.request('POST', path+'/approve', approval)[0],202)
        self.assertEqual(self.request('POST', path+'/approve', approval)[0],202)
        self.wait(lambda: (self.root/'entered').exists())
        web.terminate(); web.join(3)
        self.assertTrue(worker.is_alive())
        (self.root/'release').touch()
        batches = ResearchBatches(WebResearchJobs(self.root, adapter=Adapter()))
        done = self.wait(lambda: (s if (s := batches.status(m['batch_id']))['state']['state']=='completed' else None),timeout=35)
        self.assertEqual(done['job_counts'], {'succeeded':2})
        self.web()
        code, result = self.request('GET', path)
        self.assertEqual(code,200); self.assertEqual(result['job_counts'],{'succeeded':2})
        code, results = self.request('GET', '/api/research-results/'+m['features'][0]['id'])
        self.assertEqual(code,200); self.assertEqual(len(results['relationships']),10)
        self.assertEqual({r['mode'] for r in results['relationships']},{'TS','CS'})
        self.assertTrue(any(any(t['stage']=='P2' for t in r['results']) for r in results['relationships']))
        self.assertEqual(len(list((self.root/'storage/catalog/submissions').glob('*.json'))),2)
        print('Batch HTTP evidence: preview ran no kernels; exact approval; independent worker; TS+CS; 10 horizon outcomes; P2 evidence; web restart; 2 unique submissions.')

    def test_invalid_routes_payloads_and_retry_identity(self):
        self.web(); m=manifest()
        self.assertEqual(self.request('POST','/api/batches',m)[0],202)
        self.assertEqual(self.request('POST','/api/batches',m)[0],202)
        self.assertEqual(self.request('POST','/api/batches',dict(m,name='changed'))[0],409)
        self.assertEqual(self.request('POST','/api/batches/'+m['batch_id']+'/resume',{'extra':True})[0],400)
        self.assertEqual(self.request('GET','/api/batches/'+m['batch_id']+'?ignore=1')[0],400)
        self.assertEqual(self.request('GET','/api/batches')[0],200)
        self.assertFalse(list((self.root/'storage/catalog/submissions').glob('*.json')))
