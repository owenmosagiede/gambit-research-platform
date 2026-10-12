"""Tests of the proposed v0.2 specification and synthetic examples, not a store.

Full Draft 2020-12 checks run when the optional jsonschema test dependency is
available. Pure fixture/identity assertions always run. No scientific engine,
production resolver, or production v0.2 hash implementation is introduced.
"""

import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import unittest

try:
    from jsonschema import Draft202012Validator, FormatChecker, ValidationError
except ImportError:
    Draft202012Validator = None


def format_checker():
    """Use a standard-library UTC checker; jsonschema extras are not installed."""
    checker = FormatChecker()
    @checker.checks('date-time', raises=ValueError)
    def actual_utc_date(value):
        if not isinstance(value, str):
            return True
        datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%fZ')
        return True
    return checker

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / 'specs/schemas/platform.schema.json').read_text())
FIXTURES = ROOT / 'tests/fixtures/specification_v0_2'
RECORDS = json.loads((FIXTURES / 'catalog_records.json').read_text())
ROWS = json.loads((FIXTURES / 'observation_rows.json').read_text())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')


def recipe_digest(recipe):
    """Fixture oracle for the documented recipe projection, not production API."""
    recipe = copy.deepcopy(recipe)
    recipe['sources'].sort(key=lambda item: item['alias'])
    for step in recipe['steps']:
        step['parameters'].sort(key=lambda item: item['name'])
    return hashlib.sha256(canonical({'identity_profile': '0.2.0', 'kind': 'predictor_recipe', 'recipe': recipe})).hexdigest()


def semantic_record(record):
    omitted = {'display_name'}
    if record.get('record_type') == 'snapshot_manifest':
        omitted.add('members')
    if record.get('record_type') == 'materialization_manifest':
        omitted.add('partitions')
    return {key: value for key, value in record.items() if key not in omitted}


def records(kind):
    return [record for record in RECORDS if record['record_type'] == kind]


def check_recipe_graph(recipe):
    """Small fixture acceptance oracle for graph/order requirements in the spec."""
    known = set()
    for source in recipe['sources']:
        if source['alias'] in known:
            raise ValueError('duplicate source alias')
        known.add(source['alias'])
    transformed = False
    for step in recipe['steps']:
        if step['node'] in known or not all(name in known for name in step['inputs']):
            raise ValueError('duplicate node or forward/missing input')
        if transformed and step['phase'] == 'interaction':
            raise ValueError('interaction follows transformation')
        transformed |= step['phase'] == 'transformation'
        names = [parameter['name'] for parameter in step['parameters']]
        if len(names) != len(set(names)):
            raise ValueError('duplicate parameter name')
        known.add(step['node'])
    if not transformed or recipe['output_node'] not in known:
        raise ValueError('no transformation or missing output')


