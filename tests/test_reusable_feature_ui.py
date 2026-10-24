"""Execute the shipped recipe selector against read-only API contract fixtures."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from urllib.parse import urlencode

PROJECT = Path(__file__).resolve().parents[1]


def ref(identifier, version='1.0.0'):
    return {'id': identifier, 'version': version,
            'content_sha256': hashlib.sha256(f'{identifier}@{version}'.encode()).hexdigest()}


def feature(index=0, kind='reusable_fx_recipe', basis_log=False):
    identifier = ('FEATURE_RECIPE_' if kind == 'reusable_fx_recipe' else 'FEATURE_') + f'{index:064x}'
    steps = [] if basis_log else [{'operator': ref('TR_BASE_log', '2.0.0'), 'label': 'Log Level', 'parameters': []}]
    steps.append({'operator': ref('TR_BASE_vol_downside' if basis_log else 'TR_BASE_momentum_skip_diff', '2.0.0'),
                  'label': 'Downside Semivolatility' if basis_log else 'Skip-Recent Difference',
                  'parameters': ([{'name': 'basis', 'value': {'type': 'token', 'value': 'log'}},
                                  {'name': 'w', 'value': {'type': 'integer', 'value': '21'}}]
                                 if basis_log else [{'name': 'k', 'value': {'type': 'integer', 'value': str(index + 1)}},
                                                    {'name': 's', 'value': {'type': 'integer', 'value': '5'}}])})
    return {'id': identifier, 'version': '1.0.0', 'reference': ref(identifier),
            'name': 'CES existing Feature' if kind == 'stored_feature' else 'Reusable FX recipe ' + str(index),
            'kind': kind, 'registration_state': 'registered', 'transformations': steps,
            'signal_id': 'SIGNAL_' + 'c' * 64 if kind == 'stored_feature' else None}


def readiness(stored=False):
    return {key: {'decision': ('ready' if stored else 'blocked') if key == 'retrospective_research'
                  else 'blocked' if key == 'historical_replay' else 'unresolved'}
            for key in ('retrospective_research', 'historical_replay', 'live_use')}


def materialization():
    return {'reference': ref('MATERIALIZATION_' + 'd' * 64), 'legacy_feature': ref('FEATURE_' + 'b' * 64),
            'signal_id': 'SIGNAL_' + 'e' * 64, 'row_count': 64,
            'status_counts': {'valid': 64, 'missing': 0, 'invalid': 0},
            'coverage': {'reference_start': '2024-01-02', 'reference_end': '2024-03-29',
                         'cutoff_start': '2026-10-09', 'cutoff_end': '2026-10-09'},
            'readiness_capabilities': readiness(True)}


def resolution(item, identifier='AUDUSD', members=('AUDUSD',), stored=('AUDUSD',)):
    blocked = item['kind'] == 'stored_feature'
    rows = [{'instrument_id': member, 'state': 'blocked' if blocked else 'materialized' if member in stored else 'missing',
             'reason': 'Application to Scope members requires an explicit research application rule.' if blocked else None,
             'materializations': [materialization()] if member in stored and not blocked else [],
             'readiness': readiness(member in stored and not blocked)} for member in members]
    return {'schema_version': '1.0.0', 'submission_compatible': not blocked, 'recipe': {key: item[key] for key in ('reference', 'name', 'kind')},
            'scope': {'id': identifier, 'version': '1.0.0', 'reference': ref(identifier),
                      'display_name': 'FTMO Universe' if identifier == 'FTMO_UNIVERSE' else identifier,
                      'membership_snapshot': ref('MEMBERSHIP_' + identifier)},
            'member_count': len(rows), 'members': rows,
            'summary': {state + '_member_count': sum(row['state'] == state for row in rows)
                        for state in ('materialized', 'missing', 'blocked')},
            'issues': [], 'selection_read_only': True, 'registration_state': 'registered'}


def path(item, scope='AUDUSD'):
    return '/api/feature-resolution?' + urlencode({'feature_id': item['id'], 'feature_version': item['version'],
                                                  'scope_id': scope, 'scope_version': '1.0.0'})


def choose_feature(item):
    return {'action': 'select', 'element': 'feature', 'value': {key: item[key] for key in ('id', 'version')}}


def choose_scope(identifier):
    return {'action': 'select', 'element': 'scope', 'value': {'id': identifier, 'version': '1.0.0'},
            'binding': scope_binding(identifier)}


def scope_binding(identifier):
    return {'id': identifier, 'version': '1.0.0', 'reference': ref(identifier),
            'definition_binding': ref(identifier), 'membership_snapshot': ref('MEMBERSHIP_' + identifier)}


def feature_catalog(items):
    return {'schema_version': '1.0.0', 'feature_count': len(items), 'features': items, 'issues': []}


def ui(items, steps=(), *, responses=None, hold=(), fail_catalog=False, catalog=None):
    node = shutil.which('node')
    if not node:
        raise unittest.SkipTest('Node.js required for actual Feature selector checks')
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
const ids = Object.fromEntries(["feature", "scope", "feature-status", "feature-retry", "feature-details-link",
  "scope-retry", "feature-coverage", "feature-coverage-title", "feature-coverage-status", "feature-coverage-body", "feature-coverage-retry"
].map(id => [id, new Element(id)]));
const requests = [], pending = [], signals = [], responses = input.responses, events = [], windowListeners = {};
const output = value => ({ok: value !== null, json: async () => value});
const context = {document: {getElementById: id => ids[id], createElement: tag => new Element(tag)},
  window: {setTimeout: () => 1, clearTimeout: () => {}, addEventListener: (name, fn) => windowListeners[name] = fn,
    dispatchEvent: event => { events.push(event); if (windowListeners[event.type]) windowListeners[event.type](event); }},
  AbortController, CustomEvent: class { constructor(type, data = {}) { this.type = type; this.detail = data.detail; } },
  fetch: async (url, options) => {
    requests.push({url, method: options.method}); signals.push(options.signal);
    if (input.hold.includes(url)) return new Promise((resolve, reject) => pending.push({url, resolve, reject}));
    if (url === "/api/feature-library") {
      if (input.fail_catalog) throw new Error("Unavailable");
      return output(input.catalog);
    }
    return output(responses[url] ?? null);
  }};
const flush = () => new Promise(resolve => setImmediate(resolve));
const snapshots = [];
function bindScope(binding) {
  ids.scope.dataset = binding ? {scopeReference: JSON.stringify(binding.definition_binding),
    membershipSnapshot: JSON.stringify(binding.membership_snapshot), scopeResolution: JSON.stringify(binding)} : {};
}
const read = node => ({tag:node.tag, text:node.textContent, value:node.value, disabled:node.disabled,
  label:node.label, title:node.title, children:node.children.map(read)});
function snapshot() {
  const item = ids.feature;
    snapshots.push(JSON.parse(JSON.stringify({disabled:item.disabled, value:item.value, title:item.title, dataset:item.dataset,
    options:item.children.map(read), validity:item.validity, busy:ids["feature-coverage"].attributes["aria-busy"],
    panelHidden:ids["feature-coverage"].hidden, status:ids["feature-status"].textContent,
    coverageStatus:ids["feature-coverage-status"].textContent, body:read(ids["feature-coverage-body"]),
    retryHidden:ids["feature-retry"].hidden, coverageRetryHidden:ids["feature-coverage-retry"].hidden,
    detailsHidden:ids["feature-details-link"].hidden, requests, events, aborted:signals.map(signal => signal.aborted)})));
}
(async () => {
  vm.runInNewContext(fs.readFileSync(input.script, "utf8"), context);
  await flush(); snapshot();
  for (const step of input.steps) {
    if (step.action === "select") {
      ids[step.element].value = JSON.stringify(step.value);
      if (step.element === "scope") bindScope(step.binding);
      ids[step.element].listeners.change();
    }
    else if (step.action === "retry") ids[step.element || "feature-coverage-retry"].listeners.click();
    else if (step.action === "scope-reset") { ids.scope.value = ""; context.window.dispatchEvent(new context.CustomEvent("scope-state-change")); }
    else if (step.action === "scope-binding") {
      bindScope(step.binding); context.window.dispatchEvent(new context.CustomEvent("scope-state-change"));
    }
    else if (step.action === "refresh") {
      if (step.catalog) input.catalog = step.catalog;
      if (step.hold) input.hold.push("/api/feature-library");
      context.window.dispatchEvent(new context.CustomEvent("experiment-catalog-refresh"));
    }
    else if (step.action === "stored-details") {
      const find = node => node.tag === "button" ? node : node.children.map(find).find(Boolean);
      find(ids["feature-coverage-body"]).listeners.click();
    }
    else if (step.action === "details") ids["feature-details-link"].listeners.click();
    else if (step.action === "respond") responses[step.path] = step.value;
    else if (step.action === "settle") {
      const request = pending[step.index];
      if (step.error) request.reject(new Error("Unavailable"));
      else request.resolve(output(step.value ?? (request.url === "/api/feature-library" ? input.catalog : responses[request.url])));
    }
    await flush(); snapshot();
  }
  process.stdout.write(JSON.stringify(snapshots));
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    payload = {'script': str(PROJECT / 'ui/features.js'), 'steps': list(steps), 'hold': list(hold),
               'fail_catalog': fail_catalog,
               'catalog': catalog if catalog is not None else feature_catalog(items),
               'responses': responses or {path(item): resolution(item) for item in items}}
    result = subprocess.run([node, '-e', harness], input=json.dumps(payload), text=True,
                            capture_output=True, check=True)
    return json.loads(result.stdout)


def flatten(node):
    return '\n'.join([node['text'], *(flatten(child) for child in node['children'])])


class ReusableFeatureUiTests(unittest.TestCase):
    def setUp(self):
        self.recipe = feature(62)
        self.legacy = feature(200, 'stored_feature')
        self.universe = resolution(self.recipe, 'FTMO_UNIVERSE', ('AUDUSD', 'USDJPY', 'EURGBP'))
        self.responses = {path(self.recipe): resolution(self.recipe),
                          path(self.recipe, 'FTMO_UNIVERSE'): self.universe}

    def test_180_configurations_plus_non_fx_without_instrument_bound_dropdown_entries(self):
        items = [feature(i) for i in range(180)] + [self.legacy]
        view = ui(items)[0]
        self.assertFalse(view['disabled'])
        self.assertEqual(len(view['options']), 182)
        self.assertTrue(all(not item['disabled'] for item in view['options'][1:]))
        self.assertNotIn('AUDUSD', ' '.join(item['text'] for item in view['options']))
        self.assertEqual(len({item['value'] for item in view['options'][1:]}), 181)
        self.assertEqual(view['options'][180]['text'], 'Reusable FX recipe 179 · Log Level → Skip-Recent Difference (k=180, s=5)')
        self.assertEqual(view['options'][181]['text'], 'CES existing Feature')
        self.assertEqual(view['requests'], [{'url': '/api/feature-library', 'method': 'GET'}])
        self.assertEqual(view['dataset']['catalogCount'], '181')
        self.assertIn('181 registered Features', view['status'])

    def test_internal_log_basis_is_rendered_without_invented_log_step(self):
        view = ui([feature(0, basis_log=True)])[0]
        self.assertEqual(view['options'][1]['text'], 'Reusable FX recipe 0 · Downside Semivolatility (basis=log, w=21)')
        self.assertNotIn('Log Level', view['options'][1]['text'])

    def test_currency_and_single_pair_recipe_names_remain_distinct(self):
        ts, cs = feature(0), feature(1)
        ts['name'] = 'TS Momentum · 63 weekdays'
        cs['name'] = 'Currency CS Momentum · 63 weekdays'
        cs['transformations'] = deepcopy(ts['transformations'])
        view = ui([ts, cs])[0]
        labels = [option['text'] for option in view['options'][1:]]
        self.assertNotEqual(*labels)
        for item, label in zip((ts, cs), labels):
            self.assertIn(item['name'], label)
            self.assertIn('Skip-Recent Difference', label)

    def test_refresh_preserves_only_the_exact_feature_reference(self):
        for case in ('unchanged', 'renamed', 'changed_hash', 'retired'):
            with self.subTest(case=case):
                item = deepcopy(self.recipe)
                if case == 'renamed':
                    item['name'] = 'Current registered name'
                if case == 'changed_hash':
                    item['reference']['content_sha256'] = 'f' * 64
                catalog = feature_catalog([] if case == 'retired' else [item])
                views = ui([self.recipe], [choose_feature(self.recipe), choose_scope('AUDUSD'),
                                          {'action': 'refresh', 'catalog': catalog, 'hold': True},
                                          {'action': 'settle', 'index': 0}])
                pending, current = views[-2:]
                self.assertEqual(pending['dataset'], {})
                self.assertEqual(pending['value'], '')
                self.assertEqual(pending['title'], '')
                self.assertEqual(pending['body']['children'], [])
                self.assertTrue(pending['panelHidden'])
                if case in ('unchanged', 'renamed'):
                    self.assertEqual(json.loads(current['dataset']['featureReference']), self.recipe['reference'])
                    self.assertIn('featureResolution', current['dataset'])
                else:
                    self.assertEqual(current['value'], '')
                    self.assertNotIn('featureReference', current['dataset'])
                    self.assertNotIn('featureResolution', current['dataset'])
                self.assertTrue(all(request['method'] == 'GET' for request in current['requests']))

    def test_scope_refresh_during_catalog_load_keeps_loading_state_without_old_bindings(self):
        views = ui([self.recipe], [choose_feature(self.recipe), choose_scope('AUDUSD'),
                                  {'action': 'refresh', 'hold': True},
                                  {'action': 'scope-binding', 'binding': None}])
        pending = views[-1]
        self.assertEqual(pending['dataset'], {})
        self.assertTrue(pending['disabled'])
        self.assertIn('Loading registered Features', pending['status'])
        self.assertEqual(pending['body']['children'], [])

    def test_retirement_refresh_cannot_be_undone_by_late_coverage_or_catalog(self):
        steps = [choose_scope('AUDUSD'), choose_feature(self.recipe),
                 {'action': 'refresh', 'catalog': feature_catalog([]), 'hold': True},
                 {'action': 'refresh', 'catalog': feature_catalog([])},
                 {'action': 'settle', 'index': 2, 'value': feature_catalog([])},
                 {'action': 'settle', 'index': 1, 'value': feature_catalog([self.recipe])},
                 {'action': 'settle', 'index': 0}]
        views = ui([self.recipe], steps, hold=[path(self.recipe)])
        latest = views[-3]
        self.assertEqual(latest['dataset'], {'catalogCount': '0'})
        self.assertEqual(latest['value'], '')
        self.assertEqual(latest['dataset'], views[-2]['dataset'])
        self.assertEqual(latest['dataset'], views[-1]['dataset'])
        self.assertEqual(latest['options'], views[-1]['options'])
        self.assertTrue(views[-1]['aborted'][1])
        self.assertTrue(views[-1]['aborted'][2])

    def test_same_scope_value_requires_current_verified_binding_after_refresh(self):
        changed = scope_binding('AUDUSD')
        changed['membership_snapshot'] = ref('MEMBERSHIP_NEW')
        new_response = resolution(self.recipe)
        new_response['scope']['membership_snapshot'] = changed['membership_snapshot']
        steps = [choose_feature(self.recipe), choose_scope('AUDUSD'),
                 {'action': 'scope-binding', 'binding': None},
                 {'action': 'respond', 'path': path(self.recipe), 'value': new_response},
                 {'action': 'scope-binding', 'binding': changed}]
        views = ui([self.recipe], steps)
        cleared, restored = views[3], views[-1]
        self.assertNotIn('featureResolution', cleared['dataset'])
        self.assertTrue(cleared['panelHidden'])
        self.assertEqual(len(cleared['requests']), 2)
        self.assertEqual(json.loads(restored['dataset']['featureResolution'])['scope']['membership_snapshot'],
                         changed['membership_snapshot'])
        self.assertEqual(len(restored['requests']), 3)

    def test_unverified_scope_and_stale_membership_resolution_fail_closed(self):
        unverified = choose_scope('AUDUSD'); unverified.pop('binding')
        view = ui([self.recipe], [choose_feature(self.recipe), unverified])[-1]
        self.assertEqual(len(view['requests']), 1)
        self.assertNotIn('featureResolution', view['dataset'])
        self.assertTrue(view['panelHidden'])
        changed = scope_binding('AUDUSD')
        changed['membership_snapshot'] = ref('MEMBERSHIP_NEW')
        view = ui([self.recipe], [choose_feature(self.recipe), choose_scope('AUDUSD'),
                                  {'action': 'scope-binding', 'binding': changed}])[-1]
        self.assertNotIn('featureResolution', view['dataset'])
        self.assertTrue(view['validity'])

    def test_registered_selection_before_scope_does_not_claim_readiness_or_request_preparation(self):
        view = ui([self.recipe], [choose_feature(self.recipe)])[-1]
        self.assertEqual(json.loads(view['dataset']['featureReference']), self.recipe['reference'])
        self.assertEqual(view['validity'], '')
        self.assertTrue(view['panelHidden'])
        self.assertIn('Registered recipe. Choose Scope', view['status'])
        self.assertEqual(len(view['requests']), 1)
        self.assertNotIn('featureResolution', view['dataset'])

    def test_same_feature_resolves_instrument_and_universe_without_changing_definition(self):
        views = ui([self.recipe], [choose_feature(self.recipe), choose_scope('AUDUSD'), choose_scope('FTMO_UNIVERSE')],
                   responses=self.responses)
        instrument, universe = views[-2:]
        self.assertEqual(instrument['dataset']['featureReference'], universe['dataset']['featureReference'])
        self.assertEqual(instrument['dataset']['experimentFeature'], universe['dataset']['experimentFeature'])
        self.assertIn('1 of 1', instrument['coverageStatus'])
        self.assertIn('1 of 3', universe['coverageStatus'])
        self.assertIn('2 missing', universe['coverageStatus'])
        body = flatten(universe['body'])
        for text in ['AUDUSD', 'USDJPY', 'EURGBP', '2024-01-02', '2024-03-29', '64 scheduled observations',
                     'Not materialized', 'Historical replay: blocked', 'Live use: unresolved']:
            self.assertIn(text, body)
        self.assertNotIn('full history', body.lower())
        self.assertTrue(all(request['method'] == 'GET' for request in universe['requests']))
        self.assertEqual([item['url'] for item in universe['requests'][1:]], [path(self.recipe), path(self.recipe, 'FTMO_UNIVERSE')])

    def test_stored_details_link_opens_the_exact_materialization_from_coverage(self):
        view = ui([self.recipe], [choose_feature(self.recipe), choose_scope('AUDUSD'), {'action': 'stored-details'}])[-1]
        self.assertEqual([event for event in view['events'] if event['type']=='open-signal'], [{'type': 'open-signal', 'detail': {
            'signal_id': materialization()['signal_id'], 'materialization_id': materialization()['reference']['id']}}])

    def test_excluded_stale_records_do_not_override_usable_member_status(self):
        response = resolution(self.recipe)
        response['issues'] = [{'code': 'STALE_SOURCE_SNAPSHOT'}]
        view = ui([self.recipe], [choose_feature(self.recipe), choose_scope('AUDUSD')],
                  responses={path(self.recipe): response})[-1]
        self.assertIn('1 of 1', view['coverageStatus'])
        self.assertIn('0 blocked', view['coverageStatus'])
        self.assertIn('Unusable records are excluded', view['coverageStatus'])
        self.assertNotIn('members remain blocked', view['coverageStatus'])

    def test_no_materialization_keeps_registered_recipe_selectable_with_missing_status(self):
        response = resolution(self.recipe, stored=())
        view = ui([self.recipe], [choose_scope('AUDUSD'), choose_feature(self.recipe)],
                  responses={path(self.recipe): response})[-1]
        self.assertFalse(view['disabled'])
        self.assertFalse(view['options'][1]['disabled'])
        self.assertEqual(view['validity'], '')
        self.assertIn('Registered recipe. 0/1', view['status'])
        self.assertIn('Not materialized', flatten(view['body']))

    def test_pending_or_changed_scope_clears_old_coverage_and_ignores_late_response(self):
        views = ui([self.recipe], [choose_feature(self.recipe), choose_scope('FTMO_UNIVERSE'),
                                  choose_scope('AUDUSD'), {'action': 'settle', 'index': 0}],
                   responses=self.responses, hold=[path(self.recipe, 'FTMO_UNIVERSE')])
        self.assertNotIn('featureResolution', views[2]['dataset'])
        self.assertEqual(views[2]['body']['children'], [])
        self.assertTrue(views[-1]['aborted'][1])
        self.assertEqual(views[-2]['dataset'], views[-1]['dataset'])
        self.assertEqual(json.loads(views[-1]['dataset']['featureResolution'])['scope']['id'], 'AUDUSD')

    def test_different_feature_rejects_late_coverage_and_never_changes_definition(self):
        other = feature(3, basis_log=True)
        responses = {path(self.recipe): resolution(self.recipe), path(other): resolution(other, stored=())}
        views = ui([self.recipe, other], [choose_scope('AUDUSD'), choose_feature(self.recipe), choose_feature(other),
                                        {'action': 'settle', 'index': 0}], responses=responses, hold=[path(self.recipe)])
        self.assertEqual(json.loads(views[-1]['dataset']['featureReference']), other['reference'])
        self.assertIn('0/1', views[-1]['status'])

    def test_scope_catalog_retry_clears_previous_feature_coverage_after_programmatic_reset(self):
        view = ui([self.recipe], [choose_feature(self.recipe), choose_scope('AUDUSD'), {'action': 'scope-reset'}])[-1]
        self.assertNotIn('featureResolution', view['dataset'])
        self.assertTrue(view['panelHidden'])
        self.assertIn('Choose Scope', view['status'])
        self.assertEqual(len(view['requests']), 2)

    def test_failed_resolution_clears_prior_result_and_retry_uses_same_choice(self):
        responses = dict(self.responses); responses[path(self.recipe, 'FTMO_UNIVERSE')] = None
        views = ui([self.recipe], [choose_feature(self.recipe), choose_scope('AUDUSD'), choose_scope('FTMO_UNIVERSE'),
                                  {'action': 'respond', 'path': path(self.recipe, 'FTMO_UNIVERSE'), 'value': self.universe},
                                  {'action': 'retry'}], responses=responses)
        failed = views[3]
        self.assertNotIn('featureResolution', failed['dataset'])
        self.assertTrue(failed['validity'])
        self.assertFalse(failed['coverageRetryHidden'])
        self.assertEqual(views[-1]['validity'], '')
        self.assertEqual(json.loads(views[-1]['dataset']['featureResolution'])['scope']['id'], 'FTMO_UNIVERSE')

    def test_changed_recipe_scope_counts_or_non_read_only_resolution_fail_closed(self):
        mutations = [lambda v: v['recipe'].update(reference=ref('OTHER_RECIPE')),
                     lambda v: v['scope'].update(version='2.0.0'),
                     lambda v: v.update(member_count=2),
                     lambda v: v['summary'].update(materialized_member_count=2),
                     lambda v: v.update(selection_read_only=False),
                     lambda v: v['members'][0]['materializations'][0].update(row_count=65)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                response = resolution(self.recipe); mutate(response)
                view = ui([self.recipe], [choose_feature(self.recipe), choose_scope('AUDUSD')],
                          responses={path(self.recipe): response})[-1]
                self.assertNotIn('featureResolution', view['dataset'])
                self.assertTrue(view['validity'])
                self.assertFalse(view['coverageRetryHidden'])

    def test_existing_non_fx_source_observations_are_separate_from_scope_readiness(self):
        response = resolution(self.legacy)
        source = materialization(); source['readiness_capabilities'] = {}; source['row_count'] = 187
        source['status_counts'] = {'valid': 187, 'missing': 0, 'invalid': 0}
        response.update(source_materializations=[source], source_application_note='Scope application requires an explicit rule.')
        view = ui([self.legacy], [choose_feature(self.legacy), choose_scope('AUDUSD'), {'action': 'details'}],
                  responses={path(self.legacy): response})[-1]
        self.assertFalse(view['disabled'])
        self.assertFalse(view['detailsHidden'])
        self.assertIn('Existing source observations', flatten(view['body']))
        self.assertIn('187 observations', flatten(view['body']))
        self.assertIn('0 of 1', view['coverageStatus'])
        self.assertIn('1 blocked', view['coverageStatus'])
        self.assertEqual([event for event in view['events'] if event['type']=='open-signal'], [{'type': 'open-signal', 'detail': {'signal_id': self.legacy['signal_id']}}])

    def test_empty_invalid_or_unavailable_catalog_has_no_mock_or_signal_fallback(self):
        for kwargs in [{}, {'fail_catalog': True}, {'catalog': {'schema_version': '1.0.0', 'features': [],
                                                               'feature_count': 1, 'issues': []}}]:
            with self.subTest(kwargs=kwargs):
                view = ui([], **kwargs)[0]
                self.assertTrue(view['disabled'])
                self.assertEqual(view['dataset'], {} if kwargs else {'catalogCount': '0'})
                self.assertEqual(len(view['options']), 1)
                self.assertEqual(view['requests'], [{'url': '/api/feature-library', 'method': 'GET'}])

    def test_signal_library_cannot_overwrite_recipe_selector_and_markup_preserves_inputs(self):
        signal = (PROJECT / 'ui/signals.js').read_text()
        self.assertNotIn('populateFeatures', signal)
        self.assertNotIn('$("feature")', signal)
        self.assertIn('window.addEventListener("open-signal"', signal)
        self.assertIn('request("/api/signal-library-summaries"', signal)
        html = (PROJECT / 'ui/index.html').read_text()
        self.assertIn('<script src="/features.js" defer></script>', html)
        self.assertIn('id="feature-coverage"', html)
        for identifier in ['feature', 'target', 'scope', 'expected-direction']:
            self.assertIn(f'<select id="{identifier}"', html)
        self.assertNotIn('id="experiment-submit"', html)
        self.assertIn('id="experiment-contract"', html)


if __name__ == '__main__':
    unittest.main()
