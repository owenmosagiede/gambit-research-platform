"""Run the shipped grouped Signal Library UI against explicit API fixtures."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import unittest

PROJECT = Path(__file__).resolve().parents[1]


def ref(identifier):
    return {'id': identifier, 'version': '1.0.0', 'content_sha256': hashlib.sha256(identifier.encode()).hexdigest()}


def sid(index=1):
    return 'SIGNAL_' + f'{index:064x}'


def mid(index=1):
    return 'MATERIALIZATION_' + f'{index:064x}'


def chain(k=63, internal=False):
    steps = [] if internal else [{'node': 'log_price', 'operator': ref('TR_BASE_log'), 'label': 'Log Level', 'parameters': []}]
    steps.append({'node': 'fx_value', 'operator': ref('TR_BASE_vol_downside' if internal else 'TR_BASE_momentum_skip_diff'),
                  'label': 'Downside Semivolatility' if internal else 'Skip Recent Difference',
                  'parameters': ([{'name': 'basis', 'value': {'type': 'token', 'value': 'log'}},
                                  {'name': 'w', 'value': {'type': 'integer', 'value': '21'}}] if internal else
                                 [{'name': 'k', 'value': {'type': 'integer', 'value': str(k)}},
                                  {'name': 's', 'value': {'type': 'integer', 'value': '5'}}])})
    return steps


def capabilities():
    return {'retrospective_research': {'decision': 'ready'},
            'historical_replay': {'decision': 'blocked', 'reason': 'Historical source availability is unknown.'},
            'live_use': {'decision': 'unresolved'}}


def materialization(index=1):
    return {'id': mid(index), 'reference': ref(mid(index)), 'row_count': 2,
            'status_counts': {'valid': 2, 'missing': 0, 'invalid': 0},
            'coverage': {'reference_start': '2024-01-02', 'reference_end': '2024-01-03',
                         'cutoff_start': '2026-10-09', 'cutoff_end': '2026-10-09'},
            'readiness_capabilities': capabilities()}


def signal(index=1, instrument='AUDUSD', k=63, *, ces=False, internal=False):
    source = {'name': 'Average Hourly Earnings' if ces else instrument + ' Closing Price',
              'series_id': 'CES0500000003' if ces else instrument, 'provider': 'FRED_ALFRED' if ces else 'Twelve Data',
              'frequency': 'monthly' if ces else 'daily', 'units': 'USD' if ces else 'USD_per_AUD'}
    return {'signal_id': sid(index), 'name': 'Existing CES monthly change' if ces else instrument + ' Log Skip Recent Difference',
            'feature': ref('FEATURE_' + f'{index:064x}'), 'source': source, 'unit': 'dimensionless' if ces else 'log_USD_per_AUD',
            'value_semantics': 'fractional_change' if ces else 'difference', 'row_count': 2, 'materialization_count': 1,
            'default_materialization_id': mid(index), 'coverage': materialization(index)['coverage'],
            'status_counts': {'valid': 2, 'missing': 0, 'invalid': 0}, 'materialization_state': 'materialized',
            'scientific_state': 'untested', 'transformations': chain(k, internal),
            'availability_semantics': 'archive_date' if ces else 'unknown_historical_availability'}


def output(index=1, instrument='AUDUSD', k=63, internal=False):
    value = signal(index, instrument, k, internal=internal)
    value['detail_href'] = '/api/signal-library-outputs/' + value['signal_id']
    mat = materialization(index); mat['href'] = value['detail_href'] + '?materialization_id=' + mat['id']
    value['materializations'] = [mat]
    return value


def research(linked=False):
    links = [] if not linked else [{'signal_id': sid(), 'projection': ref('ENTRY_abc'),
        'relationship': ref('RELATIONSHIP_abc'), 'trial_results': [ref('TRIAL_RESULT_abc')],
        'admission_results': [], 'validation_results': [ref('VALIDATION_RESULT_abc')],
        'attempt_ids': ['10000000-0000-4000-8000-000000000001']}]
    return {'state': 'results_linked' if linked else 'untested',
            'label': 'Research results linked' if linked else 'Untested',
            'relationship_count': len(links), 'relationships': links, 'metrics': [],
            'description': 'Authoritative relationship records retain Scope, Target and horizon.' if linked else 'No tested relationships are stored.'}


def group(index=1, k=63, *, outputs=None, linked=True, internal=False):
    identifier = 'FEATURE_RECIPE_' + f'{index:064x}'
    return {'kind': 'reusable_fx_recipe', 'id': identifier, 'recipe': ref(identifier),
            'name': '21-day log downside semivolatility' if internal else f'{k}-day log momentum · skip 5 days',
            'source': {'label': 'Closing prices', 'input_contract': {'value_semantics': 'price', 'frequency': 'daily', 'observation_clock': 'scheduled_weekdays'}},
            'transformations': chain(k, internal), 'observation_count': None, 'research': research(linked),
            'outputs': outputs if outputs is not None else [output(index, k=k, internal=internal)]}


def ces():
    item = signal(90, ces=True)
    item['scientific_state'] = 'results_linked'
    linked = research(True); linked['relationships'][0]['signal_id'] = item['signal_id']
    return {'kind': 'stored_signal', 'id': item['signal_id'], 'signal': item, 'research': linked}


def detail(item, *, linked=False, ces=False):
    summary = deepcopy(item)
    mats = summary.pop('materializations', [materialization(90 if ces else 1)])
    summary.pop('detail_href', None)
    rows = [{'evaluation_cutoff': '2026-10-09', 'reference_time': date, 'value': value, 'status': 'valid',
             'reason_code': None, 'available_at': None, 'lineage': ref('LINEAGE_' + date)}
            for date, value in [('2024-01-02', '0.01'), ('2024-01-03', '0.02')]]
    research_value = research(linked)
    if ces:
        research_value.pop('relationships'); research_value.pop('label')
    return {'schema_version': '1.0.0', 'signal': summary, 'selected_materialization_id': mats[0]['id'],
            'materializations': mats, 'statistics': {'kind': 'descriptive_observation_statistics', 'row_count': 2,
            'valid_count': 2, 'missing_count': 0, 'invalid_count': 0, 'null_count': 0,
            'min': .01, 'max': .02, 'mean': .015, 'median': .015, 'sample_standard_deviation': .007, 'reason_counts': {}},
            'observations': rows, 'provenance': {'feature': summary['feature']},
            'timing': {'retrospective_snapshot': not ces, 'description': 'Archive replay' if ces else 'Historical availability remains unknown.'},
            'source_metadata': {'provider': {'body': {'seasonal_adjustment': 'Not recorded'}}},
            'recipe': {'selection': {'entity_id': summary['source']['series_id'], 'measure': 'close'}},
            'research': research_value}


def recorded_group():
    item = group(linked=True)
    item['research']['label'] = 'Research results recorded'
    first = item['research']['relationships'][0]
    first.update(scope={'id': 'AUDUSD', 'version': '1.0.0'}, mode='TS', horizon=21,
                 target_family='price_return', expected_direction='POSITIVE', p1_status='admitted', p2_status='VALIDATED',
                 trial_results=[ref('TRIAL_P1_a'), ref('TRIAL_P2_a')], results=[
        {'stage': 'P1', 'period': {'start_inclusive': '2015-01-01', 'end_exclusive': '2022-01-01'},
         'metrics': {'primary_effect': '0.25', 'hac_t_statistic': '2.7'}, 'sample': {'usable_date_count': 900},
         'research_spec': ref('RSPEC_fixture'), 'authority': ref('TRIAL_P1_a')},
        {'stage': 'P2', 'period': {'start_inclusive': '2022-01-01', 'end_exclusive': '2026-09-01'},
         'metrics': {'primary_effect': '0.12', 'effect_retention_ratio': '0.48', 'directional_hac_t_statistic': '1.8'},
         'sample': {'effective_observation_count': 25}, 'research_spec': ref('RSPEC_fixture'), 'authority': ref('TRIAL_P2_a')},
    ])
    other = deepcopy(first)
    other.update(relationship=ref('RELATIONSHIP_cs_other'), projection=ref('ENTRY_cs_other'),
                 scope={'id': 'FTMO_UNIVERSE', 'version': '1.0.0'}, mode='CS', horizon=63,
                 p2_status='FAILED', trial_results=[ref('TRIAL_P2_b')], results=[
        {'stage': 'P2', 'period': {'start_inclusive': '2022-01-01', 'end_exclusive': '2025-01-01'},
         'metrics': {'primary_effect': '-0.08', 'directional_hac_t_statistic': None},
         'sample': {'effective_observation_count': 16}, 'research_spec': ref('RSPEC_other'), 'authority': ref('TRIAL_P2_b')},
    ])
    item['research']['relationships'].append(other)
    item['research']['relationship_count'] = 2
    return item


def catalog_for(*entries):
    return {'schema_version': '1.0.0', 'entry_count': len(entries), 'entries': list(entries), 'issues': []}


def refresh_event(index=1):
    return {'request_id': '10000000-0000-4000-8000-000000000001', 'results': [ref('RESEARCHLINK_' + str(index))]}


def ui(entries, steps=(), *, responses=None, hold=(), fail_catalog=False, catalog=None, catalogs=None, initial_hash="#signals", registry=None):
    node = shutil.which('node')
    if not node:
        raise unittest.SkipTest('Node.js required for shipped Signal Library UI checks')
    harness = r'''
const fs = require("fs"), vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.listeners = {};
    this.hidden = false; this.value = ""; this.textContent = ""; this.attributes = {}; this.scrollTop = 0; }
  replaceChildren(...items) { for(const c of this.children) c.parentElement=null; this.children=[];this.append(...items); }
  append(...items) { for(const item of items) { if(item.parentElement) item.parentElement.children=item.parentElement.children.filter(c=>c!==item); item.parentElement=this;this.children.push(item); } }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name]; }
  removeAttribute(name) { delete this.attributes[name]; }
  focus() {}
  click() { this.listeners.click({target:this}); }
  closest(selector) { return this.tag === "button" ? this : null; }
}
const ids = Object.fromEntries(["signal-table-container", "signal-library-status", "signal-detail-body", "signal-detail-status",
  "signal-detail-title", "experiment-inputs", "signal-page", "pit-sidebar", "signal-sidebar", "sidebar-signal-status",
  "sidebar-signal-issues", "signal-library-issues", "sidebar-signal-retry", "signal-library-retry", "sidebar-signal-items",
  "signal-detail", "signal-detail-retry", "library-items", "signal-detail-home", "ledger-page", "signal-back"].map(id => [id, new Element(id)]));
const skip = new Element("a"), nav = [], windowListeners = {}, requests = [], pending = [], signals = [];
const timers = new Map(); let clock = 0, nextTimer = 0;
const responses = input.responses; let catalogIndex = 0;
const output = value => ({ok: value !== null, json: async () => value});
const context = {document: {getElementById: id => ids[id], createElement: tag => new Element(tag),
  createDocumentFragment: () => new Element("fragment"), createTextNode: value => {const n = new Element("text"); n.textContent=value;return n;},
  querySelector: () => skip, querySelectorAll: () => nav},
  window: {location:{hash:input.initial_hash || "#signals"},
    setTimeout: (fn, delay) => { const id=++nextTimer; timers.set(id,{fn,at:clock+delay}); return id; },
    clearTimeout: id => timers.delete(id),
    addEventListener: (name, fn) => windowListeners[name] = fn}, AbortController,
  fetch: async (url, options) => {
    requests.push({url, method:options.method}); signals.push(options.signal);
    if (input.hold.includes(url)) return new Promise((resolve,reject) => {
      pending.push({url,resolve,reject});
      options.signal.addEventListener('abort', () => reject(new Error('Aborted')), {once:true});
    });
    if (url === "/api/signal-library-summaries") {
      if(input.fail_catalog) throw new Error("Unavailable"); return output(input.catalogs ? input.catalogs[Math.min(catalogIndex++,input.catalogs.length-1)] : input.catalog);
    }
    return output(responses[url] ?? null);
  }};
const flush = () => new Promise(resolve => setImmediate(resolve));
const snapshots = [];
const read = node => ({tag:node.tag, text:node.textContent, className:node.className, hidden:node.hidden, dataset:node.dataset, attributes:node.attributes,
  children:node.children.map(read)});
const find = (node, predicate) => predicate(node) ? node : node.children.map(child => find(child,predicate)).find(Boolean);
function snapshot() {
  snapshots.push(JSON.parse(JSON.stringify({table:read(ids["signal-table-container"]), sidebar:read(ids["sidebar-signal-items"]),
    detail:read(ids["signal-detail-body"]), title:ids["signal-detail-title"].textContent, status:ids["signal-detail-status"].textContent,
    detailHidden:ids["signal-detail"].hidden, catalogStatus:ids["signal-library-status"].textContent, busy:ids["signal-detail"].attributes["aria-busy"],
    catalogRetryHidden:ids["signal-library-retry"].hidden, detailRetryHidden:ids["signal-detail-retry"].hidden,
    issues:ids["signal-library-issues"].textContent, issuesHidden:ids["signal-library-issues"].hidden,
    experimentHidden:ids["experiment-inputs"].hidden, signalsHidden:ids["signal-page"].hidden, skipHref:skip.href,
    requests, aborted:signals.map(signal => signal.aborted)})));
}
(async () => {
  vm.runInNewContext(fs.readFileSync(input.script,"utf8"),context); await flush(); snapshot();
  for(const step of input.steps) {
    if(step.action === "advance") {
      clock += step.ms;
      for(const [id,timer] of [...timers]) if(timer.at <= clock) {timers.delete(id);timer.fn();}
    }
    else if(step.action === "navigate") { context.window.location.hash=step.hash; windowListeners["hashchange"](); }
    else if(step.action === "select") {
      const row=find(ids["signal-table-container"],node=>node.dataset.entryId===step.id);
      find(row,node=>node.tag==="button").click();
    } else if(step.action === "output") {
      find(ids["signal-detail-body"],node=>node.tag==="button" && node.dataset.signalId===step.id && node.dataset.materializationId===step.mid).click();
    } else if(step.action === "open") windowListeners["open-signal"]({detail:{signal_id:step.id,materialization_id:step.mid}});
    else if(step.action === "refresh") windowListeners["research-results-updated"]({detail:step.detail});
    else if(step.action === "retry") ids[step.element || "signal-detail-retry"].click();
    else if(step.action === "settle") {
      const req=pending[step.index];
      if(step.error) req.reject(new Error("Unavailable"));
      else req.resolve(output(step.value ?? (req.url==="/api/signal-library-summaries" ? input.catalog : responses[req.url])));
    }
    await flush(); snapshot();
  }
  process.stdout.write(JSON.stringify(snapshots));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    response_map = {}
    for entry in entries:
        if entry['kind'] == 'stored_signal':
            response_map['/api/signal-library/' + entry['id']] = detail(entry['signal'], ces=True, linked=True)
        else:
            for output_item in entry['outputs']:
                for mat in output_item['materializations']:
                    value = detail(output_item, linked=entry['research']['state'] == 'results_linked')
                    value['selected_materialization_id'] = mat['id']
                    response_map[mat['href']] = value
    payload = {'registry':registry,'initial_hash': initial_hash, 'script': str(PROJECT/'ui/signals.js'), 'steps': list(steps), 'hold': list(hold),
               'fail_catalog': fail_catalog, 'catalogs': catalogs, 'responses': response_map if responses is None else responses,
               'catalog': catalog if catalog is not None else {'schema_version': '1.0.0', 'entry_count': len(entries),
                                                              'entries': entries, 'issues': []}}
    result = subprocess.run([node, '-e', harness], input=json.dumps(payload), text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def flatten(node):
    return '\n'.join([node['text'], *(flatten(child) for child in node['children'])])


def rows(node):
    if node.get('className') == 'card-list':
        result=[]
        for card in node['children']:
            summary=card['children'][0]['children'][0]
            result.append(['\n'.join(flatten(child).strip() for child in field['children'] if child.get('className')!='card-field-label') for field in summary['children']])
        return result
    if node['tag'] == 'tbody':
        return [[flatten(cell).strip() for cell in row['children']] for row in node['children']]
    for child in node['children']:
        result = rows(child)
        if result:
            return result
    return []


class SignalRecipeUiTests(unittest.TestCase):
    def setUp(self):
        self.group = group(outputs=[output(1), output(2, 'EURUSD')])
        self.legacy = ces()

    def test_verified_research_remains_visible_without_stored_outputs(self):
        item=group(outputs=[])
        views=ui([item],[{'action':'select','id':item['id']}])
        self.assertEqual(len(rows(views[0]['table'])),1)
        self.assertIn('No stored outputs are catalogued',flatten(views[-1]['detail']))
        self.assertEqual(rows(views[0]['table'])[0][-1],'Research results available')

    def test_registration_catalog_is_never_used_as_a_fallback(self):
        item=group(outputs=[])
        registry={'feature_count':1,'features':[{'id':item['id'],'reference':item['recipe'],'name':item['name'],
            'kind':'reusable_fx_recipe','transformations':item['transformations'],'signal_id':None}]}
        states=ui([],registry=registry,hold=['/api/signal-library-summaries'],steps=[{'action':'settle','index':0,'error':True}])
        self.assertEqual(rows(states[0]['table']),[])
        self.assertEqual(rows(states[-1]['table']),[])
        self.assertFalse(states[-1]['catalogRetryHidden'])
        self.assertEqual([r['url'] for r in states[0]['requests']],['/api/signal-library-summaries'])

    def test_registration_or_preparation_alone_cannot_enter_the_library(self):
        for item in (group(linked=False), group(outputs=[], linked=False)):
            with self.subTest(prepared=bool(item['outputs'])):
                view = ui([item])[0]
                self.assertEqual(rows(view['table']), [])
                self.assertFalse(view['catalogRetryHidden'])
        legacy = ces(); legacy.pop('research')
        self.assertEqual(rows(ui([legacy])[0]['table']), [])

    def test_empty_researched_catalog_has_an_honest_empty_state(self):
        view = ui([])[0]
        self.assertEqual(view['catalogStatus'], '0 researched Signals')
        self.assertIn('No researched Signals yet', flatten(view['table']))
        self.assertIn('Prepared observations alone do not count', flatten(view['table']))
        self.assertTrue(view['catalogRetryHidden'])

    def test_legacy_pit_hash_uses_experiment_without_pit_or_filter_elements(self):
        for route in ('#pit', '#pit-page'):
            view = ui([], initial_hash=route)[0]
            self.assertFalse(view['experimentHidden'])
            self.assertTrue(view['signalsHidden'])
            self.assertEqual(view['skipHref'], '#experiment-inputs')
            self.assertEqual(view['requests'], [])

    def test_partial_catalog_discloses_missing_records_without_replacing_verified_entries(self):
        data = catalog_for(self.group); data['issues'] = [{'code': 'unverified_record'}]
        view = ui([self.group], catalog=data)[0]
        self.assertEqual(len(rows(view['table'])), 1)
        self.assertFalse(view['issuesHidden'])
        self.assertIn('Verified entries are shown', view['issues'])
        self.assertFalse(view['catalogRetryHidden'])

    def test_superseded_catalog_request_cannot_replace_newer_verified_results(self):
        first = group(1); later = group(2, k=21)
        states = ui([first], hold=['/api/signal-library-summaries'], steps=[
            {'action': 'retry', 'element': 'signal-library-retry'},
            {'action': 'settle', 'index': 1, 'value': catalog_for(later)},
            {'action': 'settle', 'index': 0, 'value': catalog_for(first)}])
        self.assertTrue(states[-1]['aborted'][0])
        self.assertEqual(rows(states[-1]['table'])[0][0], later['name'])

    def test_cold_catalog_can_complete_after_thirty_five_seconds(self):
        states=ui([self.group], hold=['/api/signal-library-summaries'], steps=[
            {'action':'advance','ms':35000}, {'action':'settle','index':0}])
        self.assertEqual(states[1]['aborted'], [False])
        self.assertEqual(len(rows(states[-1]['table'])), 1)
        self.assertEqual(states[-1]['catalogStatus'], '1 researched Signal')
        self.assertTrue(states[-1]['catalogRetryHidden'])

    def test_unresponsive_catalog_times_out_without_inventing_cards(self):
        item=group(outputs=[])
        registry={'feature_count':1,'features':[{'id':item['id'],'reference':item['recipe'],
            'name':item['name'],'kind':'reusable_fx_recipe','transformations':item['transformations'],'signal_id':None}]}
        states=ui([], registry=registry, hold=['/api/signal-library-summaries'], steps=[
            {'action':'advance','ms':60000}])
        self.assertTrue(states[-1]['aborted'][-1])
        self.assertEqual(rows(states[-1]['table']), [])
        self.assertFalse(states[-1]['catalogRetryHidden'])
        self.assertTrue(all(r['method']=='GET' for r in states[-1]['requests']))

    def test_grouped_fx_summary_has_exact_five_cells_and_no_instrument_details(self):
        view = ui([self.group])[0]
        self.assertEqual(rows(view['table']), [['63-day log momentum · skip 5 days', 'Closing prices',
            'Log Level → Skip Recent Difference (k=63, s=5)', 'N/A', 'Research results available']])
        self.assertEqual(view['catalogStatus'], '1 researched Signal')
        summary = flatten(view['table']) + flatten(view['table'])
        for forbidden in ('AUDUSD', 'EURUSD', 'Twelve Data', 'log_USD_per_AUD', 'SIGNAL_', 'MATERIALIZATION_', '2024', '2 observations'):
            self.assertNotIn(forbidden, summary)
        self.assertEqual(len(view['requests']), 1)
        self.assertEqual(view['requests'][0]['url'], '/api/signal-library-summaries')

    def test_configuration_parameters_disambiguate_generic_names_without_extra_log(self):
        other = group(3, k=21)
        internal = group(4, internal=True)
        view = ui([self.group, other, internal])[0]
        self.assertEqual(len(rows(view['table'])), 3)
        self.assertIn('(k=63, s=5)', flatten(view['table']))
        self.assertIn('(k=21, s=5)', flatten(view['table']))
        self.assertEqual(rows(view['table'])[2][2], 'Downside Semivolatility (basis=log, w=21)')
        self.assertNotIn('Log Level', rows(view['table'])[2][2])

    def test_legacy_ces_summary_is_preserved(self):
        view = ui([self.group, self.legacy])[0]
        legacy = rows(view['table'])[1]
        self.assertIn(self.legacy['signal']['name'], legacy[0])
        self.assertNotIn(self.legacy['id'], legacy[0])
        self.assertIn('CES0500000003', legacy[1]); self.assertIn('FRED / ALFRED', legacy[1])
        self.assertEqual(legacy[4], 'Research results available')
        self.assertIn('2 observations', flatten(view['table']))

    def test_recipe_click_reveals_output_coverage_readiness_without_fetching_or_computing(self):
        view = ui([self.group], [{'action':'select','id':self.group['id']}])[-1]
        self.assertEqual(view['title'], '63-day log momentum · skip 5 days')
        body = flatten(view['detail'])
        for required in ('AUDUSD', 'EURUSD', 'Twelve Data', 'Historical replay: blocked', 'Live use: unresolved',
                         '2 valid', 'Stored instrument outputs', 'sample does not establish coverage',
                         'Feature lookback', 'forecast horizon separately measures future returns'):
            self.assertIn(required, body)
        self.assertEqual(len(view['requests']), 1)

    def test_explicit_output_fetches_exact_new_adapter_and_retains_group_heading(self):
        view = ui([self.group], [{'action':'select','id':self.group['id']},
                                 {'action':'output','id':sid(2),'mid':mid(2)}])[-1]
        self.assertEqual(view['title'], self.group['name'])
        self.assertEqual(view['requests'][-1]['url'], self.group['outputs'][1]['materializations'][0]['href'])
        self.assertIn('EURUSD · Stored output details', flatten(view['detail']))
        self.assertIn('Historical availability unknown', view['status'])
        self.assertIn('LINEAGE_', flatten(view['detail']))
        self.assertTrue(all(request['method'] == 'GET' for request in view['requests']))

    def test_same_instrument_multiple_materializations_keep_exact_output_selection(self):
        item = group()
        extra = materialization(10)
        extra['href'] = item['outputs'][0]['detail_href'] + '?materialization_id=' + extra['id']
        item['outputs'][0]['materializations'].append(extra)
        item['outputs'][0]['materialization_count'] = 2
        view = ui([item], [{'action':'select','id':item['id']},
                          {'action':'output','id':sid(),'mid':extra['id']}])[-1]
        self.assertEqual(view['requests'][-1]['url'], extra['href'])
        self.assertEqual(view['title'], item['name'])
        self.assertTrue(view['detailRetryHidden'])
        self.assertIn('Stored output details', flatten(view['detail']))

    def test_open_signal_event_uses_same_group_and_exact_materialization(self):
        view = ui([self.group], [{'action':'open','id':sid(1),'mid':mid(1)}])[-1]
        self.assertEqual(view['title'], self.group['name'])
        self.assertEqual(view['requests'][-1]['url'], self.group['outputs'][0]['materializations'][0]['href'])
        self.assertIn('Stored output details', flatten(view['detail']))

    def test_external_exact_link_waits_for_catalog_before_choosing_adapter(self):
        views = ui([self.group], [{'action':'open','id':sid(1),'mid':mid(1)}, {'action':'settle','index':0}],
                   hold=['/api/signal-library-summaries'])
        self.assertEqual(len(views[1]['requests']), 1)
        self.assertEqual(views[-1]['requests'][-1]['url'], self.group['outputs'][0]['materializations'][0]['href'])
        self.assertEqual(views[-1]['title'], self.group['name'])

    def test_ces_click_keeps_legacy_detail_endpoint_and_text(self):
        view = ui([self.legacy], [{'action':'select','id':self.legacy['id']}])[-1]
        self.assertEqual(view['requests'][-1]['url'], '/api/signal-library/' + self.legacy['id'])
        self.assertEqual(view['title'], self.legacy['signal']['name'])
        self.assertIn('Research results available', flatten(view['detail']))

    def test_stale_detail_cannot_replace_newer_recipe_selection(self):
        other = group(3, k=21)
        href = self.group['outputs'][0]['materializations'][0]['href']
        views = ui([self.group, other], [{'action':'open','id':sid(1),'mid':mid(1)},
                    {'action':'select','id':other['id']}, {'action':'settle','index':0}], hold=[href])
        self.assertEqual(views[-1]['title'], other['name'])
        self.assertIn('(k=21, s=5)', flatten(views[-1]['detail']))
        self.assertNotIn('AUDUSD · Stored output details', flatten(views[-1]['detail']))
        self.assertTrue(views[-1]['aborted'][1])

    def test_linked_research_is_not_untested_or_universally_validated(self):
        item = group(linked=True)
        view = ui([item], [{'action':'select','id':item['id']}, {'action':'output','id':sid(),'mid':mid()}])[-1]
        self.assertEqual(rows(view['table'])[0][4], 'Research results available')
        self.assertIn('RELATIONSHIP_abc', flatten(view['detail']))
        self.assertIn('TRIAL_RESULT_abc', flatten(view['detail']))
        self.assertIn('Scope, Target and horizon belong to each authoritative relationship', flatten(view['detail']))
        self.assertNotIn('Research results: not tested', flatten(view['detail']))
        self.assertIn('Research results available', view['status'])

    def test_multiple_historical_projections_of_one_relationship_preserve_all_links(self):
        item = group(linked=True)
        second = deepcopy(item['research']['relationships'][0])
        second['projection'] = ref('ENTRY_later')
        item['research']['relationships'].append(second)
        item['research']['relationship_count'] = 1
        view = ui([item], [{'action':'select','id':item['id']}])[-1]
        self.assertEqual(rows(view['table'])[0][4], 'Research results available')
        self.assertIn('ENTRY_abc', flatten(view['detail']))
        self.assertIn('ENTRY_later', flatten(view['detail']))
        self.assertTrue(view['catalogRetryHidden'])

    def test_distinct_relationship_references_count_separately_and_keep_both_links(self):
        for change in ('id', 'version', 'content_sha256'):
            with self.subTest(reference_field=change):
                item = group(linked=True)
                second = deepcopy(item['research']['relationships'][0])
                second['projection'] = ref('ENTRY_other')
                second['relationship'][change] = {'id':'RELATIONSHIP_other', 'version':'2.0.0',
                    'content_sha256':'a'*64}[change]
                item['research']['relationships'].append(second)
                item['research']['relationship_count'] = 2
                view = ui([item], [{'action':'select','id':item['id']}])[-1]
                self.assertEqual(rows(view['table'])[0][4], 'Research results available')
                self.assertIn('ENTRY_abc', flatten(view['detail']))
                self.assertIn('ENTRY_other', flatten(view['detail']))
                self.assertTrue(view['catalogRetryHidden'])

    def test_invalid_links_or_duplicate_recipe_ids_fail_closed(self):
        bad_research = group(); bad_research['research']['relationship_count'] = 2
        bad_href = group(); bad_href['outputs'][0]['detail_href'] = 'https://other.test/output'
        cases = [[bad_research], [bad_href], [self.group, self.group]]
        for entries in cases:
            with self.subTest(entries=entries):
                view = ui(entries)[0]
                self.assertEqual(rows(view['table']), [])
                self.assertFalse(view['catalogRetryHidden'])
                self.assertEqual(len(view['requests']), 1)

    def test_recorded_metrics_keep_scope_horizon_period_and_authority_separate(self):
        item = recorded_group()
        view = ui([item], [{'action': 'select', 'id': item['id']}])[-1]
        def sections(node):
            return ([node] if node['tag'] == 'section' else []) + [part for child in node['children'] for part in sections(child)]
        sections = sections(view['detail'])
        self.assertEqual(len(sections), 2)
        first, second = map(flatten, sections)
        for text in ['TS · 21-day forecast horizon', 'AUDUSD', 'Price Return', 'VALIDATED', 'primary effect', '0.25', '0.12',
                     'P1 · 2015-01-01 – 2022-01-01 (exclusive)', 'P2 · 2022-01-01 – 2026-09-01 (exclusive)',
                     'TRIAL_P1_a', 'TRIAL_P2_a', 'RSPEC_fixture']:
            self.assertIn(text, first)
        for text in ['CS · 63-day forecast horizon', 'FTMO_UNIVERSE', 'FAILED', '-0.08', 'Unavailable',
                     'P2 · 2022-01-01 – 2025-01-01 (exclusive)', 'TRIAL_P2_b', 'RSPEC_other']:
            self.assertIn(text, second)
        self.assertNotIn('FTMO_UNIVERSE', first)
        self.assertNotIn('TRIAL_P2_a', second)
        self.assertEqual(rows(view['table'])[0][4], 'Research results available')
        self.assertEqual(rows(view['table'])[0][3], 'N/A')
        self.assertNotIn('VALIDATED', flatten(view['table']))

    def test_new_result_event_refreshes_existing_selection_and_deduplicates_repeats(self):
        old, updated = group(), recorded_group()
        states = ui([old], [{'action': 'select', 'id': old['id']},
                           {'action': 'refresh', 'detail': refresh_event()},
                           {'action': 'refresh', 'detail': refresh_event()}],
                    catalogs=[catalog_for(old), catalog_for(updated)])
        final = states[-1]
        self.assertEqual(len(final['requests']), 2)
        self.assertEqual(final['title'], old['name'])
        self.assertIn('TRIAL_P2_a', flatten(final['detail']))
        self.assertEqual(rows(final['table'])[0][4], 'Research results available')
        self.assertTrue(all(call['method'] == 'GET' for call in final['requests']))

    def test_hidden_library_defers_and_coalesces_refresh_until_opened(self):
        item = recorded_group()
        states = ui([item], [
            {'action': 'refresh', 'detail': refresh_event(1)},
            {'action': 'refresh', 'detail': refresh_event(2)},
            {'action': 'navigate', 'hash': '#signals'},
            {'action': 'navigate', 'hash': '#experiment'},
            {'action': 'refresh', 'detail': refresh_event(3)},
            {'action': 'refresh', 'detail': refresh_event(4)},
            {'action': 'navigate', 'hash': '#signals'}], initial_hash='#experiment')
        self.assertEqual(len(states[0]['requests']), 0)
        self.assertEqual(len(states[2]['requests']), 0)
        self.assertEqual(len(states[3]['requests']), 1)
        self.assertEqual(len(states[6]['requests']), 1)
        self.assertEqual(len(states[7]['requests']), 2)
        self.assertIn('Research results available', flatten(states[-1]['table']))

    def test_historical_output_link_loads_catalog_from_experiment_page(self):
        item = group()
        final = ui([item], [{'action': 'open', 'id': sid(), 'mid': mid()}],
                   initial_hash='#experiment')[-1]
        self.assertEqual(len(final['requests']), 2)
        self.assertIn('Observations', flatten(final['detail']))
        self.assertFalse(final['detailHidden'])

    def test_refresh_coalesces_new_results_while_catalog_request_is_in_flight(self):
        item = recorded_group()
        states = ui([item], [{'action': 'refresh', 'detail': refresh_event(1)},
                            {'action': 'refresh', 'detail': refresh_event(2)},
                            {'action': 'settle', 'index': 0},
                            {'action': 'refresh', 'detail': refresh_event(3)},
                            {'action': 'refresh', 'detail': refresh_event(3)},
                            {'action': 'settle', 'index': 1}, {'action': 'settle', 'index': 2}],
                    hold=['/api/signal-library-summaries'])
        self.assertEqual(len(states[2]['requests']), 1)
        self.assertEqual(len(states[3]['requests']), 2)
        self.assertIn('Updating research results', states[3]['catalogStatus'])
        self.assertIn('last verified library', states[3]['catalogStatus'])
        self.assertEqual(len(states[5]['requests']), 2)
        self.assertEqual(len(states[-1]['requests']), 3)
        self.assertTrue(all(call['method'] == 'GET' for call in states[-1]['requests']))

    def test_failed_background_refresh_retains_verified_entries_and_discloses_staleness(self):
        item = group()
        final = ui([item], [{'action': 'select', 'id': item['id']}, {'action': 'refresh', 'detail': refresh_event()}],
                   catalogs=[catalog_for(item), None])[-1]
        self.assertEqual(len(rows(final['table'])), 1)
        self.assertEqual(final['title'], item['name'])
        self.assertIn('last verified library', final['catalogStatus'])
        self.assertFalse(final['catalogRetryHidden'])
        self.assertEqual(len(final['requests']), 2)

    def test_refresh_keeps_selected_historical_output_and_its_observations(self):
        old, updated = group(), recorded_group()
        final = ui([old], [{'action': 'open', 'id': sid(), 'mid': mid()}, {'action': 'refresh', 'detail': refresh_event()}],
                   catalogs=[catalog_for(old), catalog_for(updated)])[-1]
        self.assertEqual(final['title'], old['name'])
        body = flatten(final['detail'])
        self.assertIn('AUDUSD · Stored output details', body)
        self.assertIn('LINEAGE_', body)
        self.assertIn('TRIAL_P2_a', body)
        self.assertEqual(len(final['requests']), 3)
        self.assertEqual(final['requests'][1]['url'], old['outputs'][0]['materializations'][0]['href'])

    def test_disappearing_researched_selection_is_removed_after_refresh(self):
        item = recorded_group()
        final = ui([item], [{'action': 'select', 'id': item['id']},
                           {'action': 'refresh', 'detail': refresh_event()}],
                   catalogs=[catalog_for(item), catalog_for()])[-1]
        self.assertEqual(rows(final['table']), [])
        self.assertTrue(final['detailHidden'])
        self.assertEqual(final['detail']['children'], [])

    def test_removed_output_cannot_keep_stale_observations_after_refresh(self):
        item = recorded_group(); updated = deepcopy(item); updated['outputs'] = []
        final = ui([item], [{'action': 'open', 'id': sid(), 'mid': mid()},
                           {'action': 'refresh', 'detail': refresh_event()}],
                   catalogs=[catalog_for(item), catalog_for(updated)])[-1]
        self.assertIn('No stored outputs are catalogued', flatten(final['detail']))
        self.assertNotIn('Stored output details', flatten(final['detail']))
        self.assertNotIn('LINEAGE_', flatten(final['detail']))

    def test_all_recorded_outcomes_remain_available_without_validation_filter(self):
        for outcome in ('rejected', 'PRECHECK', 'UNRESOLVED', 'FAILED'):
            item = recorded_group()
            item['research']['relationships'][0].update(p1_status='rejected', p2_status=outcome)
            view = ui([item], [{'action': 'select', 'id': item['id']}])[-1]
            self.assertEqual(len(rows(view['table'])), 1)
            self.assertIn(outcome, flatten(view['detail']))

    def test_invalid_structured_results_or_refresh_event_fail_closed(self):
        item = recorded_group(); item['research']['relationships'][0]['results'][0]['period']['end_exclusive'] = '2010-01-01'
        view = ui([item])[0]
        self.assertFalse(view['catalogRetryHidden'])
        self.assertEqual(rows(view['table']), [])
        view = ui([group()], [{'action': 'refresh', 'detail': {'request_id': 'x', 'results': [{'id': 'bad'}]}},
                             {'action': 'refresh', 'detail': {'request_id': 'x', 'results': []}}])[-1]
        self.assertEqual(len(view['requests']), 1)

    def test_failed_output_and_catalog_show_retry_without_fallback_materialization(self):
        href = self.group['outputs'][0]['materializations'][0]['href']
        view = ui([self.group], [{'action':'open','id':sid(),'mid':mid()}], responses={href:None})[-1]
        self.assertFalse(view['detailRetryHidden'])
        self.assertEqual(view['detail']['children'], [])
        unavailable = ui([self.group], fail_catalog=True)[0]
        self.assertFalse(unavailable['catalogRetryHidden'])
        self.assertEqual(len(unavailable['requests']), 1)


if __name__ == '__main__':
    unittest.main()
