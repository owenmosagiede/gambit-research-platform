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


def startup(hash_value='#ledger', steps=(), *, hold_queue=False, hold_catalogs=True,
            hold_readiness=True):
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
        'holdReadiness': hold_readiness,
        'responses': {
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
let clock=1000000,nextTimer=0;
const add=(map,n,fn)=>(map[n] ||= []).push(fn);
const fire=(map,n,e={})=>{for(const fn of map[n]||[])fn(e);};
const catalogs=new Set(['/api/feature-library','/api/scope-library','/api/target-library']);
const held=url=>catalogs.has(url)&&input.holdCatalogs || url==='/api/experiments'&&input.holdQueue ||
 url==='/api/research-readiness'&&input.holdReadiness;
function finish(request,error=false){
 if(request.done)throw Error('Request already settled');
 request.done=true;active.splice(active.indexOf(request),1);
 timeline.push({type:'response',url:request.url});
 if(error)request.reject(Error('Fixture network failure'));
 else request.resolve({ok:true,status:200,json:async()=>input.responses[request.url]});
 pump();
}
function pump(){
 while(active.length<4&&waiting.length){
  const request=waiting.shift();active.push(request);request.started=true;
  timeline.push({type:'start',url:request.url,slots:active.length});
  if(!held(request.url))queueMicrotask(()=>finish(request));
 }
}
const context={AbortController,Date:class extends Date{static now(){return clock;}},
 CustomEvent:class{constructor(type,options={}){this.type=type;this.detail=options.detail;}},
 document:{getElementById:id=>ids[id]||null,createElement:tag=>new Element(tag),
  createElementNS:(_,tag)=>new Element(tag),createDocumentFragment:()=>new Element('fragment'),
  createTextNode:text=>{const e=new Element('text');e.textContent=text;return e;},
  querySelector:selector=>selector==='.skip-link'?skip:null,querySelectorAll:selector=>selector==='[data-page]'?nav:[],
  hidden:false,visibilityState:'visible',addEventListener:(n,fn)=>add(docEvents,n,fn)},
 window:{location:{hash:input.hash},localStorage:{getItem:()=>null,setItem:()=>{throw Error('Unexpected storage write');}},
  addEventListener:(n,fn)=>add(events,n,fn),dispatchEvent:e=>{timeline.push({type:'event',event:e.type,detail:e.detail});fire(events,e.type,e);},
  setTimeout:(fn,ms)=>{const id=++nextTimer;timers.set(id,{fn,ms,at:clock+ms});return id;},clearTimeout:id=>timers.delete(id)},
 fetch:(url,options={})=>new Promise((resolve,reject)=>{
  if(!Object.hasOwn(input.responses,url))throw Error('Unexpected endpoint: '+url);
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
 catalog:ids['contract-catalog-status'].textContent,readiness:ids['research-readiness-status'].textContent,
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
  if(step.action==='settle'){
   const request=active.filter(x=>x.url===step.url&&!x.done)[step.index||0];if(!request)throw Error('No active request to settle: '+step.url);
   finish(request,step.error);
  }
  if(step.action==='settle-catalog'){
   const request=active.find(x=>catalogs.has(x.url)&&!x.done);if(!request)throw Error('No active catalog to settle');finish(request,step.error);
  }
  if(step.action==='poll'){const t=[...timers].find(([,v])=>v.ms===5000);if(t){timers.delete(t[0]);t[1].fn();}}
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
    def assert_read_only(self, snapshot):
        self.assertTrue(all(row['method'] == 'GET' and row['body'] is None
                            for row in snapshot['calls']))

    def test_direct_history_does_not_queue_behind_hidden_contract_catalogs(self):
        for address in ('#ledger', '#ledger-page'):
            with self.subTest(address=address):
                view = startup(address)[0]
                self.assertIn('1 of 1 saved submissions', view['ledger'])
                self.assertIn('10000000-0000-4000-8000-000000000001', view['ledgerRows'])
                self.assertEqual([row['url'] for row in view['calls']], ['/api/experiments'])
                self.assertFalse(view['waiting'])
                self.assert_read_only(view)

    def test_direct_signals_has_real_researched_entries_without_hidden_reads(self):
        for address in ('#signals', '#signal-page'):
            with self.subTest(address=address):
                view = startup(address)[0]
                self.assertIn('1 researched Signal', view['signals'])
                self.assertIn('63-day log momentum', view['signalCards'])
                self.assertTrue({'/api/experiments', '/api/signal-library-summaries'} <=
                                {row['url'] for row in view['calls']})
                self.assertFalse(CONTRACT_READS & {row['url'] for row in view['calls']})
                self.assertFalse(view['waiting'])
                self.assert_read_only(view)

    def test_default_contract_first_verifies_queue_then_serializes_catalog_warmup(self):
        steps = [{'action': 'event', 'name': 'pageshow'},
                 {'action': 'settle', 'url': '/api/experiments'},
                 *[{'action': 'settle-catalog'} for _ in range(3)]]
        for address in ('', '#experiment', '#experiment-inputs', '#trial-example'):
            with self.subTest(address=address):
                views = startup(address, steps, hold_queue=True)
                for view in views[:2]:
                    self.assertEqual([row['url'] for row in view['calls']], ['/api/experiments'])
                    self.assertNotIn('No saved submissions', view['ledger'])
                for view in views[2:]:
                    self.assertIn('1 of 1 saved submissions', view['ledger'])
                    self.assertLessEqual(len(CATALOGS & set(view['active'])), 1)
                called = [row['url'] for row in views[-1]['calls']]
                self.assertEqual(called[0], '/api/experiments')
                for endpoint in CONTRACT_READS:
                    self.assertEqual(called.count(endpoint), 1)
                self.assert_read_only(views[-1])

    def test_first_contract_entry_within_thirty_seconds_is_not_throttled(self):
        views = startup('#ledger', [
            {'action': 'navigate', 'hash': '#experiment', 'ms': 1000},
            {'action': 'event', 'name': 'pageshow'},
            {'action': 'navigate', 'hash': '#experiment-inputs'},
            *[{'action': 'settle-catalog'} for _ in range(3)],
        ])
        self.assertFalse(CONTRACT_READS & {row['url'] for row in views[0]['calls']})
        for endpoint in CONTRACT_READS:
            self.assertEqual([row['url'] for row in views[-1]['calls']].count(endpoint), 1)
        self.assertIn('1 of 1 saved submissions', views[-1]['ledger'])

    def test_leaving_contract_does_not_schedule_remaining_hidden_catalogs(self):
        views = startup('#experiment', [
            {'action': 'navigate', 'hash': '#ledger'},
            {'action': 'settle-catalog'},
            {'action': 'event', 'name': 'pageshow'},
        ])
        self.assertEqual(sum(row['url'] in CATALOGS for row in views[-1]['calls']), 1)
        self.assertIn('1 of 1 saved submissions', views[-1]['ledger'])
        self.assertFalse(CATALOGS & set(views[-1]['active']))

    def test_explicit_refresh_restarts_one_complete_catalog_cycle(self):
        views = startup('#experiment', [
            *[{'action': 'settle-catalog'} for _ in range(3)],
            {'action': 'click', 'id': 'contract-refresh'},
            {'action': 'event', 'name': 'pageshow'},
            *[{'action': 'settle-catalog'} for _ in range(3)],
        ])
        called = [row['url'] for row in views[-1]['calls']]
        for endpoint in CATALOGS:
            self.assertEqual(called.count(endpoint), 2)
        self.assertIn('1 of 1 saved submissions', views[-1]['ledger'])
        self.assert_read_only(views[-1])

    def test_slow_catalog_cannot_starve_signal_reads_or_history_refresh(self):
        views = startup('#experiment', [
            {'action': 'navigate', 'hash': '#signals', 'ms': 5000},
            {'action': 'click', 'id': 'queue-refresh'},
            {'action': 'navigate', 'hash': '#ledger'},
        ])
        for view in views:
            self.assertEqual(len(CATALOGS & set(view['active'])), 1)
            self.assertFalse(view['waiting'])
            self.assertIn('1 of 1 saved submissions', view['ledger'])
        self.assertIn('1 researched Signal', views[1]['signals'])
        self.assertIn('63-day log momentum', views[1]['signalCards'])
        self.assertEqual([row['url'] for row in views[-1]['calls']].count('/api/experiments'), 2)
        self.assert_read_only(views[-1])

    def test_failed_initial_queue_read_unlocks_contract_once_without_claiming_empty_history(self):
        views = startup('#experiment', [
            {'action': 'settle', 'url': '/api/experiments', 'error': True},
            {'action': 'event', 'name': 'pageshow'},
            {'action': 'settle', 'url': '/api/experiments'},
            *[{'action': 'settle-catalog'} for _ in range(3)],
        ], hold_queue=True)
        self.assertIn('unavailable', views[1]['ledger'].lower())
        self.assertNotIn('No saved submissions', views[1]['ledger'])
        settled = [event for event in views[-1]['timeline']
                   if event.get('event') == 'research-queue-settled']
        self.assertEqual(len(settled), 1)
        self.assertEqual(settled[0]['detail'], {'verified': False})
        for endpoint in CONTRACT_READS:
            self.assertEqual([row['url'] for row in views[-1]['calls']].count(endpoint), 1)
        self.assertIn('1 of 1 saved submissions', views[-1]['ledger'])

    def test_pagehide_during_first_queue_read_defers_contract_until_pageshow(self):
        views = startup('#experiment', [
            {'action': 'event', 'name': 'pagehide'},
            {'action': 'settle', 'url': '/api/experiments'},
            {'action': 'event', 'name': 'pageshow'},
            {'action': 'event', 'name': 'pageshow'},
            {'action': 'settle', 'url': '/api/experiments'},
            *[{'action': 'settle-catalog'} for _ in range(3)],
        ], hold_queue=True)
        self.assertFalse(CONTRACT_READS & {row['url'] for row in views[2]['calls']})
        self.assertIn('1 of 1 saved submissions', views[2]['ledger'])
        self.assertEqual(sum(event.get('event') == 'research-queue-settled'
                             for event in views[-1]['timeline']), 1)
        for endpoint in CONTRACT_READS:
            self.assertEqual([row['url'] for row in views[-1]['calls']].count(endpoint), 1)

    def test_queue_deadline_leaves_server_work_but_retry_still_has_capacity(self):
        views = startup('#experiment', [
            {'action': 'advance', 'ms': 60000},
            {'action': 'click', 'id': 'queue-refresh'},
            {'action': 'settle', 'url': '/api/experiments', 'index': 1},
        ], hold_queue=True)
        self.assertTrue(views[1]['calls'][0]['aborted'])
        self.assertFalse(views[1]['calls'][0]['done'])
        self.assertIn('unavailable', views[1]['ledger'].lower())
        self.assertEqual(len(views[2]['active']), 4)
        self.assertFalse(views[2]['waiting'])
        self.assertIn('1 of 1 saved submissions', views[-1]['ledger'])
        self.assertEqual(sum(event.get('event') == 'research-queue-settled'
                             for event in views[-1]['timeline']), 1)
        self.assert_read_only(views[-1])

    def test_return_after_interrupted_warmup_reloads_current_catalog_without_throttle(self):
        views = startup('#experiment', [
            {'action': 'navigate', 'hash': '#ledger'},
            {'action': 'settle-catalog'},
            {'action': 'navigate', 'hash': '#experiment-inputs', 'ms': 1000},
            *[{'action': 'settle-catalog'} for _ in range(3)],
        ])
        called = [row['url'] for row in views[-1]['calls']]
        self.assertEqual(called.count('/api/scope-library'), 2)
        self.assertEqual(called.count('/api/feature-library'), 1)
        self.assertEqual(called.count('/api/target-library'), 1)
        self.assertFalse(CATALOGS & set(views[-1]['active']))

    def test_repeated_forced_refresh_during_warmup_coalesces_one_followup_cycle(self):
        views = startup('#experiment', [
            {'action': 'click', 'id': 'contract-refresh'},
            {'action': 'click', 'id': 'contract-refresh'},
            {'action': 'event', 'name': 'pageshow'},
            *[{'action': 'settle-catalog'} for _ in range(6)],
        ])
        for view in views:
            self.assertLessEqual(len(CATALOGS & set(view['active'])), 1)
        for endpoint in CATALOGS:
            self.assertEqual([row['url'] for row in views[-1]['calls']].count(endpoint), 2)
        self.assert_read_only(views[-1])


if __name__ == '__main__':
    unittest.main()
