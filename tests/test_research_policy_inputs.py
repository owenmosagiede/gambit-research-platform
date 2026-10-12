"""Synthetic-only v2 policy source pins, derived periods and selector isolation."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import test_research_inputs as base_fixture
from data.alfred_onboarding import Store
from data.fx_feature_recipes import build_fx_feature, get_fx_policy
from data.fx_records import make_record
from data.targets.fx import materialize
from data.transformations.identity import reference
from data.transformations.registry import Registry
from research import inputs
from research.contracts import canonical, ref, load_profile, ResearchError


def scheduled_profile(profile):
    profile = deepcopy(profile)
    profile.update(version='2.0.0', discovery_start_rule='scope_structural_start_v1')
    profile['periods']['P1']['start_inclusive'] = None
    profile['kernel'].update(kernel_policy='scheduled_weekday_hac_v2', missing_evidence='unresolved_required_v1')
    return profile


class ResearchPolicyInputsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = base_fixture.ResearchInputsTests(methodName='runTest')
        self.fixture.setUp(); self.addCleanup(self.fixture.tearDown)
        f = self.fixture
        self.root, self.store = f.root, f.store
        self.profile = scheduled_profile(f.profile)
        self.intent = deepcopy(f.intent)
        self.scope = deepcopy(f.scope)
        self.snapshots = {'EURUSD': f.fx.snapshot}
        self.bindings = [{'instrument_id': 'EURUSD', 'feature': reference(f.fx.feature), 'source_view': f.fx.view}]
        meta = dict(f.fx.meta, base_currency='GBP', quote_currency='USD', unit='USD_per_GBP')
        dataset = self.store.install_record(make_record('dataset_definition', {
            'kind': 'fx_constructed_dataset', 'profile': 'fx_price.1.0.0', 'instrument_id': 'GBPUSD',
            'source_metadata': meta}))
        view = self.store.install_record(make_record('source_view_definition', {
            'kind': 'fx_constructed_view', 'profile': 'fx_price.1.0.0', 'dataset': dataset, 'source_metadata': meta}))
        body = deepcopy(f.fx.snapshot_record['body'])
        body.update(instrument_id='GBPUSD', economic_id='FX_GBP_USD', definition=view, source_metadata=meta,
                    coverage={'start': f.fx.days[4], 'end': f.fx.days[-1]})
        self.snapshots['GBPUSD'] = self.store.install_record(make_record('snapshot_manifest', body))
        step = f.fx.feature['body']['recipe']['steps'][-1]
        variant = {'operator': step['operator'], 'parameters': step['parameters'], 'grid_policy': step['grid_policy'],
                   'mode': 'log_first', 'parameter_frequency': 'daily'}
        feature = build_fx_feature(self.root, {'instrument_id': 'GBPUSD', 'price_snapshot': self.snapshots['GBPUSD']},
                                  variant, registry=Registry(self.root), evaluation_policy=get_fx_policy(self.root))
        self.store.install_record(feature)
        self.bindings.append({'instrument_id': 'GBPUSD', 'feature': reference(feature), 'source_view': view})
        self.current = [{'instrument_id': symbol, 'price_snapshot': binding} for symbol, binding in self.snapshots.items()]
        self.price_calls = []
        for replacement in (
            patch('research.inputs.resolve_scope', side_effect=lambda *args: deepcopy(self.scope)),
            patch('research.inputs.list_instruments', side_effect=lambda *args: deepcopy(self.current)),
            patch('research.inputs.legacy_bindings_for_recipe', side_effect=lambda *args, **kw: deepcopy(self.bindings)),
            patch('research.inputs._price_snapshot', side_effect=self.price),
            patch('data.targets.fx._price_snapshot', side_effect=self.price),
        ):
            replacement.start(); self.addCleanup(replacement.stop)
        materialize(self.root, self.snapshots['GBPUSD'], f.fx.batch, knowledge_cutoff='2024-05-02')
        targets = {symbol: {} for symbol in self.snapshots}
        for path in (self.root / 'storage/catalog/target_store').glob('*/manifest.json'):
            manifest = json.loads(path.read_bytes())
            definition = inputs.TargetStore(self.root).resolve(manifest['definition'])
            symbol = self.store.resolve(manifest['price_snapshot'])['body']['instrument_id']
            targets[symbol][str(definition['body']['horizon']['amount'])] = reference(manifest)
        self.profile['target_selection'].update(selection_scope='registered_fx_registry',
            source_snapshots=deepcopy(self.snapshots), materializations=targets)
        self.price_calls.clear()

    def price(self, store, binding, policy, verify_rows=True):
        self.price_calls.append((deepcopy(binding), verify_rows))
        snapshot = store.resolve(binding)
        prices = [r for r in self.fixture.fx.prices if r['reference_time'] >= snapshot['body']['coverage']['start']]
        return snapshot, deepcopy(prices) if verify_rows else None

    def plan(self):
        return inputs.resolve_plan(self.root, self.intent, self.profile)

    def test_same_profile_resolves_individual_and_universe_without_any_execution(self):
        original = deepcopy(self.profile)
        with (patch('research.inputs.prepare_fx_feature', side_effect=AssertionError('preparation on selection')),
              patch('research.inputs.read_materialization', side_effect=AssertionError('observation read on selection')),
              patch('research.inputs._phase_target_rows', side_effect=AssertionError('Target read on selection')),
              patch.object(Store, 'install', side_effect=AssertionError('write on selection'))):
            single = self.plan()
            self.scope.update(kind='universe', members=['EURUSD', 'GBPUSD'])
            universe = self.plan()
        self.assertEqual(single['mode'], 'TS'); self.assertEqual(universe['mode'], 'CS')
        self.assertEqual(single['recipe'], universe['recipe']); self.assertEqual(self.profile, original)
        self.assertEqual(single['periods']['P1']['start_inclusive'], self.fixture.fx.days[0])
        self.assertEqual(universe['periods']['P1']['start_inclusive'], self.fixture.fx.days[4])
        self.assertIsNone(universe['profile']['periods']['P1']['start_inclusive'])
        self.assertEqual([m['instrument_id'] for m in single['members']], ['EURUSD'])
        self.assertEqual([m['instrument_id'] for m in universe['members']], ['EURUSD', 'GBPUSD'])
        self.assertTrue(all(not verify for _, verify in self.price_calls))
        inputs._validate_plan(single); inputs._validate_plan(universe)

    def test_stale_display_snapshot_cannot_override_explicit_completed_source(self):
        body = deepcopy(self.fixture.fx.snapshot_record['body']); body['fixture_display_generation'] = 'different'
        stale = self.store.install_record(make_record('snapshot_manifest', body))
        self.current[0]['price_snapshot'] = stale
        plan = self.plan()
        self.assertEqual(plan['members'][0]['price_snapshot'], self.snapshots['EURUSD'])
        self.assertNotEqual(plan['members'][0]['price_snapshot'], stale)
        self.assertEqual([binding for binding, _ in self.price_calls], [self.snapshots['EURUSD']])

    def test_automatic_start_is_frozen_and_rehashed_period_tampering_is_rejected(self):
        plan = self.plan()
        changed = deepcopy(plan); changed['periods']['P1']['start_inclusive'] = self.fixture.fx.days[1]
        changed['plan_id'] = inputs._plan_id(changed)
        with self.assertRaises(inputs.InputsBlocked): inputs._validate_plan(changed)
        # A later catalog/source projection cannot redefine the already frozen plan.
        self.current[0]['price_snapshot'] = self.snapshots['GBPUSD']
        inputs._validate_plan(plan)
        self.assertEqual(plan['members'][0]['price_snapshot'], self.snapshots['EURUSD'])

    def test_rehashed_structural_common_start_tampering_is_rejected(self):
        plan = self.plan(); plan['structural_common_start'] = self.fixture.fx.days[1]
        plan['plan_id'] = inputs._plan_id(plan)
        with self.assertRaises(inputs.InputsBlocked): inputs._validate_plan(plan)

    def test_registry_pin_map_rejects_unknown_member(self):
        selection = self.profile['target_selection']
        selection['source_snapshots']['UNKNOWN'] = self.snapshots['EURUSD']
        selection['materializations']['UNKNOWN'] = deepcopy(selection['materializations']['EURUSD'])
        with self.assertRaises(inputs.InputsBlocked): self.plan()

    def test_registry_pin_map_requires_all_five_horizons_even_for_unselected_members(self):
        for symbol in ('EURUSD', 'GBPUSD'):
            with self.subTest(symbol=symbol):
                original = self.profile['target_selection']['materializations'][symbol].pop('252')
                try:
                    with self.assertRaises(inputs.InputsBlocked): self.plan()
                finally:
                    self.profile['target_selection']['materializations'][symbol]['252'] = original

    def test_registry_pin_map_requires_matching_source_and_target_member_sets(self):
        del self.profile['target_selection']['source_snapshots']['GBPUSD']
        with self.assertRaises(inputs.InputsBlocked): self.plan()

    def test_registry_pin_map_rejects_non_exact_unselected_references(self):
        pins = self.profile['target_selection']['materializations']['GBPUSD']
        pins['1'] = pins['1']['id']
        with self.assertRaises(inputs.InputsBlocked): self.plan()

    def test_target_pin_cannot_be_relabelled_as_another_horizon(self):
        pins = self.profile['target_selection']['materializations']['EURUSD']
        pins['1'] = pins['7']
        with self.assertRaises(inputs.InputsBlocked): self.plan()

    def test_source_pin_cannot_be_relabelled_as_another_instrument(self):
        self.profile['target_selection']['source_snapshots']['EURUSD'] = self.snapshots['GBPUSD']
        with self.assertRaises(inputs.InputsBlocked) as error: self.plan()
        self.assertEqual(error.exception.reasons[0]['instrument_id'], 'EURUSD')

    def test_automatic_start_cannot_be_enabled_under_old_kernel_policy(self):
        self.profile['kernel'].update(kernel_policy='retained_legacy_v1', missing_evidence='legacy_failed_v1')
        with self.assertRaises(inputs.InputsBlocked): self.plan()

    def test_scope_without_structural_discovery_history_is_blocked(self):
        with patch('research.inputs._structural_start', return_value=self.profile['periods']['P1']['end_exclusive']):
            with self.assertRaisesRegex(inputs.InputsBlocked, 'no structural history'): self.plan()

    def test_immutable_profile_reference_is_loaded_and_content_change_rejected(self):
        profile = deepcopy(self.profile)
        path = self.root / 'definitions/research_specs' / profile['id'] / (profile['version'] + '.json')
        path.parent.mkdir(parents=True); path.write_bytes(canonical(profile) + b'\n')
        (self.root / 'config/research_execution.json').write_bytes(canonical({'research_spec': ref(profile)}) + b'\n')
        self.assertEqual(load_profile(self.root), profile)
        changed = deepcopy(profile); changed['kernel']['missing_evidence'] = 'legacy_failed_v1'
        path.write_bytes(canonical(changed) + b'\n')
        with self.assertRaises(ResearchError): load_profile(self.root)


if __name__ == '__main__': unittest.main()
