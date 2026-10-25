"""Real immutable records, HTTP projections, and shipped dashboard interaction tests."""
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from api.feature_research import feature_research, trial_evidence
from research.contracts import ref, digest, ResearchError
from research.store import ResearchStore
from test_signal_library_api import inventory, running, request

ROOT=Path(__file__).resolve().parents[1]
RECIPE='FEATURE_RECIPE_'+digest('dashboard recipe')
SPEC={'id':'RSPEC_TEST','version':'2.0.0','content_sha256':digest('spec')}


def fixture(root, mode='CS', horizon=21, p2='VALIDATED', direction='POSITIVE', scope='G10'):
    s=ResearchStore(root)
    relation=s.put('relationship',{'mode':mode,'horizon':horizon,'scope':scope,'p2':p2,'direction':direction},
        {'recipe':{'id':RECIPE,'version':'1.0.0','content_sha256':digest(RECIPE)},'scope':{'id':scope,'version':'1.0.0','content_sha256':digest(scope)},
         'mode':mode,'horizon':horizon,'target_family':'price_return','expected_direction':direction})
    rows=[{'date':str(date(2020,1,1)+timedelta(days=i)), 'instrument':'EURUSD','feature':str(i/1000),
           'target':str(i/3000), 'lineage':{'fixture_row':i}} for i in range(1301)]
    history=[{'anchor_date':'2020-01-02','rank_ic':'0.5','instrument_count':3},
             {'anchor_date':'2020-01-06','rank_ic':'-0.25','instrument_count':3}]
    trials=[]
    for stage in ['P1'] + (['P2'] if p2 not in ('PRECHECK','NOT_RUN') else []):
        key={'relationship':ref(relation),'stage':stage,'research_spec':SPEC,
             'period':{'start_inclusive':'2020-01-01' if stage=='P1' else '2022-01-01',
                       'end_exclusive':'2022-01-01' if stage=='P1' else '2026-09-01'},
             'discovery_trial':ref(trials[0]) if trials else None}
        artifact=s.artifact(key,{'aligned_sample':rows, 'observation_exclusions':rows[:3],
            'cross_sectional_ic_history':history if mode=='CS' else [],
            'stability':{'full_sample_sign':'positive','subperiods':[{'start':'2020-01-02','end':'2020-01-06',
                'primary_statistic':'0.125','statistic_sign':'positive','observation_count':2}]},
            'blocks':[{'start':'2022-01-01','end':'2022-06-01','oriented_effect':'0.06','raw_effect':'0.06',
                'expected_sign':True,'observation_count':10}], 'leaveouts':[{'omitted_block':1,'oriented_effect':'0.05'}],
            'robustness_slices':[{'oriented_effect':'0.04'},{'oriented_effect':'0.07'}],
            'scheduled_hac':{'missing_scheduled_period_count':1,'usable_dates':['2020-01-02','2020-01-06']}})
        metrics={'primary_effect':'0.125','predictive_coefficient':'0.125','alpha':'0.01','mean_rank_ic':'0.125',
            'hac_t_statistic':'2.84','hac_standard_error':'0.044','hac_maxlags':20,'median_rank_ic':'0.125',
            'positive_ic_frequency':'0.5','negative_ic_frequency':'0.5','time_series_spearman_ic':'0.03',
            'raw_discovery_effect':'0.125','oriented_discovery_effect':'0.125','oriented_validation_effect':'0.06',
            'effect_retention_ratio':'0.48','directional_hac_t_statistic':'2.1','directional_p_value':'0.018'}
        evidence=({'execution_completed':{'status':'pass'},'absolute_hac_t':{'status':'pass','minimum':'2'},
                    'sign_stability':{'status':'pass','observed':3,'minimum':2}} if stage=='P1' else
                  {key:{'status':'pass'} for key in ['discovery_direction','sample_sufficiency','direction','magnitude','inference','stability']})
        if horizon==252 and stage=='P2':evidence['inference']['status']='diagnostic'
        trials.append(s.put('trial',key,{'stage':stage,'mode':mode,'horizon':horizon,'metrics':metrics,'sample':{
            'usable_date_count':2,'usable_pair_count':1301,'excluded_pair_count':3,'incomplete_dates':[],
            'effective_observation_count':30,'minimum_effective_observations':15,'validation_data_accessed':stage=='P2'},
            'evidence':evidence,'artifact_manifests':[ref(artifact)], 'reason_codes':[],
            'fdr_diagnostics':{'family_size':1,'adjusted_p_value':'0.018'} if stage=='P2' else None}))
    admission=s.put('admission',{'relation':ref(relation)}, {'relationship':ref(relation),'trial':ref(trials[0]),
                   'decision':'rejected' if p2=='NOT_RUN' else 'admitted'})
    validations=[]
    if p2!='NOT_RUN':
        validations=[s.put('validation',{'relation':ref(relation)}, {'relationship':ref(relation),
            'discovery_trial':ref(trials[0]),'evaluation_trial':None if p2=='PRECHECK' else ref(trials[1]),
            'decision':'FAILED' if p2=='PRECHECK' else p2,'research_spec':SPEC,
            'period':{'start_inclusive':'2022-01-01','end_exclusive':'2026-09-01'},
            'reason_codes':['DISCOVERY_EFFECT_CONTRADICTS_EXPECTED_DIRECTION'] if p2=='PRECHECK' else []})]
    s.put('link',{'relation':ref(relation)}, {'relationship':ref(relation),'trial_results':list(map(ref,trials)),
          'admission_results':[ref(admission)],'validation_results':list(map(ref,validations))})
    return trials


class DashboardAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def test_exact_metrics_evidence_and_scope_without_writes(self):
        trials=fixture(self.root);before=inventory(self.root);data=feature_research(self.root,RECIPE)
        r=data['relationships'][0];self.assertEqual(r['scope']['id'],'G10');self.assertEqual(r['horizon'],21)
        self.assertEqual(r['results'][0]['metrics'],trials[0]['body']['metrics'])
        self.assertEqual(r['results'][1]['authority'],ref(trials[1]));self.assertEqual(r['p2_status'],'VALIDATED')
        self.assertEqual(inventory(self.root),before)
    def test_precheck_preserves_failed_without_inventing_validation_statistics(self):
        fixture(self.root,p2='PRECHECK');r=feature_research(self.root,RECIPE)['relationships'][0]
        self.assertEqual(r['p2_status'],'FAILED');self.assertEqual([x['stage'] for x in r['results']],['P1'])
        self.assertIsNone(r['validations'][0]['evaluation_trial'])
    def test_distinct_horizons_scopes_and_directions_are_not_combined(self):
        fixture(self.root);fixture(self.root,horizon=7,direction='NEGATIVE',scope='EURUSD',mode='TS')
        r=feature_research(self.root,RECIPE)['relationships'];self.assertEqual(len(r),2)
        self.assertEqual({(v['scope']['id'],v['expected_direction'],v['horizon']) for v in r},{('G10','POSITIVE',21),('EURUSD','NEGATIVE',7)})
    def test_corrupt_unrelated_link_is_reported_without_hiding_verified_results(self):
        fixture(self.root)
        store=ResearchStore(self.root);path=store.path('link','RESEARCHLINK_'+'f'*64);path.write_text('{')
        result=feature_research(self.root,RECIPE)
        self.assertEqual(len(result['relationships']),1)
        self.assertEqual(result['issues'][0]['record_id'],path.stem)
    def test_cs_chart_uses_all_dates_and_actual_spacing(self):
        t=fixture(self.root)[0];d=trial_evidence(self.root,t['id'])
        self.assertEqual(d['chart']['points'],[{'x':'2020-01-02','y':.5,'date':'2020-01-02'}, {'x':'2020-01-06','y':.25,'date':'2020-01-06'}])
        self.assertEqual(d['artifacts']['scheduled_hac']['missing_scheduled_period_count'],1)
        self.assertNotIn('usable_dates',d['artifacts']['scheduled_hac'])
    def test_scatter_is_bounded_without_changing_authoritative_statistics(self):
        t=fixture(self.root,mode='TS')[0];d=trial_evidence(self.root,t['id']);self.assertEqual(d['chart']['total_count'],1301)
        self.assertEqual(d['chart']['display_count'],1200);self.assertEqual(d['chart']['points'][-1]['x'],1.3)
        self.assertEqual(ResearchStore(self.root).get('trial',t['id'])['body']['metrics'],t['body']['metrics'])
    def test_paginated_evidence_retains_full_rows_and_lineage(self):
        t=fixture(self.root)[0];d=trial_evidence(self.root,t['id'],'aligned_sample',100)
        self.assertEqual(len(d['rows']),100);self.assertEqual(d['rows'][0]['lineage'],{'fixture_row':100});self.assertEqual(d['total'],1301)
    def test_corrupt_evidence_fails_closed(self):
        t=fixture(self.root)[0];p=next((self.root/'storage/payloads/sha256').rglob('*.json'));p.write_text('[]')
        with self.assertRaises(ResearchError):trial_evidence(self.root,t['id'])
        with self.assertRaises(ResearchError):feature_research(self.root,RECIPE)
    def test_http_routes_and_invalid_queries(self):
        t=fixture(self.root)[0]
        with running(self.root) as addr:
            for path in ['/api/feature-research/'+RECIPE,'/api/trial-evidence/'+t['id'], '/api/trial-evidence/'+t['id']+'?role=aligned_sample&offset=100']:
                code,_,body=request(addr,path);self.assertEqual(code,200,body);self.assertEqual(json.loads(body)['schema_version'],'1.0.0')
            for suffix in ['?role=secret','?offset=-1','?role=aligned_sample&offset=no','?role=aligned_sample&role=aligned_sample','?offset=100']:
                self.assertEqual(request(addr,'/api/trial-evidence/'+t['id']+suffix)[0],400)
            self.assertEqual(request(addr,'/api/feature-research/invalid')[0],400)


