"""Five fixed pair-level benchmark carry hypotheses, retrospective date labels.

Rate reference dates are not asserted to be historical publication dates. Scores
use only reference-date prefixes; future financing is never a feature operand.
"""
from bisect import bisect_left
from collections import deque
from datetime import date, timedelta
from decimal import Decimal
import math
from statistics import fmean, stdev

from data.feature_store import FeatureStore
from data.fx_value import next_weekday, eligibility
from data.transformations.contracts import normalize_reference, decimal_text
from data.transformations.identity import canonical_bytes, digest, reference
from research.store import inside, read_json, install_bytes

SCHEMA = '0.12.0'
FAMILIES = ('level', 'risk_63', 'change_63', 'relative_1260', 'real_actual')
CURRENCIES = frozenset('AUD CAD CHF EUR GBP JPY NOK NZD SEK USD'.split())
NAMES = dict(zip(FAMILIES, ('Nominal carry level', 'Carry relative to FX risk · 63 weekdays',
    'Change in carry · 63 weekdays', 'Carry relative to its own history · 1260 weekdays',
    'Inflation-adjusted carry · published actuals')))
RULES = {
    'level': {'formula': 'base_benchmark_rate_pct_minus_quote_benchmark_rate_pct', 'unit': 'percentage_points_per_annum'},
    'risk_63': {'formula': 'differential_fraction_divided_by_annualized_prior_spot_log_return_stdev',
        'lookback': 63, 'ddof': 1, 'annualization': 252, 'exclude_current_close': True, 'unit': 'dimensionless'},
    'change_63': {'formula': 'current_differential_minus_differential_63_scheduled_weekdays_ago',
        'lookback': 63, 'unit': 'percentage_points'},
    'relative_1260': {'formula': 'current_minus_prior_mean_divided_by_prior_sample_stdev',
        'lookback': 1260, 'ddof': 1, 'exclude_current': True, 'unit': 'standard_deviations'},
    'real_actual': {'formula': 'nominal_differential_minus_first_published_actual_annual_inflation_differential',
        'year_selection': 'latest_common_actual_reference_year_available_at_cutoff',
        'inflation': 'existing_WEO_first_actual_frozen', 'unit': 'percentage_points_per_annum'},
}


def record(kind, body, name=None):
    if kind not in ('feature_recipe_definition', 'snapshot_manifest'):
        raise ValueError('Unsupported carry record kind')
    value = {'schema_version': SCHEMA, 'record_type': kind, 'version': '1.0.0', 'body': body}
    value['id'] = ('FEATURE_RECIPE_' if kind == 'feature_recipe_definition' else 'SNAPSHOT_') + digest(value)
    if name is not None: value['display_name'] = name
    return value


def recipe(family):
    if family not in FAMILIES: raise ValueError('Unknown fixed carry recipe')
    return record('feature_recipe_definition', {'kind': 'fx_carry_recipe_v1', 'family': family,
        'rules': RULES[family], 'input_contract': 'pinned_benchmark_rates_pair_spot_and_dated_actual_inflation',
        'scope': 'individual_pair_TS', 'orientation': 'long_base_short_quote',
        'rate_clock': 'retrospective_reference_date_assumed_usable_next_scheduled_weekday',
        'rate_state': 'latest_observation_preserve_unknown_nulls_carry_nonexistent_days_max_7_calendar_days',
        'price_clock': 'retrospective_reference_date', 'horizons': [1, 7, 21, 63],
        'historical_pit_certified': False, 'live_certified': False}, NAMES[family])


def validate_record(value):
    if value.get('schema_version') != SCHEMA or record(value['record_type'], value['body'], value.get('display_name')) != value:
        raise ValueError('Carry record identity differs')
    body = value['body']
    if value['record_type'] == 'feature_recipe_definition':
        if value != recipe(body.get('family')): raise ValueError('Carry recipe differs from fixed definition')
    else:
        fields = {'kind', 'family', 'pair', 'recipe', 'price_snapshot', 'funding_snapshot', 'inflation_capture',
                  'observations', 'row_count', 'first_anchor', 'coverage', 'source_timing'}
        if set(body) != fields or body['kind'] != 'fx_carry_feature_snapshot_v1':
            raise ValueError('Invalid carry snapshot fields')
        pair = body['pair']
        if len(pair) != 6 or pair[:3] not in CURRENCIES or pair[3:] not in CURRENCIES or pair[:3] == pair[3:]:
            raise ValueError('Unsupported carry pair')
        if body['family'] not in FAMILIES or body['recipe'] != reference(recipe(body['family'])):
            raise ValueError('Carry snapshot recipe differs')
        for key in ('recipe', 'price_snapshot', 'funding_snapshot'): normalize_reference(body[key])
        for key in ('observations', 'inflation_capture'):
            member = body[key]
            if member is None and key == 'inflation_capture' and body['family'] != 'real_actual': continue
            if not isinstance(member, dict) or set(member) != {'blob_sha256', 'format', 'byte_count', 'row_count', 'role'}:
                raise ValueError('Carry requires exact payload bindings')
        if body['family'] != 'real_actual' and body['inflation_capture'] is not None:
            raise ValueError('Only real carry consumes inflation')
        if body['row_count'] <= 0 or body['source_timing'] != 'retrospective_rate_and_spot_date_labels_not_PIT':
            raise ValueError('Invalid carry output or timing claim')
        if set(body['coverage']) != {'1', '7', '21', '63'}: raise ValueError('Incomplete carry horizon coverage')
    return value


