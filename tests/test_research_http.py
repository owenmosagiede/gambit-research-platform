"""Local HTTP tests over temporary pending-profile stores, never production research."""
from copy import deepcopy
from http.client import HTTPConnection
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from api.server import make_server
from runtime.research_jobs import ResearchJobs

PROJECT = Path(__file__).resolve().parents[1]
REQUEST_ID = '10000000-0000-4000-8000-000000000001'


def submission():
    return {'request_id': REQUEST_ID,
            'feature': {'id': 'FEATURE_RECIPE_' + 'a' * 64, 'version': '1.0.0'},
            'scope': {'id': 'AUDUSD', 'version': '1.0.0'},
            'target_family': 'price_return', 'expected_direction': 'POSITIVE'}


class ResearchHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='research_http_isolated_')
        self.root = Path(self.temp.name) / 'research_platform'
        (self.root/'config').mkdir(parents=True)
        from test_research_runtime import profile
        pending = profile()
        pending['approval_state'] = 'approved'
        (self.root/'config/research_execution.json').write_text(json.dumps(pending))
        (self.root/'ui').mkdir()
        shutil.copyfile(PROJECT/'ui/submission.js', self.root/'ui/submission.js')
        self.server = None
        from test_research_runtime import Adapter
        self.adapter = Mock(wraps=Adapter())

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
        self.temp.cleanup()

    def start(self, *, idle_worker=False):
        injected = ResearchJobs(self.root, adapter=self.adapter) if idle_worker else None
        self.server = make_server(self.root, research_jobs=injected)
        self.server.research_jobs.adapter = self.adapter
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.origin = f'http://127.0.0.1:{self.port}'

    def request(self, path, *, method='GET', value=None, raw=None, headers=None, origin=True):
        content = raw if raw is not None else json.dumps(value).encode() if value is not None else None
        supplied = {'Content-Type': 'application/json'} if content is not None else {}
        if origin:
            supplied['Origin'] = self.origin
        supplied.update(headers or {})
        conn = HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn.request(method, path, body=content, headers=supplied)
            response = conn.getresponse()
            body = response.read()
            return response.status, dict(response.getheaders()), json.loads(body) if body and response.headers.get_content_type() == 'application/json' else body
        finally:
            conn.close()

    def await_status(self, status):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            code, _, value = self.request('/api/experiments/' + REQUEST_ID)
            if code == 200 and value['job']['status'] == status:
                return value['job']
            time.sleep(.01)
        self.fail('Temporary fixture did not reach ' + status)

    def test_default_web_and_readiness_get_create_no_requests_or_storage(self):
        config=self.root/'config/research_execution.json'; value=json.loads(config.read_text());value['approval_state']='pending';config.write_text(json.dumps(value))
        self.start()
        self.assertIsNone(self.server.research_jobs.thread)
        code, headers, value = self.request('/api/research-readiness')
        self.assertEqual(code, 200)
        self.assertTrue(value['implementation_installed'])
        self.assertFalse(value['execution_enabled'])
        self.assertTrue(value['blockers'])
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertFalse((self.root/'storage').exists())
        self.adapter.resolve_plan.assert_not_called()

    def test_pending_profile_rejected_before_recording_or_preparing(self):
        config=self.root/'config/research_execution.json';value=json.loads(config.read_text());value['approval_state']='pending';config.write_text(json.dumps(value))
        self.start()
        code, _, value = self.request('/api/experiments', method='POST', value=submission())
        self.assertEqual(code, 422)
        self.assertFalse(value['recorded'])
        self.adapter.resolve_plan.assert_not_called()
        self.adapter.prepare_phase.assert_not_called()
        self.assertFalse((self.root/'storage/catalog/submissions').exists())

    def test_obsolete_resume_returns_explicit_conflict_without_requeue(self):
        self.start(idle_worker=True)
        self.request('/api/experiments', method='POST', value=submission())
        self.request('/api/experiments/' + REQUEST_ID + '/cancel', method='POST', value={})
        before = {p: p.read_bytes() for p in (self.root/'storage').rglob('*.json')}
        with patch('runtime.research_jobs.implementation', return_value={'changed': True}):
            code, _, body = self.request('/api/experiments/' + REQUEST_ID + '/resume', method='POST', value={})
            self.assertEqual(code, 409)
            self.assertIn('cannot resume', body['error']['message'])
            code, _, body = self.request('/api/experiments/' + REQUEST_ID)
            self.assertFalse(body['job']['resumable'])
            self.assertEqual(body['job']['status'], 'cancelled')
        self.assertEqual(before, {p: p.read_bytes() for p in (self.root/'storage').rglob('*.json')})

    def test_duplicate_request_reuses_identity_but_conflicting_payload_is_rejected(self):
        self.start(idle_worker=True)
        first = self.request('/api/experiments', method='POST', value=submission())
        second = self.request('/api/experiments', method='POST', value=submission())
        self.assertEqual([first[0], second[0]], [202, 200])
        self.assertEqual(first[2]['job']['request_id'], second[2]['job']['request_id'])
        self.assertEqual(first[2]['job']['submission_receipt'], second[2]['job']['submission_receipt'])
        changed = submission(); changed['expected_direction'] = 'NEGATIVE'
        self.assertEqual(self.request('/api/experiments', method='POST', value=changed)[0], 409)
        stored = json.loads((self.root/'storage/catalog/submissions'/f'{REQUEST_ID}.json').read_text())
        self.assertEqual(stored['intent']['expected_direction'], 'POSITIVE')
        self.assertEqual(len(list((self.root/'storage/catalog/submissions').glob('*.json'))), 1)

    def test_queue_endpoint_lists_frozen_jobs_without_execution(self):
        self.start(idle_worker=True)
        self.assertEqual(self.request('/api/experiments')[2]['items'],[])
        self.request('/api/experiments',method='POST',value=submission())
        other=submission();other['request_id']='20000000-0000-4000-8000-000000000002';other['expected_direction']='NEGATIVE'
        self.request('/api/experiments',method='POST',value=other)
        code,headers,value=self.request('/api/experiments')
        self.assertEqual(code,200);self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual([i['job']['request_id'] for i in value['items']],[REQUEST_ID,other['request_id']])
        self.assertEqual([i['queue_position'] for i in value['items']],[1,2])
        self.assertEqual(value['items'][1]['intent']['expected_direction'],'NEGATIVE')
        self.assertEqual(self.adapter.resolve_plan.call_count,2)
        self.adapter.prepare_phase.assert_not_called()
        self.assertEqual(self.request('/api/experiments?run=true')[0],400)

    def test_local_referrer_policy_preserves_safari_post_origin(self):
        self.start()
        code,headers,_=self.request('/submission.js',origin=False)
        self.assertEqual(code,200)
        self.assertEqual(headers['Referrer-Policy'],'same-origin')
        self.assertNotIn('Access-Control-Allow-Origin',headers)
    def test_origin_rejection_explicitly_does_not_record_work(self):
        self.start()
        code,_,value=self.request('/api/experiments',method='POST',value=submission(),headers={'Origin':'null'})
        self.assertEqual(code,403);self.assertEqual(value['error']['code'],'INVALID_ORIGIN')
        self.assertIs(value['recorded'],False)
        self.assertFalse((self.root/'storage').exists())
        self.adapter.resolve_plan.assert_not_called()

    def test_exact_local_origin_required_for_mutations(self):
        self.start(idle_worker=True)
        for origin, headers in [(False, {}), (True, {'Origin': 'https://evil.example'}),
                                (True, {'Origin': 'null'}), (True, {'Host': 'evil.example'}),
                                (True, {'Origin': f'http://localhost:{self.port}'})]:
            with self.subTest(headers=headers, origin=origin):
                self.assertEqual(self.request('/api/experiments', method='POST', value=submission(), headers=headers, origin=origin)[0], 403)
        self.assertFalse((self.root/'storage/catalog/submissions').exists())
        self.assertEqual(self.request('/api/experiments', method='POST', value=submission())[0], 202)

    def test_localhost_origin_with_matching_host_is_allowed(self):
        self.start(idle_worker=True)
        headers = {'Host': f'localhost:{self.port}', 'Origin': f'http://localhost:{self.port}'}
        self.assertEqual(self.request('/api/experiments', method='POST', value=submission(), headers=headers)[0], 202)

    def test_body_shape_duplicate_keys_and_nonfinite_values_are_rejected(self):
        self.start(idle_worker=True)
        invalid = [[], {}, dict(submission(), horizon=21), dict(submission(), target_family='total_return'),
                   dict(submission(), request_id='../escape'), dict(submission(), feature={'id': 'x', 'version': 'latest'}),
                   dict(submission(), expected_direction='positive')]
        for body in invalid:
            with self.subTest(body=body):
                self.assertEqual(self.request('/api/experiments', method='POST', value=body)[0], 400)
        for body in [b'{"request_id":"a","request_id":"b"}', b'{"x":NaN}', b'not json']:
            with self.subTest(raw=body):
                self.assertEqual(self.request('/api/experiments', method='POST', raw=body)[0], 400)
        self.assertFalse((self.root/'storage/catalog/submissions').exists())

    def test_body_content_type_and_size_are_bounded(self):
        self.start(idle_worker=True)
        self.assertEqual(self.request('/api/experiments', method='POST', value=submission(), headers={'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.request('/api/experiments', method='POST', raw=b'x'*16385)[0], 413)
        self.assertEqual(self.request('/api/experiments', method='POST', raw=b'')[0], 413)
        self.assertFalse((self.root/'storage/catalog/submissions').exists())

    def test_cancel_and_resume_keep_same_frozen_request_and_require_empty_body(self):
        self.start(idle_worker=True)
        self.request('/api/experiments', method='POST', value=submission())
        path = self.root/'storage/catalog/submissions'/f'{REQUEST_ID}.json'; frozen = path.read_bytes()
        base = '/api/experiments/' + REQUEST_ID
        self.assertEqual(self.request(base + '/cancel', method='POST', value={'change': True})[0], 400)
        code, _, cancelled = self.request(base + '/cancel', method='POST', value={})
        self.assertEqual(code, 200)
        self.assertEqual(cancelled['job']['status'], 'cancelled')
        old_attempt = cancelled['job']['attempt_id']
        code, _, resumed = self.request(base + '/resume', method='POST', value={})
        self.assertEqual(code, 200)
        self.assertEqual(resumed['job']['status'], 'queued')
        self.assertNotEqual(resumed['job']['attempt_id'], old_attempt)
        self.assertEqual(self.request(base + '/resume', method='POST', value={})[0], 409)
        self.assertEqual(path.read_bytes(), frozen)
        self.adapter.resolve_plan.assert_called_once()
        self.adapter.prepare_phase.assert_not_called()

    def test_retry_after_rejected_policy_can_record_only_after_approval(self):
        config=self.root/'config/research_execution.json';value=json.loads(config.read_text());value['approval_state']='pending';config.write_text(json.dumps(value))
        self.start()
        self.assertEqual(self.request('/api/experiments', method='POST', value=submission())[0],422)
        self.assertEqual(self.request('/api/experiments/'+REQUEST_ID)[0],404)
        self.adapter.resolve_plan.assert_not_called()
        value['approval_state']='approved';config.write_text(json.dumps(value))
        self.assertEqual(self.request('/api/experiments', method='POST', value=submission())[0],202)
        self.adapter.resolve_plan.assert_called_once()
        self.adapter.prepare_phase.assert_not_called()

    def test_queries_invalid_ids_and_wrong_methods_cannot_start_work(self):
        self.start(idle_worker=True)
        self.assertEqual(self.request('/api/research-readiness?run=true')[0], 400)
        self.assertEqual(self.request('/api/experiments/../escape')[0], 404)
        self.assertEqual(self.request('/api/experiments/' + REQUEST_ID)[0], 404)
        self.assertEqual(self.request('/api/experiments?run=true', method='POST', value=submission())[0], 400)
        for method in ['PUT', 'PATCH', 'DELETE']:
            self.assertEqual(self.request('/api/experiments', method=method, value=submission())[0], 405)
        self.assertFalse((self.root/'storage/catalog/submissions').exists())

    def test_old_read_routes_stay_read_only_and_new_script_is_available(self):
        self.start(idle_worker=True)
        code, _, value = self.request('/api/pit-library')
        self.assertEqual(code, 200)
        self.assertEqual(value['dataset_count'], 0)
        for route in ['/api/pit-library', '/api/signal-library', '/api/feature-library', '/api/scope-library', '/']:
            with self.subTest(route=route):
                code, headers, _ = self.request(route, method='POST', value={})
                self.assertEqual(code, 405)
                self.assertEqual(headers['Allow'], 'GET, HEAD')
        code, headers, body = self.request('/submission.js')
        self.assertEqual(code, 200)
        self.assertIn('text/javascript', headers['Content-Type'])
        self.assertEqual(body, (PROJECT/'ui/submission.js').read_bytes())
        self.assertFalse((self.root/'storage/catalog/submissions').exists())


if __name__ == '__main__':
    unittest.main()
