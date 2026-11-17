"""Two fixed five-year FX value calculations with dated, immutable inputs.

REER uses one internally consistent archived vintage for its entire monthly
lookback. WEO freezes the first completed-year actual and advances each pair
only when both currencies' observations are available.
"""
from bisect import bisect_left
from collections import deque
from datetime import date, timedelta
from decimal import Decimal
import csv
import io
import math
from statistics import median
from zipfile import ZipFile

from data.alfred_onboarding import strict_json
from data.feature_store import FeatureStore
from data.transformations.contracts import decimal_text
from data.transformations.identity import canonical_bytes, digest, reference
from research.store import inside, install_bytes, read_json


SCHEMA = '0.9.0'
FAMILIES = ('weo_bilateral', 'reer_relative')
COUNTRIES = dict(zip(
    'AUD CAD CHF CNH CZK EUR GBP HKD HUF ILS JPY MXN NOK NZD PLN SEK SGD USD ZAR'.split(),
    'AU CA CH CN CZ XM GB HK HU IL JP MX NO NZ PL SE SG US ZA'.split()))
RULES = {
    'weo_bilateral': {'lookback': 1260, 'unit': 'valid_scheduled_weekday_closes',
        'formula': 'log_prior_median_real_exchange_rate_over_current',
        'inflation': 'first_completed_year_actual_frozen', 'base_year': 2005,
        'first_close': '2006-10-02', 'year_update': 'both_currency_actuals_available'},
    'reer_relative': {'lookback': 60, 'unit': 'consecutive_calendar_months',
        'formula': 'base_log_prior_median_over_latest_minus_quote_log_prior_median_over_latest',
        'history': 'one_complete_archived_vintage_per_currency',
        'vintage': 'latest_available_per_currency', 'CNH_proxy': 'RBCNBIS'},
}


def next_weekday(day):
    value = date.fromisoformat(day) + timedelta(days=1)
    while value.weekday() >= 5:
        value += timedelta(days=1)
    return value.isoformat()


def make_record(kind, body, display_name=None):
    prefixes = {'feature_recipe_definition': 'FEATURE_RECIPE_', 'snapshot_manifest': 'SNAPSHOT_'}
    if kind not in prefixes:
        raise ValueError('Unknown FX value record kind')
    record = {'schema_version': SCHEMA, 'record_type': kind, 'version': '1.0.0', 'body': body}
    record['id'] = prefixes[kind] + digest(record)
    if display_name is not None:
        record['display_name'] = display_name
    return record


def recipe(family):
    if family not in FAMILIES:
        raise ValueError('Unknown five-year value family')
    return make_record('feature_recipe_definition', {
        'kind': 'fx_value_five_year_recipe', 'family': family, 'rules': RULES[family],
        'input_contract': 'dated_macro_and_pinned_pair_spot_v1',
        'scope': 'individual_pair_TS', 'unit': 'log_ratio',
        'availability': 'strictly_after_date_only_source_and_close',
        'missing': 'preserve_invalid_new_state', 'horizons': [1, 7, 21, 63],
    }, 'Five-year ' + ('WEO bilateral value' if family == 'weo_bilateral' else 'relative REER value'))


def validate_record(record):
    if record.get('schema_version') != SCHEMA:
        raise ValueError('Unsupported FX value schema')
    kind, body = record['record_type'], record['body']
    if make_record(kind, body, record.get('display_name')) != record:
        raise ValueError('FX value record identity differs')
    if kind == 'feature_recipe_definition':
        if record != recipe(body.get('family')):
            raise ValueError('FX value recipe differs from its fixed five-year definition')
    else:
        required = {'kind', 'family', 'pair', 'recipe', 'price_snapshot', 'capture',
                    'observations', 'row_count', 'first_anchor', 'coverage', 'source_timing'}
        if set(body) != required or body['kind'] != 'fx_value_feature_snapshot':
            raise ValueError('Invalid FX value snapshot fields')
        if body['family'] not in FAMILIES or body['recipe'] != reference(recipe(body['family'])):
            raise ValueError('FX value snapshot recipe differs')
        pair = body['pair']
        if len(pair) != 6 or pair[:3] not in COUNTRIES or pair[3:] not in COUNTRIES or pair[:3] == pair[3:]:
            raise ValueError('Invalid FX value currency pair')
        for name in ('observations', 'capture'):
            member = body[name]
            if set(member) != {'blob_sha256', 'format', 'byte_count', 'row_count', 'role'}:
                raise ValueError('Missing exact value input payload binding')
        if body['row_count'] <= 0 or body['source_timing'] != 'dated_macro_retrospective_spot_date_labels':
            raise ValueError('Unsupported value source clock')
    return record