class SpecificationFixtureTests(unittest.TestCase):
    def test_all_object_shapes_are_closed_and_refs_local(self):
        def walk(value):
            if isinstance(value, dict):
                if value.get('type') == 'object':
                    self.assertIs(value.get('additionalProperties'), False)
                if '$ref' in value:
                    name = value['$ref'].removeprefix('#/$defs/')
                    self.assertIn(name, SCHEMA['$defs'])
                if 'pattern' in value:
                    re.compile(value['pattern'])
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(SCHEMA)

    def test_one_parent_signal_groups_two_distinct_relationships(self):
        feature = records('feature_definition')[0]
        self.assertEqual(feature['id'], 'FEATURE_' + recipe_digest(feature['body']['recipe']))
        self.assertEqual(feature['body']['signal_id'], 'SIGNAL_' + recipe_digest(feature['body']['recipe']))
        relations = records('relationship_record')
        self.assertEqual(len(relations), 2)
        self.assertEqual({r['signal_id'] for r in relations}, {feature['body']['signal_id']})
        self.assertEqual(len({r['target']['id'] for r in relations}), 2)
        self.assertEqual(len({r['evaluation_scope']['id'] for r in relations}), 2)
        targets = records('target_definition')
        self.assertEqual({r['body']['horizon']['count'] for r in targets}, {'1', '5'})
        trials = records('trial_record')
        self.assertEqual(len({r['id'] for r in trials}), 2)
        self.assertEqual({r['scientific_key']['relationship']['id'] for r in trials}, {r['id'] for r in relations})

    def test_signal_parent_identity_excludes_evaluation_and_label(self):
        feature = records('feature_definition')[0]
        original = recipe_digest(feature['body']['recipe'])
        changed = copy.deepcopy(feature)
        changed['display_name'] = 'Another inert human label'
        changed['version'] = '2.0.0'
        self.assertEqual(recipe_digest(changed['body']['recipe']), original)
        for field in ('target', 'evaluation_scope', 'expected_direction', 'research_spec', 'evaluation_period'):
            self.assertNotIn(field, feature['body']['recipe'])

    def test_relationship_and_trial_fixture_ids_follow_domain_projections(self):
        for record in records('relationship_record'):
            projection = {key: record[key] for key in ('signal_id', 'target', 'evaluation_scope', 'expected_direction', 'mode')}
            projection.update(identity_profile='0.2.0', kind='relationship')
            self.assertEqual(record['id'], 'RELATIONSHIP_' + hashlib.sha256(canonical(projection)).hexdigest())
        for record in records('trial_record'):
            projection = {'identity_profile': '0.2.0', 'kind': 'trial', 'scientific_key': record['scientific_key']}
            self.assertEqual(record['id'], 'TRIAL_' + hashlib.sha256(canonical(projection)).hexdigest())
            self.assertIn(record['scientific_key']['resolved_experiment_id'], record['provenance']['resolved_experiment_ids'])

    def test_recipe_input_parameter_operator_and_order_change_identity(self):
        original = records('feature_definition')[0]['body']['recipe']
        digest = recipe_digest(original)
        changes = []
        changed = copy.deepcopy(original)
        changed['sources'][0]['source_view']['content_sha256'] = 'a' * 64
        changes.append(changed)
        changed = copy.deepcopy(original)
        changed['steps'][0]['parameters'][0]['value']['value'] = '4'
        changes.append(changed)
        changed = copy.deepcopy(original)
        changed['steps'][0]['operator']['version'] = '2.0.0'
        changes.append(changed)
        for changed in changes:
            self.assertNotEqual(recipe_digest(changed), digest)
        two = copy.deepcopy(original)
        second = copy.deepcopy(two['steps'][0])
        second['node'] = 'second'
        second['inputs'] = ['transformed']
        two['steps'].append(second)
        two['output_node'] = 'second'
        reversed_steps = copy.deepcopy(two)
        reversed_steps['steps'].reverse()
        self.assertNotEqual(recipe_digest(two), recipe_digest(reversed_steps))

    def test_named_lists_normalize_but_step_order_does_not(self):
        recipe = copy.deepcopy(records('feature_definition')[0]['body']['recipe'])
        source = copy.deepcopy(recipe['sources'][0])
        source['alias'] = 'another_source'
        recipe['sources'].append(source)
        extra = copy.deepcopy(recipe['steps'][0]['parameters'][0])
        extra['name'] = 'another_parameter'
        recipe['steps'][0]['parameters'].append(extra)
        reversed_named = copy.deepcopy(recipe)
        reversed_named['sources'].reverse()
        reversed_named['steps'][0]['parameters'].reverse()
        self.assertEqual(recipe_digest(recipe), recipe_digest(reversed_named))

    def test_recipe_graph_accepts_example_and_rejects_invalid_sequences(self):
        recipe = records('feature_definition')[0]['body']['recipe']
        check_recipe_graph(recipe)
        variants = []
        changed = copy.deepcopy(recipe)
        changed['steps'][0]['inputs'] = ['not_yet_defined']
        variants.append(changed)
        changed = copy.deepcopy(recipe)
        changed['steps'][0]['parameters'].append(copy.deepcopy(changed['steps'][0]['parameters'][0]))
        variants.append(changed)
        changed = copy.deepcopy(recipe)
        interaction = copy.deepcopy(changed['steps'][0])
        interaction.update(node='late_interaction', phase='interaction', inputs=['transformed'])
        changed['steps'].append(interaction)
        variants.append(changed)
        for changed in variants:
            with self.assertRaises(ValueError):
                check_recipe_graph(changed)

    def test_library_resolves_authoritative_results_without_metric_copies(self):
        by_id = {r['id']: r for r in RECORDS if 'id' in r}
        library = records('signal_library_entry')[0]
        self.assertNotIn('metrics', library)
        decisions = set()
        for group in library['relationship_results']:
            self.assertNotIn('metrics', group)
            relation = by_id[group['relationship']['id']]
            self.assertEqual(relation['signal_id'], library['signal_id'])
            for reference in group['trial_results']:
                trial = by_id[reference['id']]
                self.assertEqual(trial['scientific_key']['relationship']['id'], relation['id'])
                self.assertTrue(trial['metrics'])
            for reference in group['admission_results']:
                result = by_id[reference['id']]
                self.assertEqual(result['relationship']['id'], relation['id'])
                self.assertEqual(result['record_type'], 'admission_record')
                decisions.add(result['decision'])
            for reference in group['validation_results']:
                result = by_id[reference['id']]
                self.assertEqual(result['record_type'], 'validation_record')
                self.assertEqual(result['relationship']['id'], relation['id'])
                self.assertEqual(result['decision'], 'failed')
                self.assertIsNone(result['evaluation_trial'])
                self.assertEqual(result['metrics'], [])
        self.assertEqual(decisions, {'admitted', 'rejected'})

    def test_fixture_references_match_included_immutable_records(self):
        by_id = {r['id']: r for r in RECORDS if 'id' in r}
        def walk(value):
            if isinstance(value, dict):
                if set(value) == {'id', 'version', 'content_sha256'} and value['id'] in by_id:
                    target = by_id[value['id']]
                    self.assertEqual(value['version'], target['version'])
                    semantic = semantic_record(target)
                    self.assertEqual(value['content_sha256'], hashlib.sha256(canonical(semantic)).hexdigest())
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(RECORDS)

    def test_representation_bytes_do_not_change_semantic_snapshot_or_materialization(self):
        for kind, physical, logical in (('snapshot_manifest', 'members', 'semantic_content_sha256'),
                                       ('materialization_manifest', 'partitions', 'semantic_rows_sha256')):
            original = records(kind)[0]
            repacked = copy.deepcopy(original)
            repacked[physical][0]['blob_sha256'] = 'f' * 64
            repacked[physical][0]['byte_count'] += 1
            self.assertNotEqual(canonical(original), canonical(repacked))
            self.assertEqual(canonical(semantic_record(original)), canonical(semantic_record(repacked)))
            changed_rows = copy.deepcopy(original)
            changed_rows[logical] = 'e' * 64
            self.assertNotEqual(canonical(semantic_record(original)), canonical(semantic_record(changed_rows)))

    def test_materialization_identity_uses_frozen_inputs_before_output_rows(self):
        fields = ('dataset_role', 'definition', 'source_snapshots', 'upstream_materializations', 'calculation_scope',
                  'membership_snapshot', 'information_cutoff', 'period', 'observation_schema_version', 'implementation', 'policy_bindings')
        for record in records('materialization_manifest'):
            projection = {'identity_profile': '0.2.0', 'kind': 'materialization', 'input_key': {key: record[key] for key in fields}}
            expected = 'MATERIALIZATION_' + hashlib.sha256(canonical(projection)).hexdigest()
            self.assertEqual(record['id'], expected)
            changed = copy.deepcopy(record)
            changed['semantic_rows_sha256'] = 'a' * 64
            changed_projection = {'identity_profile': '0.2.0', 'kind': 'materialization', 'input_key': {key: changed[key] for key in fields}}
            self.assertEqual(projection, changed_projection)
            self.assertNotEqual(semantic_record(record), semantic_record(changed))

    def test_admitted_p1_example_does_not_establish_p3_eligibility(self):
        by_id = {r['id']: r for r in RECORDS if 'id' in r}
        admissions = records('admission_record')
        self.assertEqual(len(admissions), 2)
        for admission in admissions:
            trial = by_id[admission['trial']['id']]
            policy = by_id[admission['policy']['id']]
            eligible = admission['record_type'] == 'validation_record' and admission['decision'] == 'validated' and trial['scientific_key']['stage'] == 'P2' and policy['body']['approval_state'] == 'approved'
            self.assertFalse(eligible)

    def test_failed_p2_precheck_preserves_context_without_inventing_evaluation(self):
        by_id = {r['id']: r for r in RECORDS if 'id' in r}
        validation = records('validation_record')[0]
        self.assertEqual(validation['decision'], 'failed')
        self.assertEqual(by_id[validation['trial']['id']]['scientific_key']['stage'], 'P1')
        self.assertIsNone(validation['evaluation_trial'])
        self.assertEqual(validation['metrics'], [])
        self.assertTrue(validation['research_spec'])
        self.assertTrue(validation['evaluation_period'])
        self.assertTrue(validation['implementation'])


