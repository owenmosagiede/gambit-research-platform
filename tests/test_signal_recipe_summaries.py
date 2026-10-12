"""Grouped Signal presentation over synthetic published output and exact recipes.

Real persistence fixtures exercise verified reads without production data. FX
grouping mocks the already-tested source/recipe projection boundary only; actual
registered operator metadata supplies the displayed chains and parameters.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from api import signal_library, signal_summaries
from data.feature_store import FeatureStore, publish_feature, read_materialization
from data.feature_store_contracts import make_library_entry
from data.reusable_feature_contracts import INPUT_CONTRACT, RECIPE_KIND, make_record
from data.transformations.engine import execute_recipe
from data.transformations.identity import digest, make_feature_definition, reference
from data.transformations.registry import Registry
from test_feature_store import persistence_fixture, _copy_metadata_closure
from test_signal_library_api import inventory, running, request


def fake_reference(prefix, seed):
    return {'id':prefix+digest(seed),'version':'1.0.0','content_sha256':digest({'content':seed})}


class SignalRecipeSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_temp=tempfile.TemporaryDirectory(prefix='signal_summary_fixture_')
        cls.addClassCleanup(cls.fixture_temp.cleanup)
        cls.fixture=Path(cls.fixture_temp.name)/'platform';cls.fixture.mkdir()
        cls.arguments=persistence_fixture(cls.fixture)
        cls.published=publish_feature(cls.fixture,**cls.arguments)
        registry=Registry(Path(__file__).resolve().parents[1])
        _copy_metadata_closure(cls.fixture,[registry.operator(identifier) for identifier in (
            'TR_BASE_level_log','TR_BASE_momentum_skip_diff','TR_BASE_distribution_skew','TR_BASE_vol_downside')])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='signal_summary_case_');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'platform';shutil.copytree(self.fixture,self.root)
        self.signal_id=self.published['signal_id'];self.arguments=deepcopy(type(self).arguments)
        native=patch('data.reusable_features.list_reusable_fx_recipes',return_value=[])
        native.start();self.addCleanup(native.stop)

    def list(self):return signal_summaries.list_signal_summaries(self.root)

    def detail(self,materialization_id=None):
        return signal_summaries.get_signal_output_detail(self.root,self.signal_id,materialization_id)

    def publish_subset(self,cutoffs):
        args=deepcopy(self.arguments)
        original=[row['evaluation_cutoff'] for row in args['result']['observations']]
        args['result']=execute_recipe(args['input_series'],args['feature']['body']['recipe'],cutoffs,
            registry=Registry(self.root),implementation=reference(args['implementation']))
        args['operand_links']=[args['operand_links'][original.index(cutoff)] for cutoff in cutoffs]
        return publish_feature(self.root,**args)

    def relationships(self):
        return [{'relationship':fake_reference('RELATIONSHIP_','relationship'),
            'trial_results':[fake_reference('TRIAL_','trial')],'admission_results':[],
            'validation_results':[fake_reference('VALIDATION_','validation')],
            'attempt_ids':['00000000-0000-4000-8000-000000000001']}]

    def link_research(self):
        entry=make_library_entry(self.published['feature'],[self.published['materialization']],
            relationship_results=self.relationships())
        FeatureStore(self.root).install_record(entry)
        return entry

    def fx_item(self,symbol='AUDUSD',operator='TR_BASE_momentum_skip_diff',params=None):
        """Metadata-only output fixture; its verified-loader boundary is mocked."""
        params=params or ({'basis':'log','w':21} if operator=='TR_BASE_vol_downside' else
                          {'w':21} if operator=='TR_BASE_distribution_skew' else {'k':63,'s':5})
        registry=Registry(self.root);op=registry.operator(operator)
        grid=op['body']['execution_contract']['grid_profile'];steps=[]
        if operator!='TR_BASE_vol_downside':
            log=registry.operator('TR_BASE_level_log')
            steps.append({'node':'log_price','phase':'transformation','operator':reference(log),
                'inputs':['source'],'parameters':[],'grid_policy':grid})
        parameters=[{'name':name,'unit':'change_basis' if name=='basis' else 'observations',
            'value':{'kind':'token' if isinstance(value,str) else 'integer','value':str(value)}}
            for name,value in sorted(params.items())]
        steps.append({'node':'fx_value','phase':'transformation','operator':reference(op),
            'inputs':['log_price' if len(steps) else 'source'],'parameters':parameters,'grid_policy':grid})
        item=deepcopy(read_materialization(self.root,self.published['materialization']['id']))
        old_recipe=item['feature']['body']['recipe'];old_recipe.update(steps=steps,output_node='fx_value')
        old_recipe['selection']['entity_id']=symbol;old_recipe['selection']['measure']='close'
        old_recipe['output_unit']='dimensionless' if operator!='TR_BASE_momentum_skip_diff' else 'log_USD_per_AUD'
        item['feature']=make_feature_definition(old_recipe,symbol+' synthetic output')
        body={'kind':'reusable_fx_feature_recipe','input_contract':deepcopy(INPUT_CONTRACT),
            'steps':steps,'output_node':'fx_value','output_contract':{'unit_template':
                'log_quote_currency_per_base_currency' if operator=='TR_BASE_momentum_skip_diff' else 'dimensionless',
                'value_semantics':'difference' if operator=='TR_BASE_momentum_skip_diff' else 'statistic'},
            'history_mode':'resolved_state','calculation_geometry':'independent_per_instrument',
            **{name:old_recipe[name] for name in ('history_policy','execution_policy','evaluation_policy')}}
        reusable=make_record(RECIPE_KIND,body,'Identical cosmetic display name')
        item['signal_id']=item['feature']['body']['signal_id']
        item['materialization_state']='materialized';item['scientific_state']='untested'
        item['metadata']['dataset']={'schema_version':'0.5.0','record_type':'dataset_definition',
            'id':'DATASET_'+digest(symbol),'version':'1.0.0','display_name':symbol+' closing prices',
            'body':{'kind':'fx_constructed_dataset','instrument_id':symbol,
                'source_metadata':{'unit':old_recipe['output_unit'],'price_basis':'unknown','timing':{}}}}
        item['manifest']['metadata']['availability_semantics']='unknown_historical_availability'
        item['manifest']['id']='MATERIALIZATION_'+digest({'symbol':symbol,'recipe':reusable['id']})
        item['library_entries']=[make_library_entry(reference(item['feature']),[reference(item['manifest'])])]
        return reusable,item

    @contextmanager
    def fx_outputs(self,pairs,*,unmaterialized=()):
        store=FeatureStore(self.root);original=signal_summaries._load_output_metadata
        outputs={item['signal_id']:item for _,item in pairs}
        mapping={item['feature']['id']:{'recipe':recipe,'feature':reference(item['feature']),
            'instrument_id':item['feature']['body']['recipe']['selection']['entity_id'],
            'source_view':item['feature']['body']['recipe']['sources'][0]['source_view'],
            'price_snapshot':item['manifest']['input_key']['source_snapshots'][0]} for recipe,item in [*pairs,*unmaterialized]}
        for identifier in outputs:(self.root/signal_library.ENTRIES/identifier).mkdir()
        def load(root,identifier,**kwargs):
            return (store,[deepcopy(outputs[identifier])]) if identifier in outputs else original(root,identifier,**kwargs)
        def project(feature):return deepcopy(mapping[feature['id']]['recipe'])
        for recipe,_ in [*pairs,*unmaterialized]:store.install_record(recipe)
        with patch('data.reusable_features.list_reusable_fx_recipes',return_value=list({r['id']:r for r,_ in [*pairs,*unmaterialized]}.values())), patch.object(signal_summaries,'_load_output_metadata',side_effect=load), \
             patch.object(signal_summaries,'reusable_recipe_mapping_context',return_value=(mapping,project)):
            yield

    def test_non_fx_summary_and_verified_detail_are_preserved(self):
        old=signal_library.list_signal_library(self.root)['signals'][0]
        result=self.list();self.assertEqual(result['schema_version'],'1.0.0')
        self.assertEqual(result['entry_count'],1);self.assertEqual(result['issues'],[])
        entry=result['entries'][0]
        self.assertEqual((entry['kind'],entry['id']),('stored_signal',self.signal_id))
        self.assertEqual(entry['signal']['feature'],old['feature'])
        self.assertEqual(entry['signal']['coverage'],old['coverage'])
        self.assertEqual(entry['signal']['row_count'],old['row_count'])
        self.assertEqual(entry['signal']['verification_state'],'catalog_metadata_only')
        detail=self.detail()
        self.assertEqual(detail['observations'],signal_library.get_signal_detail(self.root,self.signal_id)['observations'])
        self.assertEqual(detail['statistics']['row_count'],3)

    def test_two_instruments_share_one_recipe_without_combined_observation_count(self):
        a=self.fx_item('AUDUSD');b=self.fx_item('EURUSD')
        self.assertEqual(a[0]['id'],b[0]['id'])
        with self.fx_outputs([a,b]):result=self.list()
        groups=[entry for entry in result['entries'] if entry['kind']=='reusable_fx_recipe']
        self.assertEqual(len(groups),1)
        group=groups[0];self.assertEqual(group['id'],a[0]['id']);self.assertEqual(group['recipe'],reference(a[0]))
        self.assertIsNone(group['observation_count'])
        self.assertEqual(len(group['outputs']),2)
        self.assertEqual({o['source']['series_id'] for o in group['outputs']},{'AUDUSD','EURUSD'})
        self.assertEqual(group['research']['state'],'untested')
        self.assertEqual(group['research']['relationship_count'],0)
        self.assertNotIn('metrics',group)

    def test_distinct_parameters_remain_separate_even_with_identical_display_names(self):
        a=self.fx_item(params={'k':63,'s':5});b=self.fx_item(params={'k':252,'s':21})
        self.assertEqual(a[0]['display_name'],b[0]['display_name'])
        with self.fx_outputs([a,b]):result=self.list()
        groups=[entry for entry in result['entries'] if entry['kind']=='reusable_fx_recipe']
        self.assertEqual({g['id'] for g in groups},{a[0]['id'],b[0]['id']})
        self.assertTrue(all(len(g['outputs'])==1 for g in groups))

    def test_registry_only_recipes_appear_in_signal_library(self):
        stored=self.fx_item();unprepared=self.fx_item(operator='TR_BASE_distribution_skew')
        with self.fx_outputs([stored],unmaterialized=[unprepared]):result=self.list()
        ids={entry['id'] for entry in result['entries']}
        self.assertIn(stored[0]['id'],ids);self.assertIn(unprepared[0]['id'],ids)
        untested=next(x for x in result['entries'] if x['id']==unprepared[0]['id'])
        self.assertEqual(untested['outputs'],[]);self.assertEqual(untested['research']['state'],'untested')

    def test_authoritative_research_joins_existing_recipe_without_changing_outputs(self):
        from api.catalog_cache import CatalogCache
        from runtime.research_jobs import ResearchJobs
        from test_research_runtime import Adapter, KernelSpy, profile, intent
        recipe, output = self.fx_item()
        (self.root/'config').mkdir(exist_ok=True)
        (self.root/'config/research_execution.json').write_text(json.dumps(profile()))
        request = intent(mode='CS'); request['feature'] = {'id':recipe['id'],'version':recipe['version']}
        jobs = ResearchJobs(self.root, adapter=Adapter(), kernels=KernelSpy())
        self.addCleanup(jobs.close)
        cache = CatalogCache()
        read = lambda: cache.get_verified('signals', self.root, self.list)
        with self.fx_outputs([(recipe,output)]):
            before = read()
            self.assertEqual(next(e for e in before['entries'] if e['id']==recipe['id'])['research']['state'], 'untested')
            jobs.submit(request); jobs.run_pending_once()
            result = read()
        self.assertEqual(jobs.get(request['request_id'])['status'],'succeeded')
        group = next(entry for entry in result['entries'] if entry['id']==recipe['id'])
        self.assertEqual(group['outputs'], next(e for e in before['entries'] if e['id']==recipe['id'])['outputs'])
        self.assertEqual(result['entry_count'],2)  # Existing CES-style fixture plus one FX recipe.
        self.assertEqual(len(group['outputs']),1)
        self.assertIsNone(group['observation_count'])
        self.assertEqual(group['research']['relationship_count'],5)
        self.assertEqual(group['research']['state'],'results_linked')
        self.assertTrue(all('results' not in r for r in group['research']['relationships']))
        for relationship in jobs.store.results_for_recipe(recipe['id']):
            self.assertEqual(relationship['mode'],'CS')
            self.assertEqual(relationship['scope']['id'],'SCOPE_CS')
            for trial_result in relationship['results']:
                authority=jobs.store.resolve('trial',trial_result['authority'])
                self.assertEqual(trial_result['metrics'],authority['body']['metrics'])
        legacy = next(entry for entry in result['entries'] if entry['id']==self.signal_id)
        self.assertEqual(legacy['signal']['feature'],signal_library.list_signal_library(self.root)['signals'][0]['feature'])

    def test_readable_momentum_name_and_internal_log_basis_preserve_operator_chain(self):
        momentum=self.fx_item();downside=self.fx_item('USDJPY','TR_BASE_vol_downside')
        with self.fx_outputs([momentum,downside]):result=self.list()
        groups={entry['id']:entry for entry in result['entries']}
        group=groups[momentum[0]['id']]
        self.assertEqual(group['name'],'Log Skip Recent Momentum')
        self.assertEqual(group['source']['label'],'Closing prices')
        self.assertEqual([s['label'] for s in group['transformations']],['Log Level','Skip Recent Difference'])
        self.assertEqual(group['transformations'][-1]['parameters'],momentum[0]['body']['steps'][-1]['parameters'])
        log_basis=groups[downside[0]['id']]['transformations']
        self.assertEqual([s['operator']['id'] for s in log_basis],['TR_BASE_vol_downside'])
        self.assertIn({'name':'basis','unit':'change_basis','value':{'kind':'token','value':'log'}},log_basis[0]['parameters'])

    def test_multiple_materializations_and_projection_versions_keep_all_exact_outputs(self):
        later=self.publish_subset(['2020-03-15'])
        folder=self.root/signal_library.ENTRIES/self.signal_id
        entry=json.loads(next(folder.glob('*.json')).read_text())
        duplicate=make_library_entry(self.published['feature'],[self.published['materialization'],later['materialization']],supersedes=reference(entry))
        FeatureStore(self.root).install_record(duplicate)
        store,loaded=signal_summaries._load_outputs(self.root,self.signal_id)
        self.assertEqual(len(loaded),2)
        self.assertEqual({reference(item['manifest'])['id'] for item in loaded},
            {self.published['materialization']['id'],later['materialization']['id']})
        detail=self.detail(later['materialization']['id'])
        self.assertEqual(len(detail['materializations']),2)
        self.assertEqual(detail['statistics']['row_count'],1)
        self.assertTrue(all('/api/signal-library-outputs/' in item['href'] for item in detail['materializations']))

    def test_linked_research_is_preserved_without_fabricating_metrics_or_recipe_validation(self):
        self.link_research()
        # The old endpoint retains its explicitly unresearched contract.
        with self.assertRaises(ValueError):signal_library.get_signal_detail(self.root,self.signal_id)
        result=self.list();self.assertEqual(result['entry_count'],1)
        detail=self.detail();research=detail['research']
        self.assertNotIn(research['state'],('untested','validated'))
        self.assertEqual(research['relationship_count'],1)
        self.assertIn(self.relationships()[0]['relationship']['id'],json.dumps(research))
        self.assertIn(self.relationships()[0]['trial_results'][0]['id'],json.dumps(research))
        self.assertEqual(detail['statistics']['row_count'],3)
        self.assertEqual(research.get('metrics',[]),[])

    def test_grouped_research_retains_links_without_parent_wide_validation(self):
        a=self.fx_item('AUDUSD');b=self.fx_item('EURUSD')
        a[1]['library_entries']=[make_library_entry(reference(a[1]['feature']),[reference(a[1]['manifest'])],
            relationship_results=self.relationships())]
        a[1]['scientific_state']='research_links_present'
        with self.fx_outputs([a,b]):result=self.list()
        group=next(entry for entry in result['entries'] if entry['kind']=='reusable_fx_recipe')
        self.assertNotIn(group['research']['state'],('untested','validated'))
        self.assertEqual(group['research']['relationship_count'],1)
        self.assertEqual(len(group['outputs']),2)
        self.assertIn(a[1]['signal_id'],json.dumps(group['research']))

    def test_malformed_output_isolated_and_corrupt_payload_rejected(self):
        bad=self.root/signal_library.ENTRIES/('SIGNAL_'+'f'*64);bad.mkdir();(bad/'bad.json').write_text('{')
        result=self.list();self.assertEqual(result['entry_count'],1);self.assertEqual(len(result['issues']),1)
        self.assertNotIn(str(self.root),json.dumps(result))
        manifest=FeatureStore(self.root).resolve(self.published['materialization']);part=manifest['partitions'][0]
        payload=self.root/f"storage/payloads/sha256/{part['blob_sha256'][:2]}/{part['blob_sha256']}.jsonl"
        payload.write_bytes(payload.read_bytes()+b' ')
        with self.assertRaises(ValueError):self.detail()
        self.assertEqual(self.list()['entry_count'],1)  # Catalog presence does not certify payload integrity.

    def test_catalog_never_loads_observations_or_trial_artifacts(self):
        with patch.object(signal_summaries,'read_materialization',side_effect=AssertionError('No payload reads')),patch('research.store.ResearchStore.verify_artifact',side_effect=AssertionError('No artifact reads')):
            result=self.list()
        self.assertEqual(result['entry_count'],1)

    def test_repeated_real_reads_and_http_get_head_do_not_write(self):
        before=inventory(self.root)
        first=self.list();self.detail();self.assertEqual(first,self.list())
        detail='/api/signal-library-outputs/'+self.signal_id
        with running(self.root) as address:
            for endpoint in ('/api/signal-library-summaries',detail,detail+'?materialization_id='+self.published['materialization']['id']):
                with self.subTest(endpoint=endpoint):
                    status,headers,body=request(address,endpoint)
                    self.assertEqual(status,200);self.assertIsInstance(json.loads(body),dict)
                    self.assertEqual(headers['Cache-Control'],'no-store')
                    head_status,head_headers,head_body=request(address,endpoint,'HEAD')
                    self.assertEqual((head_status,head_body),(200,b''))
                    self.assertEqual(headers['Content-Length'],head_headers['Content-Length'])
        self.assertEqual(inventory(self.root),before)

    def test_http_caches_refresh_after_a_separate_process_publishes_output(self):
        args=deepcopy(self.arguments)
        args['result']=execute_recipe(args['input_series'],args['feature']['body']['recipe'],['2020-03-15'],
            registry=Registry(self.root),implementation=reference(args['implementation']))
        args['operand_links']=[args['operand_links'][-1]]
        arguments_path=Path(self.temp.name)/'publication.json'
        arguments_path.write_text(json.dumps(args))
        endpoint='/api/signal-library-summaries'
        with running(self.root) as first, running(self.root) as second:
            for address in (first,second):
                status,_,body=request(address,endpoint)
                self.assertEqual(status,200)
                self.assertEqual(json.loads(body)['entries'][0]['signal']['materialization_count'],1)
            child=subprocess.run([sys.executable,'-c',
                'import json,sys; from pathlib import Path; from data.feature_store import publish_feature; '
                'publish_feature(Path(sys.argv[1]),**json.loads(Path(sys.argv[2]).read_text()))',
                str(self.root),str(arguments_path)],capture_output=True,text=True,timeout=30)
            self.assertEqual(child.returncode,0,child.stderr)
            after_publication=inventory(self.root)
            for address in (first,second):
                status,_,body=request(address,endpoint)
                self.assertEqual(status,200)
                response=json.loads(body)
                self.assertEqual(response['issues'],[])
                self.assertEqual(response['entries'][0]['signal']['materialization_count'],2)
            self.assertEqual(inventory(self.root),after_publication)

    def test_warm_catalog_rechecks_corrupt_metadata_and_recovers_after_repair(self):
        from api.catalog_cache import CatalogCache
        from data.feature_store import record_path
        cache=CatalogCache()
        read=lambda:cache.get_verified('signals',self.root,self.list)
        original=read()
        operator=Registry(self.root).operator('TR_BASE_change_pct')
        path=self.root/record_path(operator);saved=path.read_bytes()
        path.write_bytes(b'{')
        broken=read()
        self.assertTrue(broken['issues'])
        self.assertFalse(cache.verified_entries)
        self.assertNotEqual(broken,original)
        path.write_bytes(saved)
        self.assertEqual(read(),original)

    def test_http_rejects_invalid_queries_and_mutations_without_writes(self):
        before=inventory(self.root);detail='/api/signal-library-outputs/'+self.signal_id
        cases=[('/api/signal-library-summaries?scope=FX',400),(detail+'?other=x',400),
            (detail+'?materialization_id=',400),(detail+'?materialization_id=../secret',400),
            (detail+'?materialization_id=x&materialization_id=y',400),
            (detail+'?materialization_id='+'MATERIALIZATION_'+'f'*64,404),
            ('/api/signal-library-outputs/SIGNAL_x',404),
            ('/api/signal-library-outputs/'+'SIGNAL_'+'f'*64,404)]
        with running(self.root) as address:
            for endpoint,expected in cases:
                with self.subTest(endpoint=endpoint):
                    status,_,body=request(address,endpoint)
                    self.assertEqual(status,expected);self.assertNotIn(str(self.root).encode(),body)
            for method in ('POST','PUT','PATCH','DELETE'):
                self.assertEqual(request(address,'/api/signal-library-summaries',method)[0],405)
                self.assertEqual(request(address,detail,method)[0],405)
        self.assertEqual(inventory(self.root),before)


if __name__=='__main__':unittest.main()
