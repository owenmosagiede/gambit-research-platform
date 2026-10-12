"""Signal API acceptance using isolated synthetic stores; never mutate production."""
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest

from api import server, signal_library
from data.feature_store import FeatureStore, publish_feature
from data.transformations.engine import execute_recipe
from data.transformations.identity import make_feature_definition, reference
from data.transformations.registry import Registry
from test_feature_store import persistence_fixture


def inventory(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file()}


@contextmanager
def running(root):
    service = server.make_server(root, port=0)
    thread = threading.Thread(target=service.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()
    try:
        yield service.server_address
    finally:
        service.shutdown(); service.server_close(); thread.join(timeout=3)
        if thread.is_alive():
            raise AssertionError('Server did not stop')


def request(address, path, method='GET', headers=None):
    connection = http.client.HTTPConnection(*address, timeout=10)
    try:
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


class SignalLibraryApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_temp = tempfile.TemporaryDirectory(prefix='signal_api_fixture_')
        cls.addClassCleanup(cls.fixture_temp.cleanup)
        cls.fixture = Path(cls.fixture_temp.name) / 'research_platform'
        cls.fixture.mkdir()
        cls.arguments = persistence_fixture(cls.fixture)
        cls.published = publish_feature(cls.fixture, **cls.arguments)
        (cls.fixture / 'ui').mkdir()
        for name in ('index.html', 'library.css', 'library.js', 'signals.js'):
            (cls.fixture / 'ui' / name).write_text('Fixture asset ' + name)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='signal_api_case_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'research_platform'
        shutil.copytree(self.fixture, self.root)
        self.signal_id = self.published['signal_id']
        self.arguments = deepcopy(type(self).arguments)

    def catalog(self):
        return signal_library.list_signal_library(self.root)

    def detail(self, materialization_id=None):
        return signal_library.get_signal_detail(self.root, self.signal_id, materialization_id)

    def publish_subset(self, cutoffs):
        arguments = deepcopy(self.arguments)
        original_dates = [row['evaluation_cutoff'] for row in arguments['result']['observations']]
        arguments['result'] = execute_recipe(arguments['input_series'], arguments['feature']['body']['recipe'], cutoffs,
            registry=Registry(self.root), implementation=reference(arguments['implementation']))
        arguments['operand_links'] = [arguments['operand_links'][original_dates.index(cutoff)] for cutoff in cutoffs]
        return publish_feature(self.root, **arguments)

    def publish_second_signal(self):
        arguments = deepcopy(self.arguments)
        recipe = arguments['feature']['body']['recipe']
        policy = FeatureStore(self.root).resolve(recipe['evaluation_policy'])
        policy['id'] = 'POL_TRANSFORM_FIXTURE_SECOND_EVALUATION'
        FeatureStore(self.root).install_record(policy)
        recipe['evaluation_policy'] = reference(policy)
        arguments['feature'] = make_feature_definition(recipe, 'Another synthetic Feature')
        arguments['result'] = execute_recipe(arguments['input_series'], recipe,
            [row['evaluation_cutoff'] for row in arguments['result']['observations']],
            registry=Registry(self.root), implementation=reference(arguments['implementation']))
        arguments['policy_bindings'] = [dict(binding, artifact=reference(policy)) if binding['role'] == 'evaluation' else binding
                                       for binding in arguments['policy_bindings']]
        return publish_feature(self.root, **arguments)

    def test_one_unique_signal_and_exact_feature_populates_catalog(self):
        response = self.catalog()
        self.assertEqual(response['schema_version'], '1.0.0')
        self.assertEqual(response['signal_count'], 1)
        self.assertEqual(response['issues'], [])
        item = response['signals'][0]
        self.assertEqual(item['signal_id'], self.signal_id)
        self.assertEqual(item['feature'], reference(self.arguments['feature']))
        self.assertEqual(item['source']['series_id'], 'SYNTHETIC_SERIES')
        self.assertEqual(item['source']['dataset']['id'], 'DS_SYNTHETIC')
        self.assertEqual(item['materialization_count'], 1)
        self.assertEqual(item['row_count'], 3)
        self.assertEqual(item['scientific_state'], 'untested')
        self.assertEqual(item['materialization_state'], 'materialized')
        self.assertEqual(item['unit'], 'dimensionless')
        self.assertEqual(item['transformations'][0]['operator']['id'], 'TR_BASE_change_pct')

    def test_detail_contains_verified_values_lineage_and_descriptive_statistics(self):
        result = self.detail()
        stats = result['statistics']
        self.assertEqual((stats['row_count'], stats['valid_count'], stats['missing_count'], stats['invalid_count'], stats['null_count']), (3, 2, 0, 1, 1))
        self.assertEqual(stats['reason_counts'], {'INSUFFICIENT_HISTORY': 1})
        expected = [float(Decimal(110) / Decimal(100) - 1), float(Decimal(110) / Decimal(105) - 1)]
        self.assertAlmostEqual(stats['min'], min(expected))
        self.assertAlmostEqual(stats['max'], max(expected))
        self.assertAlmostEqual(stats['mean'], sum(expected) / 2)
        self.assertAlmostEqual(stats['median'], sum(expected) / 2)
        self.assertAlmostEqual(stats['sample_standard_deviation'], abs(expected[0] - expected[1]) / 2 ** .5)
        self.assertEqual(result['research']['state'], 'untested')
        self.assertEqual(result['research']['metrics'], [])
        self.assertEqual(result['research']['relationship_count'], 0)
        self.assertTrue(all(row['lineage']['id'].startswith('LINEAGE_') for row in result['observations']))
        self.assertEqual(result['provenance']['materialization'], self.published['materialization'])
        self.assertEqual(result['timing']['precision'], 'date')
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_multiple_projection_versions_and_materializations_are_one_signal(self):
        later = self.publish_subset(['2020-03-15'])
        response = self.catalog()
        self.assertEqual(response['signal_count'], 1)
        self.assertEqual(response['signals'][0]['materialization_count'], 2)
        expected = max(self.published['materialization']['id'], later['materialization']['id'])
        self.assertEqual(response['signals'][0]['default_materialization_id'], expected)
        detail = self.detail(later['materialization']['id'])
        self.assertEqual(detail['selected_materialization_id'], later['materialization']['id'])
        self.assertEqual(detail['statistics']['row_count'], 1)
        self.assertIsNone(detail['statistics']['sample_standard_deviation'])
        self.assertEqual(len(detail['materializations']), 2)
        self.assertEqual({row['id'] for row in detail['materializations']}, {expected, min(self.published['materialization']['id'], later['materialization']['id'])})

    def test_default_prefers_latest_cutoff_over_new_projection_order(self):
        earlier = self.publish_subset(['2020-03-01'])
        self.assertNotEqual(earlier['materialization']['id'], self.published['materialization']['id'])
        self.assertEqual(self.catalog()['signals'][0]['default_materialization_id'], self.published['materialization']['id'])

    def test_future_distinct_signals_appear_as_separate_unique_rows(self):
        another = self.publish_second_signal()
        response = self.catalog()
        self.assertEqual(response['signal_count'], 2)
        self.assertEqual({item['signal_id'] for item in response['signals']}, {self.signal_id, another['signal_id']})
        self.assertEqual(len({item['feature']['id'] for item in response['signals']}), 2)

    def test_empty_catalog_and_absent_signal(self):
        shutil.rmtree(self.root / signal_library.ENTRIES)
        self.assertEqual(self.catalog(), {'schema_version': '1.0.0', 'signal_count': 0, 'signals': [], 'issues': []})
        with self.assertRaises(signal_library.SignalNotFound):
            self.detail()

    def test_malformed_signal_does_not_hide_healthy_signal(self):
        malformed = self.root / signal_library.ENTRIES / ('SIGNAL_' + 'f' * 64)
        malformed.mkdir()
        (malformed / 'broken.json').write_text('{')
        response = self.catalog()
        self.assertEqual(response['signal_count'], 1)
        self.assertEqual(len(response['issues']), 1)
        self.assertEqual(response['issues'][0]['code'], 'UNAVAILABLE_SIGNAL')
        self.assertNotIn(str(self.root), json.dumps(response))

    def test_fresh_reads_reject_corrupt_payload_and_all_linked_materializations(self):
        self.assertEqual(self.catalog()['signal_count'], 1)
        self.publish_subset(['2020-03-15'])
        manifest = FeatureStore(self.root).resolve(self.published['materialization'])
        part = manifest['partitions'][0]
        path = self.root / f"storage/payloads/sha256/{part['blob_sha256'][:2]}/{part['blob_sha256']}.jsonl"
        path.write_bytes(path.read_bytes() + b' ')
        self.assertEqual(self.catalog()['signal_count'], 0)
        self.assertEqual(len(self.catalog()['issues']), 1)
        with self.assertRaises(ValueError):
            self.detail()

    def test_conflicting_exact_materialization_refs_fail_closed(self):
        path = next((self.root / signal_library.ENTRIES / self.signal_id).glob('*.json'))
        original = json.loads(path.read_text())
        changed = deepcopy(original)
        changed['feature_materializations'][0]['content_sha256'] = '0' * 64
        from data.feature_store_contracts import make_library_entry
        changed = make_library_entry(changed['feature'], changed['feature_materializations'])
        FeatureStore(self.root).install_record(changed)
        self.assertEqual(self.catalog()['signal_count'], 0)
        with self.assertRaisesRegex(ValueError, 'Conflicting exact materialization'):
            self.detail()

    def test_bad_signal_ids_and_unlinked_materializations_never_resolve(self):
        for identifier in ('SIGNAL_x', '../definitions', self.signal_id + '/..', 'SIGNAL_' + 'A' * 64):
            with self.subTest(identifier=identifier), self.assertRaises(signal_library.SignalNotFound):
                signal_library.get_signal_detail(self.root, identifier)
        with self.assertRaises(signal_library.SignalNotFound):
            self.detail('MATERIALIZATION_' + '0' * 64)

    def test_read_only_including_repeated_api_calls(self):
        before = inventory(self.root)
        first = self.catalog()
        self.detail(); self.detail()
        self.assertEqual(first, self.catalog())
        self.assertEqual(inventory(self.root), before)

    def test_http_list_detail_head_and_explicit_materialization(self):
        before = inventory(self.root)
        with running(self.root) as address:
            for path in ('/api/signal-library', '/api/signal-library/' + self.signal_id,
                         '/api/signal-library/' + self.signal_id + '?materialization_id=' + self.published['materialization']['id']):
                status, headers, body = request(address, path)
                self.assertEqual(status, 200)
                self.assertEqual(headers['Cache-Control'], 'no-store')
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
                self.assertNotIn('Access-Control-Allow-Origin', headers)
                self.assertIsInstance(json.loads(body), dict)
                head_status, head_headers, head_body = request(address, path, 'HEAD')
                self.assertEqual(head_status, 200)
                self.assertEqual(head_body, b'')
                self.assertEqual(head_headers['Content-Length'], headers['Content-Length'])
        self.assertEqual(inventory(self.root), before)

    def test_http_invalid_queries_missing_and_arbitrary_paths(self):
        detail = '/api/signal-library/' + self.signal_id
        cases = [('/api/signal-library?anything=x', 400), (detail + '?anything=x', 400),
                 (detail + '?materialization_id=', 400), (detail + '?materialization_id=../x', 400),
                 (detail + '?materialization_id=x&materialization_id=y', 400),
                 (detail + '?materialization_id=' + 'MATERIALIZATION_' + '0' * 64, 404),
                 ('/api/signal-library/SIGNAL_x', 404), ('/api/signal-library/' + 'SIGNAL_' + 'f' * 64, 404),
                 ('/api/signal-library/%2e%2e/.env', 404), ('/../.env', 404),
                 ('/storage/catalog/feature_store', 404), ('/api/unknown', 404)]
        with running(self.root) as address:
            for path, expected in cases:
                with self.subTest(path=path):
                    status, _, body = request(address, path)
                    self.assertEqual(status, expected)
                    self.assertIn('error', json.loads(body))
                    self.assertNotIn(str(self.root).encode(), body)

    def test_http_corrupt_signal_has_generic_error(self):
        path = next((self.root / signal_library.ENTRIES / self.signal_id).glob('*.json'))
        path.write_text('LOCAL_PATH_SECRET')
        with running(self.root) as address:
            status, _, body = request(address, '/api/signal-library/' + self.signal_id)
        self.assertEqual(status, 503)
        self.assertNotIn(b'LOCAL_PATH_SECRET', body)
        self.assertEqual(json.loads(body)['error']['code'], 'SIGNAL_UNAVAILABLE')

    def test_http_security_and_methods_leave_store_unchanged(self):
        before = inventory(self.root)
        with self.assertRaises(ValueError):
            server.make_server(self.root, host='0.0.0.0')
        with running(self.root) as address:
            for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE', 'CONNECT'):
                status, headers, body = request(address, '/api/signal-library', method)
                self.assertEqual(status, 405)
                self.assertEqual(headers['Allow'], 'GET, HEAD')
                self.assertIn('error', json.loads(body))
            for headers in ({'Host': 'evil.example'}, {'Origin': 'https://evil.example'}):
                status, _, _ = request(address, '/api/signal-library', headers=headers)
                self.assertEqual(status, 403)
        self.assertEqual(inventory(self.root), before)

    def test_new_server_preserves_pit_and_explicit_assets_only(self):
        with running(self.root) as address:
            status, _, body = request(address, '/api/pit-library')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['dataset_count'], 0)
            for path, filename in (('/', 'index.html'), ('/library.css', 'library.css'),
                                   ('/library.js', 'library.js'), ('/signals.js', 'signals.js')):
                status, _, body = request(address, path)
                self.assertEqual(status, 200)
                self.assertEqual(body, (self.root / 'ui' / filename).read_bytes())


if __name__ == '__main__':
    unittest.main()
