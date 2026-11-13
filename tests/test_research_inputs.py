"""Research input integration in isolated synthetic stores only.

Price-source admission and the reusable registry/Scope catalogs are fixture
boundaries. Real Feature kernels, Target construction, stores, semantic identities,
phase loader, lineage and duplicate prevention execute against temporary data.
"""
from copy import deepcopy
from datetime import date
import json
import unittest
from unittest.mock import patch

from data.alfred_onboarding import Store
from data.fx_records import make_record
from data.reusable_features import _definition
from data.fx_feature_recipes import get_fx_policy
from data.targets.fx import materialize
from data.transformations.identity import reference, digest
from data.transformations.registry import Registry
from research import inputs
import test_fx_feature_store as feature_fixture


def approved_profile():
    """Test-only approval, never written into or selected by production config."""
    return {'id': 'ISOLATED_RESEARCH_INPUT_FIXTURE', 'version': '1.0.0', 'approval_state': 'approved',
        'availability_mode': 'retrospective_date_label', 'exposure_classification': 'ISOLATED_TEST_ONLY',
        'periods': {'P1': {'start_inclusive': '2024-01-02', 'end_exclusive': '2024-03-01'},
                    'P2': {'start_inclusive': '2024-03-01', 'end_exclusive': '2024-04-23'}},
        'target_selection': {'knowledge_cutoff': '2024-05-02', 'materializations': {}},
        'approvals': {name: True for name in inputs.APPROVALS},
        'kernel': {'kernel_policy': 'retained_legacy_v1', 'spacing': 1, 'horizon_unit': 'scheduled_weekdays',
                   'clock_compatibility': 'approved', 'missing_evidence': 'legacy_failed_v1'}}