HARNESS=r'''
const fs=require('fs'),vm=require('vm');const input=JSON.parse(fs.readFileSync(0,'utf8'));
class Node { constructor(tag){this.tag=tag;this.children=[];this.listeners={};this.dataset={};this.attributes={};this.textContent='';this.value='';this.disabled=false;}
append(...children){this.children.push(...children);}replaceChildren(...children){this.children=children;}
setAttribute(k,v){this.attributes[k]=v;}addEventListener(k,v){this.listeners[k]=v;}
querySelector(s){return find(this,n=>s==='[data-role="robustness"]'?n.dataset.role==='robustness':s==='.'+n.className);}}
function find(n,fn){return fn(n)?n:n.children.map(c=>find(c,fn)).find(Boolean);}
function all(n,fn){return (fn(n)?[n]:[]).concat(...n.children.map(c=>all(c,fn)));}
const host=new Node('host'),requests=[],pending=[];
const window={setTimeout:()=>1,clearTimeout:()=>{}};
const ctx={window,document:{createElement:t=>new Node(t),createElementNS:(_,t)=>new Node(t)},AbortController,
fetch:async(url,opts)=>{requests.push({url,method:opts.method});if(input.hold?.includes(url))return new Promise(resolve=>pending.push({url,resolve}));return {ok:!!input.responses[url],json:async()=>input.responses[url]};}};
const flush=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
const snapshots=[];const text=n=>[n.textContent,...n.children.map(text)].join(' ');
const visible=n=>n.tag==='details' ? n.children.filter(c=>c.tag==='summary').map(visible).join(' ') : [n.textContent,...n.children.map(visible)].join(' ');
function snap(){snapshots.push({text:text(host),primaryText:visible(host),selectOptions:all(host,n=>n.tag==='option').map(n=>n.textContent),requests:[...requests],buttons:all(host,n=>n.tag==='button').map(n=>({label:n.textContent,disabled:n.disabled,pressed:n.attributes['aria-pressed']})),svgs:all(host,n=>n.tag==='svg').length});}
(async()=>{vm.runInNewContext(fs.readFileSync(input.script,'utf8'),ctx);window.SignalResearch.mount(host,input.entry);await flush();snap();
for(const step of input.steps){if(step.action==='button'){const b=find(host,n=>n.tag==='button'&&n.textContent===step.label);if(!b)throw Error('Missing button '+step.label);if(!b.disabled)b.listeners.click();}
else if(step.action==='context'){const s=find(host,n=>n.tag==='select'&&n.attributes['aria-label']==='Scope · hypothesis');s.value=all(s,n=>n.tag==='option')[step.index].value;s.listeners.change();}
else if(step.action==='settle'){const p=pending[step.index];p.resolve({ok:true,json:async()=>input.responses[p.url]});}
await flush();snap();}process.stdout.write(JSON.stringify(snapshots));})().catch(e=>{console.error(e);process.exitCode=1;});
'''


