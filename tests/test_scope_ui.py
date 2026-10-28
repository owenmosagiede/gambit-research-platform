"""Scope UI binding checks execute the shipped script with registry API fixtures."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from urllib.parse import quote


PROJECT = Path(__file__).resolve().parents[1]


def ref(identifier, version='1.0.0'):
    return {'id': identifier, 'version': version,
            'content_sha256': hashlib.sha256(f'{identifier}@{version}'.encode()).hexdigest()}


def entry(identifier, members, kind='universe', version='1.0.0', name=None):
    """Interface fixtures are not registrations or generated scientific outputs."""
    return {'id': identifier, 'version': version, 'kind': kind,
            'display_name': name or identifier, 'reference': ref(identifier, version),
            'member_count': len(members), 'members': members,
            'membership_snapshot': ref('MEMBERSHIP_' + identifier, version),
            'readiness': {'registered_member_count': len(members),
                          'stored_price_member_count': len(members),
                          'retrospective_ready_member_count': len(members),
                          'historical_replay_ready_member_count': 0,
                          'live_ready_member_count': 0}}


def detail(item):
    value = deepcopy(item)
    value.update(experiment_scope={'id': item['id'], 'version': item['version']},
                 definition_binding=item['reference'],
                 dependency={'requirement': 'required', 'bindings': [
                     {'role': 'membership', 'artifact': item['membership_snapshot']},
                     {'role': 'selection_policy', 'artifact': ref('SELECTION_POLICY')}]})
    return value


def path(item):
    return '/api/scope-library/' + quote(item['id'], safe='') + '?version=' + quote(item['version'], safe='')


def select(item):
    return {'action': 'select', 'value': {'id': item['id'], 'version': item['version']}}


def catalog(items):
    return {'schema_version': '1.0.0', 'scope_count': len(items), 'scopes': items, 'issues': []}


def catalog_counts(items):
    return {'catalogCount': str(len(items)),
            'universeCount': str(sum(item['kind'] == 'universe' for item in items)),
            'instrumentCount': str(sum(item['kind'] == 'instrument' for item in items))}


def ui(items, steps=(), *, responses=None, hold=(), fail_catalog=False, catalog=None):
    node = shutil.which('node')
    if not node:
        raise unittest.SkipTest('Node.js required for actual Scope selector checks')
    harness = r'''
const fs = require("fs"), vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.listeners = {};
    this.disabled = false; this.hidden = false; this.value = ""; this.textContent = ""; this.attributes = {}; this.validity = ""; }
  replaceChildren(...items) { this.children = items; }
  append(...items) { this.children.push(...items); }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setAttribute(name, value) { this.attributes[name] = value; }
  setCustomValidity(message) { this.validity = message; }
}
const ids = Object.fromEntries(["scope", "scope-status", "scope-retry"].map(id => [id, new Element(id)]));
const paths = [], pending = [], signals = [], events = [], responses = input.responses;
const windowListeners = {}; let holdCatalog = false;
const output = value => ({ok: value !== null, json: async () => value});
const context = {document: {getElementById: id => ids[id], createElement: tag => new Element(tag)},
  window: {setTimeout: () => 1, clearTimeout: () => {},
    addEventListener: (name, callback) => windowListeners[name] = callback,
    dispatchEvent: event => { events.push({type:event.type, value:ids.scope.value}); windowListeners[event.type]?.(event); }},
  CustomEvent: class { constructor(type) { this.type = type; } }, AbortController,
  fetch: async (url, options) => {
    paths.push(url); signals.push(options.signal);
    if (url === "/api/scope-library") {
      if (holdCatalog) { holdCatalog = false; return new Promise((resolve, reject) => pending.push({url, resolve, reject})); }
      if (input.fail_catalog) throw new Error("Unavailable");
      return output(input.catalog);
    }
    if (input.hold.includes(url)) return new Promise((resolve, reject) => pending.push({url, resolve, reject}));
    return output(responses[url] ?? null);
  }};
const flush = () => new Promise(resolve => setImmediate(resolve));
const snapshots = [];
function snapshot() {
  const scope = ids.scope;
  const read = node => ({tag:node.tag, text:node.textContent, value:node.value, disabled:node.disabled,
    label:node.label, children:node.children.map(read)});
  snapshots.push(JSON.parse(JSON.stringify({disabled:scope.disabled, value:scope.value, dataset:scope.dataset,
    options:scope.children.map(read), validity:scope.validity, busy:scope.attributes["aria-busy"],
    status:ids["scope-status"].textContent, retryHidden:ids["scope-retry"].hidden,
    retryText:ids["scope-retry"].textContent, paths, events, aborted:signals.map(signal => signal.aborted)})));
}
(async () => {
  vm.runInNewContext(fs.readFileSync(input.script, "utf8"), context);
  // The page coordinator activates catalog reads after queue startup.
  windowListeners["experiment-catalog-refresh"]();
  await flush(); snapshot();
  for (const step of input.steps) {
    if (step.action === "select") { ids.scope.value = JSON.stringify(step.value); ids.scope.listeners.change(); }
    else if (step.action === "retry") ids["scope-retry"].listeners.click();
    else if (step.action === "respond") responses[step.path] = step.value;
    else if (step.action === "catalog") input.catalog = step.value;
    else if (step.action === "hold-catalog") holdCatalog = true;
    else if (step.action === "refresh") windowListeners["experiment-catalog-refresh"]();
    else if (step.action === "settle") {
      const request = pending[step.index];
      if (step.error) request.reject(new Error("Unavailable"));
      else request.resolve(output(step.value ?? responses[request.url]));
    }
    await flush(); snapshot();
  }
  process.stdout.write(JSON.stringify(snapshots));
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    payload = {'script': str(PROJECT / 'ui/scopes.js'), 'steps': list(steps), 'hold': list(hold),
               'fail_catalog': fail_catalog,
               'catalog': catalog if catalog is not None else {
                   'schema_version': '1.0.0', 'scope_count': len(items), 'scopes': items, 'issues': []},
               'responses': responses if responses is not None else {path(item): detail(item) for item in items}}
    result = subprocess.run([node, '-e', harness], input=json.dumps(payload), text=True,
                            capture_output=True, check=True)
    return json.loads(result.stdout)


class ScopeUiTests(unittest.TestCase):
    def setUp(self):
        self.instrument = entry('AUDUSD', ['AUDUSD'], 'instrument')
        self.universe = entry('FTMO_UNIVERSE', ['AUDUSD', 'EURUSD'], name='FTMO Universe')
        self.items = [self.instrument, self.universe]

    def test_registry_groups_and_registered_counts_without_frontend_universe_list(self):
        instruments = [entry(f'PAIR_{index}', [f'PAIR_{index}'], 'instrument') for index in range(43)]
        universes = [entry(f'NEW_GROUP_{index}', [item['id'] for item in instruments[:index + 1]],
                           name=f'Registered Group {index}') for index in range(18)]
        view = ui(instruments + universes)[0]
        self.assertFalse(view['disabled'])
        self.assertEqual(view['dataset'], catalog_counts(instruments + universes))
        self.assertEqual([group['label'] for group in view['options'][1:]], ['Instruments', 'Universes'])
        self.assertEqual([len(group['children']) for group in view['options'][1:]], [43, 18])
        self.assertEqual(view['options'][2]['children'][17]['text'], 'Registered Group 17 · 18 pairs')
        self.assertEqual(json.loads(view['options'][1]['children'][0]['value']), {'id': 'PAIR_0', 'version': '1.0.0'})

    def test_instrument_selection_resolves_exact_version_and_preserves_contract(self):
        view = ui(self.items, [select(self.instrument)])[-1]
        self.assertEqual(view['paths'][-1], '/api/scope-library/AUDUSD?version=1.0.0')
        self.assertEqual(json.loads(view['dataset']['experimentScope']), {'id': 'AUDUSD', 'version': '1.0.0'})
        self.assertEqual(json.loads(view['dataset']['resolvedMembers']), ['AUDUSD'])
        self.assertEqual(json.loads(view['dataset']['scopeReference']), self.instrument['reference'])
        self.assertEqual(json.loads(view['dataset']['membershipSnapshot']), self.instrument['membership_snapshot'])
        self.assertEqual(json.loads(view['dataset']['scopeDependency']), detail(self.instrument)['dependency'])
        self.assertEqual(json.loads(view['dataset']['scopeResolution']), detail(self.instrument))
        self.assertEqual(view['validity'], '')
        self.assertEqual(view['busy'], 'false')

    def test_universe_resolves_registry_version_instead_of_current_or_inferred_members(self):
        universe = entry('FX_NEW_GROUP', ['EURUSD', 'AUDUSD'], version='2.1.0', name='New group')
        view = ui([universe], [select(universe)])[-1]
        self.assertEqual(view['paths'][-1], '/api/scope-library/FX_NEW_GROUP?version=2.1.0')
        self.assertEqual(json.loads(view['dataset']['resolvedMembers']), ['EURUSD', 'AUDUSD'])
        self.assertEqual(json.loads(view['dataset']['experimentScope']), {'id': 'FX_NEW_GROUP', 'version': '2.1.0'})
        self.assertIn('Fixed research group', view['status'])
        self.assertIn('broker eligibility is unverified', view['status'])

    def test_missing_data_changes_readiness_text_without_dropping_members(self):
        self.universe['readiness'].update(stored_price_member_count=1, retrospective_ready_member_count=0)
        view = ui(self.items, [select(self.universe)])[-1]
        self.assertEqual(json.loads(view['dataset']['resolvedMembers']), ['AUDUSD', 'EURUSD'])
        self.assertIn('1 of 2 members have stored prices', view['status'])
        self.assertIn('Provisional retrospective research: 0/2', view['status'])
        self.assertIn('Historical replay: 0/2', view['status'])

    def test_pending_selection_clears_prior_binding_and_prevents_unresolved_submission(self):
        views = ui(self.items, [select(self.instrument), select(self.universe)], hold=[path(self.universe)])
        self.assertTrue(views[1]['dataset'])
        self.assertEqual(views[2]['dataset'], catalog_counts(self.items))
        self.assertTrue(views[2]['validity'])
        self.assertEqual(views[2]['busy'], 'true')

    def test_older_resolution_cannot_replace_newer_selection(self):
        views = ui(self.items, [select(self.universe), select(self.instrument),
                               {'action': 'settle', 'index': 0}], hold=[path(self.universe)])
        self.assertEqual(json.loads(views[-1]['dataset']['experimentScope'])['id'], 'AUDUSD')
        self.assertTrue(views[-1]['aborted'][1])
        self.assertEqual(views[-1]['status'], views[-2]['status'])

    def test_error_clears_binding_and_retry_resolves_same_version(self):
        responses = {path(self.instrument): detail(self.instrument), path(self.universe): None}
        views = ui(self.items, [select(self.instrument), select(self.universe),
                               {'action': 'respond', 'path': path(self.universe), 'value': detail(self.universe)},
                               {'action': 'retry'}], responses=responses)
        self.assertEqual(views[2]['dataset'], catalog_counts(self.items))
        self.assertTrue(views[2]['validity'])
        self.assertFalse(views[2]['retryHidden'])
        self.assertEqual(views[-1]['paths'][-2:], [path(self.universe), path(self.universe)])
        self.assertEqual(json.loads(views[-1]['dataset']['resolvedMembers']), self.universe['members'])
        self.assertTrue(views[-1]['retryHidden'])

    def test_changed_version_membership_or_binding_is_rejected(self):
        for field, mutation in [
                ('version', '9.0.0'), ('members', ['AUDUSD', 'GBPUSD']),
                ('member_count', 1), ('membership_snapshot', ref('OTHER_SNAPSHOT')),
                ('definition_binding', ref('OTHER_DEFINITION')),
                ('experiment_scope', {'id': 'OTHER', 'version': '1.0.0'}),
                ('dependency', {'requirement': 'required', 'bindings': []}),
                ('dependency', {'requirement': 'required', 'bindings': [
                    {'role': 'membership', 'artifact': self.universe['membership_snapshot']},
                    {'role': 'selection_policy', 'artifact': ref('SELECTION_POLICY')},
                    {'role': 'selection_policy', 'artifact': ref('OTHER_POLICY')}]})]:
            with self.subTest(field=field):
                response = detail(self.universe)
                response[field] = mutation
                view = ui(self.items, [select(self.universe)], responses={path(self.universe): response})[-1]
                self.assertEqual(view['dataset'], catalog_counts(self.items))
                self.assertTrue(view['validity'])
                self.assertFalse(view['retryHidden'])

    def test_empty_or_unavailable_catalog_has_no_mock_fallback(self):
        for kwargs in [{}, {'fail_catalog': True}]:
            with self.subTest(kwargs=kwargs):
                view = ui([], **kwargs)[0]
                self.assertTrue(view['disabled'])
                self.assertEqual(view['dataset'], {} if kwargs.get('fail_catalog') else catalog_counts([]))
                self.assertEqual(len(view['options']), 1)
                self.assertTrue(view['options'][0]['disabled'])

    def test_invalid_catalog_counts_duplicate_members_or_versions_fail_closed(self):
        bad_member = deepcopy(self.universe)
        bad_member['members'] = ['AUDUSD', 'AUDUSD']
        bad_ready = deepcopy(self.universe)
        bad_ready['readiness']['stored_price_member_count'] = 3
        for items in [[bad_member], [bad_ready], [self.universe, self.universe]]:
            with self.subTest(items=items):
                view = ui(items)[0]
                self.assertTrue(view['disabled'])
                self.assertEqual(view['dataset'], {})
                self.assertFalse(view['retryHidden'])

    def test_unknown_selection_clears_saved_binding(self):
        view = ui(self.items, [select(self.instrument),
                              {'action': 'select', 'value': {'id': 'UNREGISTERED', 'version': '1.0.0'}}])[-1]
        self.assertEqual(view['dataset'], catalog_counts(self.items))
        self.assertTrue(view['validity'])
        self.assertEqual(len(view['paths']), 2)

    def test_catalog_resets_notify_dependent_selectors_without_changing_scope_contract(self):
        for kwargs in [{}, {'fail_catalog': True}]:
            with self.subTest(kwargs=kwargs):
                view = ui(self.items, **kwargs)[0]
                self.assertTrue(view['events'])
                self.assertTrue(all(event == {'type': 'scope-state-change', 'value': ''} for event in view['events']))
                self.assertEqual(view['dataset'], {} if kwargs.get('fail_catalog') else catalog_counts(self.items))

    def test_refresh_replaces_retired_universes_with_live_currency_catalog(self):
        updated = [entry('FX_CCY_VS_' + quote, ['EUR' + quote, 'JPY' + quote],
                         name=quote + ' Pairs') for quote in ('USD', 'CAD', 'AUD')]
        for item in updated:
            item['reference_currency'] = item['id'].removeprefix('FX_CCY_VS_')
        view = ui(self.items, [select(self.universe), {'action': 'catalog', 'value': catalog(updated)},
                              {'action': 'refresh'}])[-1]
        self.assertEqual(view['dataset'], catalog_counts(updated))
        self.assertEqual(view['value'], '')
        self.assertTrue(view['validity'])
        self.assertIn('3 universes · 0 individual pairs', view['status'])
        self.assertEqual(len(view['options'][1]['children']), 3)
        self.assertEqual(view['options'][1]['children'][0]['text'], 'USD Pairs · 2 currencies vs USD')
        self.assertNotIn('FTMO', json.dumps(view['options']))

    def test_refresh_preserves_and_resolves_only_exact_unchanged_selection(self):
        view = ui(self.items, [select(self.instrument), {'action': 'refresh'}])[-1]
        self.assertEqual(json.loads(view['value']), {'id': 'AUDUSD', 'version': '1.0.0'})
        self.assertEqual(view['paths'], ['/api/scope-library', path(self.instrument),
                                         '/api/scope-library', path(self.instrument)])
        self.assertEqual(json.loads(view['dataset']['scopeResolution']), detail(self.instrument))
        self.assertEqual(view['validity'], '')

    def test_refresh_clears_reused_identity_with_changed_immutable_binding(self):
        for binding in ('reference', 'membership_snapshot'):
            with self.subTest(binding=binding):
                changed = deepcopy(self.instrument)
                changed[binding]['content_sha256'] = 'f' * 64
                view = ui(self.items, [select(self.instrument),
                                      {'action': 'catalog', 'value': catalog([changed])},
                                      {'action': 'refresh'}])[-1]
                self.assertEqual(view['value'], '')
                self.assertEqual(view['dataset'], catalog_counts([changed]))
                self.assertTrue(view['validity'])

    def test_refresh_keeps_registry_issue_notice_after_preserved_selection_resolves(self):
        updated = catalog(self.items)
        updated['issues'] = [{'scope_id': 'UNAVAILABLE', 'reason': 'Stored scope could not be verified'}]
        view = ui(self.items, [select(self.instrument), {'action': 'catalog', 'value': updated},
                              {'action': 'refresh'}])[-1]
        self.assertEqual(json.loads(view['dataset']['experimentScope'])['id'], 'AUDUSD')
        self.assertIn('Some registry records are unavailable', view['status'])
        self.assertFalse(view['retryHidden'])
        self.assertEqual(view['retryText'], 'Retry loading scopes')

    def test_refresh_invalidates_late_resolution_from_retired_selection(self):
        views = ui(self.items, [select(self.universe),
                               {'action': 'catalog', 'value': catalog([self.instrument])},
                               {'action': 'refresh'}, {'action': 'settle', 'index': 0}],
                   hold=[path(self.universe)])
        self.assertEqual(views[-1]['dataset'], catalog_counts([self.instrument]))
        self.assertEqual(views[-1]['value'], '')
        self.assertEqual(views[-1]['status'], views[-2]['status'])
        self.assertTrue(views[-1]['aborted'][1])

    def test_late_catalog_cannot_overwrite_new_refresh_or_drop_valid_choice(self):
        views = ui(self.items, [select(self.instrument), {'action': 'hold-catalog'},
                               {'action': 'refresh'},
                               {'action': 'catalog', 'value': catalog([self.instrument])},
                               {'action': 'refresh'},
                               {'action': 'settle', 'index': 0, 'value': catalog(self.items)}])
        self.assertEqual(json.loads(views[-1]['dataset']['experimentScope'])['id'], 'AUDUSD')
        self.assertEqual(views[-1]['dataset']['catalogCount'], '1')
        self.assertEqual(views[-1]['options'], views[-2]['options'])

    def test_failed_refresh_clears_old_options_and_resolved_bindings(self):
        view = ui(self.items, [select(self.instrument), {'action': 'catalog', 'value': None},
                              {'action': 'refresh'}])[-1]
        self.assertEqual(view['dataset'], {})
        self.assertTrue(view['disabled'])
        self.assertTrue(view['validity'])
        self.assertEqual(len(view['options']), 1)
        self.assertFalse(view['retryHidden'])

    def test_markup_uses_existing_styles_and_keeps_four_inputs(self):
        from html.parser import HTMLParser
        class Parser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.group_depth = 0
                self.selects = []
                self.scripts = []
            def handle_starttag(self, tag, attrs):
                attributes = dict(attrs)
                if tag == 'div':
                    if self.group_depth:
                        self.group_depth += 1
                    elif 'experiment-contract-inputs' in attributes.get('class', '').split():
                        self.group_depth = 1
                        self.contract_role = attributes.get('role')
                if tag == 'select' and self.group_depth:
                    self.selects.append(attributes)
                if tag == 'script':
                    self.scripts.append(attributes.get('src'))
            def handle_endtag(self, tag):
                if tag == 'div' and self.group_depth:
                    self.group_depth -= 1
        parser = Parser()
        source = (PROJECT / 'ui/index.html').read_text()
        parser.feed(source)
        self.assertEqual(parser.contract_role, 'group')
        self.assertEqual([item['id'] for item in parser.selects],
                         ['feature', 'target', 'scope', 'expected-direction'])
        self.assertEqual(parser.selects[2]['aria-describedby'], 'scope-status')
        self.assertIn('/scopes.js', parser.scripts)
        self.assertIn('id="scope-status" class="field-note"', source)
        self.assertIn('id="scope-retry" class="text-button"', source)
        self.assertNotIn('mock-scope-', source)
        self.assertNotIn('id="experiment-submit"', source)


if __name__ == '__main__':
    unittest.main()
