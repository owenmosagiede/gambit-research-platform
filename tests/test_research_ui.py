"""Exercise the shipped read-only Experiment contract guide without running research."""
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


def exact(value, digest='a'):
    return dict(value, content_sha256=digest * 64)


def scope_binding(kind='instrument'):
    return dict(SCOPE, kind=kind, reference=exact(SCOPE, 'b'), definition_binding=exact(SCOPE, 'b'),
                membership_snapshot=exact({'id': 'MEMBERSHIP_fixture', 'version': '1.0.0'}, 'c'),
                members=['AUDUSD'], member_count=1)


def feature_resolution(application='per_instrument_input', **changes):
    value = {'recipe': {'reference': exact(FEATURE), 'kind': 'reusable_fx_recipe'},
             'scope': dict(SCOPE, reference=exact(SCOPE, 'b'),
                           membership_snapshot=scope_binding()['membership_snapshot']),
             'application': {'contract': {'kind': application}}, 'submission_compatible': True}
    value.update(changes)
    return value


def ui(steps=(), *, routes=None, held=(), saved=None, initial=None):
    node = shutil.which('node')
    if not node:
        raise unittest.SkipTest('Node.js is needed for the actual contract UI checks')
    harness = r'''const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
class Element {
 constructor(id){this.id=id;this.children=[];this.dataset={};this.listeners={};this.textContent='';this.value='';this.disabled=false;this.hidden=false;this.selectedOptions=[];this.options=[];this.attributes={};this.validity={valid:true};}
 setAttribute(k,v){this.attributes[k]=v;} getAttribute(k){return this.attributes[k]??null;}
 setCustomValidity(message){this.validationMessage=message;this.validity={valid:!message};}
 append(...c){this.children.push(...c);} replaceChildren(...c){this.children=c;}
 addEventListener(n,f){(this.listeners[n] ||= []).push(f);} fire(n){for(const f of this.listeners[n]||[])f({preventDefault(){}});}
}
const names=['feature','scope','target','expected-direction','contract-example','contract-selection-status','contract-catalog-status','contract-refresh','experiment-inputs','experiment-contract','research-specification','research-readiness-retry','research-readiness-status','research-method-summary','research-readiness-blockers','research-operational-incidents'];
const ids=Object.fromEntries(names.map(n=>[n,new Element(n)]));
function select(id,value){ids[id].value=typeof value==='string'?value:JSON.stringify(value);ids[id].selectedOptions=[{textContent:id,disabled:false}];}
function dataset(id,key,value){if(value===null)delete ids[id].dataset[key];else ids[id].dataset[key]=typeof value==='string'?value:JSON.stringify(value);}
select('feature',input.feature);dataset('feature','featureReference',input.featureRef);dataset('feature','featureResolution',input.resolution);dataset('feature','featureKind','reusable_fx_recipe');dataset('feature','catalogCount','106');
select('scope',input.scope);dataset('scope','scopeReference',input.scopeRef);dataset('scope','membershipSnapshot',input.scopeResolution.membership_snapshot);dataset('scope','resolvedMembers',input.scopeResolution.members);dataset('scope','scopeResolution',input.scopeResolution);dataset('scope','catalogCount','50');dataset('scope','universeCount','7');dataset('scope','instrumentCount','43');
select('target','price');dataset('target','returnBasis','price');select('expected-direction','POSITIVE');
for(const [id,patch] of Object.entries(input.initial||{})){if(patch.value!==undefined)select(id,patch.value);for(const [key,value] of Object.entries(patch.dataset||{}))dataset(id,key,value);if(patch.disabled!==undefined)ids[id].disabled=patch.disabled;}
let seq=0,now=1000000;const timers=new Map(),calls=[],events={},docEvents={},pending=[],sent=[],saved={},counts={},storage=[];
if(input.saved)saved['research-platform.experiment-request.v1']=JSON.stringify(input.saved);
const add=(map,n,f)=>(map[n] ||= []).push(f),fire=(map,n,event={})=>{for(const f of map[n]||[])f(event);};
const storageApi={getItem:k=>{storage.push(['read',k]);return saved[k]||null;},setItem:(k,v)=>{storage.push(['write',k]);saved[k]=v;},removeItem:k=>{storage.push(['remove',k]);delete saved[k];}};
const context={document:{getElementById:id=>ids[id]||null,querySelector:()=>null,createElement:n=>new Element(n),hidden:false,visibilityState:'visible',addEventListener:(n,f)=>add(docEvents,n,f)},AbortController,
 Date:class extends Date{static now(){return now;}},
 CustomEvent:class{constructor(type,opts){this.type=type;this.detail=opts?.detail;}},
 window:{localStorage:storageApi,sessionStorage:storageApi,location:{hash:'#experiment'},crypto:{randomUUID:()=>{throw Error('Read-only UI generated request ID');}},
 setTimeout:(fn,ms)=>{timers.set(++seq,{fn,ms});return seq;},clearTimeout:k=>timers.delete(k),
 addEventListener:(n,f)=>add(events,n,f),dispatchEvent:e=>{sent.push(e);fire(events,e.type,e);}},
 fetch:async(url,opts={})=>{const index=calls.length;calls.push({url,method:opts.method||'GET',body:opts.body?JSON.parse(opts.body):null});
 const key=(opts.method||'GET')+' '+url,n=counts[key]||0;counts[key]=n+1;const list=input.routes[key];
 const value=list?list[Math.min(n,list.length-1)]:url==='/api/research-readiness'?input.readiness:{error:true};
 if(input.held.includes(index))return new Promise((resolve,reject)=>pending.push({index,value,resolve,reject}));return response(value);}};
function response(v){if(v.error&&!v.http)throw Error('Network interrupted');return {ok:!v.http,status:v.http||200,json:async()=>v};}
const flush=()=>new Promise(r=>setImmediate(r)),views=[];
function tree(n){return {text:n.textContent,children:n.children.map(tree)};}
function snap(){views.push(JSON.parse(JSON.stringify({calls,dispatched:sent,saved,storage,registeredEvents:Object.keys(events),
 example:ids['contract-example'].textContent,selection:ids['contract-selection-status'].textContent,catalog:ids['contract-catalog-status'].textContent,
 specification:ids['research-specification'].textContent,method:ids['research-method-summary'].textContent,
 readiness:ids['research-readiness-status'].textContent,blockers:tree(ids['research-readiness-blockers']),incidents:tree(ids['research-operational-incidents']),
 refreshDisabled:ids['contract-refresh'].disabled,readinessRetryDisabled:ids['research-readiness-retry'].disabled})));}
(async()=>{vm.runInNewContext(fs.readFileSync(input.script,'utf8'),context);
// The actual queue module supplies this initial read-completion event.
fire(events,'research-queue-settled',{detail:{verified:true}});await flush();snap();
for(const step of input.steps){
 now+=step.ms||0;
 if(step.action==='change'){select(step.id,step.value);ids[step.id].fire('change');}
 if(step.action==='dataset'){dataset(step.id,step.key,step.value);fire(events,step.event||`${step.id}-state-change`);}
 if(step.action==='resolution'){dataset('feature','featureResolution',step.value);fire(events,'feature-state-change');}
 if(step.action==='disabled'){ids[step.id].disabled=step.value;fire(events,`${step.id}-state-change`);}
 if(step.action==='validity'){ids[step.id].setCustomValidity(step.message);fire(events,`${step.id}-state-change`);}
 if(step.action==='busy'){ids[step.id].setAttribute('aria-busy',String(step.value));}
 if(step.action==='click')ids[step.id]?.fire('click');
 if(step.action==='event'){if(step.hash!==undefined)context.window.location.hash=step.hash;fire(events,step.name,{detail:step.detail});}
 if(step.action==='visibility'){context.document.hidden=step.hidden;context.document.visibilityState=step.hidden?'hidden':'visible';fire(docEvents,'visibilitychange');}
 if(step.action==='settle'){const p=pending.find(p=>p.index===step.index);if(step.error)p.reject(Error('Network interrupted'));else p.resolve(response(step.value||p.value));}
 if(step.action==='health'){const t=[...timers].find(([,v])=>v.ms===30000);if(t){timers.delete(t[0]);t[1].fn();}}
 await flush();snap();}process.stdout.write(JSON.stringify(views));})().catch(e=>{console.error(e);process.exitCode=1;});'''
    service = readiness()
    service['research_spec'] = exact({'id': 'SPEC_TS_DEFAULT', 'version': '1.0.0'}, 'd')
    data = {'script': str(PROJECT / 'ui/submission.js'), 'feature': FEATURE, 'featureRef': exact(FEATURE),
            'scope': SCOPE, 'scopeRef': exact(SCOPE, 'b'), 'scopeResolution': scope_binding(),
            'resolution': feature_resolution(), 'readiness': service, 'steps': list(steps),
            'routes': routes or {}, 'held': list(held), 'saved': saved, 'initial': initial or {}}
    result = subprocess.run([node, '-e', harness], input=json.dumps(data), text=True,
                            capture_output=True, check=True)
    return json.loads(result.stdout)