class DashboardUITests(unittest.TestCase):
    setUp = DashboardAPITests.setUp
    def ui(self,steps=(),hold=(),data=None):
        data=data if data is not None else feature_research(self.root,RECIPE);responses={'/api/feature-research/'+RECIPE:data}
        for r in data['relationships']:
            for t in r['results']:
                path='/api/trial-evidence/'+t['authority']['id'];responses[path]=trial_evidence(self.root,t['authority']['id'])
                for offset in (0,100):responses[path+f'?role=aligned_sample&offset={offset}']=trial_evidence(self.root,t['authority']['id'],'aligned_sample',offset)
        proc=subprocess.run([shutil.which('node'),'-e',HARNESS],input=json.dumps({'script':str(ROOT/'ui/signal-research.js'),
            'entry':{'recipe':{'id':RECIPE}},'responses':responses,'steps':steps,'hold':hold}),text=True,capture_output=True,check=True)
        return json.loads(proc.stdout)
    def test_stage_tabs_real_values_chart_evidence_and_pagination(self):
        fixture(self.root);v=self.ui([{'action':'button','label':'P2 Validation'},{'action':'button','label':'Aligned observations'},{'action':'button','label':'Next'}])
        self.assertIn('Mean rank IC',v[0]['text'].replace('mean','Mean'));self.assertIn('HAC t-statistic',v[0]['text']);self.assertEqual(v[0]['svgs'],1)
        self.assertIn('Effect retention',v[1]['text']);self.assertIn('Leave-one-block-out',v[1]['text']);self.assertIn('Chronological halves',v[1]['text']);self.assertIn('0.48',v[1]['text'])
        self.assertIn('101–200 of 1,301 saved rows',v[3]['text']);self.assertTrue(all(r['method']=='GET' for r in v[3]['requests']))
    def test_unmaterialized_untested_definition_has_honest_empty_state(self):
        v=self.ui()[0];self.assertIn('No research results yet',v['text']);self.assertEqual(v['svgs'],0);self.assertEqual(len(v['requests']),1)
        self.assertNotIn('Experiment page',v['text']);self.assertNotIn('registered',v['text'])
    def test_precheck_and_rejected_do_not_show_fake_validation_charts(self):
        for outcome in ('PRECHECK','NOT_RUN'):
            with self.subTest(outcome=outcome):
                # Independent directories keep outcomes from sharing context.
                self.root=Path(self.temp.name)/outcome;fixture(self.root,p2=outcome)
                v=self.ui([{'action':'button','label':'P2 Validation'}])[-1]
                self.assertEqual(v['svgs'],0);self.assertNotIn('Effect retention',v['text'])
                self.assertIn('before a P2 evaluation' if outcome=='PRECHECK' else 'P1 did not admit',v['text'])
    def test_negative_hypothesis_and_252_diagnostic_are_explicit(self):
        fixture(self.root,mode='TS',direction='NEGATIVE',horizon=252)
        v=self.ui([{'action':'button','label':'P2 Validation'}])[-1]
        self.assertIn('lower Target returns',v['text']);self.assertIn('Diagnostic',v['text']);self.assertIn('5 of 5 required',v['text']);self.assertNotIn('IC history',[b['label'] for b in v['buttons']])
    def test_missing_horizons_disabled_and_ts_has_no_cs_metrics(self):
        fixture(self.root,mode='TS');v=self.ui()[0]
        self.assertIn('predictive coefficient β',v['text']);self.assertNotIn('Daily IC direction',v['text']);self.assertNotIn('Cumulative rank IC',v['text'])
        self.assertTrue(next(b for b in v['buttons'] if b['label']=='7')['disabled'])
    def test_forecast_horizon_and_readable_scope_keep_exact_ids_in_provenance(self):
        fixture(self.root)
        data=feature_research(self.root,RECIPE)
        data['relationships'][0]['scope_label']='USD currency basket'
        view=self.ui(data=data)[0]
        self.assertIn('Forecast horizon · scheduled weekdays',view['primaryText'])
        self.assertIn('21-day forecast horizon',view['primaryText'])
        self.assertIn('USD currency basket',view['primaryText'])
        self.assertNotIn(RECIPE,view['primaryText'])
        self.assertNotIn('TRIAL_',view['primaryText'])
        self.assertNotIn(SPEC['id'],view['primaryText'])
        self.assertIn(RECIPE,view['text'])
        self.assertIn(SPEC['id'],view['text'])

    def test_multiple_saved_branches_use_readable_labels_not_hash_suffixes(self):
        fixture(self.root)
        data=feature_research(self.root,RECIPE)
        other=deepcopy(data['relationships'][0]);other['projection']['id']='RESEARCHLINK_'+'d'*64
        data['relationships'].append(other)
        view=self.ui(data=data)[0]
        options=' '.join(view['selectOptions'])
        self.assertIn('Saved result 1',options);self.assertIn('Saved result 2',options)
        self.assertNotIn('dddddddddddd',options)
        self.assertNotIn(other['projection']['id'],view['primaryText'])

    def test_partial_research_warning_preserves_verified_results_and_exact_refs(self):
        fixture(self.root)
        data=feature_research(self.root,RECIPE)
        data['issues']=[{'code':'UNAVAILABLE_RESEARCH_LINK','record_id':'RESEARCHLINK_'+'b'*64,
                        'message':'A saved result could not be verified.'}]
        view=self.ui(data=data)[0]
        self.assertIn('Some research records are unavailable',view['primaryText'])
        self.assertIn('mean rank IC',view['primaryText'])
        self.assertIn('0.125',view['primaryText'])
        self.assertEqual(view['svgs'],1)
        self.assertIn('Retry research',[b['label'] for b in view['buttons']])
        self.assertNotIn(data['issues'][0]['record_id'],view['primaryText'])
        self.assertIn(data['issues'][0]['record_id'],view['text'])

    def test_all_unavailable_research_does_not_claim_nothing_was_tested(self):
        data={'schema_version':'1.0.0','recipe_id':RECIPE,'relationships':[],
              'issues':[{'code':'UNAVAILABLE_RESEARCH_LINK','record_id':'RESEARCHLINK_bad',
                         'message':'A saved result could not be verified.'}]}
        view=self.ui(data=data)[0]
        self.assertIn('Research verification incomplete',view['primaryText'])
        self.assertIn('No verified results available',view['primaryText'])
        self.assertNotIn('No research results yet',view['primaryText'])
        self.assertEqual(view['svgs'],0)
        self.assertIn('Retry research',[b['label'] for b in view['buttons']])

    def test_invalid_partial_warning_projection_fails_closed(self):
        fixture(self.root)
        data=feature_research(self.root,RECIPE);data['issues']={'not':'an array'}
        view=self.ui(data=data)[0]
        self.assertIn('Saved research could not be verified',view['text'])
        self.assertEqual(view['svgs'],0)

    def test_stale_evidence_response_cannot_replace_new_stage(self):
        t=fixture(self.root);v=self.ui([{'action':'button','label':'P2 Validation'},{'action':'settle','index':0}],hold=['/api/trial-evidence/'+t[0]['id']])
        self.assertIn('Validation outcome',v[-1]['text']);self.assertNotIn('Admission checklist',v[-1]['text']);self.assertEqual(v[-1]['svgs'],1)
