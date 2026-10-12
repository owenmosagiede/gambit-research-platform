"""Independent acceptance of approved FX recipe enumeration and registration.

All writes are confined to isolated synthetic stores. Production operator and
policy records are read only; no FX observations are copied or materialized.
"""
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from data import fx_feature_recipes as recipes
from data.feature_store import FeatureStore, PublicationError
from data.fx_records import make_record
from data.fx_pipeline import _universe
from data.transformations.identity import canonical_bytes, reference, make_feature_definition
from data.transformations.registry import Registry
from data.transformations.engine import _parameters
from test_feature_store import _copy_metadata_closure

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_COUNTS = {'accel_second_diff':4,'accel_slope_change':6,'change_diff':6,
    'distribution_iqr':4,'distribution_kurtosis':4,'distribution_quantile_range':8,
    'distribution_quantile_skew':4,'distribution_skew':4,'extreme_range':5,
    'momentum_skip_diff':8,'persistence_diff_autocorr':8,'persistence_variance_ratio':5,
    'shock_change_percentile':11,'shock_change_zscore':11,'shock_standardized_change':11,
    'smooth_ew_change':4,'trend_ema_distance':4,'trend_ma_distance':5,'trend_slope':4,
    'trend_slope_tstat':4,'vol_abs_change':5,'vol_asymmetry':5,'vol_change':6,
    'vol_diff_sd':5,'vol_downside':5,'vol_ewma':4,'vol_ratio':7,'vol_upside':5,
    'volscale_diff':9,'volscale_trend':9}


def inventory(root):
    return {str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file()}


def synthetic_instrument(store, symbol):
    meta={'base_currency':symbol[:3],'quote_currency':symbol[3:],
          'unit':symbol[3:]+'_per_'+symbol[:3],'price_field':'close','price_basis':'unknown',
          'timing':{'timezone':None,'bar_boundary':None,'session_convention':None,'synchronization':'unverified'}}
    construction=make_record('transformation_definition',{'kind':'fx_price_recipe','profile':'fx_price.1.0.0','instrument_id':symbol,
        'alignment_policy':{'mode':'single_source_observation'}},symbol+' fixture construction')
    store.install_record(construction)
    dataset=make_record('dataset_definition',{'kind':'fx_constructed_dataset','profile':'fx_price.1.0.0',
        'instrument_id':symbol,'economic_id':'FX_'+symbol[:3]+'_'+symbol[3:],'source_metadata':meta},symbol+' fixture')
    view=make_record('source_view_definition',{'kind':'fx_constructed_view','profile':'fx_price.1.0.0',
        'dataset':reference(dataset),'source_metadata':meta},symbol+' fixture close')
    snapshot=make_record('snapshot_manifest',{'kind':'fx_constructed_prices','profile':'fx_price.1.0.0',
        'instrument_id':symbol,'definition':reference(view),'recipe':reference(construction),'source_metadata':meta,'record_count':0,'members':[]},symbol+' empty fixture snapshot')
    for record in (dataset,view,snapshot):store.install_record(record)
    return {'instrument_id':symbol,'price_snapshot':reference(snapshot)}


class FxFeatureRecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_temp=tempfile.TemporaryDirectory(prefix='fx_recipe_template_')
        cls.addClassCleanup(cls.template_temp.cleanup)
        cls.template=Path(cls.template_temp.name).resolve()
        shutil.copytree(ROOT/'specs/schemas',cls.template/'specs/schemas')
        actual=Registry(ROOT)
        records=actual.all_operators()+[actual.get_policy(name) for name in ('POL_TRANSFORM_HISTORY','POL_TRANSFORM_EXECUTION')]
        _copy_metadata_closure(cls.template,records)
        store=FeatureStore(cls.template)
        cls.evidence=store.resolve(actual.get_policy('POL_TRANSFORM_HISTORY')['body']['specification'])
        payload=cls.evidence['body']['payload']
        cls.policy_payload=store.payload({'blob_sha256':payload['sha256'],'format':'json','byte_count':payload['byte_count']})
        cls.policy={'schema_version':'0.2.0','record_type':'policy_definition','id':recipes.POLICY_ID,'version':recipes.POLICY_VERSION,
            'display_name':'Isolated fixture evaluation policy','body':{'kind':'selection','approval_state':'approved',
            'compatibility_evidence':[],'specification':reference(cls.evidence),
            'parameters':[{'name':key,'unit':'policy_setting','value':{'kind':'token','value':value}}
                          for key,value in sorted(recipes.RULES.items())]}}
        store.install_record(cls.policy)
        cls.instruments=[synthetic_instrument(store,symbol) for symbol in _universe()]
        (cls.template/'config').mkdir()
        (cls.template/'config/fx_retrospective_completion.json').write_text(json.dumps({'return_policy':{}}))

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='fx_recipe_case_')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()/'platform'
        shutil.copytree(self.template,self.root)
        self.registry=Registry(self.root)
        self.configurations=recipes.configurations(self.registry)
        self.instrument=next(item for item in self.instruments if item['instrument_id']=='EURUSD')

    def variant(self,identifier):
        return next(item for item in self.configurations if item['operator']['id']==identifier)

    def build(self,identifier, instrument=None):
        return recipes.build_fx_feature(self.root,instrument or self.instrument,self.variant(identifier),registry=self.registry)

    def registration_mocks(self):
        stack=ExitStack()
        stack.enter_context(patch.object(recipes,'_approved_policy',return_value={}))
        stack.enter_context(patch.object(recipes,'verify_review',return_value={'discrepancies':[],'reviewed_operator_count':98,'requested_operator_count':30}))
        stack.enter_context(patch.object(recipes,'_policy_records',return_value=(self.policy,self.evidence,self.policy_payload,{})))
        stack.enter_context(patch.object(recipes,'list_instruments',return_value=deepcopy(self.instruments)))
        stack.enter_context(patch.object(recipes,'configurations',return_value=[self.variant('TR_BASE_change_diff'),self.variant('TR_BASE_vol_ewma')]))
        stack.enter_context(patch.object(recipes,'_price_snapshot',side_effect=lambda store,binding,policy,verify_rows: (store.resolve(binding),None)))
        return stack

    def register(self):
        request=self.root/'request.txt'
        request.write_text('Synthetic test request, isolated fixture only.\n')
        return recipes.register_fx_recipes(self.root,review_path=self.root/'unused_review.txt',request_path=request)

    def test_exact_30_operator_sets_and_180_approved_daily_configurations(self):
        actual=Counter(item['operator']['id'] for item in self.configurations)
        self.assertEqual(actual,{'TR_BASE_'+name:count for name,count in EXPECTED_COUNTS.items()})
        self.assertEqual(len(self.configurations),180)
        self.assertEqual((len(recipes.LOG_FIRST),len(recipes.LOG_BASIS)),(23,7))
        self.assertEqual(len({item['id'] for item in self.configurations}),180)
        for item in self.configurations:
            entry=self.registry.resolve(item['operator'])
            params=_parameters({'parameters':item['parameters']},entry)
            self.registry.validate_parameters(entry,params,'daily',item['grid_policy'])
            self.assertEqual(item['parameter_frequency'],'daily')
            if item['operator']['id'] in recipes.LOG_BASIS:self.assertEqual(params['basis'],'log')

    def test_all_configurations_build_correct_chains_without_definition_changes(self):
        before=inventory(self.root/'definitions/transformations')
        features=[]
        for item in self.configurations:
            feature=recipes.build_fx_feature(self.root,self.instrument,item,registry=self.registry,evaluation_policy=self.policy)
            steps=feature['body']['recipe']['steps']
            if item['operator']['id'] in recipes.LOG_FIRST:
                self.assertEqual([step['operator']['id'] for step in steps],['TR_BASE_level_log',item['operator']['id']])
                self.assertEqual(steps[0]['parameters'],[])
            else:
                self.assertEqual(len(steps),1)
                self.assertEqual(_parameters(steps[0],self.registry.resolve(steps[0]['operator']))['basis'],'log')
            features.append(feature)
        self.assertEqual(len({feature['id'] for feature in features}),180)
        self.assertEqual(inventory(self.root/'definitions/transformations'),before)

    def test_output_units_and_meaning_follow_composed_contracts(self):
        expected={'TR_BASE_change_diff':('log_USD_per_EUR','difference'),
                  'TR_BASE_trend_slope':('log_USD_per_EUR_per_observation','difference'),
                  'TR_BASE_distribution_iqr':('log_USD_per_EUR','statistic'),
                  'TR_BASE_trend_slope_tstat':('dimensionless','statistic'),
                  'TR_BASE_vol_ewma':('dimensionless','volatility')}
        for identifier,(unit,meaning) in expected.items():
            with self.subTest(identifier=identifier):
                result=recipes.validate_fx_recipe(self.root,self.build(identifier))
                self.assertEqual((result['unit'],result['value_semantics']),(unit,meaning))

    def test_optional_price_ratio_and_already_log_operators_are_excluded(self):
        for identifier in ('TR_BASE_standard_zscore','TR_BASE_change_pct','TR_BASE_change_log','TR_PRICE_change_log','TR_BASE_momentum_skip_return'):
            variant=deepcopy(self.variant('TR_BASE_change_diff'))
            variant['operator']=reference(self.registry.operator(identifier))
            with self.subTest(identifier=identifier),self.assertRaises(PublicationError):
                recipes.build_fx_feature(self.root,self.instrument,variant,registry=self.registry)

    def test_double_log_extra_difference_and_wrong_basis_fail_closed(self):
        for identifier in ('TR_BASE_distribution_skew','TR_BASE_vol_ewma'):
            feature=self.build(identifier)
            recipe=deepcopy(feature['body']['recipe'])
            extra={'node':'extra','phase':'transformation','operator':reference(self.registry.operator('TR_BASE_level_log')),
                   'inputs':['source'],'parameters':[],'grid_policy':reference(self.registry.get_policy('POL_TRANSFORM_GRID_BASE'))}
            recipe['steps'][0]['inputs']=['extra'];recipe['steps'].insert(0,extra)
            altered=make_feature_definition(recipe,'Invalid extra log')
            with self.assertRaises(PublicationError):recipes.validate_fx_recipe(self.root,altered)
        feature=self.build('TR_BASE_vol_ewma');recipe=deepcopy(feature['body']['recipe'])
        next(p for p in recipe['steps'][0]['parameters'] if p['name']=='basis')['value']['value']='diff'
        altered=make_feature_definition(recipe,'Wrong basis')
        with self.assertRaises(PublicationError):recipes.validate_fx_recipe(self.root,altered)
        feature=self.build('TR_BASE_distribution_skew');recipe=deepcopy(feature['body']['recipe'])
        recipe['steps'][0].update(operator=reference(self.registry.operator('TR_BASE_change_log')),
            parameters=[{'name':'k','unit':'observations','value':{'kind':'integer','value':'1'}}])
        with self.assertRaises(PublicationError):recipes.validate_fx_recipe(self.root,make_feature_definition(recipe,'Extra differencing'))

    def test_unapproved_parameters_and_inconsistent_source_selection_rejected(self):
        variant=deepcopy(self.variant('TR_BASE_change_diff'))
        variant['parameters'][0]['value']['value']='2'
        with self.assertRaises(ValueError):recipes.build_fx_feature(self.root,self.instrument,variant,registry=self.registry)
        feature=self.build('TR_BASE_change_diff');recipe=deepcopy(feature['body']['recipe']);recipe['selection']['entity_id']='AUDUSD'
        with self.assertRaises(PublicationError):recipes.validate_fx_recipe(self.root,make_feature_definition(recipe,'Wrong instrument'))

    def test_canonical_identity_reuses_labels_and_distinguishes_source_instruments(self):
        first=self.build('TR_BASE_change_diff')
        second=self.build('TR_BASE_change_diff')
        renamed=deepcopy(first);renamed['display_name']='Different display label'
        other=self.build('TR_BASE_change_diff',next(i for i in self.instruments if i['instrument_id']=='AUDUSD'))
        self.assertEqual(reference(first),reference(second))
        self.assertEqual(reference(first),reference(renamed))
        self.assertNotEqual(first['id'],other['id'])
        self.assertEqual(first['body']['signal_id'].removeprefix('SIGNAL_'),first['id'].removeprefix('FEATURE_'))

    def test_repeat_registration_reuses_all_43_bindings_and_preserves_existing_files(self):
        with self.registration_mocks():
            first=self.register()
            baseline=inventory(self.root)
            second=self.register()
        self.assertEqual((first['configuration_count'],first['instrument_count'],first['binding_count']),(2,43,86))
        self.assertEqual((first['added_recipe_definitions'],first['reused_recipe_definitions']),(86,0))
        self.assertEqual((second['added_recipe_definitions'],second['reused_recipe_definitions']),(0,86))
        self.assertEqual(second['catalog'],first['catalog'])
        self.assertEqual(inventory(self.root),baseline)
        self.assertFalse((self.root/'storage/catalog/signal_library').exists())
        self.assertFalse((self.root/'storage/catalog/feature_store').exists())

    def test_registration_preserves_equivalent_existing_display_name(self):
        feature=self.build('TR_BASE_change_diff');feature['display_name']='Existing user label'
        FeatureStore(self.root).install_record(feature)
        with self.registration_mocks():result=self.register()
        self.assertEqual((result['added_recipe_definitions'],result['reused_recipe_definitions']),(85,1))
        self.assertEqual(FeatureStore(self.root).resolve(reference(feature))['display_name'],'Existing user label')

    def test_conflicting_existing_identity_aborts_before_new_definitions(self):
        feature=self.build('TR_BASE_change_diff');FeatureStore(self.root).install_record(feature)
        path=self.root/'definitions/features'/feature['id']/'1.0.0.json'
        changed=deepcopy(feature);changed['body']['recipe']['output_unit']='dimensionless'
        path.write_bytes(canonical_bytes(changed)+b'\n')
        before=inventory(self.root/'definitions')
        with self.registration_mocks(),self.assertRaises(PublicationError):self.register()
        self.assertEqual(inventory(self.root/'definitions'),before)


    def replace_catalog(self, result, mutate):
        store=FeatureStore(self.root)
        original=store.resolve(result['catalog'])
        body=deepcopy(original['body'])
        mutate(body)
        changed=make_record('onboarding_evidence',body,original['display_name'])
        # This intentional replacement occurs only inside the test's temp root.
        path=self.root/'storage/catalog/onboarding/evidence'/(original['id']+'.json')
        path.unlink()
        store.install_record(changed)
        return changed

    def test_catalog_configuration_and_count_tampering_fail_closed(self):
        cases=[lambda body:body.update(configuration_count=999),
               lambda body:body['configurations'][0]['parameters'][0]['value'].update(value='999'),
               lambda body:body.update(binding_count=body['binding_count']+1)]
        with self.registration_mocks():
            result=self.register()
            for change in cases:
                with self.subTest(change=change):
                    altered=self.replace_catalog(result,change)
                    with self.assertRaises(PublicationError):recipes.list_fx_recipes(self.root)
                    (self.root/'storage/catalog/onboarding/evidence'/(altered['id']+'.json')).unlink()
                    result=self.register()

    def test_catalog_reduced_universe_is_not_a_complete_registration(self):
        def shrink(body):
            body['bindings']=[b for b in body['bindings'] if b['instrument_id']=='EURUSD']
            body.update(instrument_count=1,binding_count=len(body['bindings']))
        with self.registration_mocks():
            result=self.register()
            self.replace_catalog(result,shrink)
            with self.assertRaises(PublicationError):recipes.list_fx_recipes(self.root)

    def test_catalog_source_and_feature_swaps_are_rejected(self):
        def source_swap(body):
            first=body['bindings'][0]
            other=next(item for item in body['bindings'] if item['instrument_id']!=first['instrument_id'])
            first['source_view']=other['source_view']
        def feature_swap(body):
            first=body['bindings'][0]
            other=next(item for item in body['bindings'] if item['instrument_id']!=first['instrument_id'])
            first['feature'],other['feature']=other['feature'],first['feature']
        with self.registration_mocks():
            result=self.register()
            for change in (source_swap,feature_swap):
                with self.subTest(change=change):
                    altered=self.replace_catalog(result,change)
                    with self.assertRaises(PublicationError):recipes.list_fx_recipes(self.root,limit=100)
                    (self.root/'storage/catalog/onboarding/evidence'/(altered['id']+'.json')).unlink()
                    result=self.register()

    def test_registration_rerun_counts_existing_materializations_separately(self):
        feature=self.build('TR_BASE_change_diff')
        with self.registration_mocks():
            first=self.register()
            with patch('api.signal_library.list_signal_library',return_value={'signals':[{'feature':reference(feature)}]}):
                second=self.register()
        self.assertEqual(first['registered_unmaterialized'],86)
        self.assertEqual(second['registered_unmaterialized'],85)
        self.assertEqual(second['reused_recipe_definitions'],86)


if __name__=='__main__':unittest.main()
