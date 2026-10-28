"""FX-facing Target filtering/readiness interface; persisted reads use the real service.

Readiness UI fixtures are explicitly interface fixtures, not production approval.
Actual migrated-source execution is tested separately by the FX integration suite.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from api import target_library
from data.targets.service import materialize
from test_signal_library_api import running, request
from target_persistence_fixture import persistence_fixture
from test_target_library_api import HORIZONS, CATEGORY_OPTIONS, weekday_family_catalog, assert_categories

PROJECT=Path(__file__).resolve().parents[1]


def inspect_ui(catalog, detail=None, *, click=False, selection=None):
    node=shutil.which('node')
    if node is None:
        raise unittest.SkipTest('Node.js is required for actual Target inspection UI checks')
    script=r'''
const fs=require("fs"),vm=require("vm"),input=JSON.parse(fs.readFileSync(0,"utf8"));
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.listeners={};this.disabled=false;this.hidden=false;this.value="";this.textContent="";this.attributes={};}
 replaceChildren(...items){this.children=items;} append(...items){this.children.push(...items);}
 addEventListener(name,fn){this.listeners[name]=fn;} setAttribute(name,value){this.attributes[name]=value;}
}
const names=["target","target-status","target-retry","target-details","target-details-link","target-instruments","target-instrument-table","target-instruments-heading","target-details-title","target-details-status","target-details-body","target-detail-retry"];
const events={};const ids=Object.fromEntries(names.map(id=>[id,new Element(id)]));let paths=[],timeouts=[],loadingStatuses=[],loadingOptions=[];
const context={document:{getElementById:id=>ids[id],createElement:tag=>new Element(tag)},AbortController,
 window:{addEventListener:(name,fn)=>events[name]=fn,setTimeout:(_fn,delay)=>{timeouts.push(delay);return timeouts.length;},clearTimeout:()=>{}},fetch:async url=>{paths.push(url);loadingStatuses.push(ids["target-status"].textContent);loadingOptions.push(ids.target.children.map(x=>({value:x.value,text:x.textContent,disabled:x.disabled})));return {ok:true,json:async()=>url==="/api/target-library"?input.catalog:input.detail};}};
vm.runInNewContext(fs.readFileSync(input.script,"utf8").replaceAll("} catch (_error) {", "} catch (_error) { globalThis.testError = _error.stack;"),context);
// The page coordinator activates the standalone Target selector.
events["experiment-catalog-refresh"]();
function content(item){return [item.textContent,...item.children.map(content)].join(" ");}
function emit(){process.stdout.write(JSON.stringify({disabled:ids.target.disabled,value:ids.target.value,dataset:ids.target.dataset,pin:ids.target.dataset.materializationId||null,
 options:ids.target.children.map(x=>({value:x.value,text:x.textContent,disabled:x.disabled})),status:ids["target-status"].textContent,
 instrumentsHidden:ids["target-instruments"].hidden,instruments:content(ids["target-instrument-table"]),
 scriptError:context.testError||null,detailsLinkHidden:ids["target-details-link"].hidden,detailsTitle:ids["target-details-title"].textContent,detailsHidden:ids["target-details"].hidden,detailsStatus:ids["target-details-status"].textContent,details:content(ids["target-details-body"]),paths,timeouts,loadingStatuses,loadingOptions}));}
setImmediate(()=>{if(input.selection!==null){ids.target.value=input.selection;ids.target.listeners.change();}if(input.click){ids["target-details-link"].listeners.click();setImmediate(emit);}else emit();});
'''
    output=subprocess.run([node,'-e',script],input=json.dumps({'catalog':catalog,'detail':detail,'click':click,'selection':selection,
        'script':str(PROJECT/'ui/targets.js')}),capture_output=True,text=True,check=True)
    return json.loads(output.stdout)


class FxTargetApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='fx_target_api_')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        inputs=persistence_fixture(self.root)
        inputs['request']['anchors']['mark_ids']=['MARK_0','MARK_1','MARK_2']
        saved=materialize(self.root,inputs['request'])
        self.target_id=saved['target_id'];self.materialization_id=saved['materialization']['id']
        self.catalog=target_library.list_target_library(self.root)
        self.detail=target_library.get_target_detail(self.root,self.target_id,self.materialization_id)
        self.detail_path='/api/target-library/'+self.target_id+'?materialization_id='+self.materialization_id

    def retrospective_catalog(self, decision='ready', policy=True):
        result=deepcopy(self.catalog)
        target=result['targets'][0]
        target['instrument_id']='EURJPY'
        target['construction']={'method':'usd_triangulation','version':'1.0.0','price_basis':'unknown','alignment':'retrospective_date_label_proxy'}
        target['coverage']={'start':'2024-01-02','end':'2024-01-04'}
        capability={'decision':decision,'reason':'Snapshot only; exact close and historical publication unavailable.',
                    'policy':{'id':'POLICY_INTERFACE_FIXTURE','version':'1.0.0','content_sha256':'a'*64} if policy else None}
        capabilities={'retrospective_research':capability,'historical_replay':{'decision':'unresolved','reason':'No historical vintages'},
                      'live_use':{'decision':'unresolved','reason':'No live certification'}}
        target['readiness_capabilities']=capabilities
        target['readiness']='uncertified'
        for saved in target['materializations']:
            saved['research_readiness']='uncertified'
            saved['readiness_capabilities']=capabilities
            saved['coverage']=target['coverage']
        result['instruments']=[{'instrument_id':'EURJPY','display_name':'EURJPY',
            'construction':target['construction'],'dependencies':['EUR/USD','JPY/USD'],
            'price_coverage':target['coverage'],'price_row_count':6,'target_ids':[self.target_id],
            'readiness_capabilities':capabilities}]
        result['instrument_count']=1
        return result

    def test_instrument_and_horizon_filters_use_registry_values(self):
        fixture=self.retrospective_catalog()
        with patch.object(target_library,'list_targets',return_value=fixture):
            selected=target_library.list_target_library(self.root,'EURJPY','2','trading_sessions')
            self.assertEqual(selected['target_count'],1)
            self.assertEqual(selected['instruments'][0]['instrument_id'],'EURJPY')
            self.assertEqual(target_library.list_target_library(self.root,'EURGBP')['target_count'],0)
            self.assertEqual(target_library.list_target_library(self.root,None,'5','calendar_days')['target_count'],0)
        self.assertEqual(fixture['target_count'],1)

    def test_actual_http_list_filter_and_explicit_date_range(self):
        instrument=self.catalog['targets'][0]['investment_series']
        with running(self.root) as address:
            status,_,body=request(address,'/api/target-library?instrument_id='+instrument+'&horizon_amount=2&horizon_unit=trading_sessions')
            self.assertEqual(status,200)
            self.assertEqual(json.loads(body)['target_count'],1)
            status,_,body=request(address,self.detail_path+'&start_inclusive=2024-01-03&end_exclusive=2024-01-04&range_precision=date')
            self.assertEqual(status,200)
            result=json.loads(body)
            self.assertEqual([row['prediction_anchor'] for row in result['observations']],['2024-01-03'])
            self.assertEqual(result['range_selection']['field'],'prediction_anchor')
            self.assertEqual(result['manifest']['id'],self.materialization_id)

    def test_range_never_replaces_historical_availability_check(self):
        with running(self.root) as address:
            status,_,body=request(address,self.detail_path+'&start_inclusive=2024-01-02&end_exclusive=2024-01-03&range_precision=date&training_cutoff=2024-01-03&cutoff_precision=date')
        self.assertEqual(status,200)
        result=json.loads(body)
        self.assertEqual(result['observations'],[])
        self.assertEqual(result['training_selection']['selected_count'],0)

    def test_invalid_filters_reject_instead_of_inventing_precision(self):
        cases=['/api/target-library?horizon_amount=2','/api/target-library?horizon_amount=0&horizon_unit=calendar_days',
               '/api/target-library?horizon_amount=2&horizon_unit=days','/api/target-library?instrument_id=../EURUSD',
               self.detail_path+'&start_inclusive=2024-01-03',self.detail_path+'&range_precision=date',
               self.detail_path+'&start_inclusive=2024-01-04&end_exclusive=2024-01-03&range_precision=date',
               self.detail_path+'&start_inclusive=2024-01-03T00:00:00.000000Z&range_precision=utc_timestamp']
        with running(self.root) as address:
            for path in cases:
                with self.subTest(path=path):
                    status,_,body=request(address,path)
                    self.assertEqual(status,400)
                    self.assertEqual(json.loads(body)['error']['code'],'UNSUPPORTED_QUERY')

    def test_approved_retrospective_family_discloses_uncertified_history_and_live_use(self):
        catalog=weekday_family_catalog(self.retrospective_catalog())
        view=inspect_ui(catalog,self.detail,selection='price',click=True)
        self.assertIsNone(view['scriptError'])
        self.assertFalse(view['disabled'])
        assert_categories(self,view)
        self.assertIsNone(view['pin'])
        self.assertEqual(view['dataset']['returnBasis'],'price')
        self.assertEqual(json.loads(view['dataset']['horizons']),HORIZONS)
        self.assertEqual(view['dataset']['horizonUnit'],'scheduled_weekdays')
        self.assertEqual(len(json.loads(view['dataset']['targetBindings'])),5)
        self.assertIn('provisional retrospective',view['status'].lower())
        self.assertIn('not certified historical',view['status'].lower())
        self.assertIn('Live: unresolved',view['instruments'])
        self.assertTrue(view['detailsLinkHidden'])
        self.assertTrue(view['detailsHidden'])
        self.assertEqual(view['paths'],['/api/target-library'])

    def test_loading_keeps_disabled_categories_and_no_observation_detail_fetch(self):
        view=inspect_ui(weekday_family_catalog(self.retrospective_catalog()),selection='price',click=True)
        self.assertIsNone(view['scriptError'])
        self.assertEqual(view['timeouts'],[300000])
        self.assertEqual(view['loadingStatuses'][0],'Verifying stored Targets… This can take longer while research is preparing data.')
        loading=view['loadingOptions'][0]
        self.assertEqual([(item['value'],item['text']) for item in loading[1:]],CATEGORY_OPTIONS)
        self.assertTrue(all(item['disabled'] for item in loading))
        self.assertEqual(view['paths'],['/api/target-library'])

    def test_family_requires_all_five_populated_horizons(self):
        for missing in HORIZONS:
            with self.subTest(missing=missing):
                catalog=weekday_family_catalog(self.retrospective_catalog())
                catalog['targets']=[item for item in catalog['targets'] if item['horizon']['amount']!=missing]
                catalog['target_count']=len(catalog['targets'])
                view=inspect_ui(catalog)
                self.assertTrue(view['disabled'])
                assert_categories(self,view)
                self.assertEqual(view['dataset'],{})
        catalog=weekday_family_catalog(self.retrospective_catalog())
        catalog['targets'][0]['materializations'][0]['valid_count']=0
        view=inspect_ui(catalog)
        self.assertTrue(view['disabled'])
        self.assertEqual(view['dataset'],{})

    def test_family_binding_spans_instruments_without_individual_options(self):
        first=weekday_family_catalog(self.retrospective_catalog(),tag='cross',instrument_id='EURJPY')
        second=weekday_family_catalog(self.retrospective_catalog(),tag='direct',instrument_id='EURUSD')
        first['targets']+=second['targets']
        first['target_count']=len(first['targets'])
        view=inspect_ui(first,selection='price')
        self.assertFalse(view['disabled'])
        assert_categories(self,view)
        bindings=json.loads(view['dataset']['targetBindings'])
        self.assertEqual(len(bindings),10)
        self.assertEqual({row['target_id'] for row in bindings},{row['target_id'] for row in first['targets']})
        self.assertEqual({row['horizon']['amount'] for row in bindings},set(HORIZONS))
        self.assertEqual({row['definition_version'] for row in bindings},{'1.0.0'})
        for item in view['options']:
            self.assertNotIn('EUR',item['text'])
            self.assertNotIn('weekday',item['text'])
            self.assertNotIn('universe',item['text'].lower())
        for amount in HORIZONS:
            self.assertIn(str(amount),view['status'])

    def test_family_only_binds_the_exact_registered_weekday_calendar(self):
        for schedule in (None,{'calendar_id':'OTHER','calendar_version':'1.0.0','holiday_exclusions':False},
                         {'calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'2.0.0','holiday_exclusions':False},
                         {'calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0','holiday_exclusions':True}):
            with self.subTest(schedule=schedule):
                catalog=weekday_family_catalog(self.retrospective_catalog())
                if schedule is None: catalog['targets'][0].pop('schedule')
                else: catalog['targets'][0]['schedule']=schedule
                view=inspect_ui(catalog)
                self.assertTrue(view['disabled'])
                self.assertEqual(view['dataset'],{})
        catalog=weekday_family_catalog(self.retrospective_catalog())
        catalog['targets'][0]['horizon']['unit']='trading_sessions'
        self.assertTrue(inspect_ui(catalog)['disabled'])

    def test_family_excludes_other_bases_comparisons_and_ineligible_definitions(self):
        for field,value in (('return_basis','total_return'),('return_basis','benchmark_excess'),
                            ('comparison','arithmetic_difference'),('source_eligibility','unverified'),
                            ('definition_state','invalid')):
            with self.subTest(field=field,value=value):
                catalog=weekday_family_catalog(self.retrospective_catalog())
                catalog['targets'][0][field]=value
                view=inspect_ui(catalog)
                self.assertTrue(view['disabled'])
                self.assertEqual(view['dataset'],{})
                assert_categories(self,view)

    def test_total_and_excess_remain_disabled_even_with_interface_fixture_rows(self):
        catalog=weekday_family_catalog(self.retrospective_catalog())
        for basis in ('total_return','benchmark_excess'):
            other=weekday_family_catalog(self.retrospective_catalog(),tag=basis)
            for target in other['targets']:
                target['return_basis']=basis
                if basis=='benchmark_excess':target['comparison']='arithmetic_difference'
            catalog['targets']+=other['targets']
        catalog['target_count']=len(catalog['targets'])
        view=inspect_ui(catalog,selection='price')
        assert_categories(self,view)
        self.assertEqual(len(json.loads(view['dataset']['targetBindings'])),5)
        for basis in ('total_return','benchmark_excess'):
            self.assertEqual(inspect_ui(catalog,selection=basis)['dataset'],{})

    def test_unapproved_or_unpinned_retrospective_policy_never_enables_selection(self):
        for decision,policy in [('unresolved',True),('blocked',True),('ready',False)]:
            with self.subTest(decision=decision,policy=policy):
                view=inspect_ui(weekday_family_catalog(self.retrospective_catalog(decision,policy)))
                self.assertTrue(view['disabled'])
                self.assertIsNone(view['pin'])
                self.assertEqual(view['dataset'],{})
                self.assertTrue(all(option['disabled'] for option in view['options']))

    def test_registered_instruments_visible_without_fabricated_target_definitions(self):
        catalog=self.retrospective_catalog('blocked')
        catalog.update(targets=[],target_count=0)
        catalog['instruments'][0]['target_ids']=[]
        catalog['instruments'][0]['blockers']=['Horizon and calendar policy not approved']
        view=inspect_ui(catalog)
        self.assertTrue(view['disabled'])
        assert_categories(self,view)
        self.assertFalse(view['instrumentsHidden'])
        self.assertIn('EURJPY',view['instruments'])
        self.assertIn('EUR/USD, JPY/USD',view['instruments'])
        self.assertIn('horizon and calendar policy not approved',view['instruments'])
        self.assertEqual(view['dataset'],{})

    def test_disclosure_count_follows_actual_registry_not_requested_universe(self):
        catalog=weekday_family_catalog(self.retrospective_catalog())
        view=inspect_ui(catalog)
        self.assertIn('EURJPY',view['instruments'])
        self.assertNotIn('AUDCAD',view['instruments'])
        self.assertNotIn('43',view['instruments'])
        self.assertEqual(sum(not option['disabled'] for option in view['options']),1)


if __name__=='__main__':unittest.main()