@unittest.skipUnless(Draft202012Validator, 'optional jsonschema dependency unavailable: Draft 2020-12 checks not run')
class FullJsonSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = Draft202012Validator(SCHEMA, format_checker=format_checker())
        cls.row_validator = Draft202012Validator({'$ref': '#/$defs/observation_row', '$defs': SCHEMA['$defs']}, format_checker=format_checker())

    def test_draft202012_schema_and_all_record_examples(self):
        Draft202012Validator.check_schema(SCHEMA)
        for record in RECORDS:
            with self.subTest(record=record.get('id', record['record_type'])):
                self.validator.validate(record)
        for row in ROWS:
            self.row_validator.validate(row)

    def test_frozen_foundation_schema_and_fixtures_with_engine(self):
        foundation = json.loads((ROOT / 'specs/schemas/contracts.schema.json').read_text())
        Draft202012Validator.check_schema(foundation)
        validator = Draft202012Validator(foundation)
        for name in ('synthetic_experiment.json', 'synthetic_submission.json', 'synthetic_resolved_experiment.json'):
            validator.validate(json.loads((ROOT / 'tests/fixtures' / name).read_text()))

    def test_p1_admission_and_p2_validation_have_distinct_decision_vocabularies(self):
        admission = copy.deepcopy(records('admission_record')[0])
        self.validator.validate(admission)
        validation = copy.deepcopy(records('validation_record')[0])
        self.validator.validate(validation)
        for decision in ('admitted', 'rejected'):
            invalid = copy.deepcopy(validation)
            invalid['decision'] = decision
            with self.assertRaises(ValidationError):
                self.validator.validate(invalid)
        for decision in ('validated', 'failed'):
            invalid = copy.deepcopy(admission)
            invalid['decision'] = decision
            with self.assertRaises(ValidationError):
                self.validator.validate(invalid)

    def test_p2_validation_cannot_claim_success_or_metrics_without_evaluation(self):
        validation = copy.deepcopy(records('validation_record')[0])
        validation['decision'] = 'validated'
        with self.assertRaises(ValidationError):
            self.validator.validate(validation)
        validation = copy.deepcopy(records('validation_record')[0])
        validation['metrics'] = copy.deepcopy(records('trial_record')[0]['metrics'])
        with self.assertRaises(ValidationError):
            self.validator.validate(validation)

    def test_unknown_fields_and_library_metric_copies_rejected(self):
        for source in (records('feature_definition')[0], records('signal_library_entry')[0], records('relationship_record')[0]):
            candidate = copy.deepcopy(source)
            candidate['metrics'] = []
            with self.assertRaises(ValidationError):
                self.validator.validate(candidate)
        candidate = copy.deepcopy(records('signal_library_entry')[0])
        candidate['relationship_results'][0]['metrics'] = []
        with self.assertRaises(ValidationError):
            self.validator.validate(candidate)

    def test_unpinned_reference_and_float_parameter_rejected(self):
        for version in ('latest', '1.x', '1.0.0-beta'):
            candidate = copy.deepcopy(records('feature_definition')[0])
            candidate['body']['recipe']['steps'][0]['operator']['version'] = version
            with self.assertRaises(ValidationError):
                self.validator.validate(candidate)
        candidate = copy.deepcopy(records('feature_definition')[0])
        candidate['body']['recipe']['steps'][0]['parameters'][0]['value'] = {'kind': 'decimal', 'value': 0.1}
        with self.assertRaises(ValidationError):
            self.validator.validate(candidate)

    def test_canonical_decimal_strings_reject_alternative_spellings(self):
        v = Draft202012Validator({'$ref': '#/$defs/decimal', '$defs': SCHEMA['$defs']})
        for valid in ('0', '1', '-1', '0.01', '-0.01', '12.301'):
            v.validate(valid)
        for invalid in ('-0', '01', '1.0', '0.10', '+1', '1e2', '.1', '1.', 'NaN', 'Infinity', '1\n'):
            with self.assertRaises(ValidationError):
                v.validate(invalid)

    def test_missing_observation_cannot_claim_valid_value(self):
        candidate = copy.deepcopy(ROWS[1])
        candidate['value'] = '0'
        with self.assertRaises(ValidationError):
            self.row_validator.validate(candidate)
        candidate = copy.deepcopy(ROWS[0])
        candidate['available_at'] = None
        with self.assertRaises(ValidationError):
            self.row_validator.validate(candidate)

    def test_empty_materialization_has_no_partitions_or_nonzero_status_counts(self):
        original = records('materialization_manifest')[0]
        empty = copy.deepcopy(original)
        empty.update(partitions=[], row_count=0, status_counts={'valid': 0, 'missing': 0, 'invalid': 0},
                     semantic_rows_sha256=hashlib.sha256(canonical([])).hexdigest())
        self.validator.validate(empty)
        invalid_variants = []
        nonzero_rows = copy.deepcopy(empty)
        nonzero_rows['row_count'] = 1
        invalid_variants.append(nonzero_rows)
        nonzero_status = copy.deepcopy(empty)
        nonzero_status['status_counts']['missing'] = 1
        invalid_variants.append(nonzero_status)
        unexpected_partition = copy.deepcopy(empty)
        unexpected_partition['partitions'] = copy.deepcopy(original['partitions'])
        invalid_variants.append(unexpected_partition)
        empty_partition = copy.deepcopy(original)
        empty_partition['partitions'][0]['row_count'] = 0
        invalid_variants.append(empty_partition)
        for candidate in invalid_variants:
            with self.assertRaises(ValidationError):
                self.validator.validate(candidate)
    def test_scope_dependent_recipe_requires_policy_binding(self):
        candidate = copy.deepcopy(records('feature_definition')[0])
        candidate['body']['recipe']['calculation_scope_requirement'] = 'bound_at_materialization'
        with self.assertRaises(ValidationError):
            self.validator.validate(candidate)

    def test_utc_timestamp_rejects_nonexistent_calendar_date(self):
        candidate = copy.deepcopy(ROWS[0])
        candidate['observation_time'] = '2000-02-31T00:00:00.000000Z'
        with self.assertRaises(ValidationError):
            self.row_validator.validate(candidate)


if __name__ == '__main__':
    unittest.main()
