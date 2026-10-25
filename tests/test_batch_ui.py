"""Batch monitor is dormant; its retained asset remains read-only in isolation."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BID = '10000000-0000-4000-8000-000000000001'


def batch(status='preparing', approved=True):
    return {'batch_id': BID, 'name': 'Momentum pilot', 'state': {'state': 'dispatching' if approved else 'ready'},
        'created_at': '2026-10-18T01:00:00Z', 'unique_experiments': 3, 'previewed': 3, 'approved': approved,
        'preview_complete': True, 'preview_sha256': 'a'*64, 'preview_counts': {'new': 3}, 'job_counts': {'succeeded': 1, status: 1}, 'items': [
            {'intent': {'feature': {'id': 'recipe', 'version': '1.0.0'}, 'scope': {'id': 'scope', 'version': '1.0.0'},
                        'expected_direction': 'POSITIVE'}, 'disposition': 'new',
             'job': {'request_id': BID, 'status': status, 'stage': 'P1 preparation', 'message': 'Preparing saved inputs',
                     'updated_at': '2026-10-18T01:00:00Z', 'horizons': [],
                     'preparation_progress': {'members_completed': 1, 'members_total': 2, 'batches_completed': 7,
                                              'instrument': 'AUDCAD', 'updated_at': '2026-10-18T01:00:00Z'}}}]}


def browser(responses, steps=()):
    script = r'''
const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
class Element {
 constructor(tag){this.tag=tag;this.textContent='';this.value='';this.children=[];this.options=[];this.listeners={};}
 append(...nodes){this.children.push(...nodes);if(this.tag==='select'){this.options=this.children;if(!this.value)this.value=nodes[0]?.value||'';}}
 replaceChildren(...nodes){this.children=[];this.append(...nodes);}
 before(n){this.feedback=n;}
 addEventListener(n,fn){this.listeners[n]=fn;}
}
const ids={};for(const id of ['batch-select','batch-status','batch-detail','batch-refresh'])ids[id]=new Element(id==='batch-select'?'select':'div');
const timers=new Map(),events={},calls=[],views=[];let seq=0,offset=0;
const context={Date,AbortController,document:{getElementById:id=>ids[id],createElement:t=>new Element(t)},
 window:{setTimeout:(fn,ms)=>{timers.set(++seq,{fn,ms});return seq;},clearTimeout:id=>timers.delete(id),addEventListener:(n,fn)=>events[n]=fn},
 fetch:async(url,options)=>{calls.push({url,method:options.method,body:options.body});const value=input.responses[Math.min(offset++,input.responses.length-1)];
  if(value.error)throw Error('offline');return {ok:!value.http,status:value.http||200,json:async()=>value};}};
const text=n=>[n.textContent,...n.children.map(text)].join(' ');
const find=(n,id)=>n.id===id?n:n.children.map(c=>find(c,id)).find(Boolean);
const walk=n=>[n,...n.children.flatMap(walk)];
const flush=()=>new Promise(r=>setImmediate(r));
function snap(){views.push({detail:text(ids['batch-detail']),buttons:walk(ids['batch-detail']).filter(n=>n.tag==='button').map(n=>n.textContent),status:ids['batch-status'].textContent,calls:[...calls],timers:[...timers.values()].map(t=>t.ms)});}
(async()=>{vm.runInNewContext(fs.readFileSync(input.script,'utf8'),context);await flush();snap();
 for(const step of input.steps){
  if(step==='poll'){const t=[...timers].find(([,v])=>v.ms===15000);if(t){timers.delete(t[0]);t[1].fn();}}
  if(step.startsWith('click:')){const b=find(ids['batch-detail'],step.slice(6));if(b&&!b.disabled)b.listeners.click();}
  if(step.startsWith('click-label:')){const b=walk(ids['batch-detail']).find(n=>n.tag==='button'&&n.textContent===step.slice(12));if(b&&!b.disabled)b.listeners.click();}
  if(step==='hide')events.pagehide();if(step==='show')events.pageshow();
  await flush();snap();
 }process.stdout.write(JSON.stringify(views));})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    node = shutil.which('node')
    if not node: raise unittest.SkipTest('Node required')
    p = subprocess.run([node, '-e', script], input=json.dumps({'script': str(ROOT/'ui/batches.js'), 'responses': responses, 'steps': steps}), text=True, capture_output=True, check=True)
    return json.loads(p.stdout)


class BatchUITests(unittest.TestCase):
    def test_batch_monitor_is_absent_from_shipped_workspace(self):
        html = (ROOT / 'ui/index.html').read_text()
        self.assertNotIn('/batches.js', html)
        self.assertNotIn('Research batches', html)
        for name in ('batch-title', 'batch-select', 'batch-status', 'batch-detail', 'batch-refresh'):
            self.assertNotIn(f'id="{name}"', html)

    def listing(self): return {'batches': [{'batch_id': BID, 'name': 'Momentum pilot'}]}

    def test_saved_counts_preparation_timestamp_and_no_launch(self):
        value = browser([self.listing(), batch()])[0]
        for phrase in ['1 of 3 experiments completed', '1 running', 'AUDCAD', '7 preparation windows', 'Last saved update', 'Positive', 'does not mean statistical validation']:
            self.assertIn(phrase, value['detail'])
        self.assertTrue(all(c['method'] == 'GET' for c in value['calls']))

    def test_network_failure_keeps_saved_progress_and_marks_unconfirmed(self):
        value = browser([self.listing(), batch(), {'error': True}], ['poll'])[-1]
        self.assertIn('1 of 3 experiments completed', value['detail'])
        self.assertIn('current progress is unconfirmed', value['status'])

    def test_browser_reopen_loads_durable_counts_without_submitting(self):
        done = batch('succeeded'); done['job_counts'] = {'succeeded': 3}; done['state']['state'] = 'completed'
        values = browser([self.listing(), batch(), self.listing(), done], ['hide', 'show'])
        self.assertNotIn(15000, values[1]['timers'])
        self.assertIn('3 of 3 experiments completed', values[-1]['detail'])
        self.assertTrue(all(c['method'] == 'GET' for c in values[-1]['calls']))

    def test_unapproved_empty_and_untrusted_text(self):
        preview = batch(approved=False); preview['items'] = []; preview['job_counts'] = {}; preview['name'] = '<img onerror=alert(1)>'
        value = browser([self.listing(), preview])[0]
        self.assertIn('Launch not approved', value['detail']); self.assertIn(preview['name'], value['detail'])
        self.assertNotIn('innerHTML', (ROOT/'ui/batches.js').read_text())
        empty = browser([{'batches': []}])[0]
        self.assertIn('No batch has been created', empty['status'])

    def test_old_checkpoint_does_not_assert_worker_stopped(self):
        value = browser([self.listing(), batch()])[0]
        self.assertIn('does not confirm a stall', value['detail'])

    def test_reconciled_history_cannot_be_launched_or_resumed(self):
        b=batch(approved=False);b['read_only']=True
        b['state']['state']='paused'
        views=browser([self.listing(),b],['click:batch-review','click:batch-launch','click:batch-resume'])
        self.assertIn('Retained historical batch',views[-1]['detail'])
        self.assertIn('cannot be relaunched',views[-1]['detail'])
        self.assertTrue(all(c['method']=='GET' for c in views[-1]['calls']))

    def test_all_batch_states_are_get_only_without_execution_controls(self):
        for state,approved in [('previewing',False),('ready',False),('approved',True),
                               ('dispatching',True),('paused',False),('paused',True),
                               ('needs_attention',True),('completed',True)]:
            with self.subTest(state=state,approved=approved):
                b=batch(approved=approved);b['state']['state']=state
                values=browser([self.listing(),b,self.listing(),b],
                    ['click:batch-review','click:batch-launch','click:batch-pause','click:batch-resume','poll'])
                self.assertEqual(values[-1]['buttons'],[])
                self.assertEqual(len(values[-1]['calls']),4)
                self.assertTrue(all(c['method']=='GET' for c in values[-1]['calls']))
                self.assertIn('Read-only batch monitor',values[-1]['detail'])

    def test_changed_or_blocked_preview_remains_visible_without_launch(self):
        changed=batch(approved=False);changed['preview_sha256']='b'*64
        changed['preview_counts']={'new':2,'blocked':1};changed['preview_complete']=False
        values=browser([self.listing(),batch(approved=False),self.listing(),changed],
            ['click:batch-review','poll','click:batch-launch'])
        self.assertIn('1 blocked',values[-1]['detail'])
        self.assertEqual(values[-1]['buttons'],[])
        self.assertTrue(all(c['method']=='GET' for c in values[-1]['calls']))

    def test_pagination_changes_visible_details_without_server_writes(self):
        b=batch();b['items']=[json.loads(json.dumps(b['items'][0])) for _ in range(26)]
        for index,item in enumerate(b['items']):item['intent']['feature']['id']='recipe-'+str(index)
        values=browser([self.listing(),b],['click-label:Next','click-label:Previous'])
        self.assertNotIn('recipe-25',values[0]['detail'])
        self.assertIn('recipe-25',values[1]['detail'])
        self.assertIn('Page 1 of 2',values[-1]['detail'])
        self.assertEqual(len(values[-1]['calls']),2)
        self.assertTrue(all(c['method']=='GET' for c in values[-1]['calls']))
