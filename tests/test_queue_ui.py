"""Execute the actual queue script against a small DOM/fetch harness."""
from pathlib import Path
import json,shutil,subprocess,unittest
from test_research_ui import job,payload,REQUEST_ID,SECOND_ID,all_text
ROOT=Path(__file__).resolve().parents[1]

def catalog(status='queued'):
    return {'items':[{'job':job(status)['job'],'intent':{k:v for k,v in payload().items() if k!='request_id'},'queue_position':1 if status=='queued' else None}],
            'issues':[],'worker':{'healthy':True}}

def ui(responses,steps=(),saved=None,storage_error=False,client=None):
    harness=r'''
const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
let creations=0;
class Element {
 constructor(tag){this.serial=++creations;this.tag=tag;this.textContent='';this.children=[];this.dataset={};this.options=[];this.listeners={};this.value='';this.open=false;}
 append(...items){this.children.push(...items);} replaceChildren(...items){this.children=items;}
 setAttribute(name,value){this[name]=value;}
 addEventListener(name,fn){this.listeners[name]=fn;}
}
const ids=Object.fromEntries(['queue-board','queue-status','queue-refresh','queue-action-status','feature','scope','ledger-items','ledger-status','ledger-search','ledger-state','ledger-from','ledger-to','ledger-clear'].map(n=>[n,new Element(n)]));
ids.feature.options=[{value:JSON.stringify(input.payload.feature),textContent:'Log Skip Recent Momentum'}];
ids.scope.options=[{value:JSON.stringify(input.payload.scope),textContent:'AUDUSD'}];
const saved={...(input.saved||{})};
let seq=0,offset=0;const timers=new Map(),calls=[],events={},sent=[];
const context={document:{getElementById:id=>ids[id],createElement:tag=>new Element(tag)},AbortController,
 CustomEvent:class {constructor(type,options){this.type=type;this.detail=options.detail;}},
 window:{researchSubmissionState:input.client,location:{hash:'#experiment'},localStorage:{getItem:key=>saved[key]||null,setItem:(key,value)=>{if(input.storage_error)throw Error('storage unavailable');saved[key]=value;}},setTimeout:(fn,ms)=>{timers.set(++seq,{fn,ms});return seq;},clearTimeout:id=>timers.delete(id),addEventListener:(n,fn)=>events[n]=fn,dispatchEvent:e=>sent.push(e)},
 fetch:async(url,options)=>{calls.push({url,method:options.method,body:options.body});const value=input.responses[Math.min(offset++,input.responses.length-1)];if(value.error&&!value.http)throw Error('network');return {ok:!value.http,status:value.http||200,json:async()=>value};}};
const walk=n=>[n,...n.children.flatMap(walk)];const tree=n=>({text:n.textContent,tag:n.tag,children:n.children.map(tree)});const views=[];
const flush=()=>new Promise(r=>setImmediate(r));
function snap(){views.push({board:tree(ids['queue-board']),ledger:tree(ids['ledger-items']),ledgerStatus:ids['ledger-status'].textContent,notice:ids['queue-action-status'].textContent,saved:{...saved},status:ids['queue-status'].textContent,buttons:walk(ids['queue-board']).filter(n=>n.tag==='button').map(n=>n.serial),buttonLabels:[...walk(ids['queue-board']),...walk(ids['ledger-items'])].filter(n=>n.tag==='button').map(n=>n.textContent),registeredEvents:Object.keys(events),calls:[...calls],sent:[...sent],timers:[...timers.values()].map(t=>t.ms)});}
(async()=>{vm.runInNewContext(fs.readFileSync(input.script,'utf8'),context);await flush();snap();
for(const step of input.steps){
 if(step==='poll'){const t=[...timers].find(([,t])=>t.ms===5000);if(t){timers.delete(t[0]);t[1].fn();}}
 if(typeof step==='object'&&step.click){walk(ids['queue-board']).find(n=>n.tag==='button'&&n.textContent===step.click)?.listeners.click();}
 if(typeof step==='object'&&step.client){events['research-submission-state']?.({detail:step.client});}
 if(step==='dismiss'){walk(ids['queue-board']).find(n=>n.className==='queue-remove').listeners.click();}
 if(step==='restore'){walk(ids['ledger-items']).find(n=>n.className==='text-button ledger-restore').listeners.click();}
 
 if(typeof step==='object'&&step.filter){ids['ledger-'+step.filter].value=step.value;ids['ledger-'+step.filter].listeners.input();}
 if(step==='hide')events.pagehide();
 await flush();snap();
}process.stdout.write(JSON.stringify(views));})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    node=shutil.which('node')
    if not node:raise unittest.SkipTest('Node unavailable')
    result=subprocess.run([node,'-e',harness],input=json.dumps({'script':str(ROOT/'ui/queue.js'),'responses':responses,'steps':steps,'payload':payload(),'saved':saved,'storage_error':storage_error,'client':client}),text=True,capture_output=True,check=True)
    return json.loads(result.stdout)

class QueueUITests(unittest.TestCase):
    def test_preparation_checkpoint_is_separate_from_research_outcomes(self):
        c=catalog('preparing');j=c['items'][0]['job'];j['stage']='P1 preparation'
        j['preparation_progress']={'phase':'P1','members_completed':1,'members_total':7,'batches_completed':3,
            'instrument':'CADCHF','start':'2018-01-01','end':'2018-12-31','updated_at':'2026-10-11T01:00:00Z'}
        text=all_text(ui([c])[0]['board'])
        for expected in ['1/7 instruments processed','3 batches processed','CADCHF','2018-01-01','Last preparation checkpoint','not P1/P2 results']:
            self.assertIn(expected,text)
        j['status']='p1'
        self.assertNotIn('Current instrument:',all_text(ui([c])[0]['board']))

    def test_real_labels_waiting_position_and_read_only_open(self):
        v=ui([catalog()])[-1]
        text=all_text(v['board']);self.assertIn('Log Skip Recent Momentum',text);self.assertIn('AUDUSD',text);self.assertIn('Waiting position 1',text)
        self.assertNotIn('Open progress',text);self.assertNotIn('Cancel',v['buttonLabels'])
        self.assertTrue(all(c['method']=='GET' for c in v['calls']))
    def test_poll_transitions_and_terminal_outcomes(self):
        v=ui([catalog(),catalog('p1'),catalog('succeeded')],['poll','poll'])
        self.assertIn('In P1',all_text(v[1]['board']))
        self.assertNotIn(REQUEST_ID,all_text(v[-1]['board']))
        self.assertIn('Completed',all_text(v[-1]['ledger']))
        self.assertIn(REQUEST_ID,all_text(v[-1]['ledger']))
        self.assertEqual(len(v[-1]['calls']),3)
    def test_unchanged_poll_preserves_card_buttons(self):
        v=ui([catalog()],['poll'])
        self.assertEqual(v[0]['buttons'],v[1]['buttons'])
    def test_stale_failure_and_pagehide(self):
        v=ui([catalog(),{'error':True}],['poll','hide'])[-1]
        self.assertIn('last verified status',v['status']);self.assertIn(REQUEST_ID,all_text(v['board']))
        self.assertNotIn(5000,v['timers'])
    def test_worker_unavailable_and_corruption_visible(self):
        c=catalog('failed');c['worker']['healthy']=False;c['issues']=[{'request_id':SECOND_ID}]
        v=ui([c])[0];self.assertIn('Worker unavailable',v['status']);self.assertIn(SECOND_ID,v['status'])
        self.assertIn('Execution failed',all_text(v['board']))
    def test_server_text_not_html(self):
        c=catalog();c['items'][0]['job']['message']='<img src=x onerror=alert(1)>'
        self.assertIn(c['items'][0]['job']['message'],all_text(ui([c])[0]['board']))
        self.assertNotIn('innerHTML',(ROOT/'ui/queue.js').read_text())

    def test_dismissed_attention_stays_in_ledger_and_no_active_delete(self):
        c=catalog('blocked');c['items'][0]['job']['attempt_id']='attempt-fixture'
        v=ui([c],['dismiss'])[-1]
        self.assertNotIn(REQUEST_ID,all_text(v['board']))
        self.assertIn('Removed from queue',all_text(v['ledger']))
        restored=ui([c],saved=v['saved'])[0]
        self.assertNotIn(REQUEST_ID,all_text(restored['board']))
        self.assertTrue(all(c['method']=='GET' for c in v['calls']))
        self.assertNotIn('×',all_text(ui([catalog()])[0]['board']))
    def test_ledger_can_restore_removed_item_without_writes_to_server(self):
        c=catalog('blocked');c['items'][0]['job']['attempt_id']='attempt-fixture'
        v=ui([c],['dismiss','restore'])[-1]
        self.assertIn(REQUEST_ID,all_text(v['board']))
        self.assertNotIn('Removed from queue',all_text(v['ledger']))
        self.assertTrue(all(c['method']=='GET' for c in v['calls']))
    def test_new_attempt_and_active_job_reappear(self):
        c=catalog('blocked');c['items'][0]['job']['attempt_id']='old-attempt'
        v=ui([c],['dismiss'])[-1]
        for status,attempt in [('blocked','new-attempt'),('queued','old-attempt')]:
            newer=catalog(status);newer['items'][0]['job']['attempt_id']=attempt
            restored=ui([newer],saved=v['saved'])[0]
            self.assertIn(REQUEST_ID,all_text(restored['board']))
    def test_failed_storage_keeps_card_and_explains(self):
        c=catalog('blocked');c['items'][0]['job']['attempt_id']='attempt-fixture'
        v=ui([c],['dismiss'],storage_error=True)[-1]
        self.assertIn(REQUEST_ID,all_text(v['board']))
        self.assertIn('could not save',v['notice'])
    def test_unreadable_preference_does_not_hide_history(self):
        v=ui([catalog('blocked')],saved={'research-platform.queue-dismissals.v1':'{broken'})[0]
        self.assertIn(REQUEST_ID,all_text(v['board']))
        self.assertIn(REQUEST_ID,all_text(v['ledger']))
    def test_ledger_search_status_dates_and_open_are_read_only(self):
        c=catalog('succeeded');c['items'].append(catalog('cancelled')['items'][0]);c['items'][1]['job']['request_id']=SECOND_ID
        v=ui([c],[{'filter':'state','value':'succeeded'},{'filter':'search','value':'absent'},
            {'filter':'search','value':'momentum'},{'filter':'from','value':'2030-01-01'},
            {'filter':'from','value':''}])
        self.assertNotIn(SECOND_ID,all_text(v[1]['ledger']))
        self.assertIn('No saved submissions',all_text(v[2]['ledger']))
        self.assertIn(REQUEST_ID,all_text(v[3]['ledger']))
        self.assertIn('No saved submissions',all_text(v[4]['ledger']))
        self.assertNotIn('Open saved progress',all_text(v[-1]['ledger']))
        self.assertTrue(all(c['method']=='GET' for c in v[-1]['calls']))

    def test_card_shows_horizons_reasons_mode_and_frozen_selection(self):
        c=catalog('blocked');c['items'][0]['job'].update(mode='CS',resumable=False,
            horizons=[{'horizon':21,'p1_status':'rejected','p2_status':'not_admitted'}],
            blockers=[{'code':'COVERAGE','message':'Missing usable dates.'}],
            resume_blocker={'code':'IMPLEMENTATION_CHANGED','message':'Use a new submission.'})
        text=all_text(ui([c])[0]['board'])
        for value in ['Cross sectional','21 · P1: Rejected · P2: Not admitted','Missing usable dates.','Use a new submission.','AUDUSD','Positive']:
            self.assertIn(value,text)
        self.assertNotIn('Resume',text)
    def test_browser_pending_notices_cannot_reintroduce_submission_recovery(self):
        c=catalog();c['items']=[]
        for state in ({'uncertain':True}, {'rejection':{'code':'INVALID_ORIGIN'}}, {'busy':True}):
            client=dict(payload=payload(),message='Old pending browser request',**state)
            v=ui([c],[{'client':client},{'click':'Check receipt'},{'click':'Check and retry'},'poll'],client=client)[-1]
            self.assertNotIn(REQUEST_ID,all_text(v['board']))
            self.assertEqual(v['buttonLabels'],[])
            self.assertNotIn('research-submission-state',v['registeredEvents'])
            self.assertFalse(any(e['type'].startswith('research-submission-') for e in v['sent']))
            self.assertTrue(all(call['method']=='GET' for call in v['calls']))

    def test_every_previously_actionable_state_is_get_only(self):
        for state in ('queued','resolving','preparing','p1','p2','blocked','failed','cancelled','succeeded'):
            with self.subTest(state=state):
                c=catalog(state);c['items'][0]['job']['resumable']=True
                v=ui([c],[{'click':'Cancel'},{'click':'Resume'},{'click':'Check and retry'},'poll'])[-1]
                self.assertEqual(len(v['calls']),2)
                self.assertTrue(all(call['method']=='GET' and call['url']=='/api/experiments' for call in v['calls']))
                self.assertFalse({'Cancel','Resume','Check and retry','Check receipt'}&set(v['buttonLabels']))
                self.assertIn(REQUEST_ID,all_text(v['board'])+all_text(v['ledger']))

    def test_saved_jobs_ignore_unconfirmed_browser_request_state(self):
        client={'payload':payload(),'uncertain':True,'busy':False,'message':'unconfirmed'}
        v=ui([catalog()],[{'client':client}],client=client)[-1]
        self.assertEqual(all_text(v['board']).count(REQUEST_ID),1)
        self.assertNotIn('unconfirmed',all_text(v['board']))
        self.assertTrue(all(call['method']=='GET' for call in v['calls']))

    def test_results_notify_signal_library_once_per_reference_set(self):
        c=catalog('succeeded');c['items'][0]['job']['results']=[{'id':'RESEARCHLINK_fixture','version':'1.0.0','content_sha256':'a'*64}]
        v=ui([c],['poll'])[-1]
        self.assertEqual(sum(e['type']=='research-results-updated' for e in v['sent']),1)
