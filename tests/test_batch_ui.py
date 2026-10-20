"""Read-only batch monitoring: restart-safe counts and honest stale status."""
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
const flush=()=>new Promise(r=>setImmediate(r));
function snap(){views.push({detail:text(ids['batch-detail']),status:ids['batch-status'].textContent,calls:[...calls],timers:[...timers.values()].map(t=>t.ms)});}
(async()=>{vm.runInNewContext(fs.readFileSync(input.script,'utf8'),context);await flush();snap();
 for(const step of input.steps){
  if(step==='poll'){const t=[...timers].find(([,v])=>v.ms===15000);if(t){timers.delete(t[0]);t[1].fn();}}
  if(step.startsWith('click:')){const b=find(ids['batch-detail'],step.slice(6));if(b&&!b.disabled)b.listeners.click();}
  if(step==='hide')events.pagehide();if(step==='show')events.pageshow();
  await flush();snap();
 }process.stdout.write(JSON.stringify(views));})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    node = shutil.which('node')
    if not node: raise unittest.SkipTest('Node required')
    p = subprocess.run([node, '-e', script], input=json.dumps({'script': str(ROOT/'ui/batches.js'), 'responses': responses, 'steps': steps}), text=True, capture_output=True, check=True)
    return json.loads(p.stdout)


class BatchUITests(unittest.TestCase):
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

    def test_review_then_launch_exact_preview_once(self):
        values = browser([self.listing(), batch(approved=False), {}, self.listing(), batch()],
                         ['click:batch-launch', 'click:batch-review', 'click:batch-launch', 'click:batch-launch'])
        self.assertTrue(all(c['method'] == 'GET' for c in values[1]['calls']))
        posts = [c for c in values[-1]['calls'] if c['method'] == 'POST']
        self.assertEqual(len(posts), 1)
        self.assertEqual(json.loads(posts[0]['body']), {'preview_sha256': 'a'*64, 'exclude_blocked': False})

    def test_changed_preview_requires_new_review(self):
        changed = batch(approved=False); changed['preview_sha256'] = 'b'*64
        values = browser([self.listing(), batch(approved=False), self.listing(), changed],
                         ['click:batch-review', 'poll', 'click:batch-launch'])
        self.assertTrue(all(c['method'] == 'GET' for c in values[-1]['calls']))

    def test_incomplete_or_blocked_cannot_launch(self):
        for key, value in [('preview_complete', False), ('preview_counts', {'new': 2, 'blocked': 1})]:
            b = batch(approved=False); b[key] = value
            views = browser([self.listing(), b], ['click:batch-review', 'click:batch-launch'])
            self.assertTrue(all(c['method'] == 'GET' for c in views[-1]['calls']))

    def test_lost_response_refreshes_without_repeating_launch(self):
        views = browser([self.listing(), batch(approved=False), {'error': True}, self.listing(), batch()],
                        ['click:batch-review', 'click:batch-launch', 'click:batch-launch'])
        self.assertEqual(sum(c['method'] == 'POST' for c in views[-1]['calls']), 1)

    def test_pause_and_resume_use_existing_batch(self):
        paused = batch(); paused['state']['state'] = 'paused'
        views = browser([self.listing(), batch(), {}, self.listing(), paused, {}, self.listing(), batch()],
                        ['click:batch-pause', 'click:batch-resume'])
        posts = [c for c in views[-1]['calls'] if c['method'] == 'POST']
        self.assertEqual([c['url'] for c in posts], ['/api/batches/'+BID+'/pause', '/api/batches/'+BID+'/resume'])