def parse_reer_archive(raw, currency, *, end_exclusive='9999-12-31'):
    """Verify and decode full original ALFRED snapshots, retaining missing cells."""
    series = 'RB' + COUNTRIES[currency] + 'BIS'
    with ZipFile(io.BytesIO(raw)) as archive:
        if archive.testzip() is not None:
            raise ValueError('ALFRED archive checksum failed')
        if ('Series ID: ' + series) not in archive.read('README.txt').decode():
            raise ValueError('REER archive belongs to another currency')
        names = [name for name in archive.namelist() if name.endswith('.csv')]
        if len(names) != 1:
            raise ValueError('Expected one full-vintage REER table')
        reader = csv.DictReader(io.StringIO(archive.read(names[0]).decode('utf-8-sig')))
        if not reader.fieldnames or reader.fieldnames[0] != 'observation_date':
            raise ValueError('Unexpected REER reference-date column')
        columns = reader.fieldnames[1:]
        vintages = {}
        for column in columns:
            if not column.startswith(series + '_') or len(column) != len(series) + 9:
                raise ValueError('REER vintage column identity differs')
            label = column[-8:]
            when = date(int(label[:4]), int(label[4:6]), int(label[6:])).isoformat()
            if when in vintages:
                raise ValueError('Duplicate REER vintage')
            vintages[when] = []
        periods = set()
        for row in reader:
            period = row['observation_date']
            if date.fromisoformat(period).day != 1 or period in periods:
                raise ValueError('Duplicate or invalid REER reference month')
            periods.add(period)
            for column, (when, values) in zip(columns, vintages.items()):
                if when >= end_exclusive:
                    continue
                text = row[column]
                value = None if text in ('.', '') else float(Decimal(text))
                if value is not None and (not math.isfinite(value) or value <= 0 or period > when):
                    raise ValueError('Invalid REER observation or reference after vintage')
                values.append((period, value))
    return vintages


def reer_states(vintages, *, end_exclusive):
    states = {}
    for when, observations in sorted(vintages.items()):
        if when >= end_exclusive:
            continue
        # Future reference-month nulls are table padding, not published updates.
        past = [(period, value) for period, value in observations if period <= when]
        published = [index for index, (_, value) in enumerate(past) if value is not None]
        score = None
        if published:
            selected = sorted(past[:published[-1] + 1])[-61:]
            months = [date.fromisoformat(period).year * 12 + date.fromisoformat(period).month
                      for period, _ in selected]
            if (len(selected) == 61 and all(value is not None for _, value in selected)
                    and months == list(range(months[0], months[0] + 61))):
                score = decimal_text(Decimal(str(math.log(median(value for _, value in selected[:-1]) / selected[-1][1]))))
        states[when] = {'value': score, 'vintage': when,
                        'reference_time': past[published[-1]][0] if published else None}
    return states


def reer_pair(base_states, quote_states, *, end_exclusive):
    result = []
    base, quote = None, None
    for when in sorted(set(base_states) | set(quote_states)):
        if when >= end_exclusive:
            break
        base = base_states.get(when, base)
        quote = quote_states.get(when, quote)
        if base is None or quote is None:
            continue
        value = (None if base['value'] is None or quote['value'] is None
                 else decimal_text(Decimal(base['value']) - Decimal(quote['value'])))
        result.append({'date': when, 'first_anchor': next_weekday(when), 'value': value,
                       'operands': {'base': base, 'quote': quote}})
    return result


