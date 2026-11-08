"""Execute the opt-in read-model UI against a bounded DOM/fetch harness."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
const fs=require('fs'),vm=require('vm');const input=JSON.parse(fs.readFileSync(0,'utf8'));const ids={},events={},timers=new Map();let sequence=0;
class Element{constructor(tag='div'){this.tag=tag;this.children=[];this.listeners={};this.hidden=false;this.value='';this.textContent='';this.dataset={};this.attributes={};}
append(...n){this.children.push(...n);}replaceChildren(...n){this.children=n;}setAttribute(k,v){this[k]=v;this.attributes[k]=v;}removeAttribute(k){delete this[k];}addEventListener(k,v){this.listeners[k]=v;}querySelector(s){return walk(this).find(n=>s==='[data-role=\"robustness\"]'?n.dataset.role==='robustness':s==='.'+n.className);}}
const get=id=>ids[id]||(ids[id]=new Element());const calls=[];let offset=0;
const ctx={document:{hidden:false,getElementById:get,createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag),querySelector:()=>({content:input.enabled?'enabled':'disabled'}),querySelectorAll:()=>[]},URLSearchParams,AbortController,CustomEvent:class{constructor(type,opt){this.type=type;this.detail=opt.detail;}},
window:{location:{hash:input.hash||'#signals'},setTimeout:(fn,ms)=>{timers.set(++sequence,{fn,ms});return sequence;},clearTimeout:id=>timers.delete(id),addEventListener:(k,v)=>events[k]=v,dispatchEvent:()=>{}},
fetch:async(url,options)=>{calls.push({url,method:options.method});let data=input.routes ? (input.routes[url.split('?')[0]]||{http:404}) : input.responses[Math.min(offset++,input.responses.length-1)];return {ok:!data.http,status:data.http||200,json:async()=>data};}};
const flush=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};const walk=n=>[n,...n.children.filter(x=>x instanceof Element).flatMap(walk)];
(async()=>{if(input.renderer)vm.runInNewContext(fs.readFileSync(input.renderer,'utf8'),ctx);vm.runInNewContext(fs.readFileSync(input.script,'utf8'),ctx);await flush();for(const step of input.steps||[]){const b=Object.values(ids).flatMap(walk).find(n=>n.tag==='button'&&n.textContent===step);if(!b)throw Error('Missing '+step);b.listeners.click();await flush();}
console.log(JSON.stringify({calls,text:Object.values(ids).flatMap(walk).map(n=>n.textContent).join(' '),svgs:Object.values(ids).flatMap(walk).filter(n=>n.tag==='svg').length,hidden:get('signal-detail-home').hidden,timers:[...timers.values()].map(t=>t.ms)}));})().catch(e=>{console.error(e);process.exitCode=1;});
'''


def response(items,**extra):
    return {'schema_version':'read_model_v1','items':items,'total':len(items),'next_cursor':None,'issues':[], 'issue_count':0,
            'freshness':{'generation':'a'*32,'observed_at':'2026-11-05T12:00:00+00:00','state':'current'},**extra}


class ReadModelUITests(unittest.TestCase):
    def run_ui(self,**kwargs):
        data={'script':str(ROOT/'ui/read-model.js'),'enabled':True,'responses':[response([])],**kwargs}
        process=subprocess.run([shutil.which('node') or 'node','-e',HARNESS],input=json.dumps(data),text=True,capture_output=True,check=True)
        return json.loads(process.stdout)

    def test_disabled_ui_does_not_fetch_or_poll(self):
        self.assertEqual(self.run_ui(enabled=False)['calls'],[])

    def test_recipe_cards_load_one_bounded_page_without_filter_bar_or_payloads(self):
        card={'id':'FEATURE_RECIPE_'+'a'*64,'name':'63-day momentum','research':{'relationship_count':1,'research_stage_pass_count':0,'description':'Exact hypotheses'}}
        view=self.run_ui(responses=[response([card],next_cursor='next'),response([])],steps=['Next page'])
        self.assertEqual(len(view['calls']),2)
        self.assertTrue(all(c['method']=='GET' for c in view['calls']))
        self.assertIn('limit=50',view['calls'][0]['url']);self.assertIn('cursor=next',view['calls'][1]['url'])
        self.assertNotIn(30000,view['timers'])

    def test_lazy_relationships_pin_generation_and_show_precheck_as_not_evaluated(self):
        card={'id':'FEATURE_RECIPE_'+'a'*64,'name':'63-day momentum','research':{'relationship_count':1,'research_stage_pass_count':0,'description':'Exact hypotheses'}}
        row={'scope':{'id':'USD'},'horizon':21,'expected_direction':'POSITIVE','p1_status':'admitted','p2_status':'FAILED','p2_evaluation_ran':False,'p2_reason_codes':['DISCOVERY_EFFECT_CONTRADICTS_EXPECTED_DIRECTION'],'research_stage_pass':False,'trial_results':[]}
        view=self.run_ui(responses=[response([card]),response([row])],steps=['View researched relationships'])
        self.assertIn('generation=',view['calls'][1]['url']);self.assertIn('No completed P2 numerical evaluation',view['text']);self.assertFalse(view['hidden'])

    def test_returning_to_first_page_keeps_the_same_generation(self):
        view=self.run_ui(responses=[response([],next_cursor='next'),response([]),response([])],steps=['Next page','Previous page'])
        self.assertIn('generation='+'a'*32,view['calls'][2]['url'])

    def test_failure_does_not_fallback_to_filesystem_api(self):
        view=self.run_ui(responses=[{'http':503}])
        self.assertEqual(len(view['calls']),1)
        self.assertIn('Existing experiments continue independently',view['text'])

    def test_staleness_is_visible_without_claiming_live_worker_health(self):
        view=self.run_ui(hash='#experiment',responses=[response([],freshness={'generation':'a'*32,'observed_at':'2026-11-05T12:00:00+00:00','state':'stale'})])
        self.assertIn('current activity unknown',view['text'])
        self.assertIn('Live worker activity is unavailable',view['text'])
        self.assertIn(30000,view['timers'])


class RichReadModelUITests(ReadModelUITests):
    def test_selected_saved_evidence_uses_only_bounded_endpoints_and_preserves_stage_metrics(self):
        import tempfile
        from read_model.projector import build as metadata
        from read_model.chart_evidence import build as charts, read_evidence
        from read_model.query import detail
        from api.feature_research import feature_research
        from test_feature_research_dashboard import fixture,RECIPE
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve()/'source';out=Path(temp).resolve()/'serving'
            trials=fixture(root,p2='FAILED',direction='NEGATIVE')
            legacy=feature_research(root,RECIPE);row=legacy['relationships'][0]
            row.update(p2_evaluation_ran=True,research_stage_pass=False,p2_reason_codes=[])
            metadata(root,out);charts(root,out)
            card={'id':RECIPE,'name':'63-day momentum','research':{'relationship_count':1,'research_stage_pass_count':0,'description':'Exact saved research'}}
            routes={'/api/read-model/v1/recipes':response([card]),'/api/read-model/v1/recipes/'+RECIPE+'/branches':response([row])}
            for trial in trials:
                routes['/api/read-model/v1/trial/'+trial['id']]=detail(out,'trial',trial['id'])
                routes['/api/read-model/v1/evidence/'+trial['id']]=read_evidence(out,trial['id'])
            for v in row['validation_results']:
                routes['/api/read-model/v1/decision/'+v['id']]=detail(out,'decision',v['id'])
            kwargs={'routes':routes,'renderer':str(ROOT/'ui/signal-research.js'),'steps':['View researched relationships','P2 Validation']}
            view=self.run_ui(**kwargs)
            self.assertIn('Validation outcome',view['text']);self.assertIn('Effect retention',view['text'])
            self.assertIn('0.48',view['text']);self.assertIn('lower Target returns',view['text'])
            self.assertGreater(view['svgs'],0)
            self.assertNotIn('Aligned observations',view['text'])
            self.assertTrue(all(c['url'].startswith('/api/read-model/v1/') and c['method']=='GET' for c in view['calls']))
            routes.pop('/api/read-model/v1/evidence/'+trials[1]['id'])
            view=self.run_ui(**kwargs)
            self.assertIn('Chart and block evidence could not be verified',view['text'])
            self.assertIn('0.48',view['text'])  # chart failure must not erase saved metrics

    def test_live_identity_is_separate_from_snapshot_and_honest_on_failure(self):
        routes={'/api/read-model/v1/queue':response([],status_counts={'queued':49}),
                '/api/read-model/v1/activity':{'schema_version':'live_activity_v1','observed_at':'2026-11-07T12:00:00Z','worker':{'state':'running'},'active':{'request_id':'fixture-request','attempt_id':'fixture-attempt','status':'p2','message':'Evaluating saved P2','updated_at':'2026-11-07T11:55:00Z'}}}
        view=self.run_ui(hash='#experiment',routes=routes)
        self.assertIn('49 waiting',view['text']);self.assertIn('Worker: Running',view['text']);self.assertIn('Evaluating saved P2',view['text'])
        self.assertIn('fixture-request',view['text']);self.assertNotIn('Negative hypothesis program',view['text'])
        routes['/api/read-model/v1/activity']={'http':503}
        view=self.run_ui(hash='#experiment',routes=routes)
        self.assertIn('49 waiting',view['text']);self.assertIn('Live worker activity is unavailable',view['text'])

    def test_live_activity_survives_catalog_read_failure(self):
        routes={'/api/read-model/v1/queue':{'http':503},'/api/read-model/v1/activity':{'schema_version':'live_activity_v1','observed_at':'2026-11-07T12:00:00Z','worker':{'state':'draining'},'active':None}}
        view=self.run_ui(hash='#experiment',routes=routes)
        self.assertIn('Worker: Draining',view['text'])
        self.assertIn('temporarily unavailable',view['text'])
