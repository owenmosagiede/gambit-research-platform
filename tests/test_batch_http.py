"""Retired batch HTTP surfaces cannot write or dispatch; experiments remain live."""
import http.client
import json
import unittest

from api.application import ApplicationRoutes, ASSETS
from api.catalog_cache import CatalogCache
from services.research_worker import WebResearchJobs, external_health
from test_research_runtime import Adapter, intent
from test_signal_library_api import inventory
import test_separate_services as services_fixture
from test_separate_services import worker_main

BID = '10000000-0000-4000-8000-000000000002'
PATHS = ['/api/batches', '/api/batches/' + BID,
         *['/api/batches/' + BID + '/' + action for action in ('approve', 'pause', 'resume')]]


class BatchHTTPTests(unittest.TestCase):
    setUp = services_fixture.SeparateServicesTests.setUp
    cleanup = services_fixture.SeparateServicesTests.cleanup
    start = services_fixture.SeparateServicesTests.start
    web = services_fixture.SeparateServicesTests.web
    request = services_fixture.SeparateServicesTests.request
    wait = services_fixture.SeparateServicesTests.wait

    def assert_retired(self, result):
        code, body = result
        self.assertEqual(code, 410, body)
        self.assertEqual(body['error']['code'], 'BATCH_RETIRED')
        self.assertIs(body['recorded'], False)

    def test_all_batch_routes_are_retired_without_research_writes(self):
        self.web()
        historical = self.root / 'storage/catalog/operations/research_batches' / BID / 'manifest.json'
        historical.parent.mkdir(parents=True)
        historical.write_text('{"historical":"unchanged"}')
        before = inventory(self.root)
        for path in PATHS + ['/api/batches/' + BID + '/unknown', '/api/batches?ignore=1']:
            with self.subTest(path=path):
                self.assert_retired(self.request('GET', path))
                self.assert_retired(self.request('POST', path, {'malformed': 'batch is never parsed'}))
        self.assertEqual(inventory(self.root), before)
        self.assertFalse((self.root / 'storage/catalog/submissions').exists())

    def test_shared_routes_never_access_jobs_or_parse_batch_payloads(self):
        class NoJobs:
            def __getattr__(self, name):
                raise AssertionError('Retired route accessed jobs: ' + name)
        before = inventory(self.root)
        for path in PATHS:
            for method in ('GET', 'HEAD', 'POST'):
                route = ApplicationRoutes(self.root, NoJobs(), CatalogCache(), method, path)
                route.write(b'not JSON') if method == 'POST' else route.read(method == 'HEAD')
                self.assert_retired((route.response[0], json.loads(route.response[1])))
        self.assertEqual(inventory(self.root), before)

    def test_retired_asset_is_not_exposed_and_head_has_no_body(self):
        self.web()
        self.assertNotIn('/batches.js', ASSETS)
        self.assertEqual(self.request('GET', '/batches.js')[0], 404)
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            c.request('HEAD', '/api/batches')
            response = c.getresponse()
            self.assertEqual(response.status, 410)
            self.assertEqual(response.read(), b'')
        finally:
            c.close()

    def test_retirement_preserves_exact_origin_checks(self):
        self.web()
        before = inventory(self.root)
        for origin in (None, 'https://other.example'):
            c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
            try:
                headers = {'Content-Type': 'application/json'}
                if origin: headers['Origin'] = origin
                c.request('POST', '/api/batches', '{}', headers)
                response = c.getresponse()
                self.assertEqual(response.status, 403)
                self.assertEqual(json.loads(response.read())['error']['code'], 'INVALID_ORIGIN')
            finally:
                c.close()
        self.assertEqual(inventory(self.root), before)

    def test_similar_non_batch_prefixes_keep_normal_unknown_route_behavior(self):
        self.web()
        before = inventory(self.root)
        for path in ('/api/batches-summary', '/api/batches_other', '/api/batches2/resume'):
            self.assertEqual(self.request('GET', path)[0], 404)
            code, response = self.request('POST', path, {})
            self.assertEqual(code, 405)
            self.assertNotEqual(response['error']['code'], 'BATCH_RETIRED')
        self.assertEqual(inventory(self.root), before)

    def test_individual_experiment_still_runs_in_independent_worker(self):
        worker = self.start(worker_main, self.root)
        web = self.web()
        self.wait(lambda: external_health(self.root)['healthy'])
        request = intent(mode='TS')
        self.assertEqual(self.request('POST', '/api/experiments', request)[0], 202)
        self.wait(lambda: (self.root/'entered').exists())
        web.terminate(); web.join(3)
        self.assertTrue(worker.is_alive())
        (self.root/'release').touch()
        jobs = WebResearchJobs(self.root, adapter=Adapter())
        self.wait(lambda: jobs.get(request['request_id'])['status'] == 'succeeded')
        self.web()
        code, results = self.request('GET', '/api/research-results/' + request['feature']['id'])
        self.assertEqual(code, 200)
        self.assertEqual(len(results['relationships']), 5)
        self.assertEqual(self.request('POST', '/api/experiments', request)[0], 200)
        self.assertEqual(len(list((self.root/'storage/catalog/submissions').glob('*.json'))), 1)


if __name__ == '__main__':
    unittest.main()