def first_actuals(rows, currency, *, end_exclusive):
    found = {}
    keys = set()
    for row in sorted(rows, key=lambda item: (item['available_on'], item['edition'])):
        if row['currency'] != currency or row['available_on'] >= end_exclusive:
            continue
        key = (row['edition'], row['year'])
        if key in keys:
            raise ValueError('Duplicate IMF inflation vintage')
        keys.add(key)
        when = date.fromisoformat(row['available_on'])
        number = Decimal(row['value_pct'])
        if not number.is_finite() or number <= -100:
            raise ValueError('Invalid IMF inflation rate')
        if row['is_actual'] == 1:
            if row['year'] >= when.year:
                continue
            if not row['actual_evidence']:
                raise ValueError('WEO actual lacks completed-year evidence')
            found.setdefault(row['year'], row)
    return found


def weo_pair(prices, rows, pair, *, end_exclusive):
    first = [first_actuals(rows, currency, end_exclusive=end_exclusive) for currency in (pair[:3], pair[3:])]
    updates = []
    ratio = Decimal(1)
    year = 2006
    while all(year in item for item in first):
        base, quote = (item[year] for item in first)
        ratio *= (1 + Decimal(base['value_pct']) / 100) / (1 + Decimal(quote['value_pct']) / 100)
        updates.append((max(base['available_on'], quote['available_on']), year, float(ratio),
                        {'base': base, 'quote': quote}))
        year += 1
    history = deque(maxlen=1260)
    ratio, cursor, operands = 1.0, 0, {'base_year': 2005}
    result = []
    for row in sorted(prices, key=lambda item: item['reference_time']):
        when = row['reference_time']
        if when < '2006-10-02' or when >= end_exclusive or date.fromisoformat(when).weekday() >= 5:
            continue
        if row['status'] != 'valid':
            continue
        while cursor < len(updates) and updates[cursor][0] <= when:
            _, _, ratio, operands = updates[cursor]
            cursor += 1
        real = float(row['value']) * ratio
        if not math.isfinite(real) or real <= 0:
            raise ValueError('Invalid real exchange rate')
        if len(history) == 1260:
            result.append({'date': when, 'first_anchor': next_weekday(when),
                           'value': decimal_text(Decimal(str(math.log(median(history) / real)))),
                           'operands': {'inflation': operands, 'spot_date': when, 'spot_sha256': digest(row)}})
        history.append(real)
    return result


def macro_inputs(store, capture, family, *, end_exclusive):
    from data.verified_inputs import memo
    return memo(store.root, 'fx_value_macro', {'capture': capture, 'family': family, 'end': end_exclusive},
                lambda: _macro_inputs(store, capture, family, end_exclusive=end_exclusive))


