"""Regression checks for dated REER/WEO value features and normal input routing."""
from copy import deepcopy
from datetime import date, timedelta
import io
import math
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from data import fx_value as value
from data.feature_store import FeatureStore
from data.transformations.identity import canonical_bytes, digest, reference
from research import feature_applications as apps, inputs
from research.schedule import apply_schedule


def months(start_year, count):
    return [f'{start_year + index // 12:04d}-{index % 12 + 1:02d}-01' for index in range(count)]


class ValueCalculationTests(unittest.TestCase):
    def test_exactly_two_fixed_five_year_definitions(self):
        for family in value.FAMILIES:
            original = value.recipe(family)
            self.assertEqual(value.validate_record(original), original)
            altered = deepcopy(original)
            altered['body']['rules']['lookback'] = 12
            with self.assertRaises(ValueError):
                value.validate_record(altered)
        self.assertEqual(value.recipe('weo_bilateral')['body']['rules']['lookback'], 1260)
        self.assertEqual(value.recipe('reer_relative')['body']['rules']['lookback'], 60)

    def test_reer_uses_prior_sixty_months_in_same_vintage(self):
        rows = list(zip(months(2009, 61), range(100, 161)))
        states = value.reer_states({'2014-02-18': rows}, end_exclusive='2015-01-01')
        self.assertAlmostEqual(float(states['2014-02-18']['value']), math.log(129.5 / 160))
        rebased = value.reer_states({'2014-02-18': [(day, number * 3) for day, number in rows]},
                                    end_exclusive='2015-01-01')
        self.assertEqual(states, rebased)
        short = value.reer_states({'2014-02-18': rows[1:]}, end_exclusive='2015-01-01')
        self.assertIsNone(short['2014-02-18']['value'])
        missing = rows.copy()
        missing[10] = (missing[10][0], None)
        self.assertIsNone(value.reer_states({'2014-02-18': missing},
                                          end_exclusive='2015-01-01')['2014-02-18']['value'])

    def test_reer_future_revision_and_proxy_cannot_change_prior_states(self):
        state = {'value': '0.1', 'vintage': '2014-02-18', 'reference_time': '2014-01-01'}
        revised = dict(state, value='0.9', vintage='2014-03-17')
        base = {'2014-02-18': state, '2014-03-17': revised}
        quote = {'2014-02-18': dict(state, value='0.03')}
        prior = value.reer_pair(base, quote, end_exclusive='2014-03-01')
        self.assertEqual(prior[0]['value'], '0.07')
        self.assertEqual(prior[0]['first_anchor'], '2014-02-19')
        self.assertEqual(prior, value.reer_pair({'2014-02-18': state}, quote, end_exclusive='2014-03-01'))
        base['2014-03-17'] = dict(revised, value=None)
        full = value.reer_pair(base, quote, end_exclusive='2014-04-01')
        self.assertIsNone(full[-1]['value'])
        self.assertEqual(value.COUNTRIES['CNH'], 'CN')

    def test_original_reer_archive_identity_and_blank_padding(self):
        raw = io.BytesIO()
        with ZipFile(raw, 'w') as archive:
            archive.writestr('README.txt', 'Series ID: RBCNBIS')
            archive.writestr('vintages.csv', 'observation_date,RBCNBIS_20140218\n2014-01-01,100\n2014-02-01,\n')
        decoded = value.parse_reer_archive(raw.getvalue(), 'CNH')
        self.assertEqual(decoded['2014-02-18'], [('2014-01-01', 100), ('2014-02-01', None)])
        with self.assertRaisesRegex(ValueError, 'another currency'):
            value.parse_reer_archive(raw.getvalue(), 'EUR')

    def test_weo_first_actual_frozen_and_pair_waits_for_both_currencies(self):
        def row(currency, edition, when, rate, actual):
            return {'currency': currency, 'edition': edition, 'available_on': when, 'year': 2006,
                    'value_pct': rate, 'is_actual': actual, 'actual_evidence': 'original_IMF_cutoff'}
        rows = [row('EUR', '2007-apr', '2007-05-01', '2', 1),
                row('USD', '2007-apr', '2007-05-01', '4', 0),
                row('EUR', '2007-oct', '2007-11-01', '9', 1),
                row('USD', '2007-oct', '2007-11-01', '3', 1)]
        rows.insert(0, row('EUR', '2006-sep', '2006-10-02', '8', 1))
        self.assertEqual(value.first_actuals(rows, 'EUR', end_exclusive='2008-01-01')[2006]['value_pct'], '2')
        prices = []
        day = date(2006, 10, 2)
        while len(prices) < 1262:
            if day.weekday() < 5:
                prices.append({'reference_time': day.isoformat(), 'status': 'valid', 'value': '1'})
            day += timedelta(days=1)
        observations = value.weo_pair(prices, rows, 'EURUSD', end_exclusive='2012-01-01')
        self.assertEqual(len(observations), 2)
        self.assertEqual(observations[0]['date'], prices[1260]['reference_time'])
        self.assertEqual(observations[0]['operands']['inflation']['base']['value_pct'], '2')
        self.assertEqual(observations[0]['operands']['inflation']['quote']['value_pct'], '3')


