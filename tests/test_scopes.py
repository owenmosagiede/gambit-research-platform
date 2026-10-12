"""Fixed memberships, exact experiment bindings and immutable publication regressions."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from contracts.experiment import normalize_resolved_experiment, resolved_experiment_id
from data.feature_store import FeatureStore, record_path
from data.fx_records import make_record
from data.scopes import (PAIR_IDS, UNIVERSES, ScopeError, ScopeNotFound, ScopeConflict,
                         register_fx_scopes, resolve_groups, list_scopes, resolve_scope)
from data.transformations.identity import canonical_bytes, reference

PROJECT = Path(__file__).resolve().parents[1]
REQUEST = 'Synthetic explicit approval of the fixed 43-pair FX scope rules for isolated tests.'
WHEN = datetime(2026, 10, 9, 15, 30, tzinfo=timezone.utc)


def metadata_fixture(root):
    root = Path(root)
    (root / 'specs/schemas').mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT / 'specs/schemas/platform.schema.json', root / 'specs/schemas/platform.schema.json')
    store = FeatureStore(root)
    for symbol in PAIR_IDS:
        base, quote = symbol[:3], symbol[3:]
        record = make_record('onboarding_evidence', {
            'kind': 'fx_instrument_registration', 'profile': 'fx_price.1.0.0',
            'instrument_id': symbol, 'economic_id': 'FX_' + base + '_' + quote,
            'source_metadata': {'base_currency': base, 'quote_currency': quote},
            'construction': {'method': 'interface_fixture'},
            'dependencies': ['PROVIDER_LABEL_THAT_IS_NOT_A_PAIR'], 'source_inputs': [],
            'price_coverage': {'start': None, 'end': None}, 'price_row_count': 0,
            'price_snapshot': None, 'blockers': ['NO_OBSERVATIONS'],
            'readiness_capabilities': {name: {'decision': 'blocked', 'reason': 'Isolated metadata fixture'}
                for name in ('historical_replay', 'live_use', 'retrospective_research')}}, symbol)
        store.install_record(record)
    return store


def fixture(root):
    """Persist real scope contracts over 43 synthetic registrations, without prices."""
    metadata_fixture(root)
    return register_fx_scopes(root, REQUEST, registered_at=WHEN)


def files(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in Path(root).rglob('*') if path.is_file()}


class ScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = tempfile.TemporaryDirectory(prefix='scope_seed_')
        cls.seed_root = Path(cls.seed.name)
        cls.registration = fixture(cls.seed_root)

    @classmethod
    def tearDownClass(cls):
        cls.seed.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='scope_test_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(self.seed_root, self.root, dirs_exist_ok=True)

    def test_counts_and_exact_independent_currency_rules(self):
        result = list_scopes(self.root)
        self.assertEqual(result['issues'], [])
        self.assertEqual(result['scope_count'], 61)
        universes = {s['id']: s for s in result['scopes'] if s['kind'] == 'universe'}
        self.assertEqual(len(universes), 18)
        pairs = set('''AUDUSD EURUSD GBPUSD NZDUSD USDCAD USDCHF USDCNH USDCZK USDHKD USDHUF
            USDILS USDJPY USDMXN USDNOK USDPLN USDSEK USDSGD USDZAR AUDCAD AUDCHF AUDJPY AUDNZD
            CADCHF CADJPY CHFJPY EURAUD EURCAD EURCHF EURCZK EURGBP EURHUF EURJPY EURNOK EURNZD
            EURPLN GBPAUD GBPCAD GBPCHF GBPJPY GBPNZD NZDCAD NZDCHF NZDJPY'''.split())
        core = set('AUD CAD CHF EUR GBP JPY NZD USD'.split())
        g10 = core | {'NOK', 'SEK'}
        expected = {
            'FTMO_UNIVERSE': pairs,
            'FX_G10': {s for s in pairs if {s[:3], s[3:]} <= g10},
            'FX_NON_G10': {s for s in pairs if not {s[:3], s[3:]} <= g10},
            'FX_CORE_28': {s for s in pairs if {s[:3], s[3:]} <= core},
            'FX_USD_PAIRS': {s for s in pairs if 'USD' in (s[:3], s[3:])},
            'FX_NON_USD_CROSSES': {s for s in pairs if 'USD' not in (s[:3], s[3:])},
            'FX_CORE_USD_PAIRS': {s for s in pairs if {s[:3], s[3:]} <= core and 'USD' in (s[:3], s[3:])},
            'FX_CORE_CROSSES': {s for s in pairs if {s[:3], s[3:]} <= core and 'USD' not in (s[:3], s[3:])},
            'FX_NORDIC': {'EURNOK', 'USDNOK', 'USDSEK'},
            'FX_CENTRAL_EUROPE': {'EURCZK', 'EURHUF', 'EURPLN', 'USDCZK', 'USDHUF', 'USDPLN'},
            'FX_ASIA_CNH_HKD_SGD': {'USDCNH', 'USDHKD', 'USDSGD'},
        }
        expected.update({'FX_' + c + '_PAIRS': {s for s in pairs if c in (s[:3], s[3:])}
                         for c in ('AUD', 'CAD', 'CHF', 'EUR', 'GBP', 'JPY', 'NZD')})
        self.assertEqual(set(universes), set(expected))
        for identifier, members in expected.items():
            self.assertEqual(set(universes[identifier]['members']), members, identifier)
            self.assertEqual(universes[identifier]['member_count'], len(members), identifier)
        self.assertEqual([universes[i]['member_count'] for i, *_ in UNIVERSES],
                         [43, 31, 12, 28, 18, 25, 7, 21, 3, 6, 3, 7, 7, 7, 11, 7, 7, 7])

    def test_partitions_and_overlap_are_preserved(self):
        scopes = {s['id']: set(s['members']) for s in list_scopes(self.root)['scopes']}
        for parent, left, right in [('FTMO_UNIVERSE', 'FX_G10', 'FX_NON_G10'),
                                    ('FTMO_UNIVERSE', 'FX_USD_PAIRS', 'FX_NON_USD_CROSSES'),
                                    ('FX_CORE_28', 'FX_CORE_USD_PAIRS', 'FX_CORE_CROSSES')]:
            self.assertFalse(scopes[left] & scopes[right])
            self.assertEqual(scopes[left] | scopes[right], scopes[parent])
        self.assertEqual(scopes['FX_EUR_PAIRS'] & scopes['FX_JPY_PAIRS'], {'EURJPY'})
        for universe in ('FTMO_UNIVERSE', 'FX_G10', 'FX_CORE_28', 'FX_NON_USD_CROSSES',
                         'FX_CORE_CROSSES', 'FX_EUR_PAIRS', 'FX_JPY_PAIRS'):
            self.assertIn('EURJPY', scopes[universe])

    def test_singleton_scopes_reuse_economic_instrument_identity(self):
        for symbol in PAIR_IDS:
            result = resolve_scope(self.root, symbol, '1.0.0')
            self.assertEqual(result['kind'], 'instrument')
            self.assertEqual(result['members'], [symbol])
            self.assertEqual(result['economic_entity_ids'], ['FX_' + symbol[:3] + '_' + symbol[3:]])

    def test_all_registered_members_remain_when_no_price_observations_exist(self):
        result = resolve_scope(self.root, 'FTMO_UNIVERSE', '1.0.0')
        self.assertEqual(result['member_count'], 43)
        self.assertEqual(result['readiness']['registered_member_count'], 43)
        self.assertEqual(result['readiness']['stored_price_member_count'], 0)
        self.assertEqual(result['readiness']['retrospective_ready_member_count'], 0)
        self.assertFalse(list((self.root / 'storage/catalog/target_store').glob('*')))

    def test_repeat_execution_is_byte_identical(self):
        before = files(self.root)
        again = register_fx_scopes(self.root, REQUEST, registered_at=datetime(2027, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(again, self.registration)
        self.assertEqual(files(self.root), before)

    def test_new_readiness_generation_does_not_change_pinned_membership(self):
        original = resolve_scope(self.root, 'FTMO_UNIVERSE', '1.0.0')
        store = FeatureStore(self.root)
        row = original['readiness']['members'][0]['instrument_id']
        # A newer registration has more stored price rows; no new observations are built here.
        old = next(store.resolve(item['registration']) for item in __import__('data.fx_pipeline', fromlist=['list_instruments']).list_instruments(self.root)
                   if item['instrument_id'] == row)
        body = deepcopy(old['body']);body['price_row_count'] = 99
        body['price_coverage'] = {'start': '2020-01-01', 'end': '2021-01-01'}
        body['readiness_capabilities']['retrospective_research']['decision'] = 'ready'
        store.install_record(make_record('onboarding_evidence', body, old['display_name']))
        before = files(self.root)
        register_fx_scopes(self.root, REQUEST)
        self.assertEqual(files(self.root), before)
        after = resolve_scope(self.root, 'FTMO_UNIVERSE', '1.0.0')
        self.assertEqual(after['members'], original['members'])
        self.assertEqual(after['membership_snapshot'], original['membership_snapshot'])
        self.assertEqual(after['definition_binding'], original['definition_binding'])
        self.assertEqual(after['readiness']['stored_price_member_count'], 1)
        self.assertEqual(after['readiness']['retrospective_ready_member_count'], 1)

    def test_experiment_binding_uses_existing_canonical_contract(self):
        resolved = json.loads((PROJECT / 'tests/fixtures/synthetic_resolved_experiment.json').read_text())
        result = resolve_scope(self.root, 'FX_EUR_PAIRS', '1.0.0')
        resolved['experiment']['scope'] = result['experiment_scope']
        resolved['definition_bindings']['scope'] = result['definition_binding']
        resolved['dependencies']['scope_membership_and_eligibility'] = result['dependency']
        normalized = normalize_resolved_experiment(resolved)
        self.assertEqual(normalized['experiment']['scope'], {'id': 'FX_EUR_PAIRS', 'version': '1.0.0'})
        self.assertIn({'role': 'membership', 'artifact': result['membership_snapshot']},
                      normalized['dependencies']['scope_membership_and_eligibility']['bindings'])
        before = resolved_experiment_id(resolved)
        resolved['dependencies']['scope_membership_and_eligibility']['bindings'][0]['artifact']['content_sha256'] = 'a' * 64
        self.assertNotEqual(resolved_experiment_id(resolved), before)

    def test_preserve_unrelated_definition_and_membership(self):
        root = self.root / 'definitions/scopes/UNRELATED_RESEARCH'
        root.mkdir(parents=True)
        path = root / '1.0.0.json'
        path.write_text('{"unrelated":true}\n')
        unrelated = self.root / 'storage/catalog/unrelated_memberships.json'
        unrelated.write_text('{"preserve":true}\n')
        before = files(self.root)
        register_fx_scopes(self.root, REQUEST)
        self.assertEqual(files(self.root), before)

    def test_incompatible_scope_name_rejects_before_any_publication(self):
        path = self.root / 'definitions/scopes/FX_G10/1.0.0.json'
        record = json.loads(path.read_text());record['display_name'] = 'Incompatible existing name'
        path.write_bytes(canonical_bytes(record) + b'\n')
        before = files(self.root)
        with self.assertRaises(ScopeConflict):register_fx_scopes(self.root, REQUEST)
        self.assertEqual(files(self.root), before)

    def test_other_existing_version_requires_explicit_resolution(self):
        old = self.root / 'definitions/scopes/FX_G10/1.0.0.json'
        alternate = old.with_name('2.0.0.json')
        record = json.loads(old.read_text());record['version'] = '2.0.0'
        alternate.write_bytes(canonical_bytes(record) + b'\n')
        before = files(self.root)
        with self.assertRaises(ScopeConflict):register_fx_scopes(self.root, REQUEST)
        self.assertEqual(files(self.root), before)

    def test_request_change_rejected_without_silent_overwrite(self):
        before = files(self.root)
        with self.assertRaises(ScopeConflict):register_fx_scopes(self.root, REQUEST + ' Different scientific rules.')
        self.assertEqual(files(self.root), before)

    def test_membership_payload_tamper_is_detected(self):
        binding = resolve_scope(self.root, 'FX_G10', '1.0.0')['membership_snapshot']
        store = FeatureStore(self.root);manifest = store.resolve(binding);member = manifest['members'][0]
        path = self.root / f"storage/payloads/sha256/{member['blob_sha256'][:2]}/{member['blob_sha256']}.jsonl"
        data = path.read_bytes();path.write_bytes(data.replace(b'EURJPY', b'FAKEFX'))
        with self.assertRaises(ValueError):resolve_scope(self.root, 'FX_G10', '1.0.0')

    def test_registration_metadata_tamper_is_detected(self):
        result = resolve_scope(self.root, 'FX_G10', '1.0.0')
        store = FeatureStore(self.root);snapshot = store.resolve(result['membership_snapshot'])
        resolution = store.resolve(snapshot['lineage'][0]);ref = resolution['body']['registered_instruments'][0]['instrument_registration']
        record = store.resolve(ref);path = self.root / record_path(record)
        record['body']['source_metadata']['base_currency'] = 'USD'
        path.write_bytes(canonical_bytes(record) + b'\n')
        with self.assertRaises(ValueError):resolve_scope(self.root, 'FX_G10', '1.0.0')

    def test_absent_version_and_invalid_paths(self):
        with self.assertRaises(ScopeNotFound):resolve_scope(self.root, 'FX_G10', '2.0.0')
        with self.assertRaises(ScopeError):resolve_scope(self.root, '../FX_G10', '1.0.0')
        with self.assertRaises(ScopeError):resolve_scope(self.root, 'FX_G10', '../1.0.0')

    def test_missing_registered_instrument_fails_before_registration(self):
        temp = tempfile.TemporaryDirectory(prefix='scope_missing_');self.addCleanup(temp.cleanup)
        root = Path(temp.name);store = metadata_fixture(root)
        for path in (root / 'storage/catalog/onboarding/evidence').glob('*.json'):
            if json.loads(path.read_text())['body']['instrument_id'] == 'USDILS':path.unlink()
        before = files(root)
        with self.assertRaisesRegex(ScopeError, 'USDILS'):register_fx_scopes(root, REQUEST)
        self.assertEqual(files(root), before)

    def test_snapshot_period_is_document_metadata_not_history(self):
        result = resolve_scope(self.root, 'FTMO_UNIVERSE', '1.0.0')
        store = FeatureStore(self.root);snapshot = store.resolve(result['membership_snapshot'])
        self.assertEqual(snapshot['period']['start_inclusive'], '2026-10-09T15:30:00.000000Z')
        self.assertEqual(snapshot['period']['end_exclusive'], '2026-10-09T15:30:00.000001Z')
        resolution = store.resolve(snapshot['lineage'][0])
        self.assertEqual(resolution['body']['period_meaning'], 'document_registration_interval_not_economic_or_broker_eligibility')
        self.assertIn('does not certify', result['readiness']['note'])


if __name__ == '__main__':
    unittest.main()