class ResearchInputsTests(unittest.TestCase):
    def setUp(self):
        self.fx = feature_fixture.FXFeatureStoreTests(methodName='runTest'); self.fx.setUp()
        self.root, self.store = self.fx.root, self.fx.store
        body = deepcopy(self.fx.snapshot_record['body'])
        body['coverage'] = {'start': self.fx.days[0], 'end': self.fx.days[-1]}
        body['recipe'] = self.store.install_record(make_record('transformation_definition', {'kind': 'ISOLATED_TEST_PRICE_CONSTRUCTION'}))
        self.fx.snapshot_record = make_record('snapshot_manifest', body)
        self.fx.snapshot = self.store.install_record(self.fx.snapshot_record)
        from decimal import Decimal
        from data.transformations.contracts import decimal_text
        for row in self.fx.prices:
            row['value'] = decimal_text(Decimal(row['value']))
            row['original_ingested_at'] = '2024-05-01T12:00:00.000000Z'
        self.fx.feature = self.fx.build_recipe('TR_BASE_change_diff', {'k': 5})
        feature = self.fx.feature; step = feature['body']['recipe']['steps'][-1]
        variant = {'operator': step['operator'], 'parameters': step['parameters'], 'grid_policy': step['grid_policy'],
                   'mode': 'log_first', 'parameter_frequency': 'daily'}
        self.recipe = _definition(Registry(self.root), get_fx_policy(self.root), variant)
        self.store.install_record(self.recipe)
        from research.feature_applications import install_binding, PER_MEMBER
        install_binding(self.root, self.recipe, PER_MEMBER)
        self.scope = {'id': 'FX_TEST_SCOPE', 'version': '1.0.0', 'kind': 'instrument', 'members': ['EURUSD'],
            'reference': {'id': 'FX_TEST_SCOPE', 'version': '1.0.0', 'content_sha256': 'a' * 64},
            'membership_snapshot': {'id': 'SNAPSHOT_' + 'b' * 64, 'version': '1.0.0', 'content_sha256': 'c' * 64}}
        self.intent = {'feature': {'id': self.recipe['id'], 'version': '1.0.0'},
            'scope': {'id': self.scope['id'], 'version': '1.0.0'}, 'target_family': 'price_return',
            'expected_direction': 'POSITIVE'}
        self.profile = approved_profile()
        (self.root / 'config/fx_retrospective_completion.json').write_text(json.dumps({
            'return_policy': self.fx.batch, 'knowledge_cutoff': '2024-05-02'}))
        self.structural_start = inputs._structural_start
        self.patches = [patch('research.inputs._structural_start', side_effect=lambda store, snapshot: snapshot['body']['coverage']['start']),
            patch('research.inputs.load_reusable_recipe', return_value=self.recipe),
            patch('research.inputs.resolve_scope', side_effect=lambda *args: deepcopy(self.scope)),
            patch('research.inputs.list_instruments', side_effect=lambda *args: [{'instrument_id': 'EURUSD', 'price_snapshot': self.fx.snapshot}]),
            patch('research.inputs.legacy_bindings_for_recipe', side_effect=lambda *args, **kw: [
                {'instrument_id': 'EURUSD', 'feature': reference(self.fx.feature), 'source_view': self.fx.view}]),
            patch('research.inputs.legacy_recipe_projector', return_value=lambda feature: deepcopy(self.recipe)),
            patch('research.inputs._price_snapshot', side_effect=self.price),
            patch('data.targets.fx._price_snapshot', side_effect=self.price)]
        for item in self.patches: item.start()
        self.targets = materialize(self.root, self.fx.snapshot, self.fx.batch, knowledge_cutoff='2024-05-02')

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.fx.tearDown()

    def price(self, store, binding, policy, verify_rows=True):
        self.assertEqual(binding, self.fx.snapshot)
        return store.resolve(binding), deepcopy(self.fx.prices) if verify_rows else None

    def plan(self): return inputs.resolve_plan(self.root, self.intent, self.profile)
    def admit(self, plan): return {'plan_id': plan['plan_id'], 'direction': 'POSITIVE', 'admitted_horizons': [1, 7]}

    def test_pending_profiles_never_touch_registry_or_observations(self):
        self.profile['approval_state'] = 'pending'
        with patch('research.inputs.load_reusable_recipe', side_effect=AssertionError('Registry read')):
            with self.assertRaisesRegex(inputs.InputsBlocked, 'unresolved scientific'):
                self.plan()

    def test_independent_required_approval_and_ordered_date_windows(self):
        for field in inputs.APPROVALS:
            with self.subTest(field=field):
                profile = deepcopy(self.profile); profile['approvals'][field] = False
                with self.assertRaises(inputs.InputsBlocked): inputs._profile(profile)
        self.profile['periods']['P1']['end_exclusive'] = '2024-03-04'
        with self.assertRaisesRegex(inputs.InputsBlocked, 'disjoint'): self.plan()

    def test_plan_is_metadata_only_exact_five_horizons_and_immutable(self):
        with (patch('research.inputs.read_materialization', side_effect=AssertionError('Feature rows read')),
              patch('research.inputs._phase_target_rows', side_effect=AssertionError('Target rows read')),
              patch.object(Store, 'install', side_effect=AssertionError('write')),
              patch.object(Store, 'blob', side_effect=AssertionError('payload write'))):
            plan = self.plan()
        self.assertEqual(plan['mode'], 'TS'); self.assertEqual(plan['horizons'], [1, 7, 21, 63, 252])
        self.assertEqual(plan['structural_common_start'], self.fx.days[0])
        self.assertEqual(plan['members'][0]['feature'], reference(self.fx.feature))
        self.assertEqual(plan['plan_id'], inputs._plan_id(plan))
        self.assertEqual(set(plan['members'][0]['targets']), {'1', '7', '21', '63', '252'})
        with self.assertRaises(inputs.InputsBlocked):
            changed = deepcopy(plan); changed['intent']['expected_direction'] = 'NEGATIVE'; inputs._validate_plan(changed)

    def test_scope_kind_selects_cs_without_changing_recipe(self):
        single = self.plan(); self.scope['kind'] = 'universe'; universe = self.plan()
        self.assertEqual(single['recipe'], universe['recipe']); self.assertEqual(universe['mode'], 'CS')

    def test_submit_preserves_plan_with_prefetched_feature_inventory(self):
        from uuid import uuid4
        from runtime.research_jobs import ResearchJobs

        (self.root / 'config/research_execution.json').write_text(json.dumps(self.profile))
        with patch('data.fx_feature_store._price_snapshot', side_effect=self.price):
            inputs.prepare_phase(self.root, self.plan(), 'P1')
        expected = self.plan()
        self.assertTrue(expected['members'][0]['feature_materializations'])
        jobs = ResearchJobs(self.root)
        self.addCleanup(jobs.close)
        request = dict(self.intent, request_id=str(uuid4()))
        # This short synthetic input fixture has no pre-2022 observations.
        with (patch('research.contracts.profile_blockers', return_value=[]),
              patch('research.inputs.feature_manifest_routes', wraps=inputs.feature_manifest_routes) as routes):
            _, created = jobs.submit(request)
        self.assertTrue(created)
        self.assertEqual(routes.call_count, 2)
        self.assertEqual(jobs._submission(request['request_id'])['frozen_plan'], expected)

    def test_missing_member_blocks_whole_frozen_resolution_with_reason(self):
        self.scope['kind'] = 'universe'; self.scope['members'].append('AUDUSD')
        with self.assertRaises(inputs.InputsBlocked) as error: self.plan()
        self.assertEqual(error.exception.reasons[0]['instrument_id'], 'AUDUSD')
        self.assertIn('no member was silently dropped', str(error.exception))

    def test_target_ambiguous_version_requires_exact_pin_not_lexical_latest(self):
        # Two fully valid materializations at the same dependencies can differ by
        # recorded implementation; a metadata fixture isolates this decision.
        target_store = inputs.TargetStore(self.root)
        # Exercise candidate-selection behavior by duplicating the discovered
        # path while preserving the valid original record, then require exactref.
        original_glob = type(target_store.path('.')).glob
        def duplicate_glob(path, pattern):
            found = list(original_glob(path, pattern))
            return iter(found + [found[0]]) if str(path).endswith('target_store') and found else iter(found)
        with patch.object(type(target_store.path('.')), 'glob', duplicate_glob):
            with self.assertRaises(inputs.InputsBlocked) as error: self.plan()
        self.assertIn('Exactly one compatible Target', error.exception.reasons[0]['message'])

    def test_explicit_target_map_rejects_an_unknown_reference(self):
        self.profile['target_selection']['materializations'] = {'EURUSD': {'1': 'MATERIALIZATION_' + '0' * 64}}
        with self.assertRaises(inputs.InputsBlocked): self.plan()

    def test_prepare_only_selected_recipe_phase_and_idempotent_reuse(self):
        plan = self.plan(); progress = []
        first = inputs.prepare_phase(self.root, plan, 'P1', progress=progress.append)
        second = inputs.prepare_phase(self.root, plan, 'P1')
        self.assertEqual(first['prepared_id'], second['prepared_id'])
        self.assertEqual(len(list((self.root / 'storage/catalog/feature_store').glob('*/manifest.json'))), 1)
        self.assertTrue(progress); self.assertTrue(all(p['instrument'] == 'EURUSD' for p in progress))
        for ref in first['members'][0]['materializations']:
            item = inputs.read_materialization(self.root, ref['id'])
            self.assertTrue(all(r['reference_time'] < '2024-03-01' for r in item['observations']))
            self.assertEqual(item['feature']['id'], self.fx.feature['id'])

    def test_frozen_compatible_existing_output_is_reused_without_preparation(self):
        self.fx.prepare(start='2024-01-02', end='2024-02-29')
        plan = self.plan()
        with patch('research.inputs.prepare_fx_feature', side_effect=AssertionError('should reuse')):
            prepared = inputs.prepare_phase(self.root, plan, 'P1')
        self.assertEqual(len(prepared['members'][0]['materializations']), 1)

    def test_output_crossing_validation_boundary_is_not_loaded_or_reused(self):
        saved = self.fx.prepare(start='2024-02-26', end='2024-03-08')
        plan = self.plan(); real = inputs.read_materialization
        def bounded(root, identifier):
            self.assertNotEqual(identifier, saved['materialization']['id']); return real(root, identifier)
        with patch('research.inputs.read_materialization', side_effect=bounded):
            prepared = inputs.prepare_phase(self.root, plan, 'P1')
        self.assertNotIn(saved['materialization'], prepared['members'][0]['materializations'])

    def test_numerical_alignment_and_nulls_keep_endpoints_and_lineage(self):
        plan = self.plan(); prepared = inputs.prepare_phase(self.root, plan, 'P1')
        loaded = inputs.load_phase(self.root, plan, prepared, 'P1', 1)
        by_day = {r['date']: r for r in loaded['rows']}
        prices = {r['reference_time']: float(r['value']) for r in self.fx.prices}
        row = by_day[self.fx.days[10]]
        import math
        self.assertAlmostEqual(float(row['feature']), math.log(prices[self.fx.days[10]]) - math.log(prices[self.fx.days[5]]))
        self.assertAlmostEqual(float(row['target']), prices[self.fx.days[11]] / prices[self.fx.days[10]] - 1)
        self.assertEqual(row['target_end'], self.fx.days[11]); self.assertTrue(row['valid'])
        self.assertIsNone(row['available_at']); self.assertIsNone(row['target_available_at'])
        self.assertFalse(row['historical_eligibility_certified']); self.assertTrue(row['lineage']['feature_lineage'])
        self.assertFalse(by_day[self.fx.days[17]]['valid'])
        self.assertTrue(all(r['target_end'] < '2024-03-01' for r in loaded['rows']))
        self.assertGreater(loaded['coverage'][0]['exclusions']['ENDPOINT_OUTSIDE_PHASE'], 0)

    def test_p1_never_decodes_validation_label_values_even_in_same_partition(self):
        plan = self.plan(); prepared = inputs.prepare_phase(self.root, plan, 'P1')
        real = inputs.strict_json; decoded = []
        def guarded(raw):
            value = real(raw)
            if isinstance(value, dict) and value.get('record_type') == 'target_observation':
                self.assertLess(value['prediction_anchor'], '2024-03-01')
                self.assertLess(value['exit_time'], '2024-03-01')
                decoded.append(value['prediction_anchor'])
            return value
        with patch('research.inputs.strict_json', side_effect=guarded):
            inputs.load_phase(self.root, plan, prepared, 'P1', 7)
        self.assertTrue(decoded)

    def test_p2_blocks_before_read_or_write_until_exact_admission(self):
        plan = self.plan()
        with patch('research.inputs.prepare_fx_feature', side_effect=AssertionError('No preparation')):
            for admission in (None, {'plan_id': plan['plan_id'], 'direction': 'NEGATIVE', 'admitted_horizons': [1]},
                              {'plan_id': 'OTHER', 'direction': 'POSITIVE', 'admitted_horizons': [1]}):
                with self.assertRaises(inputs.InputsBlocked): inputs.prepare_phase(self.root, plan, 'P2', admission=admission)
        prepared = inputs.prepare_phase(self.root, plan, 'P2', admission=self.admit(plan))
        loaded = inputs.load_phase(self.root, plan, prepared, 'P2', 1, admission=self.admit(plan))
        self.assertTrue(loaded['rows']); self.assertTrue(all(r['date'] >= '2024-03-01' for r in loaded['rows']))
        with self.assertRaises(inputs.InputsBlocked): inputs.load_phase(self.root, plan, prepared, 'P2', 21, admission=self.admit(plan))

    def test_cancel_before_preparation_and_before_any_writes(self):
        plan = self.plan()
        with patch('research.inputs.prepare_fx_feature', side_effect=AssertionError('write')):
            with self.assertRaises(inputs.InputsCancelled): inputs.prepare_phase(self.root, plan, 'P1', cancelled=lambda: True)

    def test_long_period_chunks_preserve_every_weekday_and_boundaries(self):
        period = {'start_inclusive': '2020-01-01', 'end_exclusive': '2023-03-15'}
        days = list(inputs._period_days(period)); chunks = list(inputs._chunks(days)); restored = []
        for start, end in chunks:
            self.assertLess((date.fromisoformat(end) - date.fromisoformat(start)).days, 366)
            restored.extend(d for d in days if start <= d <= end)
        self.assertEqual(restored, days); self.assertGreater(len(chunks), 3)

    def test_overlapping_compatible_outputs_keep_one_row_and_resolved_lineage(self):
        self.fx.prepare(start='2024-01-02', end='2024-02-15')
        self.fx.prepare(start='2024-02-01', end='2024-02-29')
        plan = self.plan()
        with patch('research.inputs.prepare_fx_feature', side_effect=AssertionError('already covered')):
            prepared = inputs.prepare_phase(self.root, plan, 'P1')
        loaded = inputs.load_phase(self.root, plan, prepared, 'P1', 1)
        dates = [row['date'] for row in loaded['rows']]
        self.assertEqual(len(dates), len(set(dates)))
        self.assertEqual(len(prepared['members'][0]['materializations']), 2)

    def test_null_only_member_window_stays_explicit_without_fake_output(self):
        plan = self.plan()
        with patch('research.inputs.prepare_fx_feature', side_effect=inputs.PublicationError(
                'No valid FX Feature observations; recipe remains registered only')):
            prepared = inputs.prepare_phase(self.root, plan, 'P1')
        self.assertEqual(prepared['members'][0]['materializations'], [])
        self.assertEqual(prepared['members'][0]['unavailable'][0]['reason'], 'NO_VALID_FEATURE_OBSERVATIONS')
        loaded = inputs.load_phase(self.root, plan, prepared, 'P1', 1)
        self.assertEqual(loaded['members'], ['EURUSD'])
        self.assertTrue(loaded['rows']); self.assertTrue(all(not row['valid'] for row in loaded['rows']))

    def test_multiyear_preparation_reuses_bounded_chunks_with_continuous_warmup(self):
        from data.fx_feature_store import _dates
        self.fx.days = list(_dates('2020-01-02', '2022-04-22'))
        self.fx.prices = []
        for index, day in enumerate(self.fx.days):
            row = {'reference_time': day, 'value': str(100 + index), 'status': 'valid', 'reason_code': None,
                'available_at': None, 'original_ingested_at': '2024-05-01T12:00:00.000000Z',
                'input_dependencies': [{'original_ingested_at': '2024-05-01T12:00:00Z'}]}
            row['id'] = 'FXPRICE_' + digest(row); self.fx.prices.append(row)
        body = deepcopy(self.fx.snapshot_record['body'])
        body['coverage'] = {'start': self.fx.days[0], 'end': self.fx.days[-1]}
        self.fx.snapshot_record = make_record('snapshot_manifest', body)
        self.fx.snapshot = self.store.install_record(self.fx.snapshot_record)
        materialize(self.root, self.fx.snapshot, self.fx.batch, knowledge_cutoff='2024-05-02')
        self.profile['periods'] = {'P1': {'start_inclusive': '2020-01-02', 'end_exclusive': '2022-01-01'},
                                  'P2': {'start_inclusive': '2022-01-01', 'end_exclusive': '2022-04-23'}}
        plan = self.plan(); prepared = inputs.prepare_phase(self.root, plan, 'P1')
        refs = prepared['members'][0]['materializations']; self.assertEqual(len(refs), 2)
        loaded = inputs.load_phase(self.root, plan, prepared, 'P1', 1)
        by_date = {row['date']: row for row in loaded['rows']}
        ordered = sorted([inputs.read_materialization(self.root, item['id']) for item in refs],
                         key=lambda item: item['manifest']['input_key']['period']['start_inclusive'])
        boundary = ordered[1]['observations'][0]['reference_time']
        self.assertTrue(by_date[boundary]['valid'])  # No repeated artificial warm-up gap.
        self.assertEqual(inputs.prepare_phase(self.root, plan, 'P1')['prepared_id'], prepared['prepared_id'])

    def test_non_fx_feature_application_is_explicitly_blocked_not_guessed(self):
        self.intent['feature']['id'] = 'FEATURE_' + '1' * 64
        with self.assertRaisesRegex(inputs.InputsBlocked, 'application contract is not registered'):
            self.plan()

    def test_structural_start_uses_all_required_sources_not_feature_warmup(self):
        from types import SimpleNamespace
        body = {'coverage': {'start': '2024-01-02', 'end': '2024-04-22'},
                'upstream_snapshots': ['ISOLATED_EARLY_LEG', 'ISOLATED_LATE_LEG']}
        starts = {'ISOLATED_EARLY_LEG': '2024-01-02', 'ISOLATED_LATE_LEG': '2024-02-01'}
        store = SimpleNamespace(resolve=lambda binding: {'record_type': 'snapshot_manifest', 'body': {
            'kind': 'fx_source_snapshot', 'coverage': {'start': starts[binding], 'end': '2024-04-22'}}})
        self.assertEqual(self.structural_start(store, {'body': body}), '2024-02-01')
        body['upstream_snapshots'] = []
        with self.assertRaises(inputs.InputsBlocked): self.structural_start(store, {'body': body})

    def test_ambiguous_registry_members_and_out_of_scope_target_pins_are_blocked(self):
        for pins in ({'AUDUSD': {'1': 'unused'}}, {'EURUSD': {'2': 'unused'}}, []):
            self.profile['target_selection']['materializations'] = pins
            with self.assertRaises(inputs.InputsBlocked): self.plan()
        self.profile['target_selection']['materializations'] = {}
        item = {'instrument_id': 'EURUSD', 'price_snapshot': self.fx.snapshot}
        with patch('research.inputs.list_instruments', return_value=[item, deepcopy(item)]):
            with self.assertRaisesRegex(inputs.InputsBlocked, 'conflicting identities'): self.plan()
        self.scope['members'].append('AUDUSD')
        with self.assertRaisesRegex(inputs.InputsBlocked, 'exactly one member'): self.plan()

    def test_wrong_prepared_identity_or_member_list_cannot_load(self):
        plan = self.plan(); prepared = inputs.prepare_phase(self.root, plan, 'P1')
        prepared['members'][0]['instrument_id'] = 'AUDUSD'
        with self.assertRaises(inputs.InputsBlocked): inputs.load_phase(self.root, plan, prepared, 'P1', 1)


class LinkedResearchCoverageTests(unittest.TestCase):
    def test_research_projection_does_not_hide_verified_feature_observations(self):
        import test_feature_resolution as coverage_fixture
        from data.feature_store_contracts import make_library_entry
        fixture = coverage_fixture.FeatureScopeResolutionTests(methodName='runTest')
        fixture.setUp()
        try:
            saved = fixture.materialize()
            ref = lambda prefix: {'id': prefix + '_' + '9' * 64, 'version': '1.0.0', 'content_sha256': 'a' * 64}
            linked = make_library_entry(saved['feature'], [saved['materialization']], relationship_results=[{
                'relationship': ref('RELATIONSHIP'), 'trial_results': [ref('TRIAL')],
                'admission_results': [], 'validation_results': [], 'attempt_ids': []}])
            fixture.store.install_record(linked)
            result = fixture.resolve(scope='EURUSD')
            self.assertEqual(result['summary']['materialized_member_count'], 1)
            self.assertEqual(result['members'][0]['materializations'][0]['reference'], saved['materialization'])
        finally:
            fixture.tearDown()


if __name__ == '__main__': unittest.main()
