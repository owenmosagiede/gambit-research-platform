"""Exercise the shipped Submit UI with fake HTTP and DOM; never run research."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import unittest

PROJECT = Path(__file__).resolve().parents[1]
REQUEST_ID = '10000000-0000-4000-8000-000000000001'
SECOND_ID = '10000000-0000-4000-8000-000000000002'
FEATURE = {'id': 'FEATURE_RECIPE_fixture', 'version': '1.0.0'}
SCOPE = {'id': 'SCOPE_fixture', 'version': '1.0.0'}


def readiness(enabled=True):
    return {'implementation_installed': True, 'execution_enabled': enabled,
            'blockers': [] if enabled else [{'code': 'EXPOSURE_POLICY_REQUIRED', 'message': 'A validation exposure policy is required.'}],
            'method_summary': 'P1 discovery, then P2 validation for admitted relationships.'}


def job(status='queued', request_id=REQUEST_ID, **changes):
    value = {'request_id': request_id, 'status': status, 'stage': status,
             'message': 'Waiting to resolve inputs.' if status == 'queued' else 'Fixture progress.',
             'blockers': [], 'progress': {'completed': 0, 'total': 0}, 'horizons': [],
             'results': [], 'mode': None, 'created_at': '2026-10-09T00:00:00Z', 'updated_at': '2026-10-09T00:00:00Z'}
    value.update(changes)
    return {'job': value}


def result_ref(index=1):
    return {'id': 'RESEARCHLINK_' + str(index), 'version': '1.0.0', 'content_sha256': f'{index:064x}'}


def payload():
    return {'request_id': REQUEST_ID, 'feature': FEATURE, 'scope': SCOPE,
            'target_family': 'price_return', 'expected_direction': 'POSITIVE'}


def ui(steps=(), *, routes=None, held=(), saved=None, invalid=False, combined=False):
    node = shutil.which('node')
    if not node: raise unittest.SkipTest('Node.js is needed for UI checks')
    harness = r'''const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
class Element {
 constructor(id){this.id=id;this.children=[];this.dataset={};this.listeners={};this.textContent='';this.value='';this.disabled=false;this.selectedOptions=[];this.options=[];this.attributes={};}
 setAttribute(k,v){this.attributes[k]=v;}
 append(...c){this.children.push(...c);} replaceChildren(...c){this.children=c;}
 addEventListener(n,f){(this.listeners[n] ||= []).push(f);} fire(n){for(const f of this.listeners[n]||[])f({preventDefault(){}});}
 reportValidity(){return !input.invalid;}
}
const names=['feature','scope','target','expected-direction','experiment-submit','submission-notice','submit-availability','submission-check','research-specification','research-readiness-retry','research-readiness-status','research-method-summary','research-readiness-blockers','research-operational-incidents'];
if(input.combined)names.push('queue-board','queue-status','queue-refresh','queue-action-status','ledger-items','ledger-status','ledger-search','ledger-state','ledger-from','ledger-to','ledger-clear');
const ids=Object.fromEntries(names.map(n=>[n,new Element(n)])),form=new Element('form');
function select(id,value,label){ids[id].value=typeof value==='string'?value:JSON.stringify(value);ids[id].selectedOptions=[{textContent:label||id}];}
select('feature',input.feature,'Momentum');ids.feature.dataset.featureReference=JSON.stringify(input.feature);
select('scope',input.scope,'AUDUSD');ids.scope.dataset.scopeReference=JSON.stringify(input.scope);
function nativeResolution(){const feature=JSON.parse(ids.feature.value),scope=JSON.parse(ids.scope.value);if(feature.id.startsWith('FEATURE_RECIPE_'))ids.feature.dataset.featureResolution=JSON.stringify({recipe:{reference:feature},scope,submission_compatible:true});}
nativeResolution();
select('target','price','Price Return');ids.target.dataset.returnBasis='price';select('expected-direction','POSITIVE','Positive');
let uid=0,seq=0;const timers=new Map(),calls=[],events={},pending=[],sent=[],saved={},counts={};
if(input.saved)saved['research-platform.experiment-request.v1']=JSON.stringify(input.saved);
const context={document:{getElementById:id=>ids[id],querySelector:()=>form,createElement:n=>new Element(n)},AbortController,
CustomEvent:class{constructor(type,opts){this.type=type;this.detail=opts?.detail;}},
window:{localStorage:{getItem:()=>null,setItem:()=>{}},location:{hash:'#experiment'},crypto:{randomUUID:()=>`10000000-0000-4000-8000-${String(++uid).padStart(12,'0')}`},
sessionStorage:{getItem:k=>saved[k]||null,setItem:(k,v)=>saved[k]=v,removeItem:k=>delete saved[k]},
setTimeout:(fn,ms)=>{timers.set(++seq,{fn,ms});return seq;},clearTimeout:k=>timers.delete(k),
addEventListener:(n,f)=>events[n]=f,dispatchEvent:e=>{sent.push(e);events[e.type]?.(e);}},
fetch:async(url,opts)=>{const index=calls.length;calls.push({url,method:opts.method,body:opts.body?JSON.parse(opts.body):null});
const key=opts.method+' '+url,n=counts[key]||0;counts[key]=n+1;const list=input.routes[key];
const value=list?list[Math.min(n,list.length-1)]:url==='/api/research-readiness'?input.readiness:url==='/api/experiments'&&opts.method==='GET'?{items:[],issues:[],worker:{healthy:true}}:input.job;
if(input.held.includes(index))return new Promise((resolve,reject)=>pending.push({index,value,resolve,reject}));return response(value);}};
function response(v){if(v.error&&!v.http)throw Error('Network interrupted');return {ok:!v.http,status:v.http||200,json:async()=>v};}
const flush=()=>new Promise(r=>setImmediate(r)),views=[];
function tree(n){return {text:n.textContent,children:n.children.map(tree)};}
function snap(){const state=context.window.researchSubmissionState;views.push(JSON.parse(JSON.stringify({calls,dispatched:sent,state,saved,
 board:input.combined?tree(ids['queue-board']):null,ledger:input.combined?tree(ids['ledger-items']):null,submitDisabled:ids['experiment-submit'].disabled,availability:ids['submit-availability'].textContent,checkHidden:ids['submission-check'].hidden,notice:ids['submission-notice'].textContent,
 status:state?.uncertain?'Receipt unconfirmed':state?.job?.status || (ids['submission-notice'].textContent.startsWith('Not submitted')?'Not submitted':''),
 message:state?.message||ids['submission-notice'].textContent,blockers:{text:ids['submission-notice'].textContent,children:[]},
 retryHidden:!state?.uncertain,readiness:ids['research-readiness-status'].textContent})));}
(async()=>{vm.runInNewContext(fs.readFileSync(input.script,'utf8'),context);if(input.combined)vm.runInNewContext(fs.readFileSync(input.queueScript,'utf8'),context);await flush();snap();
for(const step of input.steps){
 if(step.action==='submit')form.fire('submit');
 if(step.action==='double'){form.fire('submit');form.fire('submit');}
 if(step.action==='change'){select(step.id,step.value,step.label);if(step.binding){ids[step.id].dataset[step.binding]=JSON.stringify(step.value);nativeResolution();}ids[step.id].fire('change');}
 if(step.action==='unbind'){delete ids[step.id].dataset[step.binding];events['scope-state-change']?.({});}
 if(step.action==='validity'){ids[step.id].validity={valid:!step.message};ids[step.id].validationMessage=step.message;events[step.event||'feature-state-change']?.({});}
 if(step.action==='disabled'){ids[step.id].disabled=step.value;events[step.event||'target-state-change']?.({});}
 if(step.action==='resolution'){ids.feature.dataset.featureResolution=JSON.stringify(step.value);events['feature-state-change']?.({});}
 if(step.action==='recover')events['research-submission-recover']({detail:{request_id:step.id||context.window.researchSubmissionState.payload.request_id,resend:step.resend===true}});
 if(step.action==='queue')events['research-queue-state']({detail:step.value});
 if(step.action==='settle'){const p=pending.find(p=>p.index===step.index);if(step.error)p.reject(Error('Network interrupted'));else p.resolve(response(step.value||p.value));}
 if(step.action==='poll'){const t=[...timers].find(([,v])=>v.ms===5000);if(t){timers.delete(t[0]);t[1].fn();}}
 if(step.action==='health'){const t=[...timers].find(([,v])=>v.ms===15000);if(t){timers.delete(t[0]);t[1].fn();}}
 if(step.action==='check')ids['submission-check'].fire('click');
 if(step.action==='dismiss')events['research-submission-dismiss']({detail:{request_id:step.id||context.window.researchSubmissionState.payload.request_id}});
 if(step.action==='pagehide')events.pagehide();
 await flush();snap();}process.stdout.write(JSON.stringify(views));})().catch(e=>{console.error(e);process.exitCode=1;});'''
    data={'script':str(PROJECT/'ui/submission.js'),'feature':FEATURE,'scope':SCOPE,'readiness':readiness(),
          'job':job(),'steps':list(steps),'routes':routes or {},'held':list(held),'saved':saved,'invalid':invalid,'combined':combined,'queueScript':str(PROJECT/'ui/queue.js')}
    result=subprocess.run([node,'-e',harness],input=json.dumps(data),text=True,capture_output=True,check=True)
    return json.loads(result.stdout)


def all_text(tree):
    return tree['text']+' '+' '.join(all_text(c) for c in tree['children'])


class ResearchSubmissionUITests(unittest.TestCase):
    def test_selection_and_page_load_do_not_submit(self):
        state=ui([{'action':'change','id':'expected-direction','value':'NEGATIVE'}])[-1]
        self.assertTrue(all(c['method']=='GET' for c in state['calls']))
    def test_submit_exact_frozen_payload_and_no_extra_horizon_input(self):
        state=ui([{'action':'submit'}])[-1]
        self.assertEqual(state['calls'][1]['body'],payload())
        self.assertEqual(state['state']['job']['status'],'queued')
    def test_double_click_and_active_identical_selection_no_duplicate(self):
        state=ui([{'action':'double'},{'action':'settle','index':1},{'action':'submit'}],held=[1])[-1]
        self.assertEqual(sum(c['method']=='POST' for c in state['calls']),1)
    def test_changed_selection_can_queue_while_another_is_active(self):
        state=ui([{'action':'submit'},{'action':'change','id':'scope','value':{'id':'EURUSD','version':'1.0.0'},'binding':'scopeReference'},{'action':'submit'}],
            routes={'POST /api/experiments':[job(),job(request_id=SECOND_ID)]})[-1]
        self.assertEqual([c['body']['request_id'] for c in state['calls'] if c['method']=='POST'],[REQUEST_ID,SECOND_ID])
    def test_terminal_same_selection_creates_new_request(self):
        state=ui([{'action':'submit'},{'action':'submit'}],routes={'POST /api/experiments':[job('blocked'),job(request_id=SECOND_ID)]})[-1]
        self.assertEqual(sum(c['method']=='POST' for c in state['calls']),2)
    def test_invalid_or_unresolved_inputs_never_submit(self):
        for steps,kwargs in [([] ,{'invalid':True}),([{'action':'unbind','id':'scope','binding':'scopeReference'}],{})]:
            state=ui(steps+[{'action':'submit'}],**kwargs)[-1]
            self.assertFalse(any(c['method']=='POST' for c in state['calls']))
    def test_pending_policy_blocks_submit(self):
        state=ui([{'action':'submit'}],routes={'GET /api/research-readiness':[readiness(False)]})[-1]
        self.assertTrue(state['submitDisabled']);self.assertEqual(len(state['calls']),1)
    def test_uncertain_post_preserves_request_and_blocks_new_submission(self):
        state=ui([{'action':'submit'},{'action':'change','id':'scope','value':{'id':'EURUSD','version':'1.0.0'},'binding':'scopeReference'},{'action':'submit'}],routes={'POST /api/experiments':[{'error':True}]})[-1]
        self.assertTrue(state['state']['uncertain']);self.assertTrue(state['submitDisabled'])
        self.assertEqual(state['state']['payload'],payload())
        self.assertEqual(sum(c['method']=='POST' for c in state['calls']),1)
    def test_retry_finds_accepted_request_without_reposting(self):
        state=ui([{'action':'submit'},{'action':'recover','resend':True}],routes={'POST /api/experiments':[{'error':True}],'GET /api/experiments/'+REQUEST_ID:[job('p1')]})[-1]
        self.assertEqual(state['status'],'p1');self.assertEqual(sum(c['method']=='POST' for c in state['calls']),1)
    def test_retry_missing_request_resends_same_id_and_original_inputs(self):
        state=ui([{'action':'submit'},{'action':'change','id':'expected-direction','value':'NEGATIVE'},{'action':'recover','resend':True}],
            routes={'POST /api/experiments':[{'error':True},job()], 'GET /api/experiments/'+REQUEST_ID:[{'http':404}]})[-1]
        self.assertEqual([c['body'] for c in state['calls'] if c['method']=='POST'],[payload(),payload()])
        self.assertEqual(state['status'],'queued')
    def test_unavailable_status_never_resends(self):
        state=ui([{'action':'submit'},{'action':'recover','resend':True}],routes={'POST /api/experiments':[{'error':True}],'GET /api/experiments/'+REQUEST_ID:[{'http':503}]})[-1]
        self.assertEqual(sum(c['method']=='POST' for c in state['calls']),1)
        self.assertIn('HTTP 503',state['message']);self.assertIn('Nothing was resent',state['message'])
    def test_explicit_server_error_is_displayed(self):
        state=ui([{'action':'submit'}],routes={'POST /api/experiments':[{'http':400,'error':{'code':'INVALID_SUBMISSION','message':'Exact registered selections required.'}}]})[-1]
        self.assertIn('INVALID_SUBMISSION',state['message'])
    def test_reload_recovers_by_get_only_and_keeps_frozen_inputs(self):
        state=ui(saved={'payload':payload()},routes={'GET /api/experiments/'+REQUEST_ID:[job('queued')]})[-1]
        self.assertEqual(state['state']['payload'],payload());self.assertFalse(state['state']['uncertain'])
        self.assertTrue(all(c['method']=='GET' for c in state['calls']))
    def test_missing_saved_request_remains_visible_without_auto_research(self):
        state=ui(saved={'payload':payload()},routes={'GET /api/experiments/'+REQUEST_ID:[{'http':404}]})[-1]
        self.assertTrue(state['state']['uncertain']);self.assertIn('not found',state['message'])
        self.assertTrue(all(c['method']=='GET' for c in state['calls']))
    def test_queue_can_confirm_late_submission_without_retry(self):
        state=ui([{'action':'submit'},{'action':'queue','value':{'items':[job('p1')]}}],routes={'POST /api/experiments':[{'error':True}]})[-1]
        self.assertFalse(state['state']['uncertain']);self.assertFalse(state['submitDisabled'])
    def test_wrong_response_cannot_confirm_submission(self):
        state=ui([{'action':'submit'}],routes={'POST /api/experiments':[job(request_id=SECOND_ID)]})[-1]
        self.assertTrue(state['state']['uncertain'])
    def test_combined_ui_submit_to_card_and_completion_to_ledger(self):
        done=job('succeeded')['job'];done['results']=[result_ref()]
        listing={'items':[{'job':done,'intent':{k:v for k,v in payload().items() if k!='request_id'}}],'issues':[],'worker':{'healthy':True}}
        states=ui([{'action':'submit'},{'action':'poll'}],combined=True,routes={'GET /api/experiments':[{'items':[],'issues':[],'worker':{'healthy':True}},listing]})
        self.assertIn('Queued',all_text(states[1]['board']))
        self.assertNotIn(REQUEST_ID,all_text(states[-1]['board']))
        self.assertIn(REQUEST_ID,all_text(states[-1]['ledger']))
        self.assertFalse(states[-1]['state']['uncertain'])
        self.assertEqual(sum(c['method']=='POST' for c in states[-1]['calls']),1)
    def test_combined_ui_unconfirmed_card_then_safe_retry(self):
        states=ui([{'action':'submit'},{'action':'recover','resend':True}],combined=True,
            routes={'POST /api/experiments':[{'error':True},job()], 'GET /api/experiments/'+REQUEST_ID:[{'http':404}]})
        self.assertIn('Receipt unconfirmed',all_text(states[1]['board']))
        self.assertIn('Check and retry',all_text(states[1]['board']))
        self.assertIn('Queued',all_text(states[-1]['board']))
        self.assertNotIn('Receipt unconfirmed',all_text(states[-1]['board']))
        self.assertEqual([c['body'] for c in states[-1]['calls'] if c['method']=='POST'],[payload(),payload()])
    def test_saved_missing_receipt_unlocks_submit_without_posting(self):
        state=ui(saved={'payload':payload()},routes={'GET /api/experiments/'+REQUEST_ID:[{'http':404}]})[-1]
        self.assertFalse(state['submitDisabled'])
        self.assertIn('not found',state['availability'])
        self.assertTrue(state['state']['notRecorded'])
        self.assertTrue(all(c['method']=='GET' for c in state['calls']))
    def test_missing_receipt_submit_same_inputs_reuses_original_id(self):
        original=payload();original['request_id']=SECOND_ID
        state=ui([{'action':'submit'}],saved={'payload':original},routes={
            'GET /api/experiments/'+SECOND_ID:[{'http':404}], 'POST /api/experiments':[job(request_id=SECOND_ID)]})[-1]
        self.assertEqual([c['body'] for c in state['calls'] if c['method']=='POST'],[original])
    def test_missing_receipt_submit_changed_inputs_creates_new_request(self):
        original=payload();original['request_id']=SECOND_ID
        state=ui([{'action':'change','id':'expected-direction','value':'NEGATIVE'},{'action':'submit'}],
            saved={'payload':original},routes={'GET /api/experiments/'+SECOND_ID:[{'http':404}]})[-1]
        posts=[c['body'] for c in state['calls'] if c['method']=='POST']
        self.assertEqual(len(posts),1);self.assertEqual(posts[0]['request_id'],REQUEST_ID)
        self.assertEqual(posts[0]['expected_direction'],'NEGATIVE')
    def test_unknown_receipt_lock_is_explained_and_direct_check_is_read_only(self):
        state=ui([{'action':'check'}],saved={'payload':payload()},routes={
            'GET /api/experiments/'+REQUEST_ID:[{'http':503}]})[-1]
        self.assertTrue(state['submitDisabled']);self.assertFalse(state['checkHidden'])
        self.assertIn('unconfirmed receipt',state['availability'])
        self.assertTrue(all(c['method']=='GET' for c in state['calls']))
    def test_background_receipt_check_recovers_without_user_retry_or_post(self):
        state=ui([{'action':'submit'},{'action':'health'}],routes={
            'POST /api/experiments':[{'error':True}], 'GET /api/experiments/'+REQUEST_ID:[{'http':404}]})[-1]
        self.assertFalse(state['submitDisabled'])
        self.assertEqual(sum(c['method']=='POST' for c in state['calls']),1)
    def test_recheck_failure_reinstates_safety_after_previous_not_found(self):
        state=ui([{'action':'check'}],saved={'payload':payload()},routes={
            'GET /api/experiments/'+REQUEST_ID:[{'http':404},{'http':503}]})[-1]
        self.assertTrue(state['submitDisabled']);self.assertFalse(state['state']['notRecorded'])
    def test_found_saved_job_clears_missing_receipt_flag(self):
        state=ui([{'action':'queue','value':{'items':[job('p1')]}}],saved={'payload':payload()},
            routes={'GET /api/experiments/'+REQUEST_ID:[{'http':404}]})[-1]
        self.assertFalse(state['submitDisabled']);self.assertFalse(state['state']['notRecorded'])
        self.assertEqual(state['availability'],'')
    def test_origin_rejection_is_not_unknown_and_is_dismissible(self):
        states=ui([{'action':'submit'},{'action':'dismiss'}],combined=True,routes={
            'POST /api/experiments':[{'http':403,'error':{'code':'INVALID_ORIGIN','message':'Local application only.'}}]})
        denied=states[1]
        self.assertFalse(denied['state']['uncertain']);self.assertFalse(denied['submitDisabled'])
        self.assertIn('Submission rejected',all_text(denied['board']))
        self.assertIn('×',all_text(denied['board']))
        self.assertNotIn('Receipt unconfirmed',all_text(denied['board']))
        self.assertIsNone(states[-1]['state']);self.assertEqual(states[-1]['saved'],{})
        self.assertNotIn(REQUEST_ID,all_text(states[-1]['board']))
        self.assertEqual(sum(c['method']=='POST' for c in states[-1]['calls']),1)
    def test_unknown_receipt_dismiss_checks_and_only_clears_on_404(self):
        for response,cleared in [({'http':404},True),({'http':503},False),(job('p1'),False)]:
            with self.subTest(response=response):
                state=ui([{'action':'submit'},{'action':'dismiss'}],routes={
                    'POST /api/experiments':[{'error':True}], 'GET /api/experiments/'+REQUEST_ID:[response]})[-1]
                self.assertEqual(state['state'] is None,cleared)
                self.assertEqual(sum(c['method']=='POST' for c in state['calls']),1)
                self.assertEqual(state['calls'][-1]['url'],'/api/experiments/'+REQUEST_ID)
    def test_dismiss_different_request_cannot_clear_receipt(self):
        state=ui([{'action':'submit'},{'action':'dismiss','id':SECOND_ID}],routes={
            'POST /api/experiments':[{'error':True}]})[-1]
        self.assertIsNotNone(state['state']);self.assertTrue(state['submitDisabled'])
    def test_unclassified_403_still_requires_receipt_verification(self):
        state=ui([{'action':'submit'}],routes={'POST /api/experiments':[{'http':403}]})[-1]
        self.assertTrue(state['state']['uncertain']);self.assertTrue(state['submitDisabled'])
    def test_empty_or_unavailable_inputs_disable_with_reason(self):
        for step in [{'action':'change','id':'target','value':''},
                     {'action':'disabled','id':'target','value':True},
                     {'action':'change','id':'expected-direction','value':'UNKNOWN'},
                     {'action':'unbind','id':'scope','binding':'scopeReference'}]:
            with self.subTest(step=step):
                state=ui([step,{'action':'submit'}])[-1]
                self.assertTrue(state['submitDisabled']);self.assertTrue(state['availability'])
                self.assertFalse(any(c['method']=='POST' for c in state['calls']))
    def test_async_custom_invalidity_updates_button_and_recovery_enables(self):
        states=ui([{'action':'validity','id':'feature','message':'Universe broadcasting is unsupported.'},
                   {'action':'validity','id':'feature','message':''}])
        self.assertTrue(states[1]['submitDisabled']);self.assertIn('Universe broadcasting',states[1]['availability'])
        self.assertFalse(states[2]['submitDisabled'])
        self.assertTrue(all(c['method']=='GET' for c in states[-1]['calls']))
    def test_external_feature_requires_current_affirmative_compatibility(self):
        external={'id':'FEATURE_'+'a'*64,'version':'1.0.0'}
        resolution={'recipe':{'reference':external},'scope':SCOPE,'submission_compatible':False,
                    'source_application_note':'External stored Features support individual instrument TS only.'}
        steps=[{'action':'change','id':'feature','value':external,'binding':'featureReference'},
               {'action':'resolution','value':resolution},
               {'action':'resolution','value':dict(resolution,submission_compatible=True)},
               {'action':'change','id':'scope','value':{'id':'UNIVERSE','version':'1.0.0'},'binding':'scopeReference'}]
        states=ui(steps)
        self.assertTrue(states[1]['submitDisabled']);self.assertIn('Checking Feature',states[1]['availability'])
        self.assertTrue(states[2]['submitDisabled']);self.assertIn('individual instrument',states[2]['availability'])
        self.assertFalse(states[3]['submitDisabled']);self.assertTrue(states[4]['submitDisabled'])
        self.assertTrue(all(c['method']=='GET' for c in states[-1]['calls']))
    def test_missing_fx_outputs_and_live_readiness_do_not_disable_valid_selection(self):
        state=ui([{'action':'resolution','value':{'recipe':{'reference':FEATURE},'scope':SCOPE,'submission_compatible':True,'summary':{'materialized_member_count':0,'missing_member_count':18},
                  'members':[{'readiness':{'live_use':{'decision':'unresolved'}}}]}}])[-1]
        self.assertFalse(state['submitDisabled']);self.assertEqual(state['availability'],'')
        self.assertTrue(all(c['method']=='GET' for c in state['calls']))
    def test_old_backend_native_coverage_during_safe_upgrade_and_new_fail_closed(self):
        old={'recipe':{'reference':FEATURE,'kind':'reusable_fx_recipe'},'scope':SCOPE}
        new=dict(old,application=None,submission_compatible=False,source_application_note='Application not registered')
        states=ui([{'action':'resolution','value':old},{'action':'resolution','value':new}])
        self.assertFalse(states[1]['submitDisabled']);self.assertTrue(states[2]['submitDisabled'])
        self.assertTrue(all(c['method']=='GET' for c in states[-1]['calls']))

    def test_async_scope_and_target_failures_update_submit_immediately(self):
        for field,event in [('scope','scope-state-change'),('target','target-state-change')]:
            with self.subTest(field=field):
                states=ui([{'action':'validity','id':field,'message':'Selection unavailable','event':event},
                           {'action':'validity','id':field,'message':'','event':event}])
                self.assertTrue(states[1]['submitDisabled']);self.assertFalse(states[2]['submitDisabled'])
    def test_no_separate_progress_panel_or_open_progress_links(self):
        html=(PROJECT/'ui/index.html').read_text();queue=(PROJECT/'ui/queue.js').read_text()
        self.assertNotIn('id="experiment-progress"',html)
        self.assertNotIn('Open progress',queue);self.assertNotIn('Open saved progress',queue)
        self.assertIn('id="submission-notice"',html)

if __name__=='__main__':unittest.main()
