"""Synthetic structural checks for ALFRED CES0500000003 PIT rows.

No network calls, real-data registration, timestamp inference or PIT query engine.
Cross-row ordering/source-field equality belong to the producer's integration tests.
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
SCHEMA = json.loads((ROOT/'specs/schemas/alfred_pit_rows.schema.json').read_text())


def synthetic_row():
    return {
        'series_id': 'CES0500000003', 'entity_id': 'US',
        'observation_date': '2000-01-01', 'vintage_date': '2000-02-04', 'next_vintage_date': '2000-03-03',
        'value': '12.25', 'status': 'valid', 'timing_precision': 'date',
        'raw_snapshot': {'id': 'SNAPSHOT_'+'a'*64, 'version': '1.0.0', 'content_sha256': 'b'*64},
        'source_view': {'id': 'SYNTHETIC_SOURCE_VIEW', 'version': '1.0.0', 'content_sha256': 'c'*64},
        'source_raw_blob_sha256': 'd'*64, 'source_field': 'CES0500000003_20000204',
    }


class AlfredPitSchemaStructureTests(unittest.TestCase):
    def test_all_objects_are_closed_and_references_local(self):
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
        self.assertNotIn('available_at', SCHEMA['$defs']['alfred_pit_row']['properties'])


@unittest.skipUnless(Draft202012Validator, 'optional jsonschema unavailable: ALFRED PIT Draft 2020-12 checks not run')
class AlfredPitFullSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        checker = FormatChecker()
        @checker.checks('date', raises=ValueError)
        def calendar_date(value):
            if isinstance(value, str): datetime.strptime(value, '%Y-%m-%d')
            return True
        cls.validator = Draft202012Validator(SCHEMA, format_checker=checker)
        cls.array_validator = Draft202012Validator({'$ref': '#/$defs/alfred_pit_rows', '$defs': SCHEMA['$defs']}, format_checker=checker)

    def assert_invalid(self, row):
        with self.assertRaises(ValidationError): self.validator.validate(row)

    def test_schema_and_synthetic_valid_missing_open_ended_rows(self):
        Draft202012Validator.check_schema(SCHEMA)
        valid = synthetic_row()
        missing = copy.deepcopy(valid)
        missing.update(value=None, status='missing', next_vintage_date=None)
        self.validator.validate(valid)
        self.validator.validate(missing)
        self.array_validator.validate([valid, missing])

    def test_invented_timestamps_unknown_fields_or_precision_are_rejected(self):
        row = synthetic_row()
        row['available_at'] = '2000-02-04T00:00:00.000000Z'
        self.assert_invalid(row)
        row = synthetic_row()
        row['timing_precision'] = 'second'
        self.assert_invalid(row)

    def test_required_lineage_and_original_column_identity_are_enforced(self):
        for field in ('raw_snapshot', 'source_view', 'source_raw_blob_sha256', 'source_field'):
            row = synthetic_row()
            del row[field]
            self.assert_invalid(row)
        for field, value in (('series_id', 'OTHER_SERIES'), ('entity_id', 'OTHER_ENTITY'),
                             ('source_field', 'CES0500000003_2000-02-04'), ('source_field', 'OTHER_20000204')):
            row = synthetic_row()
            row[field] = value
            self.assert_invalid(row)

    def test_unpinned_references_and_malformed_hashes_are_rejected(self):
        for field in ('raw_snapshot', 'source_view'):
            row = synthetic_row()
            row[field]['version'] = 'latest'
            self.assert_invalid(row)
            row = synthetic_row()
            row[field]['content_sha256'] = 'not-a-digest'
            self.assert_invalid(row)
        row = synthetic_row()
        row['raw_snapshot']['id'] = 'SYNTHETIC_UNHASHED_SNAPSHOT'
        self.assert_invalid(row)

    def test_noncanonical_decimal_or_numeric_float_values_are_rejected(self):
        for value in (12.25, '12.250', '1e2', '-0', '01', 'NaN', 'Infinity', '12.25\n'):
            row = synthetic_row()
            row['value'] = value
            self.assert_invalid(row)

    def test_missing_and_valid_statuses_cannot_misrepresent_values(self):
        row = synthetic_row()
        row['status'] = 'missing'
        self.assert_invalid(row)
        row = synthetic_row()
        row['value'] = None
        self.assert_invalid(row)
        row = synthetic_row()
        row['status'] = 'invalid'
        self.assert_invalid(row)

    def test_nonexistent_or_timestamp_calendar_dates_are_rejected(self):
        for field in ('observation_date', 'vintage_date', 'next_vintage_date'):
            for value in ('2000-02-31', '2000-2-04', '2000-02-04T00:00:00Z', '2000-02-04\n'):
                row = synthetic_row()
                row[field] = value
                self.assert_invalid(row)


if __name__ == '__main__':
    unittest.main()
