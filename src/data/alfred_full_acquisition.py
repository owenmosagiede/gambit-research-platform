"""Bounded, credential-safe acquisition of the complete available ALFRED series.

Acquisition writes only an explicitly supplied staging directory. Exact official
response bytes and sanitized receipts are preserved. No registry or legacy data
is modified; publication belongs to a separate caller. Replay remains vintage-date
reconstruction, not a claim of historical intraday receipt or tradability.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from data.alfred_onboarding import (
    BASE_URL, HEADERS, SERIES, as_of, canonical, now, parse_vintages, sha, strict_json,
)

BUNDLE_FILE = 'bundle.json'
EARLIEST = '1776-07-04'
LATEST = '9999-12-31'
MAX_VINTAGES = 2000
MAX_RESPONSE_BYTES = 25_000_000
GROUPS = ('metadata_start', 'vintages', 'initial_vintage', 'observations', 'observations_paged', 'observations_terminal', 'asof_before_first',
          'asof_first', 'asof_middle', 'asof_last', 'metadata_end', 'vintages_recheck')
PARAMETERS = {'series_id', 'file_type', 'realtime_start', 'realtime_end', 'observation_start',
              'observation_end', 'output_type', 'units', 'sort_order', 'limit', 'offset'}


class AcquisitionError(ValueError):
    """An acquisition error containing no provider URL with credentials."""


def _need(condition, message):
    if not condition:
        raise AcquisitionError(message)


def _day(value):
    _need(isinstance(value, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value), 'Noncanonical calendar date')
    dt.date.fromisoformat(value)
    return value


def _time(value):
    _need(isinstance(value, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z', value), 'Noncanonical UTC timestamp')
    return dt.datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=dt.timezone.utc)


def _save_new(path, data):
    with Path(path).open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _credential(path):
    try:
        lines = Path(path).read_text().splitlines()
        values = [line.partition('=')[2].strip().strip('\"\'') for line in lines if line.startswith('FRED_API_KEY=')]
    except OSError:
        raise AcquisitionError('FRED credential unavailable; contents not logged') from None
    _need(len(values) == 1 and re.fullmatch(r'[a-z0-9]{32}', values[0]), 'FRED credential unavailable; contents not logged')
    return values[0]


def _request(directory, name, endpoint, parameters, credential, opener=urllib.request.urlopen):
    """Preserve exact response bytes while excluding credentials from all records."""
    _need(re.fullmatch(r'[a-z][a-z0-9_]*', name), 'Invalid request name')
    _need(endpoint in {BASE_URL+'series', BASE_URL+'series/observations', BASE_URL+'series/vintagedates'}, 'Unsupported official endpoint')
    _need(set(parameters) <= PARAMETERS and all(isinstance(v, str) for v in parameters.values()), 'Unsanitized request parameters')
    receipt = {'endpoint': endpoint, 'parameters': dict(parameters), 'started_at': now(), 'finished_at': None,
               'http_status': None, 'headers': {}, 'error': None, 'payload_path': None, 'sha256': None, 'byte_count': None}
    payload = None
    try:
        address = endpoint+'?'+urllib.parse.urlencode(dict(parameters, api_key=credential))
        request = urllib.request.Request(address, headers={'User-Agent': 'ResearchPlatformFullALFRED/0.1', 'Accept-Encoding': 'identity'})
        with opener(request, timeout=60) as response:
            receipt['http_status'] = response.status
            receipt['headers'] = {key.lower(): value for key, value in response.headers.items() if key.lower() in HEADERS}
            payload = response.read(MAX_RESPONSE_BYTES+1)
        _need(len(payload) <= MAX_RESPONSE_BYTES, 'Official response exceeds the acquisition bound')
        _need(credential.encode() not in payload, 'Credential reflection detected; response not retained')
        _need(200 <= receipt['http_status'] < 300, 'Official request did not succeed')
        strict_json(payload)
        relative = name+'.json'
        _save_new(Path(directory)/relative, payload)
        receipt.update(payload_path=relative, sha256=sha(payload), byte_count=len(payload))
    except urllib.error.HTTPError as exc:
        receipt.update(http_status=exc.code, error={'code': 'HTTP_ERROR', 'message': 'Official provider returned HTTP '+str(exc.code)})
    except Exception as exc:
        # Raw exception text may include an authenticated URL. Never retain it.
        receipt['error'] = {'code': type(exc).__name__, 'message': 'Official request failed; credential-bearing exception details omitted'}
    receipt['finished_at'] = now()
    _save_new(Path(directory)/(name+'.receipt.json'), canonical(receipt)+b'\n')
    if receipt['error'] is not None:
        raise AcquisitionError('Official request '+name+' failed; see its sanitized receipt') from None
    return {'receipt': receipt, 'payloadbytes': payload, 'parsed': strict_json(payload)}


def _common():
    return {'series_id': SERIES, 'file_type': 'json'}


def _observation_parameters(capture_day, output_type, asof=None):
    return dict(_common(), observation_start=EARLIEST, observation_end=LATEST,
                realtime_start=asof or EARLIEST, realtime_end=asof or capture_day,
                output_type=str(output_type), units='lin', sort_order='asc')


def _vintage_parameters(capture_day):
    # The catalog is deliberately unbounded at the end. Its maximum date must
    # agree with the independently reported provider cutoff, never be clipped.
    return dict(_common(), realtime_start=EARLIEST, realtime_end=LATEST, sort_order='asc')


def _response_bounds(parsed, base, key):
    for field in ('realtime_start', 'realtime_end', 'sort_order'):
        _need(parsed.get(field) == base[field], 'Official response '+field+' differs from the requested scope')
    expected_order = 'vintage_date' if key == 'vintage_dates' else 'observation_date'
    _need(parsed.get('order_by') == expected_order, 'Official response ordering changed')
    if key == 'observations':
        for field in ('observation_start', 'observation_end', 'units'):
            _need(parsed.get(field) == base[field], 'Official response '+field+' differs from the requested scope')
        _need(parsed.get('output_type') == int(base['output_type']), 'Official output type differs from the request')


def _page_shape(parsed, key, offset, limit, expected_count=None, maximum=None):
    _need(isinstance(parsed, dict), 'Official page must be an object')
    count = parsed.get('count')
    _need(type(count) is int and count >= 0, 'Missing or invalid official count')
    _need(type(parsed.get('offset')) is int and parsed['offset'] == offset, 'Official pagination offset mismatch')
    _need(type(parsed.get('limit')) is int and parsed['limit'] == limit, 'Official pagination limit mismatch')
    _need(expected_count is None or count == expected_count, 'Official count changed between pages')
    _need(maximum is None or count <= maximum, 'Official vintage count exceeds supported 2000-vintage JSON bound; no truncation allowed')
    items = parsed.get(key)
    _need(isinstance(items, list), 'Official page collection is missing')
    _need(len(items) == min(limit, max(0, count-offset)), 'Truncated or inconsistent official page')
    return count, items


def _acquire_pages(directory, prefix, endpoint, base, key, page_size, credential, requests, maximum=None):
    names, total, offset = [], None, 0
    while True:
        name = prefix+'_'+str(offset).zfill(6)
        entry = _request(directory, name, endpoint, dict(base, limit=str(page_size), offset=str(offset)), credential)
        total, items = _page_shape(entry['parsed'], key, offset, page_size, total, maximum)
        _response_bounds(entry['parsed'], base, key)
        requests[name] = entry
        names.append(name)
        offset += len(items)
        if offset == total:
            return names
        _need(len(items) > 0 and len(names) <= 10000, 'Pagination did not make bounded progress')


def _pages(index, requests, group, endpoint, base, key, size, maximum=None):
    names = index['request_groups'][group]
    _need(isinstance(names, list) and len(names) > 0, 'Required paginated request group is empty')
    total, offset, result = None, 0, []
    for position, name in enumerate(names):
        entry = requests[name]
        receipt, parsed = entry['receipt'], entry['parsed']
        _need(receipt['endpoint'] == endpoint and receipt['parameters'] == dict(base, limit=str(size), offset=str(offset)), 'Request does not cover the prescribed full-history page')
        _response_bounds(parsed, base, key)
        total, items = _page_shape(parsed, key, offset, size, total, maximum)
        result.extend((item, name) for item in items)
        offset += len(items)
        _need(position == len(names)-1 or offset < total, 'Extra page after complete official response')
    _need(offset == total, 'Incomplete paginated response set')
    return result


def _verify_month_paging(index, requests, raw_rows):
    """Some type-3 page sizes report an opaque count, not wide month rows.

    Never reinterpret that field as an event count. A complete single response,
    exact page slices and an empty terminal page independently prove coverage.
    """
    base = _observation_parameters(index['realtime_cutoff'], 3)
    size = index['observation_page_size']
    names = index['request_groups']['observations_paged']
    offsets = list(range(0, len(raw_rows), size))
    _need(len(names) == len(offsets), 'Missing full-history pagination verification page')
    reported_count = None
    for name, offset in zip(names, offsets):
        receipt, parsed = requests[name]['receipt'], requests[name]['parsed']
        _need(receipt['endpoint'] == BASE_URL+'series/observations' and receipt['parameters'] == dict(base, limit=str(size), offset=str(offset)), 'Wrong verification page request')
        _response_bounds(parsed, base, 'observations')
        count = parsed.get('count')
        _need(type(count) is int and count >= 0 and (reported_count is None or count == reported_count), 'Reported pagination count changed')
        reported_count = count
        _need(parsed.get('offset') == offset and parsed.get('limit') == size, 'Verification pagination offsets differ')
        _need(parsed.get('observations') == raw_rows[offset:offset+size], 'Paginated values differ from complete authoritative response')
    terminal_names = index['request_groups']['observations_terminal']
    _need(len(terminal_names) == 1, 'Missing explicit empty terminal page')
    terminal = requests[terminal_names[0]]
    expected = dict(base, limit=str(size), offset=str(len(raw_rows)))
    _need(terminal['receipt']['endpoint'] == BASE_URL+'series/observations' and terminal['receipt']['parameters'] == expected, 'Wrong terminal page request')
    parsed = terminal['parsed']
    _response_bounds(parsed, base, 'observations')
    _need(parsed.get('observations') == [] and parsed.get('offset') == len(raw_rows) and parsed.get('limit') == size and parsed.get('count') == reported_count, 'Terminal page is not empty and consistent')
    return reported_count


def _monthly_dates(start, end):
    first, last = dt.date.fromisoformat(_day(start)), dt.date.fromisoformat(_day(end))
    _need(first.day == last.day == 1 and first <= last, 'Series metadata is not an increasing monthly range')
    result, current = [], first
    while current <= last:
        result.append(current.isoformat())
        current = dt.date(current.year+1, 1, 1) if current.month == 12 else dt.date(current.year, current.month+1, 1)
    return result, current.isoformat()


def _values(output_rows):
    synthetic = []
    for item in output_rows:
        _need(isinstance(item, dict), 'Malformed as-of observation')
        _day(item.get('date'))
        synthetic.append({'date': item['date'], SERIES+'_20000101': item.get('value')})
    normalized = parse_vintages({'output_type': 3, 'units': 'lin', 'offset': 0, 'count': len(synthetic), 'observations': synthetic}, start=EARLIEST, end=LATEST)
    return {row['observation_date']: (row['value'], row['status']) for row in normalized}


def validate_bundle(index, requests):
    """Pure offline validation and assembly from a frozen index and response bytes."""
    fields = {'schema_version', 'status', 'series_id', 'capture_started_at', 'capture_finished_at', 'capture_day',
              'realtime_cutoff', 'observation_page_size', 'vintage_page_size', 'request_groups', 'asof_dates', 'request_manifest'}
    _need(isinstance(index, dict) and set(index) == fields, 'Invalid acquisition bundle fields')
    _need(index['schema_version'] == '0.1.0' and index['status'] == 'complete' and index['series_id'] == SERIES, 'Wrong or incomplete acquisition bundle')
    start, finish = _time(index['capture_started_at']), _time(index['capture_finished_at'])
    capture_day = _day(index['capture_day'])
    realtime_cutoff = _day(index['realtime_cutoff'])
    _need(start <= finish and capture_day == index['capture_started_at'][:10], 'Invalid fixed capture interval')
    _need(realtime_cutoff <= capture_day, 'Provider realtime cutoff exceeds UTC capture day')
    _need(type(index['observation_page_size']) is int and 1 <= index['observation_page_size'] <= 100000, 'Invalid observation page size')
    _need(type(index['vintage_page_size']) is int and 1 <= index['vintage_page_size'] <= 10000, 'Invalid vintage page size')
    _need(set(index['request_groups']) == set(GROUPS), 'Unexpected acquisition request groups')
    group_names = [name for group in GROUPS for name in index['request_groups'][group]]
    _need(len(group_names) == len(set(group_names)) and set(group_names) == set(requests), 'Duplicate, missing or unlisted acquisition requests')
    manifests = index['request_manifest']
    _need(isinstance(manifests, list) and len(manifests) == len(requests), 'Invalid request manifest length')
    checked = {}
    for manifest in manifests:
        _need(isinstance(manifest, dict) and set(manifest) == {'name', 'receipt_sha256', 'payload_sha256'}, 'Invalid request manifest member')
        name = manifest['name']
        _need(name in requests and name not in checked, 'Duplicate or unknown request manifest member')
        entry, receipt = requests[name], requests[name]['receipt']
        payload = entry['payloadbytes']
        _need(isinstance(payload, bytes), 'Exact response bytes required')
        _need(sha(canonical(receipt)) == manifest['receipt_sha256'], 'Sanitized receipt hash mismatch')
        _need(sha(payload) == manifest['payload_sha256'] == receipt['sha256'] and len(payload) == receipt['byte_count'], 'Official payload checksum or length mismatch')
        _need(receipt['error'] is None and type(receipt['http_status']) is int and 200 <= receipt['http_status'] < 300, 'Acquisition contains unsuccessful request')
        _need(set(receipt['parameters']) <= PARAMETERS and set(receipt['headers']) <= HEADERS, 'Credential-bearing or unsupported receipt field')
        _need(start <= _time(receipt['started_at']) <= _time(receipt['finished_at']) <= finish, 'Request timestamps outside acquisition interval')
        parsed = strict_json(payload)
        _need(entry.get('parsed', parsed) == parsed, 'Parsed response differs from exact bytes')
        checked[name] = {'receipt': receipt, 'payloadbytes': payload, 'parsed': parsed}
    requests = checked

    def metadata(group):
        names = index['request_groups'][group]
        _need(len(names) == 1, 'Metadata group must contain exactly one response')
        entry = requests[names[0]]
        _need(entry['receipt']['endpoint'] == BASE_URL+'series' and entry['receipt']['parameters'] == _common(), 'Unexpected official metadata request')
        _need(entry['parsed'].get('realtime_end') == realtime_cutoff, 'Provider realtime cutoff changed during acquisition')
        _need(entry['parsed'].get('realtime_start') == realtime_cutoff, 'Metadata realtime interval is not the observed provider date')
        result = entry['parsed'].get('seriess')
        _need(isinstance(result, list) and len(result) == 1 and result[0].get('id') == SERIES, 'Wrong official series metadata')
        _need(result[0].get('frequency_short') == 'M' and result[0].get('frequency') == 'Monthly', 'Pilot requires the documented monthly series')
        _need(result[0].get('units') == 'Dollars per Hour' and result[0].get('seasonal_adjustment') == 'Seasonally Adjusted', 'Official series units or seasonal adjustment changed')
        _need(result[0].get('realtime_start') == realtime_cutoff and result[0].get('realtime_end') == realtime_cutoff, 'Series metadata realtime interval differs from the provider snapshot')
        return result[0]

    metadata_start, metadata_end = metadata('metadata_start'), metadata('metadata_end')
    _need(metadata_start == metadata_end, 'Official series metadata changed during acquisition')
    dates_expected, next_month = _monthly_dates(metadata_start['observation_start'], metadata_start['observation_end'])
    vintage_pairs = _pages(index, requests, 'vintages', BASE_URL+'series/vintagedates', _vintage_parameters(realtime_cutoff), 'vintage_dates', index['vintage_page_size'], MAX_VINTAGES)
    vintage_dates = [_day(item) for item, _ in vintage_pairs]
    _need(vintage_dates and vintage_dates == sorted(set(vintage_dates)) and vintage_dates[-1] <= realtime_cutoff, 'Invalid or duplicate vintage-date coverage')
    recheck = _pages(index, requests, 'vintages_recheck', BASE_URL+'series/vintagedates', _vintage_parameters(realtime_cutoff), 'vintage_dates', index['vintage_page_size'], MAX_VINTAGES)
    _need([item for item, _ in recheck] == vintage_dates, 'Official vintage dates changed during acquisition')
    _need(len(index['request_groups']['observations']) == 1, 'Expected one complete authoritative wide observation response')
    observation_pairs = _pages(index, requests, 'observations', BASE_URL+'series/observations', _observation_parameters(realtime_cutoff, 3), 'observations', 100000)
    raw_rows = [item for item, _ in observation_pairs]
    _need(all(isinstance(item, dict) for item in raw_rows), 'Malformed full-history observation rows')
    observation_dates = [_day(item.get('date')) for item in raw_rows]
    _need(observation_dates == dates_expected, 'Full-history monthly coverage differs from official metadata')
    reported_paginated_count = _verify_month_paging(index, requests, raw_rows)
    for name in index['request_groups']['observations']:
        page = requests[name]['parsed']
        _need(page.get('output_type') == 3 and page.get('units') == 'lin', 'Wrong official full-history output type or units')
    rows = parse_vintages({'output_type': 3, 'units': 'lin', 'offset': 0, 'count': len(raw_rows), 'observations': raw_rows}, start=EARLIEST, end=LATEST)
    _need({row['observation_date'] for row in rows} == set(dates_expected), 'An observation month has no archived change events')
    page_by_date = {item['date']: name for item, name in observation_pairs}
    vintage_set = set(vintage_dates)
    for row in rows:
        _need(row['vintage_date'] in vintage_set, 'Change event vintage absent from the official vintage list')
        row['source_raw_blob_sha256'] = requests[page_by_date[row['observation_date']]]['receipt']['sha256']
        row['source_field'] = SERIES+'_'+row['vintage_date'].replace('-', '')
    revised_count = len(rows)
    # Output type 3 omits this provider's initial archive state. Preserve the
    # exact native type-2 first-vintage cells as an independent authoritative input.
    _need(len(index['request_groups']['initial_vintage']) == 1, 'Expected one complete initial-vintage response')
    initial_pairs = _pages(index, requests, 'initial_vintage', BASE_URL+'series/observations',
                          _observation_parameters(realtime_cutoff, 2, vintage_dates[0]), 'observations', 100000)
    initial_raw = [item for item, _ in initial_pairs]
    first_column = SERIES+'_'+vintage_dates[0].replace('-', '')
    _need(initial_raw and all(isinstance(item, dict) and set(item) == {'date', first_column} for item in initial_raw), 'Initial-vintage response has unexpected native columns')
    initial_rows = parse_vintages({'output_type': 3, 'units': 'lin', 'offset': 0, 'count': len(initial_raw), 'observations': initial_raw}, start=EARLIEST, end=LATEST)
    initial_sources = {item['date']: name for item, name in initial_pairs}
    existing_keys = {(row['observation_date'], row['vintage_date']) for row in rows}
    for row in initial_rows:
        _need(row['vintage_date'] == vintage_dates[0] and (row['observation_date'], row['vintage_date']) not in existing_keys, 'Initial and revised histories overlap; explicit reconciliation required')
        _need(row['observation_date'] in set(dates_expected), 'Initial state falls outside the documented observation history')
        row['source_raw_blob_sha256'] = requests[initial_sources[row['observation_date']]]['receipt']['sha256']
        row['source_field'] = first_column
    rows = sorted(initial_rows+rows, key=lambda row: (row['observation_date'], row['vintage_date']))
    _need({row['vintage_date'] for row in rows} == vintage_set, 'Change events do not cover every official vintage date')
    expected_asofs = {'before_first': (dt.date.fromisoformat(vintage_dates[0])-dt.timedelta(days=1)).isoformat(),
                     'first': vintage_dates[0], 'middle': vintage_dates[len(vintage_dates)//2], 'last': vintage_dates[-1]}
    _need(index['asof_dates'] == expected_asofs, 'As-of checks are not the prescribed first/middle/last vintages')
    _need(index['request_groups']['asof_before_first'] == [], 'Before-first check is a reconstruction boundary check, not an inferred HTTP result')
    _need(as_of(rows, expected_asofs['before_first']) == [], 'Unexpected value before first official vintage')
    asof_checks = [{'label': 'before_first', 'as_of_date': expected_asofs['before_first'], 'request_names': [],
                    'expected_count': 0, 'observed_count': 0, 'matches': True, 'source': 'normalized_change_events'}]
    for label in ('first', 'middle', 'last'):
        day = expected_asofs[label]
        pairs = _pages(index, requests, 'asof_'+label, BASE_URL+'series/observations', _observation_parameters(realtime_cutoff, 1, day), 'observations', index['observation_page_size'])
        for name in index['request_groups']['asof_'+label]:
            page = requests[name]['parsed']
            _need(page.get('output_type') == 1 and page.get('units') == 'lin', 'Wrong official as-of output type or units')
        official = _values([item for item, _ in pairs])
        for item, _ in pairs:
            _need(_day(item.get('realtime_start')) <= day <= _day(item.get('realtime_end')), 'Official as-of row does not cover the requested vintage date')
        selected = {row['observation_date']: (row['value'], row['status']) for row in as_of(rows, day)}
        _need(selected == official, 'Independent official '+label+' as-of response differs from reconstructed history')
        if label == 'last':
            _need(sorted(official) == dates_expected, 'Latest official state does not cover the complete metadata history')
        asof_checks.append({'label': label, 'as_of_date': day, 'request_names': index['request_groups']['asof_'+label],
                            'expected_count': len(selected), 'observed_count': len(official), 'matches': True, 'source': 'official_output_type_1'})
    coverage = {'observation_start': dates_expected[0], 'observation_end': dates_expected[-1], 'observation_periods': len(dates_expected),
                'change_events': len(rows), 'initial_vintage_rows': len(initial_rows), 'new_and_revised_change_events': revised_count,
                'vintage_date_count': len(vintage_dates), 'vintage_start': vintage_dates[0], 'vintage_end': vintage_dates[-1],
                'capture_day': capture_day, 'realtime_cutoff': realtime_cutoff, 'observation_pages': len(index['request_groups']['observations']),
                'verification_observation_pages': len(index['request_groups']['observations_paged']),
                'reported_paginated_count': reported_paginated_count, 'authoritative_reported_count': len(raw_rows),
                'vintage_pages': len(index['request_groups']['vintages']), 'missing_change_events': sum(row['status']=='missing' for row in rows),
                'all_current_observations_matched': True, 'provider_metadata_stable': True, 'provider_vintage_dates_stable': True,
                'pagination_complete': True, 'asof_check_count': len(asof_checks)}
    return {'index': index, 'metadata': metadata_start, 'rows': rows, 'vintage_dates': vintage_dates, 'requests': requests,
            'period': {'start_inclusive': dates_expected[0]+'T00:00:00.000000Z', 'end_exclusive': next_month+'T00:00:00.000000Z'},
            'capture_started_at': index['capture_started_at'], 'capture_finished_at': index['capture_finished_at'],
            'asof_checks': asof_checks, 'coverage': coverage}


def load_bundle(directory):
    directory = Path(directory)
    index = strict_json((directory/BUNDLE_FILE).read_bytes())
    requests = {}
    for item in index['request_manifest']:
        name = item['name']
        _need(re.fullmatch(r'[a-z][a-z0-9_]*', name), 'Unsafe acquisition request name')
        receipt = strict_json((directory/(name+'.receipt.json')).read_bytes())
        _need(receipt['payload_path'] == name+'.json', 'Unsafe saved payload name')
        payload = (directory/receipt['payload_path']).read_bytes()
        requests[name] = {'receipt': receipt, 'payloadbytes': payload, 'parsed': strict_json(payload)}
    return validate_bundle(index, requests)


def acquire(directory, credential_file, observation_page_size=100, vintage_page_size=10000):
    _need(type(observation_page_size) is int and 1 <= observation_page_size <= 100000, 'Invalid observation page size')
    _need(type(vintage_page_size) is int and 1 <= vintage_page_size <= 10000, 'Invalid vintage page size')
    directory = Path(directory)
    _need(not directory.exists() or not any(directory.iterdir()), 'Acquisition staging directory must be empty; old evidence is never overwritten')
    directory.mkdir(parents=True, exist_ok=True)
    credential = _credential(credential_file)
    started = now()
    capture_day = started[:10]
    _save_new(directory/'capture_start.json', canonical({'series_id': SERIES, 'capture_started_at': started, 'capture_day': capture_day})+b'\n')
    groups = {name: [] for name in GROUPS}
    requests = {}
    metadata_params = _common()
    requests['metadata_start'] = _request(directory, 'metadata_start', BASE_URL+'series', metadata_params, credential)
    groups['metadata_start'] = ['metadata_start']
    realtime_cutoff = _day(requests['metadata_start']['parsed'].get('realtime_end'))
    _need(realtime_cutoff <= capture_day, 'Provider realtime cutoff exceeds UTC capture day')
    groups['vintages'] = _acquire_pages(directory, 'vintages', BASE_URL+'series/vintagedates', _vintage_parameters(realtime_cutoff), 'vintage_dates', vintage_page_size, credential, requests, MAX_VINTAGES)
    vintage_dates = [day for name in groups['vintages'] for day in requests[name]['parsed']['vintage_dates']]
    _need(vintage_dates and vintage_dates == sorted(set(vintage_dates)), 'Official vintage list is empty, duplicated or unordered')
    initial_name = 'initial_vintage'
    requests[initial_name] = _request(directory, initial_name, BASE_URL+'series/observations',
        dict(_observation_parameters(realtime_cutoff, 2, vintage_dates[0]), limit='100000', offset='0'), credential)
    initial_total, initial_items = _page_shape(requests[initial_name]['parsed'], 'observations', 0, 100000)
    _need(initial_total == len(initial_items), 'Initial-vintage response exceeds one complete supported page')
    groups['initial_vintage'] = [initial_name]
    full_name = 'observations_full'
    observation_base = _observation_parameters(realtime_cutoff, 3)
    requests[full_name] = _request(directory, full_name, BASE_URL+'series/observations', dict(observation_base, limit='100000', offset='0'), credential)
    total, raw_rows = _page_shape(requests[full_name]['parsed'], 'observations', 0, 100000)
    _need(total == len(raw_rows), 'Authoritative wide response exceeds one complete supported page')
    groups['observations'] = [full_name]
    for offset in range(0, len(raw_rows), observation_page_size):
        name = 'observations_paged_'+str(offset).zfill(6)
        requests[name] = _request(directory, name, BASE_URL+'series/observations', dict(observation_base, limit=str(observation_page_size), offset=str(offset)), credential)
        groups['observations_paged'].append(name)
    terminal_name = 'observations_terminal'
    requests[terminal_name] = _request(directory, terminal_name, BASE_URL+'series/observations', dict(observation_base, limit=str(observation_page_size), offset=str(len(raw_rows))), credential)
    groups['observations_terminal'] = [terminal_name]
    asof_dates = {'before_first': (dt.date.fromisoformat(vintage_dates[0])-dt.timedelta(days=1)).isoformat(),
                  'first': vintage_dates[0], 'middle': vintage_dates[len(vintage_dates)//2], 'last': vintage_dates[-1]}
    for label in ('first', 'middle', 'last'):
        groups['asof_'+label] = _acquire_pages(directory, 'asof_'+label, BASE_URL+'series/observations', _observation_parameters(realtime_cutoff, 1, asof_dates[label]),
                                               'observations', observation_page_size, credential, requests)
    requests['metadata_end'] = _request(directory, 'metadata_end', BASE_URL+'series', metadata_params, credential)
    groups['metadata_end'] = ['metadata_end']
    groups['vintages_recheck'] = _acquire_pages(directory, 'vintages_recheck', BASE_URL+'series/vintagedates', _vintage_parameters(realtime_cutoff), 'vintage_dates', vintage_page_size, credential, requests, MAX_VINTAGES)
    index = {'schema_version': '0.1.0', 'status': 'complete', 'series_id': SERIES, 'capture_started_at': started, 'capture_finished_at': now(), 'capture_day': capture_day,
             'realtime_cutoff': realtime_cutoff, 'observation_page_size': observation_page_size, 'vintage_page_size': vintage_page_size, 'request_groups': groups, 'asof_dates': asof_dates,
             'request_manifest': [{'name': name, 'receipt_sha256': sha(canonical(entry['receipt'])), 'payload_sha256': sha(entry['payloadbytes'])} for name, entry in requests.items()]}
    result = validate_bundle(index, requests)
    _save_new(directory/BUNDLE_FILE, canonical(index)+b'\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--credential-file', required=True)
    args = parser.parse_args()
    result = acquire(args.output, args.credential_file)
    print(json.dumps({'bundle': str(Path(args.output)/BUNDLE_FILE), 'coverage': result['coverage']}, indent=2))


if __name__ == '__main__':
    main()
