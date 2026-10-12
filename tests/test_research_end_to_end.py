"""Complete synthetic-only current-store → Submit → P1/P2 → library integration.

Only source admission and registry/Scope discovery are synthetic boundaries.
Calculation recipes, Feature preparation, Target arithmetic, immutable stores,
research input planning/loading, runtime, legacy kernels, artifacts and result
linkage are real. No production observations or approved production profiles are
read, prepared or tested by this fixture.
"""
from copy import deepcopy
from decimal import Decimal
import json
import math
import unittest
import uuid
from unittest.mock import patch

import test_fx_feature_store as feature_fixture
from test_research_inputs import approved_profile
from data.feature_store import FeatureStore
from data.fx_feature_store import _dates
from data.fx_feature_recipes import build_fx_feature, get_fx_policy
from data.fx_records import make_record
from data.reusable_features import _definition, _project_legacy
from data.targets.fx import materialize
from data.transformations.contracts import decimal_text
from data.transformations.identity import digest, reference
from data.transformations.registry import Registry
from research import inputs
from runtime.research_jobs import ResearchJobs


class StoredResearchEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.fx = feature_fixture.FXFeatureStoreTests(methodName='runTest'); self.fx.setUp()
        self.root, self.store = self.fx.root, self.fx.store
        self.addCleanup(self.fx.tearDown)
        self.profile = approved_profile()
        self.profile.update(id='RSPEC_ISOLATED_CURRENT_STORE_END_TO_END',
            exposure_classification='ISOLATED_SYNTHETIC_TEST_ONLY',
            periods={'P1': {'start_inclusive': '2021-01-01', 'end_exclusive': '2022-01-01'},
                     'P2': {'start_inclusive': '2022-01-01', 'end_exclusive': '2022-05-01'}})
        (self.root / 'config/research_execution.json').write_text(json.dumps(self.profile))
        (self.root / 'config/fx_retrospective_completion.json').write_text(json.dumps({
            'return_policy': self.fx.batch, 'knowledge_cutoff': '2024-05-02'}))
        registry = Registry(self.root); policy = get_fx_policy(self.root)
        step = self.fx.feature['body']['recipe']['steps'][-1]
        self.variant = {'operator': step['operator'], 'parameters': step['parameters'],
                        'grid_policy': step['grid_policy'], 'mode': 'log_first', 'parameter_frequency': 'daily'}
        self.recipe = _definition(registry, policy, self.variant); self.store.install_record(self.recipe)
        from research.feature_applications import install_binding, PER_MEMBER
        install_binding(self.root, self.recipe, PER_MEMBER)
        self.symbols = ['AUDUSD', 'EURUSD', 'GBPUSD', 'NZDUSD', 'USDJPY']
        self.days = list(_dates('2020-10-01', '2022-05-31'))
        self.states, self.bindings, self.current = {}, [], []
        for index, symbol in enumerate(self.symbols):
            meta = dict(self.fx.meta, base_currency=symbol[:3], quote_currency=symbol[3:],
                        unit=symbol[3:] + '_per_' + symbol[:3])
            dataset = self.store.install_record(make_record('dataset_definition', {
                'kind': 'fx_constructed_dataset', 'profile': 'fx_price.1.0.0', 'instrument_id': symbol,
                'source_metadata': meta}, 'ISOLATED synthetic ' + symbol))
            view = self.store.install_record(make_record('source_view_definition', {
                'kind': 'fx_constructed_view', 'profile': 'fx_price.1.0.0',
                'dataset': dataset, 'source_metadata': meta}))
            construction = self.store.install_record(make_record('transformation_definition', {
                'kind': 'ISOLATED_SYNTHETIC_PRICE_ADMISSION', 'instrument_id': symbol}))
            snapshot = make_record('snapshot_manifest', {'kind': 'fx_constructed_prices', 'profile': 'fx_price.1.0.0',
                'instrument_id': symbol, 'economic_id': 'FX_' + symbol[:3] + '_' + symbol[3:],
                'definition': view, 'recipe': construction, 'source_metadata': meta,
                'coverage': {'start': self.days[0], 'end': self.days[-1]}})
            snapshot_ref = self.store.install_record(snapshot)
            prices = []
            for t, day in enumerate(self.days):
                # Deterministic changing cross-sectional order creates actual,
                # nonconstant IC evidence; no research outcome is supplied.
                level = 100 * math.exp(.0008 * (index + 1) * t +
                    .011 * math.sin(t * .11 + index * .9) + .003 * math.sin(t * .67 + index * .7))
                row = {'reference_time': day, 'value': decimal_text(Decimal(str(level))), 'status': 'valid',
                    'reason_code': None, 'available_at': None, 'original_ingested_at': '2024-05-01T12:00:00.000000Z',
                    'input_dependencies': [{'original_ingested_at': '2024-05-01T12:00:00Z'}]}
                row['id'] = 'FXPRICE_' + digest(row); prices.append(row)
            self.states[snapshot_ref['id']] = (snapshot, prices)
            current = {'instrument_id': symbol, 'price_snapshot': snapshot_ref}; self.current.append(current)
            feature = build_fx_feature(self.root, current, self.variant, registry=registry, evaluation_policy=policy)
            self.store.install_record(feature)
            self.bindings.append({'instrument_id': symbol, 'feature': reference(feature),
                                  'source_view': view, 'price_snapshot': snapshot_ref})
        self.scope = {'id': 'SCOPE_ISOLATED_CS_FIVE', 'version': '1.0.0', 'kind': 'universe',
            'members': self.symbols, 'reference': {'id': 'SCOPE_ISOLATED_CS_FIVE', 'version': '1.0.0', 'content_sha256': 'a' * 64},
            'membership_snapshot': {'id': 'SNAPSHOT_' + 'b' * 64, 'version': '1.0.0', 'content_sha256': 'c' * 64}}
        replacements = [
            patch('research.inputs.load_reusable_recipe', return_value=self.recipe),
            patch('research.inputs.resolve_scope', return_value=self.scope),
            patch('research.inputs.list_instruments', return_value=self.current),
            patch('research.inputs.legacy_bindings_for_recipe', return_value=self.bindings),
            patch('research.inputs.legacy_recipe_projector', side_effect=lambda root, recipe: lambda feature:
                _project_legacy(FeatureStore(root), feature, Registry(root), get_fx_policy(root), {recipe['id']: recipe})),
            patch('research.inputs._structural_start', side_effect=lambda store, snapshot: snapshot['body']['coverage']['start']),
            patch('research.inputs._price_snapshot', side_effect=self.price),
            patch('data.fx_feature_store._price_snapshot', side_effect=self.price),
            patch('data.targets.fx._price_snapshot', side_effect=self.price),
        ]
        for replacement in replacements:
            replacement.start(); self.addCleanup(replacement.stop)
        for item in self.current:
            materialize(self.root, item['price_snapshot'], self.fx.batch, knowledge_cutoff='2024-05-02')

    def price(self, store, binding, policy, verify_rows=True):
        snapshot, prices = self.states[binding['id']]
        self.assertEqual(store.resolve(binding), snapshot)
        return deepcopy(snapshot), deepcopy(prices) if verify_rows else None

    def test_complete_cs_submit_uses_stored_values_real_kernels_and_durable_links(self):
        request = {'request_id': str(uuid.uuid4()),
            'feature': {'id': self.recipe['id'], 'version': '1.0.0'},
            'scope': {'id': self.scope['id'], 'version': '1.0.0'},
            'target_family': 'price_return', 'expected_direction': 'POSITIVE'}
        jobs = ResearchJobs(self.root)  # Default real adapter and real P1/P2 kernels.
        self.addCleanup(jobs.close)
        jobs.submit(request); jobs.run_pending_once(); job = jobs.get(request['request_id'])
        self.assertEqual(job['status'], 'succeeded', job)
        self.assertEqual(job['mode'], 'CS'); self.assertEqual(len(job['horizons']), 5)
        results = jobs.store.results_for_recipe(self.recipe['id'])
        self.assertEqual(len(results), 5)
        self.assertEqual({r['horizon'] for r in results}, {1, 7, 21, 63, 252})
        p2_count = 0
        for relationship in results:
            self.assertEqual(relationship['mode'], 'CS')
            self.assertEqual(relationship['scope']['members'], self.symbols)
            stages = {row['stage']: row for row in relationship['results']}
            self.assertIn('P1', stages)
            p1 = stages['P1']
            self.assertEqual(p1['sample']['inference_observation_unit'], 'dates')
            self.assertEqual(p1['sample']['required_members'], self.symbols)
            if relationship['horizon'] == 252:
                trial = jobs.store.resolve('trial', p1['authority'])
                self.assertIn('INSUFFICIENT_SAMPLE', trial['body']['reason_codes'])
            else:
                self.assertIsNotNone(p1['metrics']['primary_effect'])
                self.assertGreater(p1['sample']['inference_observation_count'], 100)
            for result in relationship['results']:
                trial = jobs.store.resolve('trial', result['authority'])
                self.assertTrue(trial['body']['artifact_manifests'])
                for artifact in trial['body']['artifact_manifests']:
                    jobs.store.verify_artifact(artifact)
            if 'P2' in stages:
                p2_count += 1
                self.assertTrue(stages['P2']['sample']['validation_data_accessed'])
                self.assertEqual(stages['P2']['sample']['required_members'], self.symbols)
        self.assertGreaterEqual(p2_count, 1, results)
        # A universe produces five scoped relationships, not25 individual TS ones.
        relationship_files = list((self.root / 'storage/catalog/signal_library/relationships').rglob('*.json'))
        self.assertEqual(len(relationship_files), 5)
        plan_record = jobs.store.resolve('plan', job['plan'])
        plan = plan_record['body']
        self.assertEqual(plan['scope']['members'], self.symbols)
        self.assertEqual(plan['recipe'], reference(self.recipe))
        # Read authoritative evidence from an actual trial artifact. The persisted
        # Feature value is independently reproduced from synthetic price operands.
        first = next(item for item in results if item['horizon'] == 1)
        first_p1 = next(r for r in first['results'] if r['stage'] == 'P1')
        self.assertGreater(first_p1['sample']['usable_pair_count'], 0)
        trial = jobs.store.resolve('trial', first_p1['authority'])
        artifact = jobs.store.verify_artifact(trial['body']['artifact_manifests'][0])
        aligned = next(m for m in artifact['members'] if m['role'] == 'aligned_sample')
        sha = aligned['blob_sha256']
        sample = json.loads((self.root / f'storage/payloads/sha256/{sha[:2]}/{sha}.json').read_text())
        row = sample[0]; t = self.days.index(row['date'])
        state = next((snapshot, prices) for snapshot, prices in self.states.values()
                     if snapshot['body']['instrument_id'] == row['instrument'])
        prices = {p['reference_time']: float(p['value']) for p in state[1]}
        self.assertAlmostEqual(float(row['feature']), math.log(prices[row['date']]) - math.log(prices[self.days[t-5]]))
        self.assertAlmostEqual(float(row['target']), prices[row['target_end']] / prices[row['date']] - 1)
        self.assertIsNone(row['available_at']); self.assertIsNone(row['target_available_at'])
        self.assertFalse(row['historical_eligibility_certified'])
        self.assertTrue(row['lineage']['feature_lineage']); self.assertTrue(row['lineage']['target_operands'])
        self.assertTrue(all(r['date'] < '2022-01-01' and r['target_end'] < '2022-01-01' for r in sample))
        self.assertEqual(len(list((self.root / 'storage/catalog/target_store').glob('*/manifest.json'))), 25)
        self.assertGreater(len(list((self.root / 'storage/catalog/feature_store').glob('*/manifest.json'))), 5)
        again, created = jobs.submit(request)
        self.assertFalse(created); self.assertEqual(again['request_id'], request['request_id'])
        self.assertEqual(len(jobs.store.results_for_recipe(self.recipe['id'])), 5)


if __name__ == '__main__': unittest.main()
