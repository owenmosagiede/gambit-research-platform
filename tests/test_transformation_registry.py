"""Registration, finite-grid, policy, numerical-example and documentation parity."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator, ValidationError
from data.transformations.registry import Registry, immutable_reference
from data.transformations.numeric import calculate, parameter_requirements, FAILURE_CODES, ParameterError
from test_transformation_numeric import NUMERICAL_EXAMPLES

ROOT=Path(__file__).resolve().parents[1]


class TransformationRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=Registry(ROOT)
        cls.entries=cls.registry.all_operators()

    def test_complete_registration_mapping_and_distinct_implementations(self):
        self.assertEqual(len(self.entries),98)
        namespaces=Counter(entry['id'].split('_')[1] for entry in self.entries)
        self.assertEqual(namespaces,{'BASE':68,'PRICE':16,'RELEASE':6,'CORE':8})
        kernels={e['body']['execution_contract']['kernel'] for e in self.entries}
        self.assertEqual(len(kernels),80) #79numeric kernels +1release-event orchestration.
        self.assertEqual(len({e['id'] for e in self.entries}),98)
        families={e['body']['execution_contract']['family'] for e in self.entries if e['id'].startswith('TR_BASE_')}
        self.assertEqual(len(families),15)
        for e in self.entries:
            self.assertEqual(e['version'],'2.0.0')
            c=e['body']['execution_contract'];legacy=c['legacy_mapping']
            self.assertEqual(c['certification']['status'],'approved')
            self.assertEqual(e['body']['input_arity'],{'minimum':1,'maximum':1})
            self.assertNotIn('combine.difference',c['kernel'])
            if e['id'].startswith('TR_CORE_'):self.assertIsNone(legacy)
            else:
                self.assertEqual(legacy['version'],'0.1.0' if e['id'].startswith('TR_BASE_') else '1.0.0')
                self.assertTrue(legacy['sources'])
                self.assertTrue(all(len(s['sha256'])==64 for s in legacy['sources']))

    def test_every_registration_has_defined_independent_example(self):
        for e in self.entries:
            c=e['body']['execution_contract'];example=c['example'];p={name:float(value) if name in ['low','high','q'] else value for name,value in example['parameters'].items()}
            values=[float(x) if isinstance(x,str) else x for x in example['values']]
            with self.subTest(registration=e['id']):
                self.registry.validate_parameters(e,p,example['frequency'])
                if c['kernel']=='release.shock_change_zscore':
                    #An independently specified event-history scalar example;
                    #full event/state binding is covered by engine acceptance tests.
                    result=calculate('standard.zscore',values,{'w':p['w']})[-1]
                    self.assertAlmostEqual(float(example['expected_last']),17/math.sqrt(21))
                else:
                    source=NUMERICAL_EXAMPLES[c['kernel']]
                    self.assertEqual(example['values'],source['values'])
                    self.assertEqual(p,source['parameters'])
                    self.assertEqual(float(example['expected_last']),source['expected_last'])
                    result=calculate(c['kernel'],values,p,reference_times=example['reference_times'],frequency=example['frequency'])[-1]
                self.assertIsNone(result['reason'])
                self.assertAlmostEqual(result['value'],float(example['expected_last']),places=11)
                self.assertTrue(math.isfinite(result['value']))
                if e['id'].startswith('TR_PRICE_'):
                    self.assertEqual(c['input_semantics'],['price'])
                    if 'positive_input' in c['input_requirements']:
                        self.assertTrue(all(x>0 for x in example['values']))
                if c['temporal_mode'].startswith('release'):
                    self.assertEqual(set(c['capabilities']),{'revision_history','release_events'})

    def test_parameter_metadata_matches_mathematical_validator(self):
        for e in self.entries:
            c=e['body']['execution_contract'];requirements=parameter_requirements(c['kernel'])
            self.assertEqual(c['parameter_constraints'],requirements['constraints'])
            self.assertEqual(set(c['supported_frequencies']),set(requirements['supported_frequencies']))
            for p in e['body']['parameters']:
                if p['name'] in requirements['minima']:
                    self.assertEqual(int(p['minimum']),requirements['minima'][p['name']])
            self.assertEqual(set(c['failure_codes']),FAILURE_CODES)

    def test_every_approved_finite_grid_combination_is_mathematically_valid(self):
        totals=Counter()
        for e in self.entries:
            c=e['body']['execution_contract']
            for frequency in c['supported_frequencies']:
                grid=self.registry.enumerate_grid(e,frequency,c['grid_profile'],max_combinations=10000)
                self.assertEqual(len(grid),len({json.dumps(p,sort_keys=True) for p in grid}))
                for p in grid:
                    with self.subTest(registration=e['id'],frequency=frequency,parameters=p):
                        self.assertEqual(self.registry.validate_parameters(e,p,frequency),p)
                totals[frequency]+=len(grid)
        self.assertEqual(dict(totals),{'tick':733,'intraday':733,'daily':733,'weekly':732,'monthly':732,'quarterly':731,'semiannual':729,'annual':657,'irregular':727,'event':727})

    def test_enumeration_requires_explicit_bound_and_compatible_policy(self):
        e=self.registry.operator('TR_BASE_change_diff');policy=e['body']['execution_contract']['grid_profile']
        for bound in [None,0,-1,True,1.5,100001]:
            with self.subTest(bound=bound),self.assertRaises(ValueError):self.registry.enumerate_grid(e,'monthly',policy,bound)
        with self.assertRaises(ValueError):self.registry.enumerate_grid(e,'monthly',policy,1)
        unrelated=immutable_reference(self.registry.get_policy('POL_TRANSFORM_GRID_PRICE'))
        with self.assertRaises(ValueError):self.registry.enumerate_grid(e,'monthly',unrelated,100)
        self.assertEqual(len(self.registry.enumerate_grid(e,'monthly',policy,6)),6)

    def test_grid_policy_is_separate_from_mathematical_parameter_domain(self):
        e=self.registry.operator('TR_BASE_standard_zscore');base=e['body']['execution_contract']['grid_profile']
        self.assertEqual(self.registry.validate_parameters(e,{'w':7},'monthly'),{'w':7})
        with self.assertRaises(ValueError):self.registry.validate_parameters(e,{'w':7},'monthly',base)
        extension=immutable_reference(self.registry.get_policy('POL_TRANSFORM_GRID_WEEKLY_156'))
        self.assertNotIn({'w':156},self.registry.enumerate_grid(e,'weekly',base,100))
        self.assertIn({'w':156},self.registry.enumerate_grid(e,'weekly',extension,100))
        self.assertEqual(self.registry.validate_parameters(e,{'w':156},'weekly',extension),{'w':156})
        self.assertNotEqual(base['content_sha256'],extension['content_sha256'])
        extension_record=self.registry.resolve_policy(extension)
        preserved={p['name']:p['value']['value'] for p in extension_record['body']['parameters']}
        self.assertEqual(preserved['legacy_extension_fingerprint'],'sha256_7e3e940b7b7d659b97330e4962b6b54003844be5102c08ff747b54b56e3e5d04')
        with self.assertRaises(ValueError):self.registry.validate_parameters(e,{'w':156},'monthly',extension)
        with self.assertRaises(ValueError):self.registry.enumerate_grid(self.registry.operator('TR_PRICE_standard_zscore'),'weekly',extension,100)

    def test_invalid_legacy_axis_values_are_rejected_not_repaired(self):
        cases=[('TR_BASE_vol_diff_sd',{'w':1}),('TR_BASE_distribution_skew',{'w':2}),
               ('TR_BASE_distribution_kurtosis',{'w':3}),('TR_BASE_trend_slope',{'w':2}),
               ('TR_BASE_shock_change_zscore',{'k':4,'w':4}),('TR_PRICE_trend_ma_crossover',{'fast':4,'slow':2})]
        for id,p in cases:
            with self.subTest(id=id),self.assertRaises(ParameterError):self.registry.validate_parameters(self.registry.operator(id),p,'annual')
        e=self.registry.operator('TR_BASE_vol_diff_sd')
        self.assertNotIn({'w':1},self.registry.enumerate_grid(e,'annual',e['body']['execution_contract']['grid_profile'],100))
        seasonal=self.registry.operator('TR_BASE_seasonal_bucket_deviation')
        with self.assertRaises(ValueError):self.registry.validate_parameters(seasonal,{'history_years':3},'annual')

    def test_definitions_are_schema_valid_closed_and_resolve_exactly(self):
        validator=Draft202012Validator(json.loads((ROOT/'specs/schemas/platform.schema.json').read_text()))
        for e in self.entries:
            validator.validate(e)
            self.assertEqual(self.registry.resolve(immutable_reference(e)),e)
        e=deepcopy(self.entries[0]);e['body']['execution_contract']['unknown']=True
        with self.assertRaises(ValidationError):validator.validate(e)
        binding=immutable_reference(self.entries[0]);binding['content_sha256']='0'*64
        with self.assertRaises(ValueError):self.registry.resolve(binding)
        with self.assertRaises(ValueError):self.registry.operator('combine.difference')

    def test_policy_refs_and_definition_labels_follow_existing_identity_projection(self):
        from data.transformations.identity import reference
        for e in self.entries:
            self.assertEqual(reference(e),immutable_reference(e))
            renamed=deepcopy(e);renamed['display_name']='Renamed label'
            self.assertEqual(immutable_reference(e),immutable_reference(renamed))
        for id in ['POL_TRANSFORM_EXECUTION','POL_TRANSFORM_HISTORY','POL_TRANSFORM_UNITS','POL_TRANSFORM_MISSING']:
            policy=self.registry.get_policy(id);binding=immutable_reference(policy)
            self.assertEqual(self.registry.resolve_policy(binding),policy)
            bad=deepcopy(binding);bad['content_sha256']='0'*64
            with self.assertRaises(ValueError):self.registry.resolve_policy(bad)

    def test_generated_documentation_matches_authoritative_definitions(self):
        from data.transformations.documentation import render_documentation
        self.assertEqual((ROOT/'docs/transformation_library.md').read_text(),render_documentation(self.registry))


if __name__=='__main__':unittest.main()