class ValueRunnerIntegrationTests(unittest.TestCase):
    def setUp(self):
        from test_research_inputs import ResearchInputsTests
        self.fixture = ResearchInputsTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        store = FeatureStore(self.root)
        self.feature = value.recipe('reer_relative')
        store.install_record(self.feature)
        apps.install_binding(self.root, self.feature, apps.VALUE_PAIR)
        observations = [
            {'date': '2024-01-01', 'first_anchor': '2024-01-02', 'value': '0.1', 'operands': {}},
            {'date': '2024-02-01', 'first_anchor': '2024-02-02', 'value': '0.2', 'operands': {}},
            {'date': '2024-03-01', 'first_anchor': '2024-03-04', 'value': '99', 'operands': {}},
        ]
        self.rows = observations
        replay = patch.object(value, 'calculate', side_effect=lambda *args, **kwargs:
                              ([row for row in observations if row['date'] < kwargs['end_exclusive']], {}))
        replay.start()
        self.addCleanup(replay.stop)
        source = value.make_record('snapshot_manifest', {
            'kind': 'fx_value_feature_snapshot', 'family': 'reer_relative', 'pair': 'EURUSD',
            'recipe': reference(self.feature), 'price_snapshot': self.fixture.fx.snapshot,
            'capture': store.io.blob(canonical_bytes({'fixture': True}), 'json', 'test_capture'),
            'observations': store.io.blob(b''.join(canonical_bytes(row) + b'\n' for row in observations),
                                           'jsonl', 'value_observations', len(observations)),
            'row_count': len(observations), 'first_anchor': '2024-01-02',
            'coverage': {str(h): {'exclusion': None} for h in (1, 7, 21, 63)},
            'source_timing': 'dated_macro_retrospective_spot_date_labels'})
        store.install_record(source)
        path = self.root / 'storage/catalog/fx_value' / self.feature['id'] / 'EURUSD.json'
        path.parent.mkdir(parents=True)
        path.write_bytes(canonical_bytes({'snapshot': reference(source)}) + b'\n')
        self.source = value.source(self.root, self.feature, 'EURUSD')
        intent = deepcopy(self.fixture.intent)
        intent['feature'] = {key: self.feature[key] for key in ('id', 'version')}
        schedule = {'id': 'ISOLATED_SCHEDULE', 'version': '1.0.0', 'horizons': [1, 7, 21, 63],
                    'price_time_series': {'default': self.fixture.profile['periods'],
                                          '63': self.fixture.profile['periods']}}
        fixture_profile = dict(self.fixture.profile, exposure_classification={'untouched_holdout_claim': False})
        profile = apply_schedule(fixture_profile, schedule, price_time_series=True)
        self.plan = inputs.resolve_plan(self.root, intent, profile)

    def test_normal_plan_freezes_both_macro_and_original_price_inputs(self):
        self.assertEqual(self.plan['application_class'], 'fx_value_pair_ts')
        self.assertEqual(self.plan['value_source']['snapshot'], self.source['snapshot'])
        self.assertEqual(self.plan['members'][0]['price_snapshot'], self.fixture.fx.snapshot)
        self.assertEqual(self.plan['horizons'], [1, 7, 21, 63])
        inputs._validate_plan(self.plan)

    def test_p1_does_not_decode_p2_value_observations(self):
        original = value.strict_json
        def guarded(raw):
            item = original(raw)
            if 'date' in item:
                self.assertLess(item['date'], '2024-03-01')
            return item
        with patch.object(value, 'strict_json', side_effect=guarded):
            prepared = inputs.prepare_phase(self.root, self.plan, 'P1')
            sample = inputs.load_phase(self.root, self.plan, prepared, 'P1', 1)
        self.assertTrue(sample['rows'])
        self.assertTrue(all(row['feature'] != '99' for row in sample['rows']))
        self.assertEqual(sample['rows'][0]['feature'], '0.1')

    def test_monthly_update_is_available_only_after_release_date(self):
        prepared = inputs.prepare_phase(self.root, self.plan, 'P1')
        sample = inputs.load_phase(self.root, self.plan, prepared, 'P1', 1)
        rows = {row['date']: row for row in sample['rows']}
        self.assertEqual(rows['2024-02-01']['feature'], '0.1')
        self.assertEqual(rows['2024-02-02']['feature'], '0.2')
        self.assertTrue(all(not row['historical_eligibility_certified'] for row in sample['rows']))


if __name__ == '__main__':
    unittest.main()
