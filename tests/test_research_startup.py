"""Exercise real page startup against a bounded, contended read-only server.

Catalog and readiness responses deliberately keep server slots occupied. This models the
production failure: a hidden dropdown request must not queue ahead of saved
history or Signal Library, even though each script works in isolation.
"""
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

from test_queue_ui import catalog as queue_catalog
from test_signal_recipe_ui import group

ROOT = Path(__file__).resolve().parents[1]
CATALOGS = {'/api/scope-library', '/api/feature-library', '/api/target-library'}
CONTRACT_READS = CATALOGS | {'/api/research-readiness'}


def startup(hash_value='#experiment', steps=(), *, hold_queue=False, hold_catalogs=True,
            hold_readiness=True, read_model=True, metrics=None):
    node = shutil.which('node')
    if not node:
        raise unittest.SkipTest('Node.js is required to execute the shipped page scripts')
    html = (ROOT / 'ui/index.html').read_text()
    scripts = re.findall(r'<script src="(/[^"?]+\.js)" defer>', html)
    ids = re.findall(r'\bid="([^"]+)"', html)
    signal = group(outputs=[])
    value = {
        'root': str(ROOT), 'scripts': scripts, 'ids': ids, 'hash': hash_value,
        'steps': list(steps), 'holdQueue': hold_queue, 'holdCatalogs': hold_catalogs,
        'holdReadiness': hold_readiness, 'readModel': read_model,
        'responses': {
            '/api/research-metrics': metrics or {'schema_version':'research_metrics_v1','counting_unit':'canonical_research_jobs','observed_at':'2026-11-19T12:00:00+00:00','queued':23,'completed_last_hour':5},
            '/api/read-model/v1/ledger': {'schema_version':'read_model_v1','items':[],'total':0,'next_cursor':None,'issue_count':0,'freshness':{'generation':'a'*32,'observed_at':'2026-11-19T12:00:00+00:00','state':'current'}},
            '/api/read-model/v1/recipes': {'schema_version':'read_model_v1','items':[],'total':0,'next_cursor':None,'issue_count':0,'freshness':{'generation':'a'*32,'observed_at':'2026-11-19T12:00:00+00:00','state':'current'}},
            '/api/experiments': queue_catalog('succeeded'),
            '/api/signal-library-summaries': {
                'schema_version': '1.0.0', 'entries': [signal], 'entry_count': 1, 'issues': []},
            '/api/feature-library': {'schema_version': '1.0.0', 'features': [], 'feature_count': 0, 'issues': []},
            '/api/scope-library': {'schema_version': '1.0.0', 'scopes': [], 'scope_count': 0, 'issues': []},
            '/api/target-library': {'schema_version': '1.0.0', 'targets': [], 'target_count': 0, 'issues': []},
            '/api/research-readiness': {'execution_enabled': True, 'blockers': [], 'submission_incidents': []},
        },
    }
    harness = r'''
const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.listeners={};this.attributes={};this.value='';this.textContent='';this.disabled=false;this.hidden=false;this.open=false;this.validity={valid:true};}
 append(...items){for(const item of items){if(item.parentElement)item.parentElement.children=item.parentElement.children.filter(x=>x!==item);item.parentElement=this;this.children.push(item);}}
 replaceChildren(...items){for(const item of this.children)item.parentElement=null;this.children=[];this.append(...items);}
 addEventListener(n,fn){(this.listeners[n] ||= []).push(fn);}
 fire(n,event={}){for(const fn of this.listeners[n]||[])fn({target:this,preventDefault(){},...event});}
 setAttribute(k,v){this.attributes[k]=String(v);} getAttribute(k){return this.attributes[k]??null;} removeAttribute(k){delete this.attributes[k];}
 setCustomValidity(message){this.validationMessage=message;this.validity={valid:!message};}
 focus(){} click(){this.fire('click');} scrollIntoView(){}
 get options(){return this.children.flatMap(x=>x.tag==='optgroup'?x.children:[x]).filter(x=>x.tag==='option');}
 get selectedOptions(){return this.options.filter(x=>x.value===this.value);}
}
const ids=Object.fromEntries(input.ids.map(id=>[id,new Element(id)]));
const skip=new Element('a'),nav=['experiment','signals','ledger'].map(page=>{const e=new Element('a');e.dataset.page=page;return e;});
const events={},docEvents={},timers=new Map(),calls=[],waiting=[],active=[],timeline=[],snapshots=[];
let clock=Date.parse('2026-11-19T12:00:00Z'),nextTimer=0;
const add=(map,n,fn)=>(map[n] ||= []).push(fn);
const fire=(map,n,e={})=>{for(const fn of map[n]||[])fn(e);};
const catalogs=new Set(['/api/feature-library','/api/scope-library','/api/target-library']);
const held=url=>catalogs.has(url)&&input.holdCatalogs || ['/api/experiments','/api/research-metrics'].includes(url)&&input.holdQueue ||
 url==='/api/research-readiness'&&input.holdReadiness;
function finish(request,error=false){
 if(request.done)throw Error('Request already settled');
 request.done=true;active.splice(active.indexOf(request),1);
 timeline.push({type:'response',url:request.url});
 if(error)request.reject(Error('Fixture network failure'));
 else request.resolve({ok:true,status:200,json:async()=>input.responses[request.url.split('?')[0]]});
 pump();
}
function pump(){
 while(active.length<4&&waiting.length){
  const request=waiting.shift();active.push(request);request.started=true;
  timeline.push({type:'start',url:request.url,slots:active.length});
  if(!held(request.url))queueMicrotask(()=>finish(request));
 }
}
const context={URLSearchParams,AbortController,Date:class extends Date{static now(){return clock;}},
 CustomEvent:class{constructor(type,options={}){this.type=type;this.detail=options.detail;}},
 document:{getElementById:id=>ids[id]||null,createElement:tag=>new Element(tag),
  createElementNS:(_,tag)=>new Element(tag),createDocumentFragment:()=>new Element('fragment'),
  createTextNode:text=>{const e=new Element('text');e.textContent=text;return e;},
  querySelector:selector=>selector==='.skip-link'?skip:selector==='meta[name="gambit-read-model"]'?{content:input.readModel?'enabled':'disabled'}:selector==='meta[name="gambit-queue-metrics"]'?{content:'enabled'}:null,querySelectorAll:selector=>selector==='[data-page]'?nav:[],
  hidden:false,visibilityState:'visible',addEventListener:(n,fn)=>add(docEvents,n,fn)},
 window:{location:{hash:input.hash},localStorage:{getItem:()=>null,setItem:()=>{throw Error('Unexpected storage write');}},
  addEventListener:(n,fn)=>add(events,n,fn),dispatchEvent:e=>{timeline.push({type:'event',event:e.type,detail:e.detail});fire(events,e.type,e);},
  setTimeout:(fn,ms)=>{const id=++nextTimer;timers.set(id,{fn,ms,at:clock+ms});return id;},clearTimeout:id=>timers.delete(id)},
 fetch:(url,options={})=>new Promise((resolve,reject)=>{
  if(!Object.hasOwn(input.responses,url.split('?')[0]))throw Error('Unexpected endpoint: '+url);
  const request={url,method:options.method||'GET',body:options.body??null,resolve,reject,started:false,done:false,aborted:false};
  calls.push(request);waiting.push(request);
  // Aborting a browser fetch does not interrupt the work already on the server.
  options.signal?.addEventListener('abort',()=>{request.aborted=true;reject(Error('Client deadline'));},{once:true});pump();
 })};
const text=n=>[n.textContent,...n.children.map(text)].join(' ');
const flush=async()=>{for(let n=0;n<12;n++)await new Promise(r=>setImmediate(r));};
function snap(){snapshots.push({hash:context.window.location.hash,calls:calls.map(x=>({url:x.url,method:x.method,body:x.body,started:x.started,done:x.done,aborted:x.aborted})),
 active:active.map(x=>x.url),waiting:waiting.map(x=>x.url),timeline:[...timeline],
 ledger:ids['ledger-status'].textContent,ledgerRows:text(ids['ledger-items']),queue:ids['queue-status'].textContent,
 signals:ids['signal-library-status'].textContent,signalCards:text(ids['signal-table-container']),
 example:ids['contract-example'].textContent,queued:ids['queue-waiting-count'].textContent,completed:ids['queue-completed-count'].textContent,
 timers:[...timers.values()].map(x=>x.ms),catalogBusy:Object.fromEntries(['feature','scope','target'].map(x=>[x,ids[x].getAttribute('aria-busy')]))});}
(async()=>{
 for(const script of input.scripts)vm.runInNewContext(fs.readFileSync(input.root+'/ui'+script,'utf8'),context,{filename:script});
 await flush();snap();
 for(const step of input.steps){
  clock+=step.ms||0;
  if(step.action==='navigate'){context.window.location.hash=step.hash;fire(events,'hashchange');}
  if(step.action==='event')fire(events,step.name,{detail:step.detail});
  if(step.action==='visibility'){context.document.hidden=step.hidden;context.document.visibilityState=step.hidden?'hidden':'visible';fire(docEvents,'visibilitychange');}
  if(step.action==='click')ids[step.id].click();
  if(step.action==='select'){ids[step.id].value=step.value;ids[step.id].fire('change');}
  if(step.action==='settle'){
   const request=active.filter(x=>x.url===step.url&&!x.done)[step.index||0];if(!request)throw Error('No active request to settle: '+step.url);
   finish(request,step.error);
  }
  if(step.action==='settle-catalog'){
   const request=active.find(x=>catalogs.has(x.url)&&!x.done);if(!request)throw Error('No active catalog to settle');finish(request,step.error);
  }
  if(step.action==='poll'){const t=[...timers].find(([,v])=>v.ms===30000);if(t){timers.delete(t[0]);t[1].fn();}}
  if(step.action==='advance')for(const [id,t] of [...timers])if(t.at<=clock){timers.delete(id);t.fn();}
  await flush();snap();
 }
 process.stdout.write(JSON.stringify(snapshots));
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    result = subprocess.run([node, '-e', harness], input=json.dumps(value), text=True,
                            capture_output=True, timeout=15)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class ResearchStartupTests(unittest.TestCase):
    def test_queue_loads_only_two_operational_counts(self):
        for address in ('', '#experiment', '#experiment-inputs', '#trial-example'):
            for enabled in (True, False):
                with self.subTest(address=address, read_model=enabled):
                    view=startup(address,read_model=enabled)[0]
                    self.assertEqual(['/api/research-metrics'],[r['url'] for r in view['calls']])
                    self.assertEqual(('23','5'),(view['queued'],view['completed']))
                    self.assertIn(30000,view['timers'])
                    self.assertEqual('DISCOVERY_SIGN_V1',json.loads(view['example'])['expected_direction'])
    def test_history_and_library_never_load_contract_catalogs_or_counts(self):
        for address,endpoint in (('#ledger','ledger'),('#signals','recipes')):
            view=startup(address)[0]
            self.assertEqual(['/api/read-model/v1/'+endpoint+'?limit=50'],[r['url'] for r in view['calls']])
            self.assertNotIn(30000,view['timers'])
    def test_static_selection_updates_example_without_network_or_storage(self):
        feature='FEATURE_RECIPE_e79063e3de1bf94bb82c5cb5e276841abb70655eeadfda47e8851562205a90f6'
        views=startup('#experiment',[{'action':'select','id':'feature','value':feature},{'action':'select','id':'scope','value':'USDJPY'}])
        self.assertEqual(views[0]['calls'],views[-1]['calls'])
        example=json.loads(views[-1]['example'])
        self.assertEqual(feature,example['feature']['id']);self.assertEqual('USDJPY',example['scope']['id'])
        from research.contracts import normalize_submission
        normalize_submission(dict(example,request_id='12345678-1111-4111-8111-111111111111'))
    def test_poll_and_refresh_are_read_only_and_pause_on_other_pages(self):
        views=startup('#experiment',[{'action':'poll'},{'action':'click','id':'queue-refresh'},{'action':'navigate','hash':'#ledger'},{'action':'poll'}])
        self.assertEqual(3,sum(r['url']=='/api/research-metrics' for r in views[-1]['calls']))
        self.assertTrue(all(r['method']=='GET' and r['body'] is None for r in views[-1]['calls']))
        self.assertNotIn(30000,views[-1]['timers'])
    def test_stale_invalid_or_negative_counts_show_unknown_not_zero(self):
        valid={'schema_version':'research_metrics_v1','counting_unit':'canonical_research_jobs','observed_at':'2026-11-19T12:00:00Z','queued':23,'completed_last_hour':5}
        for changes in ({'queued':-1},{'completed_last_hour':None},{'observed_at':'2026-11-19T11:58:00Z'},{'observed_at':'2026-11-20T12:00:00Z'},{'schema_version':'bad'}):
            with self.subTest(changes=changes):
                v=startup(metrics=dict(valid,**changes))[0]
                self.assertEqual(('—','—'),(v['queued'],v['completed']));self.assertIn('unavailable',v['queue'])
    def test_failed_refresh_clears_old_counts_and_preserves_contract_example(self):
        views=startup('#experiment',[{'action':'settle','url':'/api/research-metrics'},{'action':'click','id':'queue-refresh'},{'action':'settle','url':'/api/research-metrics','error':True}],hold_queue=True)
        self.assertEqual('23',views[1]['queued']);self.assertEqual('—',views[-1]['queued']);self.assertTrue(views[-1]['example'])
    def test_page_is_static_and_examples_match_registered_definitions(self):
        from html.parser import HTMLParser
        class Options(HTMLParser):
            def __init__(self):super().__init__();self.name=None;self.choices={}
            def handle_starttag(self,tag,attrs):
                a=dict(attrs)
                if tag=='select':self.name=a.get('id');self.choices.setdefault(self.name,[])
                if tag=='option' and self.name:self.choices[self.name].append(a['value'])
            def handle_endtag(self,tag):
                if tag=='select':self.name=None
        html=(ROOT/'ui/index.html').read_text();parser=Options();parser.feed(html)
        for kind in ('feature','scope'):
            self.assertEqual(3,len(parser.choices[kind]))
            for name in parser.choices[kind]:self.assertTrue((ROOT/'definitions'/('feature_recipes' if kind=='feature' else 'scopes')/name/'1.0.0.json').is_file())
        self.assertEqual(['price_return'],parser.choices['target'])
        self.assertNotIn('expected-direction',parser.choices)
        self.assertNotIn('<script src="/submission.js"',html)
        for old in ('features','targets','scopes'):self.assertNotIn('<script src="/'+old+'.js"',html)
        self.assertNotIn('id="contract-refresh"',html);self.assertNotIn('Loading features',html)
        self.assertIn('1, 7, 21 and 63',html)

if __name__=='__main__':unittest.main()