def _days(start, end_exclusive):
    day = date.fromisoformat(start)
    while day.isoformat() < end_exclusive:
        if day.weekday() < 5: yield day.isoformat()
        day += timedelta(days=1)


def scores(prices, rates, pair, family, inflation=None, *, end_exclusive='2025-01-01'):
    """Pure causal-prefix calculation, also used for independent phase replay."""
    if family not in FAMILIES or pair[:3] not in CURRENCIES or pair[3:] not in CURRENCIES:
        raise ValueError('Unsupported carry calculation')
    from data.targets.fx_total import Rates
    # This class supplies the explicit missing/nonexistent-day and seven-day
    # reference-state rules. Its future accrual/factor method is never called.
    states = Rates({c: [r for r in rates[c] if r['date'] < end_exclusive] for c in (pair[:3], pair[3:])})
    price_map = {r['reference_time']: r for r in prices if r['reference_time'] < end_exclusive}
    if not price_map: return []
    price_start = min(price_map)
    start = max(rates[c][0]['date'] for c in (pair[:3], pair[3:]))
    inflation_years = {}
    if family == 'real_actual':
        from data.fx_value import first_actuals
        actuals = [first_actuals(inflation or [], c, end_exclusive=end_exclusive) for c in (pair[:3], pair[3:])]
        inflation_years = {y: (actuals[0][y], actuals[1][y]) for y in actuals[0].keys() & actuals[1].keys()}
    rate_history = deque(maxlen=1260)
    returns = deque(maxlen=63)
    previous_price = None
    output = []
    for day in _days(start, end_exclusive):
        base = states.accrual[pair[:3]].get(day)
        quote = states.accrual[pair[3:]].get(day)
        differential = (float(Decimal(base['rate_pct']) - Decimal(quote['rate_pct'])) if base and quote else None)
        operands = {'base_rate': ({k: base[k] for k in ('date', 'rate_pct', 'source_row_sha256')} if base else None),
                    'quote_rate': ({k: quote[k] for k in ('date', 'rate_pct', 'source_row_sha256')} if quote else None)}
        number = None
        reason = 'RATE_STATE_UNAVAILABLE' if differential is None else None
        if differential is not None and day >= price_start:
            if family == 'level': number = differential
            elif family == 'change_63':
                old = list(rate_history)[-63] if len(rate_history) >= 63 else None
                if old is not None: number = differential - old
                else: reason = 'RATE_LOOKBACK_UNAVAILABLE'
                operands['lookback_differential'] = old
            elif family == 'relative_1260':
                if len(rate_history) == 1260 and all(x is not None for x in rate_history):
                    sd = stdev(rate_history)
                    if sd > 0: number = (differential - fmean(rate_history)) / sd
                    else: reason = 'ZERO_RATE_VARIANCE'
                else: reason = 'RATE_LOOKBACK_UNAVAILABLE'
                operands['lookback_count'] = len(rate_history)
            elif family == 'risk_63':
                if len(returns) == 63 and all(x is not None for x in returns):
                    vol = stdev(returns) * math.sqrt(252)
                    if vol > 0: number = (differential / 100) / vol
                    else: reason = 'ZERO_SPOT_VOLATILITY'
                else: reason = 'SPOT_LOOKBACK_UNAVAILABLE'
                operands['prior_return_count'] = len(returns)
            else:
                eligible = [y for y, observations in inflation_years.items()
                            if all(r['available_on'] <= day for r in observations)]
                if eligible:
                    year = max(eligible); b, q = inflation_years[year]
                    number = differential - float(Decimal(b['value_pct']) - Decimal(q['value_pct']))
                    operands['inflation'] = {'reference_year': year, 'base': b, 'quote': q}
                else: reason = 'PUBLISHED_COMMON_ACTUAL_INFLATION_UNAVAILABLE'
        if number is not None and not math.isfinite(number): raise ValueError('Nonfinite carry score')
        if day >= price_start:
            output.append({'date': day, 'first_anchor': next_weekday(day),
                'value': decimal_text(Decimal(str(number))) if number is not None else None,
                'reason': reason, 'operands': operands})
        # Current close and current differential enter only tomorrow's baseline.
        rate_history.append(differential)
        row = price_map.get(day)
        current_price = float(row['value']) if row and row['status'] == 'valid' else None
        returns.append(math.log(current_price / previous_price) if current_price and previous_price else None)
        previous_price = current_price
    return output


