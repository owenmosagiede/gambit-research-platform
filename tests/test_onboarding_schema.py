"""Synthetic checks for the additive ALFRED onboarding schema, not provider tests.

Run full Draft 2020-12 checks with the optional jsonschema test dependency. This
module makes no network requests, registers no definitions and certifies no data.
"""

import copy
from datetime import datetime
import json
from pathlib import Path
import re
import unittest

try:
    from jsonschema import Draft202012Validator, FormatChecker, ValidationError
except ImportError:
    Draft202012Validator = None

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT/'specs/schemas/onboarding.schema.json').read_text())
STAMP = '2000-01-01T00:00:00.000000Z'
LATER = '2000-01-02T00:00:00.000000Z'
ENDPOINT = 'https://api.stlouisfed.org/fred/series/observations'


def reference(identifier):
    return {'id': identifier, 'version': '1.0.0', 'content_sha256': 'a'*64}


def record(kind, body):
    return {'schema_version': '0.1.0', 'record_type': kind, 'id': 'SYNTHETIC_' + kind.upper(), 'version': '1.0.0', 'body': body}


def provider():
    return record('provider_contract', {
        'provider': 'FRED_ALFRED', 'native_series_id': 'SYNTHETIC_SERIES',
        'official_endpoints': [{'role': 'series_observations', 'url': ENDPOINT}],
        'official_documentation': ['https://alfred.stlouisfed.org/'],
        'units': 'Synthetic units', 'frequency': 'Synthetic frequency', 'seasonal_adjustment': 'Synthetic adjustment',
        'availability_policy': reference('SYNTHETIC_POLICY'),
        'vintage_limitations': [{'code': 'ARCHIVE_DATE_ONLY', 'detail': 'Synthetic shape; archived vintage dates do not prove actual historical receipt or intraday availability.'}],
        'requested_live_scope': {'capability': 'live_api_daily_pull', 'cadence': 'daily', 'decision_clock_ready': False},
    })


def receipt(mode='legacy_import'):
    legacy = mode == 'legacy_import'
    return record('ingestion_receipt', {
        'mode': mode, 'dataset': reference('SYNTHETIC_DATASET'), 'provider_contract': reference('SYNTHETIC_PROVIDER'),
        'request': {'endpoint': None if legacy else ENDPOINT, 'parameters': [] if legacy else [{'name': 'series_id', 'value': 'SYNTHETIC_SERIES'}]},
        'retrieval': {'original_started_at': None if legacy else STAMP, 'original_finished_at': None if legacy else LATER, 'captured_at': LATER},
        'response': {'http_status': None if legacy else 200, 'headers': [], 'content_type': None if legacy else 'application/json', 'content_encoding': None},
        'payload': {'sha256': 'b'*64, 'byte_count': 2, 'row_count': 0},
        'source_evidence': {'legacy_store_id': 'SYNTHETIC_LEGACY' if legacy else None, 'legacy_relative_path': 'synthetic/source.json' if legacy else None, 'source_sha256': 'b'*64 if legacy else None},
        'completeness': {'outcome': 'complete', 'reason_codes': [], 'errors': []},
    })


def assessment(capability='historical_replay'):
    return record('capability_assessment', {
        'capability': capability, 'decision': 'ready', 'dataset': reference('SYNTHETIC_DATASET'),
        'provider_contract': reference('SYNTHETIC_PROVIDER'), 'snapshot': reference('SYNTHETIC_SNAPSHOT'),
        'policy': reference('SYNTHETIC_POLICY'), 'implementation': reference('SYNTHETIC_IMPLEMENTATION'),
        'evidence': [reference('SYNTHETIC_EVIDENCE')], 'interval': {'start_inclusive': STAMP, 'end_exclusive': LATER},
        'limitations': [{'code': 'SHAPE_ONLY', 'detail': 'Fictional structural example; no real readiness claim.'}],
        'checks': [{'code': 'SYNTHETIC_CHECK', 'outcome': 'pass', 'evidence': [reference('SYNTHETIC_EVIDENCE')], 'detail': 'Synthetic shape only.'}],
        'issued_at': LATER,
    })


class OnboardingSchemaStructureTests(unittest.TestCase):
    def test_all_objects_closed_and_references_local(self):
        def walk(value):
            if isinstance(value, dict):
                if value.get('type') == 'object':
                    self.assertIs(value.get('additionalProperties'), False)
                if '$ref' in value:
                    self.assertTrue(value['$ref'].startswith('#/$defs/'))
                    self.assertIn(value['$ref'][8:], SCHEMA['$defs'])
                if 'pattern' in value:
                    re.compile(value['pattern'])
                for child in value.values(): walk(child)
            elif isinstance(value, list):
                for child in value: walk(child)
        walk(SCHEMA)
        self.assertEqual(len(SCHEMA['oneOf']), 4)


