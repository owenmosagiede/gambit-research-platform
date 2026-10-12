"""Read-only FX recipe discovery and honest materialized-Feature presentation."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from api import feature_recipes, signal_library
from data.feature_store import FeatureStore, publish_feature, read_materialization
from data.transformations.identity import make_feature_definition, reference
from data.transformations.registry import Registry
from test_feature_store import persistence_fixture
from test_signal_library_api import running, request, inventory


class FeatureRecipeApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fx_feature_api_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.response = {'schema_version': '1.0.0', 'configuration_count': 30,
                         'binding_count': 1290, 'registered_count': 1290,
                         'materialized_count': 0, 'recipes': []}
        self.service = Mock(return_value=self.response)
        module = types.ModuleType('data.fx_feature_recipes')
        module.list_fx_recipes = self.service
        self.module_patch = patch.dict(sys.modules, {'data.fx_feature_recipes': module})
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)

    def test_read_only_endpoint_binds_filter_and_pagination(self):
        before = inventory(self.root)
        with running(self.root) as address:
            status, headers, data = request(address, '/api/feature-recipes?instrument_id=EURUSD&limit=7&offset=2')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data), self.response)
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.service.assert_called_with(self.root, instrument_id='EURUSD', limit=7, offset=2)
            status, _, data = request(address, '/api/feature-recipes', 'HEAD')
            self.assertEqual((status, data), (200, b''))
            self.service.assert_called_with(self.root, instrument_id=None, limit=100, offset=0)
        self.assertEqual(inventory(self.root), before)

    def test_malformed_filters_and_limits_are_not_sent_to_service(self):
        queries = ['limit=0', 'limit=501', 'limit=-1', 'limit=1.2', 'offset=-1', 'offset=nan',
                   'limit=1&limit=2', 'limit=', 'offset=', 'instrument_id=eurusd',
                   'instrument_id=../x', 'other=x', 'instrument_id=EURUSD&instrument_id=AUDUSD',
                   'limit', 'limit=true']
        with running(self.root) as address:
            for query in queries:
                with self.subTest(query=query):
                    status, _, data = request(address, '/api/feature-recipes?' + query)
                    self.assertEqual(status, 400)
                    self.assertEqual(json.loads(data)['error']['code'], 'UNSUPPORTED_QUERY')
        self.service.assert_not_called()

    def test_integrity_failures_are_unavailable_not_bad_user_queries(self):
        self.service.side_effect = ValueError('PRIVATE_REGISTRY_PATH')
        with running(self.root) as address:
            status, _, data = request(address, '/api/feature-recipes')
        self.assertEqual(status, 503)
        self.assertNotIn(b'PRIVATE_REGISTRY_PATH', data)

    def test_endpoint_rejects_writes_and_cross_origin_requests(self):
        with running(self.root) as address:
            for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                self.assertEqual(request(address, '/api/feature-recipes', method)[0], 405)
            for headers in ({'Origin': 'https://example.com'}, {'Host': 'example.com'}):
                self.assertEqual(request(address, '/api/feature-recipes', headers=headers)[0], 403)
        self.service.assert_not_called()


class FxFeaturePresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='fx_feature_presentation_')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name).resolve()
        cls.arguments = persistence_fixture(cls.root)
        cls.published = publish_feature(cls.root, **cls.arguments)
        registry = Registry(Path(__file__).resolve().parents[1])
        for identifier in ('TR_BASE_level_log', 'TR_BASE_change_diff'):
            FeatureStore(cls.root).install_record(registry.operator(identifier))

    def fx_projection(self):
        item = deepcopy(read_materialization(self.root, self.published['materialization']['id']))
        registry = Registry(self.root)
        recipe = deepcopy(item['feature']['body']['recipe'])
        log = registry.operator('TR_BASE_level_log')
        difference = registry.operator('TR_BASE_change_diff')
        recipe['steps'] = [
            {'node': 'log', 'phase': 'transformation', 'operator': reference(log), 'inputs': ['source'], 'parameters': []},
            {'node': 'difference', 'phase': 'transformation', 'operator': reference(difference), 'inputs': ['log'],
             'parameters': [{'name': 'k', 'unit': 'observations', 'value': {'kind': 'integer', 'value': '1'}}]}]
        recipe['output_node'] = 'difference'
        recipe['output_unit'] = 'log_USD_per_EUR'
        item['feature'] = make_feature_definition(recipe, 'EURUSD Log -> Difference')
        item['signal_id'] = item['feature']['body']['signal_id']
        item['materialization_state'] = 'materialized'
        item['scientific_state'] = 'untested'
        item['metadata']['dataset'] = {'schema_version': '0.5.0', 'record_type': 'dataset_definition',
            'id': 'DATASET_FX_TEST', 'version': '1.0.0', 'display_name': 'EURUSD reusable price dataset',
            'body': {'kind': 'fx_constructed_dataset', 'instrument_id': 'EURUSD',
                     'source_metadata': {'unit': 'USD_per_EUR', 'price_basis': 'unknown',
                                         'timing': {'timezone': None, 'bar_boundary': None}}}}
        item['manifest']['metadata'].update(unit='log_USD_per_EUR', value_semantics='difference',
                        availability_semantics='unknown_historical_availability')
        item['manifest']['readiness_capabilities'] = {'historical': False, 'live': False}
        for row in item['observations']:
            row['available_at'] = None
        return FeatureStore(self.root), item

    def test_fx_materialization_projection_preserves_multistep_recipe_and_unknown_availability(self):
        store, item = self.fx_projection()
        with patch.object(signal_library, '_load_signal', return_value=(store, [item])):
            result = signal_library.get_signal_detail(self.root, item['signal_id'])
        summary = result['signal']
        self.assertEqual(summary['source']['series_id'], 'EURUSD')
        self.assertEqual(summary['source']['provider'], 'Twelve Data-derived')
        self.assertEqual([step['operator']['id'] for step in summary['transformations']],
                         ['TR_BASE_level_log', 'TR_BASE_change_diff'])
        self.assertEqual(summary['value_semantics'], 'difference')
        self.assertEqual(summary['unit'], 'log_USD_per_EUR')
        self.assertEqual(result['timing']['evaluation_label'], 'Snapshot cutoff')
        self.assertTrue(result['timing']['retrospective_snapshot'])
        self.assertIn('availability is unknown', result['timing']['description'])
        self.assertTrue(all(row['available_at'] is None for row in result['observations']))
        self.assertEqual(result['research']['metrics'], [])

    def test_registered_unmaterialized_definitions_do_not_become_selectable(self):
        store, item = self.fx_projection()
        before = signal_library.list_signal_library(self.root)
        store.install_record(item['feature'])
        after = signal_library.list_signal_library(self.root)
        self.assertEqual(before, after)
        self.assertNotIn(item['signal_id'], [row['signal_id'] for row in after['signals']])

    def test_ui_uses_full_chain_and_does_not_label_every_dimensionless_statistic_a_fraction(self):
        script = (Path(__file__).resolve().parents[1] / 'ui/signals.js').read_text()
        self.assertIn('signal.transformations.map', script)
        self.assertIn('signal.value_semantics === "fractional_change"', script)
        self.assertNotIn('signal.unit === "dimensionless" ? "Fraction"', script)
        self.assertIn('Historical availability unknown', script)
        self.assertIn('row.available_at === null ? "Unknown"', script)
        self.assertNotIn('/api/feature-recipes', script)


if __name__ == '__main__':
    unittest.main()
