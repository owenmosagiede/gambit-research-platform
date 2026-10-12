"""Offline complete-history acquisition tests with fictional native-wide values.

No credentials are read and no network request occurs. Synthetic hashes are
recomputed in semantic-corruption cases to exercise validation beyond byte hashes.
"""
import copy
from pathlib import Path
import tempfile
import unittest
import urllib.error

from data import alfred_full_acquisition as acquisition


def synthetic_bundle():
    day = '2011-05-06'
    groups = {key: [] for key in acquisition.GROUPS}
    requests = {}
    index = {'schema_version': '0.1.0', 'status': 'complete', 'series_id': acquisition.SERIES,
             'capture_started_at': '2011-05-07T00:00:00.000000Z', 'capture_finished_at': '2011-05-07T00:00:05.000000Z',
             'capture_day': '2011-05-07', 'realtime_cutoff': day, 'observation_page_size': 2, 'vintage_page_size': 2,
             'request_groups': groups, 'asof_dates': {'before_first': '2011-03-03', 'first': '2011-03-04', 'middle': '2011-04-01', 'last': day},
             'request_manifest': []}

    def add(group, name, endpoint, parameters, parsed):
        payload = acquisition.canonical(parsed)+b'\n'
        receipt = {'endpoint': endpoint, 'parameters': parameters, 'started_at': '2011-05-07T00:00:01.000000Z',
                   'finished_at': '2011-05-07T00:00:02.000000Z', 'http_status': 200, 'headers': {}, 'error': None,
                   'payload_path': name+'.json', 'sha256': acquisition.sha(payload), 'byte_count': len(payload)}
        requests[name] = {'receipt': receipt, 'payloadbytes': payload, 'parsed': parsed}
        groups[group].append(name)
        index['request_manifest'].append({'name': name, 'receipt_sha256': acquisition.sha(acquisition.canonical(receipt)), 'payload_sha256': acquisition.sha(payload)})

    def page(base, key, items, count, offset, limit):
        body = {'realtime_start': base['realtime_start'], 'realtime_end': base['realtime_end'], 'sort_order': 'asc',
                'order_by': 'vintage_date' if key == 'vintage_dates' else 'observation_date', 'count': count, 'offset': offset, 'limit': limit, key: items}
        if key == 'observations':
            body.update(observation_start=base['observation_start'], observation_end=base['observation_end'], units='lin', output_type=int(base['output_type']))
        return body

    metadata = {'realtime_start': day, 'realtime_end': day, 'seriess': [{
        'id': acquisition.SERIES, 'realtime_start': day, 'realtime_end': day, 'frequency': 'Monthly', 'frequency_short': 'M',
        'units': 'Dollars per Hour', 'seasonal_adjustment': 'Seasonally Adjusted', 'observation_start': '2011-01-01', 'observation_end': '2011-03-01'}]}
    for group in ('metadata_start', 'metadata_end'):
        add(group, group, acquisition.BASE_URL+'series', acquisition._common(), copy.deepcopy(metadata))
    vintages = ['2011-03-04', '2011-04-01', day]
    for group in ('vintages', 'vintages_recheck'):
        base = acquisition._vintage_parameters(day)
        for offset in (0, 2):
            name = group+'_'+str(offset)
            add(group, name, acquisition.BASE_URL+'series/vintagedates', dict(base, offset=str(offset), limit='2'),
                page(base, 'vintage_dates', vintages[offset:offset+2], 3, offset, 2))
    seed = [{'date': '2011-01-01', 'CES0500000003_20110304': '10'}, {'date': '2011-02-01', 'CES0500000003_20110304': '.'}]
    base = acquisition._observation_parameters(day, 2, vintages[0])
    add('initial_vintage', 'initial_vintage', acquisition.BASE_URL+'series/observations', dict(base, offset='0', limit='100000'), page(base, 'observations', seed, 2, 0, 100000))
    wide = [{'date': '2011-01-01', 'CES0500000003_20110401': '11', 'CES0500000003_20110506': '11'},
            {'date': '2011-02-01', 'CES0500000003_20110401': '11.5'},
            {'date': '2011-03-01', 'CES0500000003_20110401': '12', 'CES0500000003_20110506': '12.5'}]
    base = acquisition._observation_parameters(day, 3)
    add('observations', 'observations_full', acquisition.BASE_URL+'series/observations', dict(base, offset='0', limit='100000'), page(base, 'observations', copy.deepcopy(wide), 3, 0, 100000))
    for offset in (0, 2):
        add('observations_paged', 'observations_paged_'+str(offset), acquisition.BASE_URL+'series/observations', dict(base, offset=str(offset), limit='2'),
            page(base, 'observations', copy.deepcopy(wide[offset:offset+2]), 7, offset, 2))
    add('observations_terminal', 'observations_terminal', acquisition.BASE_URL+'series/observations', dict(base, offset='3', limit='2'), page(base, 'observations', [], 7, 3, 2))
    values = {'first': ['10', '.'], 'middle': ['11', '11.5', '12'], 'last': ['11', '11.5', '12.5']}
    dates = ['2011-01-01', '2011-02-01', '2011-03-01']
    for label, native_values in values.items():
        asof = index['asof_dates'][label]
        base = acquisition._observation_parameters(day, 1, asof)
        observed = [{'date': date, 'value': value, 'realtime_start': asof, 'realtime_end': asof} for date, value in zip(dates, native_values)]
        for offset in range(0, len(observed), 2):
            add('asof_'+label, 'asof_'+label+'_'+str(offset), acquisition.BASE_URL+'series/observations', dict(base, offset=str(offset), limit='2'),
                page(base, 'observations', observed[offset:offset+2], len(observed), offset, 2))
    return index, requests