def _macro_inputs(store, capture, family, *, end_exclusive):
    """Reconstruct macro inputs from exact original publisher payloads."""
    raw = store.payload(capture)
    bundle = strict_json(raw)
    if (canonical_bytes(bundle) != raw or bundle.get('schema') != 'fx_value_macro_capture_v1'
            or bundle.get('family') != family):
        raise ValueError('Macro capture identity or provider family differs')
    if family == 'reer_relative':
        if set(bundle['currencies']) != set(COUNTRIES):
            raise ValueError('REER capture must cover all 19 approved currencies')
        return {currency: reer_states(parse_reer_archive(store.payload(member), currency,
                                                        end_exclusive=end_exclusive),
                                      end_exclusive=end_exclusive)
                for currency, member in bundle['currencies'].items()}
    from data.imf_weo_archive import (ArchiveBytes, COUNTRIES as IMF_COUNTRIES,
                                    legacy_series, workbook_series, sdmx_series)
    rows = []
    seen = set()
    for edition in bundle['editions']:
        if edition['available_on'] >= end_exclusive:
            continue
        if (edition['available_on'] <= edition['published']
                or edition['published'][:4] != edition['id'][:4]):
            raise ValueError('IMF availability must follow its edition publication')
        for kind, member in edition['files'].items():
            stream = ArchiveBytes(store.payload(member))
            if kind == 'xlsx':
                incoming = workbook_series(stream, edition['published'])
            elif kind == 'sdmx':
                incoming = sdmx_series(stream, edition['id'])
            else:
                incoming = legacy_series(stream, int(edition['id'][:4]), kind == 'groups')
            for entity, cutoff, values, evidence in incoming:
                actual = int(cutoff) if cutoff.isdigit() else None
                for label, text in values.items():
                    if not label or not label.isdigit() or len(label) != 4 or not 2006 <= int(label) <= 2023:
                        continue
                    if str(text).strip() in ('', 'n/a', '--', 'None'):
                        continue
                    key = (edition['id'], IMF_COUNTRIES[entity], int(label))
                    if key in seen:
                        raise ValueError('Duplicate original IMF currency/year record')
                    seen.add(key)
                    rows.append({'edition': edition['id'], 'currency': IMF_COUNTRIES[entity],
                        'year': int(label), 'value_pct': str(Decimal(text.replace(',', '').strip())),
                        'is_actual': None if actual is None else int(int(label) <= actual),
                        'actual_evidence': evidence, 'available_on': edition['available_on'],
                        'source_sha256': member['blob_sha256']})
    # A first-actual claim requires every earlier potentially eligible edition.
    inventory = sorted({row['edition'] for row in rows})
    known = {(row['currency'], row['year'], row['edition']): row['is_actual'] for row in rows}
    for currency in COUNTRIES:
        for year in range(2006, min(2023, date.fromisoformat(end_exclusive).year - 2) + 1):
            for edition in inventory:
                if int(edition[:4]) <= year:
                    continue
                status = known.get((currency, year, edition))
                if status is None:
                    raise ValueError('Unverified IMF release precedes a claimed first actual')
                if status == 1:
                    break
            # Every observed edition may still classify this year as estimated.
            # That year remains unavailable until an actual is published.
    return rows


def calculate(root, family, pair, price_snapshot, capture, *, end_exclusive='2025-01-01'):
    from data.targets.fx import _approved_policy, _price_snapshot
    store = FeatureStore(root)
    config = read_json(inside(root, 'config/fx_retrospective_completion.json'))
    batch = _approved_policy(store, config['return_policy'])
    snapshot, prices = _price_snapshot(store, price_snapshot, batch)
    if snapshot['body']['instrument_id'] != pair:
        raise ValueError('Value source prices belong to another pair')
    macro = macro_inputs(store, capture, family, end_exclusive=end_exclusive)
    if family == 'weo_bilateral':
        observations = weo_pair(prices, macro, pair, end_exclusive=end_exclusive)
    else:
        observations = reer_pair(macro[pair[:3]], macro[pair[3:]], end_exclusive=end_exclusive)
    return observations, eligibility(prices, observations, family)


def eligibility(prices, observations, family):
    from research.p2_validation.engine import select_non_overlapping_intervals
    valid_prices = {row['reference_time'] for row in prices if row['status'] == 'valid'}
    dates = []
    current = min(row['reference_time'] for row in prices)
    if date.fromisoformat(current).weekday() >= 5:
        current = next_weekday(current)
    while current < '2025-01-01':
        dates.append(current)
        current = next_weekday(current)
    ordered = sorted(observations, key=lambda item: item['date'])
    available = [row['date'] for row in ordered]
    result = {}
    for horizon in (1, 7, 21, 63):
        split = '2017-01-01' if horizon == 63 else '2022-01-01'
        discovery, validation = [], []
        for anchor, end in zip(dates, dates[horizon:]):
            if anchor not in valid_prices or end not in valid_prices:
                continue
            index = bisect_left(available, anchor) - 1
            if index < 0 or ordered[index]['value'] is None:
                continue
            if family == 'weo_bilateral' and ordered[index]['first_anchor'] != anchor:
                continue
            if end < split:
                discovery.append(anchor)
            elif anchor >= split:
                validation.append({'date': anchor, 'target_end': end, 'instrument': 'pair'})
        independent = len(select_non_overlapping_intervals(validation))
        exclusion = None
        if len(discovery) < horizon + 2:
            exclusion = 'INSUFFICIENT_DISCOVERY_HISTORY'
        elif independent < 15:
            exclusion = 'INSUFFICIENT_NONOVERLAPPING_VALIDATION_RETURNS'
        result[str(horizon)] = {'discovery_dates': len(discovery), 'validation_dates': len(validation),
            'nonoverlapping_validation_returns': independent, 'exclusion': exclusion}
    return result