@unittest.skipUnless(Draft202012Validator, 'optional jsonschema unavailable: onboarding Draft 2020-12 checks not run')
class OnboardingFullSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        checker = FormatChecker()
        @checker.checks('date-time', raises=ValueError)
        def actual_utc_date(value):
            if isinstance(value, str): datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%fZ')
            return True
        cls.validator = Draft202012Validator(SCHEMA, format_checker=checker)

    def assert_invalid(self, value):
        with self.assertRaises(ValidationError): self.validator.validate(value)

    def test_draft202012_and_synthetic_record_shapes(self):
        Draft202012Validator.check_schema(SCHEMA)
        evidence = record('onboarding_evidence', {'kind': 'synthetic_audit', 'payload': {'sha256': 'c'*64, 'byte_count': 2, 'row_count': None},
            'media_type': 'application/json', 'description': 'Synthetic evidence reference; no payload exists.'})
        for value in (provider(), receipt(), receipt('api_download'), assessment(), assessment('live_api_daily_pull'), evidence):
            self.validator.validate(value)

    def test_legacy_unknown_retrieval_is_not_filled_with_import_time(self):
        value = receipt()
        self.validator.validate(value)
        self.assertIsNone(value['body']['retrieval']['original_started_at'])
        self.assertIsNone(value['body']['response']['http_status'])
        value['body']['source_evidence']['source_sha256'] = None
        self.assert_invalid(value)

    def test_new_download_requires_observed_times_and_success_status(self):
        for field in ('original_started_at', 'original_finished_at'):
            value = receipt('api_download')
            value['body']['retrieval'][field] = None
            self.assert_invalid(value)
        value = receipt('api_download')
        value['body']['response']['http_status'] = 500
        self.assert_invalid(value)

    def test_transport_failure_preserves_no_payload_without_inventing_hash(self):
        value = receipt('api_download')
        value['body']['payload'] = None
        value['body']['response']['http_status'] = None
        value['body']['completeness'] = {'outcome': 'failed', 'reason_codes': ['SYNTHETIC_TRANSPORT_FAILURE'], 'errors': [{'code': 'SYNTHETIC_TIMEOUT', 'message': 'Synthetic timeout.'}]}
        self.validator.validate(value)
        value['body']['completeness'] = {'outcome': 'complete', 'reason_codes': [], 'errors': []}
        self.assert_invalid(value)

    def test_credentials_cannot_be_recorded_as_request_parameters_or_headers(self):
        value = receipt('api_download')
        value['body']['request']['parameters'].append({'name': 'api_key', 'value': 'SYNTHETIC_NOT_A_SECRET'})
        self.assert_invalid(value)
        value = receipt('api_download')
        value['body']['request']['endpoint'] += '?api_key=SYNTHETIC_NOT_A_SECRET'
        self.assert_invalid(value)
        value = receipt('api_download')
        value['body']['response']['headers'] = [{'name': 'set-cookie', 'value': 'SYNTHETIC_NOT_A_SECRET'}]
        self.assert_invalid(value)

    def test_ready_cannot_contain_failed_unresolved_or_evidenceless_checks(self):
        for outcome in ('fail', 'unresolved'):
            value = assessment()
            value['body']['checks'][0]['outcome'] = outcome
            self.assert_invalid(value)
        value = assessment()
        value['body']['checks'][0]['evidence'] = []
        self.assert_invalid(value)
        value = assessment()
        value['body']['snapshot'] = None
        self.assert_invalid(value)

    def test_daily_pull_cannot_claim_decision_clock_live_generation(self):
        value = assessment()
        value['body']['capability'] = 'live_generation'
        self.assert_invalid(value)
        value = provider()
        value['body']['requested_live_scope']['decision_clock_ready'] = True
        self.assert_invalid(value)

    def test_unresolved_capability_can_preserve_missing_snapshot_and_failures(self):
        value = assessment()
        value['body'].update(decision='unresolved', snapshot=None, evidence=[])
        value['body']['checks'][0].update(outcome='unresolved', evidence=[])
        self.validator.validate(value)

    def test_unknown_fields_bad_dates_and_unsafe_legacy_paths_rejected(self):
        value = receipt()
        value['body']['retrieval']['guessed_download_time'] = STAMP
        self.assert_invalid(value)
        value = receipt()
        value['body']['retrieval']['captured_at'] = '2000-02-31T00:00:00.000000Z'
        self.assert_invalid(value)
        for path in ('/absolute/source.json', '../source.json', 'safe/../source.json', './source.json'):
            value = receipt()
            value['body']['source_evidence']['legacy_relative_path'] = path
            self.assert_invalid(value)


if __name__ == '__main__':
    unittest.main()