def calculate(root, family, pair, price_snapshot, funding_snapshot, inflation_capture=None, *, end_exclusive='2025-01-01'):
    from data.targets.fx import _approved_policy, _price_snapshot
    from data.fx_funding import load as funding_load
    store = FeatureStore(root)
    config = read_json(inside(root, 'config/fx_retrospective_completion.json'))
    batch = _approved_policy(store, config['return_policy'])
    snapshot, prices = _price_snapshot(store, price_snapshot, batch)
    if snapshot['body']['instrument_id'] != pair: raise ValueError('Carry prices belong to another pair')
    from data.verified_inputs import memo
    def rate_prefix():
        _, all_rates = funding_load(root, funding_snapshot)
        return {c: [r for r in all_rates[c] if r['date'] < end_exclusive] for c in (pair[:3], pair[3:])}
    rates = memo(root, 'fx_carry_rate_prefix', {'funding': funding_snapshot, 'pair': pair, 'end': end_exclusive}, rate_prefix)
    inflation = None
    if family == 'real_actual':
        from data.fx_value import macro_inputs
        inflation = macro_inputs(store, inflation_capture, 'weo_bilateral', end_exclusive=end_exclusive)
    observations = scores(prices, rates, pair, family, inflation, end_exclusive=end_exclusive)
    # All carry recipes emit a complete weekday grid: use the exact-anchor
    # daily eligibility rule, never reactivate a stale last valid score.
    return observations, eligibility(prices, observations, 'weo_bilateral')


def publish(root, family, pair, price_snapshot, funding_snapshot, inflation_capture=None):
    store = FeatureStore(root); definition = recipe(family)
    observations, coverage = calculate(root, family, pair, price_snapshot, funding_snapshot, inflation_capture)
    valid = [r for r in observations if r['value'] is not None]
    if not valid: raise ValueError('Carry feature has no valid history')
    payload = b''.join(canonical_bytes(row) + b'\n' for row in observations)
    with store.writer():
        store.install_record(definition)
        snapshot = record('snapshot_manifest', {'kind': 'fx_carry_feature_snapshot_v1', 'family': family,
            'pair': pair, 'recipe': reference(definition), 'price_snapshot': price_snapshot,
            'funding_snapshot': funding_snapshot, 'inflation_capture': inflation_capture,
            'observations': store.io.blob(payload, 'jsonl', 'carry_observations', len(observations)),
            'row_count': len(observations), 'first_anchor': valid[0]['first_anchor'], 'coverage': coverage,
            'source_timing': 'retrospective_rate_and_spot_date_labels_not_PIT'})
        store.install_record(snapshot); store.verify_closure([snapshot])
        from research.feature_applications import install_binding, CARRY_PAIR
        install_binding(root, definition, CARRY_PAIR)
        install_bytes(inside(root, 'storage/catalog/fx_carry/' + definition['id'] + '/' + pair + '.json'),
                      canonical_bytes({'snapshot': reference(snapshot)}) + b'\n')
    return snapshot


def source(root, feature, pair):
    store = FeatureStore(root); validate_record(feature)
    binding = read_json(inside(root, 'storage/catalog/fx_carry/' + feature['id'] + '/' + pair + '.json'))
    snapshot = store.resolve(binding['snapshot']); validate_record(snapshot); body = snapshot['body']
    if body['recipe'] != reference(feature) or body['pair'] != pair:
        raise ValueError('Carry source differs from selected recipe or pair')
    from data.fx_funding import validate_record as validate_funding
    validate_funding(store.resolve(body['funding_snapshot']))
    store.verify_closure([snapshot])
    return {'snapshot': binding['snapshot'], **body}


def phase_observations(root, source, period):
    from data.verified_inputs import memo
    return memo(root, 'fx_carry_phase', {'source': source['snapshot'], 'period': period},
                lambda: _phase_observations(root, source, period))


def _phase_observations(root, source, period):
    from data.alfred_onboarding import strict_json
    store = FeatureStore(root); snapshot = store.resolve(source['snapshot'])
    if snapshot['body'] != {k: v for k, v in source.items() if k != 'snapshot'}:
        raise ValueError('Frozen carry source differs')
    selected = []; previous = None; lines = store.payload(source['observations']).splitlines()
    if len(lines) != source['row_count']: raise ValueError('Carry row count differs')
    for line in lines:
        marker = b'"date":"'; offset = line.index(marker) + len(marker); day = line[offset:offset+10].decode('ascii')
        if day < period['start_inclusive']: previous = line
        elif day < period['end_exclusive']: selected.append(line)
    if previous is not None: selected.insert(0, previous)
    saved = [strict_json(line) for line in selected]
    if any(canonical_bytes(row) != line or row['first_anchor'] != next_weekday(row['date']) for row, line in zip(saved, selected)):
        raise ValueError('Invalid stored carry row')
    expected, _ = calculate(root, source['family'], source['pair'], source['price_snapshot'],
        source['funding_snapshot'], source['inflation_capture'], end_exclusive=period['end_exclusive'])
    before = [r for r in expected if r['date'] < period['start_inclusive']]
    expected = before[-1:] + [r for r in expected if r['date'] >= period['start_inclusive']]
    if saved != expected: raise ValueError('Carry observations differ from independent source replay')
    return saved