def all_text(tree):
    return tree['text'] + ' ' + ' '.join(all_text(child) for child in tree['children'])


class ResearchContractUITests(unittest.TestCase):
    def assert_read_only(self, state):
        self.assertTrue(all(call['method'] == 'GET' and call['body'] is None for call in state['calls']))
        self.assertTrue(all(call['url'] == '/api/research-readiness' for call in state['calls']))
        self.assertEqual(state['storage'], [])

    def test_live_submission_incidents_are_visible_read_only(self):
        value = readiness()
        value['submission_incidents'] = [{'id': 'OPINCIDENT_fixture', 'request_id': REQUEST_ID,
                                         'message': 'Submission evidence could not be verified.'}]
        state = ui(routes={'GET /api/research-readiness': [value]})[-1]
        self.assertIn('OPINCIDENT_fixture', all_text(state['incidents']))
        self.assertIn(REQUEST_ID, all_text(state['incidents']))
        self.assertIn('could not be verified', all_text(state['incidents']))
        self.assertTrue(all(call['method'] == 'GET' for call in state['calls']))

    def test_exact_selection_is_an_example_with_no_real_request_identity(self):
        state = ui()[-1]
        expected = payload(); expected['request_id'] = '<new canonical UUID>'
        self.assertEqual(json.loads(state['example']), expected)
        self.assertIn('SPEC_TS_DEFAULT', state['specification'])
        self.assert_read_only(state)

    def test_browser_events_and_saved_pending_request_never_resend_or_mutate(self):
        saved = {'payload': payload(), 'uncertain': True}
        steps = [{'action': 'event', 'name': name, 'detail': {'request_id': REQUEST_ID, 'resend': True}}
                 for name in ('submit', 'research-submission-recover', 'research-submission-dismiss',
                              'research-submission-state', 'research-queue-state', 'research-job-update')]
        steps += [{'action': 'health'}, {'action': 'click', 'id': 'research-readiness-retry'}]
        state = ui(steps, saved=saved)[-1]
        self.assertEqual(json.loads(state['saved']['research-platform.experiment-request.v1']), saved)
        self.assertNotIn('research-submission-recover', state['registeredEvents'])
        self.assertNotIn('research-submission-dismiss', state['registeredEvents'])
        self.assert_read_only(state)

    def test_expected_direction_updates_example_without_submit(self):
        state = ui([{'action': 'change', 'id': 'expected-direction', 'value': 'NEGATIVE'}])[-1]
        self.assertEqual(json.loads(state['example'])['expected_direction'], 'NEGATIVE')
        self.assert_read_only(state)

    def test_missing_changed_or_disabled_exact_binding_cannot_appear_current(self):
        steps = [
            {'action': 'dataset', 'id': 'feature', 'key': 'featureReference', 'value': None},
            {'action': 'dataset', 'id': 'scope', 'key': 'scopeReference', 'value': None},
            {'action': 'dataset', 'id': 'feature', 'key': 'featureReference', 'value': exact({'id': 'OTHER', 'version': '1.0.0'})},
            {'action': 'change', 'id': 'scope', 'value': {'id': 'OTHER', 'version': '1.0.0'}},
            {'action': 'disabled', 'id': 'feature', 'value': True},
        ]
        for step in steps:
            with self.subTest(step=step):
                state = ui([step])[-1]
                example = json.loads(state['example'])
                key = 'scope' if step.get('id') == 'scope' else 'feature'
                self.assertNotEqual(example[key], SCOPE if key == 'scope' else FEATURE)
                self.assertNotIn('SPEC_TS_DEFAULT', state['specification'])
                self.assert_read_only(state)

    def test_target_and_direction_placeholders_do_not_claim_valid_values(self):
        for step, key, forbidden in [
            ({'action':'dataset','id':'target','key':'returnBasis','value':None}, 'target_family', 'price_return'),
            ({'action':'change','id':'target','value':'total_return'}, 'target_family', 'price_return'),
            ({'action':'change','id':'expected-direction','value':'UNKNOWN'}, 'expected_direction', 'POSITIVE'),
        ]:
            with self.subTest(step=step):
                state = ui([step])[-1]
                self.assertNotEqual(json.loads(state['example'])[key], forbidden)
                self.assert_read_only(state)

    def test_stale_scope_or_feature_hash_never_selects_a_research_spec(self):
        for field in ('recipe', 'scope'):
            value = feature_resolution()
            value[field]['reference']['content_sha256'] = 'f' * 64
            state = ui([{'action': 'resolution', 'value': value}])[-1]
            self.assertNotIn('SPEC_TS_DEFAULT', state['specification'])
            self.assert_read_only(state)

    def test_scope_definition_and_membership_must_match_current_verified_bindings(self):
        for key in ('definition_binding', 'membership_snapshot'):
            with self.subTest(key=key):
                changed = scope_binding()
                changed[key]['content_sha256'] = 'f' * 64
                state = ui([{'action':'dataset','id':'scope','key':'scopeResolution','value':changed}])[-1]
                self.assertNotIn('SPEC_TS_DEFAULT', state['specification'])
                self.assertNotIn('Example for the selected inputs', state['selection'])
                self.assert_read_only(state)

    def test_late_readiness_cannot_restore_a_stale_selection_spec(self):
        states = ui([{'action':'dataset','id':'feature','key':'featureReference','value':None},
                     {'action':'settle','index':0}], held=[0])
        self.assertNotIn('SPEC_TS_DEFAULT', states[-1]['specification'])
        self.assertNotEqual(json.loads(states[-1]['example'])['feature'], FEATURE)
        self.assert_read_only(states[-1])

    def test_unsupported_feature_scope_reports_reason_and_no_generic_spec(self):
        value = feature_resolution(submission_compatible=False, source_application_note='This combination is unsupported.')
        state = ui([{'action': 'resolution', 'value': value}])[-1]
        self.assertIn('unsupported', state['selection'].lower())
        self.assertNotIn('SPEC_TS_DEFAULT', state['specification'])
        self.assert_read_only(state)

    def test_currency_cs_never_inherits_single_pair_ts_spec(self):
        scope = scope_binding('universe'); scope['reference_currency'] = 'USD'; scope['members'] = ['AUD', 'EUR']
        value = feature_resolution('currency_quote_input')
        initial = {'scope': {'dataset': {'scopeResolution': scope, 'resolvedMembers': scope['members']}},
                   'feature': {'dataset': {'featureResolution': value}}}
        state = ui(initial=initial)[-1]
        self.assertNotIn('SPEC_TS_DEFAULT', state['specification'])
        self.assertIn('CS', state['method'])
        self.assertIn('USD', state['method'])
        self.assert_read_only(state)
        value['research_spec'] = exact({'id': 'SPEC_CS_PINNED', 'version': '2.0.0'}, 'e')
        state = ui([{'action': 'resolution', 'value': value}], initial=initial)[-1]
        self.assertIn('SPEC_CS_PINNED', state['specification'])
        self.assertNotIn('SPEC_TS_DEFAULT', state['specification'])

    def test_explicit_external_spec_is_shown_only_for_current_compatible_resolution(self):
        value = feature_resolution('stored_daily_state', research_spec=exact({'id': 'SPEC_EXTERNAL', 'version': '1.0.0'}, 'e'))
        value['recipe']['kind'] = 'stored_feature'
        state = ui([{'action': 'resolution', 'value': value}])[-1]
        self.assertIn('SPEC_EXTERNAL', state['specification'])
        self.assertNotIn('SPEC_TS_DEFAULT', state['specification'])
        value['submission_compatible'] = False
        state = ui([{'action': 'resolution', 'value': value}])[-1]
        self.assertNotIn('SPEC_EXTERNAL', state['specification'])

    def test_dynamic_catalog_counts_do_not_retain_removed_catalog(self):
        states = ui([{'action':'dataset','id':'feature','key':'catalogCount','value':'12'},
                     {'action':'dataset','id':'scope','key':'universeCount','value':'3'},
                     {'action':'dataset','id':'scope','key':'instrumentCount','value':'9'},
                     {'action':'dataset','id':'feature','key':'catalogCount','value':None}])
        self.assertIn('106', states[0]['catalog']); self.assertIn('7', states[0]['catalog']); self.assertIn('43', states[0]['catalog'])
        self.assertIn('12', states[-2]['catalog']); self.assertIn('3', states[-2]['catalog']); self.assertIn('9', states[-2]['catalog'])
        self.assertNotIn('12', states[-1]['catalog'])
        self.assert_read_only(states[-1])

    def test_manual_refresh_broadcasts_once_without_any_research_submission(self):
        # One startup activation plus one explicit refresh.
        state = ui([{'action': 'click', 'id': 'contract-refresh'}])[-1]
        self.assertEqual(sum(event['type'] == 'experiment-catalog-refresh' for event in state['dispatched']), 2)
        self.assert_read_only(state)

    def test_returning_to_page_refreshes_only_when_old_visible_and_idle(self):
        for name in ('focus', 'pageshow', 'hashchange'):
            with self.subTest(event=name):
                states = ui([{'action':'event','name':name}, {'action':'event','name':name,'ms':30001}])
                self.assertEqual(sum(event['type'] == 'experiment-catalog-refresh' for event in states[1]['dispatched']), 1)
                self.assertEqual(sum(event['type'] == 'experiment-catalog-refresh' for event in states[2]['dispatched']), 2)
        for hidden in ('hidden_document', 'other_page', 'busy_catalog'):
            with self.subTest(hidden=hidden):
                setup = {'hidden_document':[{'action':'visibility','hidden':True}],
                         'other_page':[{'action':'event','name':'hashchange','hash':'#signals'}],
                         'busy_catalog':[{'action':'busy','id':'feature','value':True}]}[hidden]
                state = ui(setup + [{'action':'event','name':'focus','ms':30001}])[-1]
                self.assertEqual(sum(event['type'] == 'experiment-catalog-refresh' for event in state['dispatched']), 1)
                self.assert_read_only(state)

    def test_visibility_refresh_and_readiness_poll_only_read_status(self):
        state = ui([{'action':'visibility','hidden':True}, {'action':'visibility','hidden':False,'ms':30001},
                    {'action':'health'}])[-1]
        self.assertEqual(sum(event['type'] == 'experiment-catalog-refresh' for event in state['dispatched']), 2)
        self.assert_read_only(state)

    def test_unavailable_or_blocked_readiness_does_not_enable_a_mutation_path(self):
        for response in ({'error': True}, readiness(False), {'execution_enabled':True}):
            with self.subTest(response=response):
                state = ui([{'action':'click','id':'research-readiness-retry'}],
                           routes={'GET /api/research-readiness':[response]})[-1]
                self.assertTrue(state['readiness'])
                self.assert_read_only(state)

    def test_markup_is_a_contract_group_and_has_no_submission_controls(self):
        html = (PROJECT / 'ui/index.html').read_text()
        self.assertIn('id="experiment-contract"', html)
        self.assertIn('role="group" aria-label="Experiment inputs"', html)
        for old in ('experiment-submit', 'submission-check', 'submission-notice'):
            self.assertNotIn(f'id="{old}"', html)
        self.assertNotIn('<form', html)


if __name__ == '__main__':
    unittest.main()
