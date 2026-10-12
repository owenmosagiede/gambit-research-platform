"""Formal FX source schema checks, separate from implementation hash checks."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from test_fx_onboarding import build_fixture
from data.fx_onboarding import onboard, read_source
from data.feature_store import FeatureStore

PROJECT = Path(__file__).resolve().parents[1]


class FXSourceSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root, legacy, audit, _ = build_fixture(Path(cls.temp.name))
        output = onboard(root, legacy, audit, migration_time='2026-10-09T10:00:00Z')
        cls.stored = read_source(root, output['sources'][0]['pit_snapshot'])
        cls.raw = FeatureStore(root).resolve(output['sources'][0]['raw_snapshot'])
        cls.schema = json.loads((PROJECT / 'specs/schemas/fx.schema.json').read_text())
        Draft202012Validator.check_schema(cls.schema)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def validator(self, name):
        return Draft202012Validator({'$ref':'#/$defs/' + name, '$defs': self.schema['$defs']}, format_checker=FormatChecker())

    def test_source_rows_snapshot_and_lineage_validate(self):
        for row in self.stored['observations']:
            self.validator('source_observation').validate(row)
        for row in self.stored['lineage']:
            self.validator('source_lineage').validate(row)
        self.validator('registry').validate(self.stored['manifest'])
        self.validator('registry').validate(self.raw)

    def test_source_cannot_claim_historical_availability(self):
        for field in ('available_at', 'source_vintage_at'):
            row = deepcopy(self.stored['observations'][0]); row[field] = '2020-01-03T00:00:00Z'
            with self.assertRaises(ValidationError): self.validator('source_observation').validate(row)

    def test_source_cannot_replace_native_date_with_timestamp(self):
        row = deepcopy(self.stored['observations'][0]); row['reference_time'] += 'T00:00:00Z'
        with self.assertRaises(ValidationError): self.validator('source_observation').validate(row)

    def test_source_quote_direction_and_values_are_typed(self):
        for field, value in [('unit','AUD_per_USD'),('value','0'),('value','NaN'),('value',1.5),('legacy_revision_number',1)]:
            row = deepcopy(self.stored['observations'][0]); row[field] = value
            with self.assertRaises(ValidationError): self.validator('source_observation').validate(row)

    def test_snapshot_does_not_accept_exact_timing_or_midpoint_claim(self):
        for mutation in ('basis','timing','readiness'):
            snapshot = deepcopy(self.stored['manifest'])
            if mutation == 'basis': snapshot['body']['source_metadata']['price_basis'] = 'midpoint'
            elif mutation == 'timing': snapshot['body']['source_metadata']['timing']['synchronization'] = 'exact'
            else: snapshot['body']['readiness']['historical_replay'] = 'ready'
            with self.assertRaises(ValidationError): self.validator('registry').validate(snapshot)

    def test_snapshot_requires_complete_shape_and_valid_payload_counts(self):
        for mutation in ('count','bytes','codec','state','extra'):
            snapshot = deepcopy(self.stored['manifest'])
            if mutation == 'count': snapshot['body']['record_count'] = -1
            elif mutation == 'bytes': snapshot['body']['members'][0]['byte_count'] = -1
            elif mutation == 'codec': snapshot['body']['members'][0]['codec'] = 'unknown'
            elif mutation == 'state': snapshot['body']['completion_state'] = 'partial'
            else: snapshot['body']['publication_time'] = '2020-01-03T00:00:00Z'
            with self.assertRaises(ValidationError): self.validator('registry').validate(snapshot)


if __name__ == '__main__': unittest.main()
