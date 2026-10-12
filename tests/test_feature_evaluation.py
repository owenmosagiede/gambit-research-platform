"""Synthetic acceptance of the approved native-date evaluation rule.

Only transformation metadata is copied into temporary fixture storage. No
production observations, provider APIs or actual publication are used here.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
from data.feature_evaluation import (execute_scheduled_recipe, resolve_native_schedule,
    EvaluationPolicyError, EVALUATION_POLICY_ID)
from data.first_signal_trial import install_approved_policy
from data.transformations import engine
from data.transformations.contracts import ContractError, normalize_result
from data.transformations.identity import (reference, make_feature_definition,
    execution_materialization_id)
from data.transformations.registry import Registry
from test_transformation_engine import fixture, recipe_for, ref
from test_feature_store import _copy_metadata_closure

ROOT = Path(__file__).resolve().parents[1]
EXECUTED = '2026-10-09T12:00:00.000000Z'
IMPLEMENTATION = ref('IMPLEMENTATION_SCHEDULE_FIXTURE')


class FeatureEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix='feature_schedule_', dir='/private/tmp')
        cls.addClassCleanup(cls.workspace.cleanup)
        cls.root = Path(cls.workspace.name)
        shutil.copytree(ROOT/'specs/schemas', cls.root/'specs/schemas')
        approved = Registry(ROOT)
        _copy_metadata_closure(cls.root, [approved.operator('TR_BASE_change_pct'),
            approved.get_policy('POL_TRANSFORM_EXECUTION'), approved.get_policy('POL_TRANSFORM_HISTORY')])
        cls.policy = install_approved_policy(cls.root, ref('VIEW_SYNTHETIC'))
        cls.registry = Registry(cls.root)

    def source(self, rows):
        """Rows declare explicit reference, native availability and value."""
        result = fixture(self.registry, [row[2] for row in rows],
                         times=[row[0] for row in rows], frequency='monthly')
        result.pop('release_events')
        result['capabilities'] = ['revision_history']
        result['cadence']['gap_policy'] = 'explicit_missing'
        for row, (_, available, _) in zip(result['observations'], rows):
            row['available_at'] = available
        return result

    def recipe(self, source):
        recipe = recipe_for(self.registry, source, [('TR_BASE_change_pct', {'k': 1})], unit='dimensionless')
        recipe['evaluation_policy'] = self.policy
        return recipe

    def execute(self, source, recipe=None):
        return execute_scheduled_recipe(source, recipe or self.recipe(source), registry=self.registry,
                                        implementation=IMPLEMENTATION, executed_at=EXECUTED)

    def test_all_native_cutoffs_once_and_full_history_fast_path(self):
        source = self.source([('2020-01-01','2020-03-05',100),
            ('2020-02-01','2020-03-05',110),('2020-03-01','2020-04-05',121)])
        before = deepcopy(source)
        with patch('data.transformations.engine.execute_recipe', wraps=engine.execute_recipe) as execute:
            actual = self.execute(source)
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(actual['cutoffs'], ['2020-03-05','2020-04-05'])
        self.assertEqual(actual['result']['execution']['cutoffs'], actual['cutoffs'])
        self.assertEqual(len(actual['operand_links']), 2)
        self.assertEqual(len(actual['result']['observations']), 2)
        self.assertEqual([r['reference_time'] for r in actual['result']['observations']], ['2020-02-01','2020-03-01'])
        for row in actual['result']['observations']:
            self.assertAlmostEqual(float(row['value']), .1)
            self.assertEqual(row['available_at'], row['evaluation_cutoff'])
        self.assertEqual(source, before)
        self.assertEqual(normalize_result(actual['result']), actual['result'])
        self.assertEqual(actual['result']['unit'], 'dimensionless')
        self.assertEqual(actual['result']['value_semantics'], 'fractional_change')

    def test_same_reference_revision_has_distinct_cutoff_and_same_state_operands(self):
        source = self.source([('2020-01-01','2020-03-05',100),('2020-02-01','2020-03-05',110),
            ('2020-01-01','2020-03-15',105),('2020-03-01','2020-04-05',121)])
        actual = self.execute(source)
        rows = actual['result']['observations']
        self.assertEqual([r['reference_time'] for r in rows], ['2020-02-01','2020-02-01','2020-03-01'])
        self.assertAlmostEqual(float(rows[0]['value']), .1)
        self.assertAlmostEqual(float(rows[1]['value']), 1/21)
        self.assertEqual(actual['operand_links'][0]['denominator'], source['observations'][0]['lineage'])
        self.assertEqual(actual['operand_links'][1]['denominator'], source['observations'][2]['lineage'])
        self.assertEqual(actual['operand_links'][0]['numerator'], actual['operand_links'][1]['numerator'])
        self.assertNotEqual(rows[0]['evaluation_cutoff'], rows[1]['evaluation_cutoff'])

    def test_future_vintage_and_future_reference_do_not_leak(self):
        base = self.source([('2020-01-01','2020-03-05',100),('2020-02-01','2020-03-05',110)])
        extended = self.source([('2020-01-01','2020-03-05',100),('2020-02-01','2020-03-05',110),
            ('2020-01-01','2020-03-15',1000),('2020-04-01','2020-03-20',9999)])
        expected = self.execute(base)['result']['observations'][0]
        actual = self.execute(extended)['result']['observations']
        self.assertEqual(expected['value'], actual[0]['value'])
        self.assertEqual(actual[-1]['reference_time'], '2020-02-01')
        self.assertAlmostEqual(float(actual[-1]['value']), -.89)
        self.assertEqual(actual[-1]['evaluation_cutoff'], '2020-03-20')

    def test_previous_calendar_month_not_previous_emitted_reference(self):
        source = self.source([('2020-01-01','2020-03-05',100),('2020-02-01','2020-03-05',110),
            ('2020-03-01','2020-05-05',121),('2020-04-01','2020-05-05',133.1)])
        actual = self.execute(source)
        rows = actual['result']['observations']
        self.assertEqual([r['reference_time'] for r in rows], ['2020-02-01','2020-04-01'])
        self.assertAlmostEqual(float(rows[-1]['value']), .1)
        self.assertEqual(actual['operand_links'][-1]['denominator'], source['observations'][2]['lineage'])
        self.assertNotEqual(actual['operand_links'][-1]['denominator'], actual['operand_links'][0]['numerator'])

    def test_missing_required_period_retains_null_and_never_creates_source_row(self):
        source = self.source([('2020-01-01','2020-02-05',100),('2020-03-01','2020-04-05',121)])
        before = deepcopy(source)
        with patch('data.transformations.engine.execute_recipe', wraps=engine.execute_recipe) as execute:
            actual = self.execute(source)
        self.assertEqual(execute.call_count, 0)
        self.assertEqual(source, before)
        self.assertEqual(actual['result']['execution']['status'], 'no_valid_output')
        self.assertEqual(len(actual['result']['observations']), 2)
        for row, links in zip(actual['result']['observations'], actual['operand_links']):
            self.assertEqual(row['reason_code'], 'MISSING_PERIOD')
            self.assertIsNone(row['value'])
            self.assertEqual(set(links), {'numerator'})
        records = actual['result']['execution']['lineage_records']
        self.assertTrue(any(any(item['role']=='numerator' for item in r['inputs']) for r in records))
        self.assertFalse(any(any(item['role']=='denominator' for item in r['inputs']) for r in records))
        self.assertEqual(normalize_result(actual['result']), actual['result'])

    def test_older_unrelated_gap_does_not_hide_actual_adjacent_operands(self):
        source = self.source([('2020-01-01','2020-03-05',100),('2020-03-01','2020-04-05',121),
            ('2020-04-01','2020-05-05',133.1)])
        before = deepcopy(source)
        with patch('data.transformations.engine.execute_recipe', wraps=engine.execute_recipe) as execute:
            actual = self.execute(source)
        self.assertEqual(execute.call_count, 1)
        pair = execute.call_args.args[0]['observations']
        self.assertEqual([r['reference_time'] for r in pair], ['2020-03-01','2020-04-01'])
        self.assertEqual(source, before)
        rows = actual['result']['observations']
        self.assertEqual([r['reason_code'] for r in rows], ['MISSING_PERIOD','MISSING_PERIOD',None])
        self.assertAlmostEqual(float(rows[-1]['value']), .1)
        expected_id = execution_materialization_id(reference(make_feature_definition(self.recipe(source))),
            source, actual['cutoffs'], IMPLEMENTATION, engine._policies(self.recipe(source)),
            output_index=[{'reference_time':r['reference_time'],'evaluation_cutoff':r['evaluation_cutoff']} for r in rows])
        self.assertEqual(actual['result']['execution']['materialization_id'], expected_id)
        platform = json.loads((ROOT/'specs/schemas/platform.schema.json').read_text())
        for record in actual['result']['execution']['lineage_records']:
            Draft202012Validator(platform).validate(record)
        refs = {reference(record)['id'] for record in actual['result']['execution']['lineage_records']}
        self.assertTrue(all(row['lineage']['id'] in refs for row in rows))

    def test_missing_values_and_zero_denominator_keep_engine_failure_reasons(self):
        for values, reason in [([None,110],'SOURCE_MISSING'),([100,None],'SOURCE_MISSING'),([0,110],'ZERO_DENOMINATOR')]:
            with self.subTest(values=values):
                source = self.source([('2020-01-01','2020-03-05',values[0]),('2020-02-01','2020-03-05',values[1])])
                actual = self.execute(source)
                row = actual['result']['observations'][0]
                self.assertIsNone(row['value'])
                self.assertEqual(row['reason_code'], reason)
                self.assertEqual(set(actual['operand_links'][0]), {'numerator','denominator'})

    def test_no_current_reference_retains_scheduled_null_without_fake_anchor(self):
        source = self.source([('2020-04-01','2020-03-05',100)])
        actual = self.execute(source)
        self.assertEqual(actual['cutoffs'], ['2020-03-05'])
        self.assertEqual(actual['operand_links'], [{}])
        self.assertIsNone(actual['result']['observations'][0]['reference_time'])
        self.assertEqual(actual['result']['observations'][0]['reason_code'], 'MISSING_PERIOD')

    def test_187_fixture_native_dates_produce_exactly_187_unique_outputs(self):
        # Count is fixture evidence only, never a hardcoded implementation limit.
        rows = [('2000-01-01','2000-03-05',100),('2000-02-01','2000-03-05',110)]
        for index in range(1,187):
            reference = 2000*12+1+index
            cutoff = reference+1
            rows.append((f'{reference//12:04d}-{reference%12+1:02d}-01',
                         f'{cutoff//12:04d}-{cutoff%12+1:02d}-05',110+index))
        actual = self.execute(self.source(rows))
        self.assertEqual(len(actual['result']['observations']),187)
        self.assertEqual(len(set(actual['cutoffs'])),187)
        self.assertEqual(actual['result']['execution']['status'],'complete')
        self.assertEqual(len({(row['reference_time'],row['evaluation_cutoff']) for row in actual['result']['observations']}),187)

    def test_policy_scope_rules_types_approval_and_presence_are_strict(self):
        source = self.source([('2020-01-01','2020-03-05',100),('2020-02-01','2020-03-05',110)])
        recipe = self.recipe(source)
        absent = deepcopy(recipe);absent.pop('evaluation_policy')
        with self.assertRaises(EvaluationPolicyError):resolve_native_schedule(source,absent,self.registry)
        altered_source = deepcopy(source);altered_source['source_view']=ref('VIEW_OTHER')
        with self.assertRaises(EvaluationPolicyError):resolve_native_schedule(altered_source,recipe,self.registry)
        original = self.registry.get_policy(EVALUATION_POLICY_ID)
        for case in ('rule','extra','duplicate','unit','kind','approval','policy_kind'):
            policy = deepcopy(original)
            if case=='rule':policy['body']['parameters'][0]['value']['value']='invented_daily_grid'
            elif case=='extra':policy['body']['parameters'].append({'name':'extra','unit':'policy_setting','value':{'kind':'token','value':'unknown'}})
            elif case=='duplicate':policy['body']['parameters'].append(deepcopy(policy['body']['parameters'][0]))
            elif case=='unit':policy['body']['parameters'][0]['unit']='wrong'
            elif case=='kind':policy['body']['parameters'][0]['value']={'kind':'integer','value':'1'}
            elif case=='approval':policy['body']['approval_state']='proposed'
            else:policy['body']['kind']='availability'
            changed = deepcopy(recipe);changed['evaluation_policy']=reference(policy)
            with patch.dict(self.registry._policies,{(policy['id'],policy['version']):policy}):
                with self.subTest(case=case),self.assertRaises(ValueError):resolve_native_schedule(source,changed,self.registry)

    def test_wrong_mode_cadence_ambiguous_month_and_unsupported_recipe_reject(self):
        source = self.source([('2020-01-01','2020-03-05',100),('2020-02-01','2020-03-05',110)])
        wrong = self.recipe(source);wrong['history_mode']='emitted_history'
        with self.assertRaises(EvaluationPolicyError):resolve_native_schedule(source,wrong,self.registry)
        wrong_source = deepcopy(source);wrong_source['cadence']['frequency']='daily'
        with self.assertRaises(EvaluationPolicyError):resolve_native_schedule(wrong_source,self.recipe(source),self.registry)
        ambiguous = self.source([('2020-01-01','2020-03-05',100),('2020-01-15','2020-03-05',110)])
        with self.assertRaises(EvaluationPolicyError):self.execute(ambiguous)
        wrong = self.recipe(source);wrong['steps'][0]['parameters'][0]['value']['value']='2'
        with self.assertRaises(EvaluationPolicyError):self.execute(source,wrong)
        wrong_source = deepcopy(source);wrong_source['history_policy']=ref('POL_OTHER')
        with self.assertRaises(ValueError):self.execute(wrong_source)

    def test_execution_time_and_provider_labels_do_not_change_materialization_identity(self):
        source = self.source([('2020-01-01','2020-03-05',100),('2020-02-01','2020-03-05',110)])
        before = self.execute(source)
        source['provenance']={'provider':'Unrelated synthetic label'}
        after = execute_scheduled_recipe(source,self.recipe(source),registry=self.registry,
            implementation=IMPLEMENTATION,executed_at='2026-10-10T12:00:00.000000Z')
        self.assertEqual(before['result']['observations'],after['result']['observations'])
        self.assertEqual(before['result']['execution']['materialization_id'],after['result']['execution']['materialization_id'])
        self.assertNotEqual(before['result']['execution']['executed_at'],after['result']['execution']['executed_at'])

    def test_unexpected_engine_failure_is_not_converted_to_scheduled_missingness(self):
        source = self.source([('2020-01-01','2020-03-05',100),('2020-02-01','2020-03-05',110)])
        with patch('data.transformations.engine.execute_recipe',side_effect=engine.ExecutionFailure('Unexpected defect')):
            with self.assertRaisesRegex(engine.ExecutionFailure,'Unexpected defect'):self.execute(source)


if __name__ == '__main__':unittest.main()
