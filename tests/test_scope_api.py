"""Scope API integration over persisted metadata fixtures, without price builds."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from api.scope_library import get_scope_resolution, InvalidScopeQuery
from contracts.experiment import normalize_resolved_experiment
from data.alfred_onboarding import strict_json
from data.feature_store import FeatureStore
from test_scopes import fixture
from test_signal_library_api import inventory, running, request

PROJECT = Path(__file__).resolve().parents[1]


class ScopeApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='scope_api_fixture_')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.fixture_root = Path(cls.temp.name) / 'research_platform'
        fixture(cls.fixture_root)
        (cls.fixture_root / 'ui').mkdir(exist_ok=True)
        shutil.copyfile(PROJECT / 'ui/scopes.js', cls.fixture_root / 'ui/scopes.js')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='scope_api_case_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'research_platform'
        shutil.copytree(self.fixture_root, self.root)

    def test_http_catalog_and_exact_resolution_preserve_contract_membership(self):
        before = inventory(self.root)
        with running(self.root) as address:
            code, headers, body = request(address, '/api/scope-library')
            self.assertEqual(code, 200)
            self.assertEqual(headers['Cache-Control'], 'no-store')
            catalog = json.loads(body)
            self.assertEqual(catalog['scope_count'], 61)
            self.assertEqual(catalog['issues'], [])
            self.assertEqual(sum(row['kind'] == 'instrument' for row in catalog['scopes']), 43)
            listed = next(row for row in catalog['scopes'] if row['id'] == 'FX_EUR_PAIRS')
            code, _, body = request(address, '/api/scope-library/FX_EUR_PAIRS?version=1.0.0')
            self.assertEqual(code, 200)
            resolved = json.loads(body)
            self.assertEqual(resolved, listed)
            self.assertEqual(resolved['member_count'], 11)
            self.assertEqual(resolved['members'], ['EURAUD', 'EURCAD', 'EURCHF', 'EURCZK', 'EURGBP',
                                                 'EURHUF', 'EURJPY', 'EURNOK', 'EURNZD', 'EURPLN', 'EURUSD'])
            code, _, body = request(address, '/api/scope-library/USDCAD?version=1.0.0')
            self.assertEqual(code, 200)
            instrument = json.loads(body)
            self.assertEqual(instrument['kind'], 'instrument')
            self.assertEqual(instrument['members'], ['USDCAD'])
        contract = strict_json((PROJECT / 'tests/fixtures/synthetic_resolved_experiment.json').read_bytes())
        unchanged = deepcopy(contract)
        contract['experiment']['scope'] = resolved['experiment_scope']
        contract['definition_bindings']['scope'] = resolved['definition_binding']
        contract['dependencies']['scope_membership_and_eligibility'] = resolved['dependency']
        normalized = normalize_resolved_experiment(contract)
        self.assertEqual(normalized['experiment']['scope'], {'id': 'FX_EUR_PAIRS', 'version': '1.0.0'})
        for field in ('feature', 'target', 'expected_direction', 'research_spec'):
            self.assertEqual(normalized['experiment'][field], unchanged['experiment'][field])
        membership = next(row['artifact'] for row in normalized['dependencies']['scope_membership_and_eligibility']['bindings']
                          if row['role'] == 'membership')
        self.assertEqual(membership, resolved['membership_snapshot'])
        snapshot = FeatureStore(self.root).resolve(membership)
        self.assertEqual(snapshot['record_count'], 11)
        self.assertEqual(inventory(self.root), before)

    def test_requires_an_exact_unambiguous_registered_version(self):
        with running(self.root) as address:
            for query in ('', '?version=', '?version=latest', '?version=01.0.0', '?version=1.0',
                          '?version=1.0.0&version=1.0.0', '?version=1.0.0&members=EURUSD'):
                with self.subTest(query=query):
                    code, _, body = request(address, '/api/scope-library/FX_G10' + query)
                    self.assertEqual(code, 400)
                    self.assertEqual(json.loads(body)['error']['code'], 'UNSUPPORTED_QUERY')
            for path in ('/api/scope-library/FX_G10?version=2.0.0',
                         '/api/scope-library/UNKNOWN_SCOPE?version=1.0.0',
                         '/api/scope-library/%2e%2e/.env?version=1.0.0'):
                self.assertEqual(request(address, path)[0], 404)
            self.assertEqual(request(address, '/api/scope-library?version=1.0.0')[0], 400)
        for version in (None, 'latest', '1.0.0\n'):
            with self.assertRaises(InvalidScopeQuery):
                get_scope_resolution(self.root, 'FX_G10', version)

    def test_missing_observations_do_not_reduce_scope_membership(self):
        with running(self.root) as address:
            code, _, body = request(address, '/api/scope-library/FTMO_UNIVERSE?version=1.0.0')
        self.assertEqual(code, 200)
        resolved = json.loads(body)
        self.assertEqual(resolved['member_count'], 43)
        self.assertEqual(len(resolved['members']), 43)
        self.assertEqual(resolved['readiness']['stored_price_member_count'], 0)

    def test_integrity_failure_is_unavailable_without_internal_details(self):
        resolved = get_scope_resolution(self.root, 'FX_G10', '1.0.0')
        store = FeatureStore(self.root)
        snapshot = store.resolve(resolved['membership_snapshot'])
        payload = snapshot['members'][0]
        path = self.root / f"storage/payloads/sha256/{payload['blob_sha256'][:2]}/{payload['blob_sha256']}.jsonl"
        path.write_bytes(path.read_bytes() + b'PRIVATE_PATH_SENTINEL')
        with running(self.root) as address:
            code, _, body = request(address, '/api/scope-library/FX_G10?version=1.0.0')
        self.assertEqual(code, 503)
        self.assertEqual(json.loads(body)['error']['code'], 'SCOPE_UNAVAILABLE')
        self.assertNotIn(str(self.root).encode(), body)
        self.assertNotIn(b'PRIVATE_PATH_SENTINEL', body)

    def test_read_only_route_asset_and_head(self):
        before = inventory(self.root)
        with running(self.root) as address:
            code, headers, body = request(address, '/api/scope-library/FX_NORDIC?version=1.0.0')
            head_code, head_headers, head_body = request(address, '/api/scope-library/FX_NORDIC?version=1.0.0', 'HEAD')
            self.assertEqual((code, head_code), (200, 200))
            self.assertEqual(headers['Content-Length'], head_headers['Content-Length'])
            self.assertEqual(head_body, b'')
            code, _, body = request(address, '/scopes.js')
            self.assertEqual(code, 200)
            self.assertEqual(body, (PROJECT / 'ui/scopes.js').read_bytes())
            self.assertEqual(request(address, '/api/scope-library', 'POST')[0], 405)
            self.assertEqual(request(address, '/api/scope-library', headers={'Host':'evil.example'})[0], 403)
        self.assertEqual(inventory(self.root), before)


if __name__ == '__main__':
    unittest.main()