def rehash(index, requests, name):
    entry = requests[name]
    entry['payloadbytes'] = acquisition.canonical(entry['parsed'])+b'\n'
    entry['receipt'].update(sha256=acquisition.sha(entry['payloadbytes']), byte_count=len(entry['payloadbytes']))
    for item in index['request_manifest']:
        if item['name'] == name:
            item.update(receipt_sha256=acquisition.sha(acquisition.canonical(entry['receipt'])), payload_sha256=entry['receipt']['sha256'])


class FullAlfredAcquisitionTests(unittest.TestCase):
    def test_complete_union_preserves_initial_missing_and_equal_value_events(self):
        result = acquisition.validate_bundle(*synthetic_bundle())
        self.assertEqual(result['coverage']['change_events'], 7)
        self.assertEqual(result['coverage']['initial_vintage_rows'], 2)
        self.assertEqual(result['coverage']['new_and_revised_change_events'], 5)
        self.assertEqual(result['coverage']['missing_change_events'], 1)
        self.assertEqual(result['coverage']['observation_periods'], 3)
        self.assertEqual(result['coverage']['vintage_date_count'], 3)
        self.assertEqual(result['period']['end_exclusive'], '2011-04-01T00:00:00.000000Z')
        self.assertEqual(len({row['source_raw_blob_sha256'] for row in result['rows']}), 2)
        self.assertEqual(len(result['asof_checks']), 4)
        self.assertTrue(all(check['matches'] for check in result['asof_checks']))

    def test_vintage_page_truncation_and_changed_count_are_rejected(self):
        for mutation in ('truncate', 'count'):
            index, requests = synthetic_bundle()
            target = requests['vintages_0']['parsed']
            if mutation == 'truncate': target['vintage_dates'].pop()
            else: target['count'] += 1
            rehash(index, requests, 'vintages_0')
            with self.subTest(mutation=mutation), self.assertRaises(acquisition.AcquisitionError):
                acquisition.validate_bundle(index, requests)

    def test_missing_verification_page_cannot_claim_complete_history(self):
        index, requests = synthetic_bundle()
        name = index['request_groups']['observations_paged'].pop()
        del requests[name]
        index['request_manifest'] = [item for item in index['request_manifest'] if item['name'] != name]
        with self.assertRaisesRegex(acquisition.AcquisitionError, 'pagination verification page'):
            acquisition.validate_bundle(index, requests)

    def test_nonempty_terminal_page_and_page_disagreement_are_rejected(self):
        for name in ('observations_terminal', 'observations_paged_0'):
            index, requests = synthetic_bundle()
            if name == 'observations_terminal': requests[name]['parsed']['observations'] = [{'date': '2011-04-01'}]
            else: requests[name]['parsed']['observations'][0]['CES0500000003_20110401'] = '999'
            rehash(index, requests, name)
            with self.subTest(name=name), self.assertRaises(acquisition.AcquisitionError):
                acquisition.validate_bundle(index, requests)

    def test_baseline_disagreement_with_independent_first_state_is_rejected(self):
        index, requests = synthetic_bundle()
        requests['initial_vintage']['parsed']['observations'][0]['CES0500000003_20110304'] = '999'
        rehash(index, requests, 'initial_vintage')
        with self.assertRaisesRegex(acquisition.AcquisitionError, 'first as-of'):
            acquisition.validate_bundle(index, requests)

    def test_response_temporal_scope_and_intraday_claims_are_not_inferred(self):
        for name, change in (('observations_full', 'top'), ('initial_vintage', 'top'), ('asof_middle_0', 'row')):
            index, requests = synthetic_bundle()
            parsed = requests[name]['parsed']
            if change == 'top': parsed['realtime_end'] = '2010-01-01'
            else: parsed['observations'][0]['realtime_end'] = '2010-01-01'
            rehash(index, requests, name)
            with self.subTest(name=name), self.assertRaises(acquisition.AcquisitionError):
                acquisition.validate_bundle(index, requests)

    def test_changed_units_or_end_metadata_block_publication(self):
        for stable_change in (False, True):
            index, requests = synthetic_bundle()
            names = ('metadata_start', 'metadata_end') if stable_change else ('metadata_end',)
            for name in names:
                requests[name]['parsed']['seriess'][0]['units'] = 'Index'
                rehash(index, requests, name)
            with self.subTest(stable_change=stable_change), self.assertRaisesRegex(acquisition.AcquisitionError, 'units'):
                acquisition.validate_bundle(index, requests)

    def test_vintage_count_over_json_limit_aborts_without_truncation(self):
        parsed = {'count': 2001, 'offset': 0, 'limit': 10000, 'vintage_dates': []}
        with self.assertRaisesRegex(acquisition.AcquisitionError, '2000-vintage'):
            acquisition._page_shape(parsed, 'vintage_dates', 0, 10000, maximum=2000)

    def test_checksum_corruption_is_rejected_before_semantic_use(self):
        index, requests = synthetic_bundle()
        requests['observations_full']['payloadbytes'] += b' '
        with self.assertRaisesRegex(acquisition.AcquisitionError, 'checksum'):
            acquisition.validate_bundle(index, requests)

    def test_nonfinite_native_value_and_unauthorized_vintage_are_rejected(self):
        for value in ('NaN', 'Infinity'):
            index, requests = synthetic_bundle()
            # Keep the verification pages consistent, so the numeric parser is
            # the failing boundary rather than a byte or page comparison.
            for name in ('observations_full', 'observations_paged_0'):
                requests[name]['parsed']['observations'][0]['CES0500000003_20110401'] = value
                rehash(index, requests, name)
            with self.subTest(value=value), self.assertRaises(ValueError):
                acquisition.validate_bundle(index, requests)

    def test_transport_exception_never_persists_credential_or_raw_exception(self):
        credential = 'a'*32
        def failed_opener(request, timeout):
            raise urllib.error.URLError('https://provider.invalid/?api_key='+credential)
        with tempfile.TemporaryDirectory(prefix='alfred_request_test_', dir='/private/tmp') as directory:
            with self.assertRaises(acquisition.AcquisitionError) as failure:
                acquisition._request(directory, 'synthetic_request', acquisition.BASE_URL+'series', acquisition._common(), credential, opener=failed_opener)
            contents = b''.join(path.read_bytes() for path in Path(directory).iterdir())
            self.assertNotIn(credential.encode(), contents)
            self.assertNotIn(b'provider.invalid', contents)
            self.assertNotIn(credential, str(failure.exception))
            self.assertFalse((Path(directory)/'synthetic_request.json').exists())

    def test_reflected_credential_response_is_not_retained(self):
        credential = 'b'*32
        class Response:
            status = 200
            headers = {'Content-Type': 'application/json'}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, bound): return acquisition.canonical({'reflected': credential})
        with tempfile.TemporaryDirectory(prefix='alfred_reflection_test_', dir='/private/tmp') as directory:
            with self.assertRaises(acquisition.AcquisitionError):
                acquisition._request(directory, 'synthetic_request', acquisition.BASE_URL+'series', acquisition._common(), credential,
                                     opener=lambda request, timeout: Response())
            self.assertFalse((Path(directory)/'synthetic_request.json').exists())
            self.assertNotIn(credential.encode(), (Path(directory)/'synthetic_request.receipt.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