def publish(root, family, pair, price_snapshot, capture):
    """Publish only complete verified inputs and their exact computed observations."""
    store = FeatureStore(root)
    feature = recipe(family)
    observations, coverage = calculate(root, family, pair, price_snapshot, capture)
    if not observations:
        raise ValueError('Value feature has insufficient five-year history')
    if len({row['date'] for row in observations}) != len(observations):
        raise ValueError('Value output has duplicate dates')
    if any(row['first_anchor'] != next_weekday(row['date']) for row in observations):
        raise ValueError('Value output violates the conservative source clock')
    valid = [row for row in observations if row['value'] is not None]
    if not valid:
        raise ValueError('Value output has no valid history')
    payload = b''.join(canonical_bytes(row) + b'\n' for row in observations)
    snapshot = make_record('snapshot_manifest', {
        'kind': 'fx_value_feature_snapshot', 'family': family, 'pair': pair,
        'recipe': reference(feature), 'price_snapshot': price_snapshot, 'capture': capture,
        'observations': store.io.blob(payload, 'jsonl', 'value_observations', len(observations)),
        'row_count': len(observations), 'first_anchor': valid[0]['first_anchor'], 'coverage': coverage,
        'source_timing': 'dated_macro_retrospective_spot_date_labels',
    })
    with store.writer():
        store.install_record(feature)
        store.install_record(snapshot)
        store.verify_closure([snapshot])
        from research.feature_applications import install_binding, VALUE_PAIR
        install_binding(root, feature, VALUE_PAIR)
        path = inside(root, 'storage/catalog/fx_value/' + feature['id'] + '/' + pair + '.json')
        install_bytes(path, canonical_bytes({'snapshot': reference(snapshot)}) + b'\n')
    return snapshot


def source(root, feature, pair):
    store = FeatureStore(root)
    selected = read_json(inside(root, 'storage/catalog/fx_value/' + feature['id'] + '/' + pair + '.json'))
    record = store.resolve(selected['snapshot'])
    validate_record(record)
    body = record['body']
    if body['recipe'] != reference(feature) or body['pair'] != pair:
        raise ValueError('Value source differs from the selected recipe or pair')
    store.verify_closure([record])
    return {'snapshot': selected['snapshot'], **body}


def phase_observations(root, source, period):
    from data.verified_inputs import memo
    return memo(root, 'fx_value_phase', {'source': source['snapshot'], 'period': period},
                lambda: _phase_observations(root, source, period))


def _phase_observations(root, source, period):
    store = FeatureStore(root)
    current = store.resolve(source['snapshot'])
    if current['body'] != {key: value for key, value in source.items() if key != 'snapshot'}:
        raise ValueError('Frozen value source differs')
    lines = store.payload(source['observations']).splitlines()
    selected = []
    previous = None
    for line in lines:
        # Dates are canonical fixed-width headers. P1 does not decode P2 scores.
        marker = b'"date":"'
        offset = line.index(marker) + len(marker)
        when = line[offset:offset + 10].decode('ascii')
        if when < period['start_inclusive']:
            previous = line
        elif when < period['end_exclusive']:
            selected.append(line)
    if previous is not None:
        selected.insert(0, previous)
    rows = []
    for line in selected:
        row = strict_json(line)
        if canonical_bytes(row) != line or row['first_anchor'] != next_weekday(row['date']):
            raise ValueError('Invalid stored value observation')
        rows.append(row)
    if len(lines) != source['row_count']:
        raise ValueError('Value output row count differs')
    expected, _ = calculate(root, source['family'], source['pair'], source['price_snapshot'],
                            source['capture'], end_exclusive=period['end_exclusive'])
    before = [row for row in expected if row['date'] < period['start_inclusive']]
    selected = before[-1:] + [row for row in expected if period['start_inclusive'] <= row['date']]
    if rows != selected:
        raise ValueError('Stored value observations differ from an independent source replay')
    return rows
