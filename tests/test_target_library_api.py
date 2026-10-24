"""Target API and existing selector acceptance over production-published fixtures."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from api import target_library
from data.targets.service import materialize
from data.targets.store import TargetStore
from test_signal_library_api import running, request
from target_persistence_fixture import persistence_fixture

PROJECT = Path(__file__).resolve().parents[1]


def inventory(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file()}


def selector(catalog=None, *, fail=False, selection=None, steps=(), history=False):
    """Execute the actual UI script with a minimal native-select DOM harness."""
    node = shutil.which('node')
    if not node:
        raise unittest.SkipTest('Node.js required for actual Target selector behavior check')
    script = r'''
const fs = require("fs"), vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.listeners = {}; this.disabled = false; this.hidden = false; this.value = ""; this.textContent = ""; }
  replaceChildren(...items) { this.children = items; }
  append(...items) { this.children.push(...items); }
  addEventListener(name, action) { this.listeners[name] = action; }
}
const ids = Object.fromEntries(["target", "target-status", "target-retry"].map(id => [id, new Element(id)]));
const listeners = {}, requests = [], pending = [], snapshots = [], signals = [];
let hold = false;
const output = value => ({ok:value !== null, json:async () => value});
const context = {document: {getElementById: id => ids[id], createElement: tag => new Element(tag)},
  window: {setTimeout: () => 1, clearTimeout: () => {}, addEventListener: (name, fn) => listeners[name] = fn,
    dispatchEvent: event => listeners[event.type]?.(event)}, AbortController,
  CustomEvent: class { constructor(type) { this.type = type; } },
  fetch: async (url, options) => {
    requests.push({url,method:options.method}); signals.push(options.signal);
    if (url !== "/api/target-library" || input.fail) throw new Error("Unavailable");
    if (hold) return new Promise((resolve, reject) => pending.push({resolve,reject}));
    return output(input.catalog);
  }};
function snapshot() {
  const select = ids.target;
  snapshots.push(JSON.parse(JSON.stringify({disabled: select.disabled, value: select.value, dataset: select.dataset,
    options: select.children.map(x => ({value:x.value,text:x.textContent,disabled:x.disabled,dataset:x.dataset})),
    status:ids["target-status"].textContent,retryHidden:ids["target-retry"].hidden,
    requests,aborted:signals.map(signal => signal.aborted)})));
}
const flush = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  vm.runInNewContext(fs.readFileSync(input.script, "utf8"), context);
  await flush();
  const select = ids.target;
  if (input.selection !== null) { select.value = input.selection; select.listeners.change(); }
  snapshot();
  for (const step of input.steps) {
    if (step.action === "refresh") {
      if (step.catalog) input.catalog = step.catalog;
      input.fail = Boolean(step.fail); hold = Boolean(step.hold);
      context.window.dispatchEvent(new context.CustomEvent("experiment-catalog-refresh"));
    } else if (step.action === "settle") {
      if (step.error) pending[step.index].reject(new Error("Unavailable"));
      else pending[step.index].resolve(output(step.catalog ?? input.catalog));
    }
    await flush(); snapshot();
  }
  process.stdout.write(JSON.stringify(snapshots));
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, '-e', script], input=json.dumps({'catalog':catalog,'fail':fail,'selection':selection,
        'steps':list(steps),'script':str(PROJECT / 'ui/targets.js')}), text=True, capture_output=True, check=True)
    views = json.loads(result.stdout)
    return views if history else views[-1]


HORIZONS = [1, 7, 21, 63, 252]
CATEGORY_OPTIONS = [('price', 'Price Return'), ('total_return', 'Total Return'),
                    ('benchmark_excess', 'Excess Return')]


def weekday_family_catalog(catalog, *, tag='interface_fixture', instrument_id=None):
    """Interface-only projection; fabricated IDs do not claim stored scientific outputs.

    Production API tests continue to use the unmodified persisted fixture.
    """
    result = deepcopy(catalog)
    original = result['targets'][0]
    targets = []
    for amount in HORIZONS:
        target = deepcopy(original)
        target['target_id'] = 'TARGET_' + hashlib.sha256(f'{tag}:{amount}'.encode()).hexdigest()
        target['horizon'] = {'amount':amount, 'unit':'scheduled_bars', 'counting':'exclusive_entry'}
        target['schedule'] = {'calendar_id':'RESEARCH_WEEKDAYS', 'calendar_version':'1.0.0',
                              'holiday_exclusions':False}
        if instrument_id is not None:
            target['instrument_id'] = instrument_id
        targets.append(target)
    result.update(targets=targets, target_count=len(targets))
    for instrument in result.get('instruments', []):
        instrument['target_ids'] = [target['target_id'] for target in targets]
    return result


def assert_categories(case, view):
    case.assertEqual([(item['value'], item['text']) for item in view['options'][1:]], CATEGORY_OPTIONS)
    case.assertTrue(view['options'][0]['disabled'])
    case.assertTrue(view['options'][2]['disabled'])
    case.assertTrue(view['options'][3]['disabled'])


class TargetLibraryApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_temp = tempfile.TemporaryDirectory(prefix='target_api_fixture_')
        cls.addClassCleanup(cls.fixture_temp.cleanup)
        cls.fixture_root = Path(cls.fixture_temp.name) / 'research_platform'
        cls.fixture_root.mkdir()
        cls.arguments = persistence_fixture(cls.fixture_root)
        cls.published = materialize(cls.fixture_root, cls.arguments['request'])
        (cls.fixture_root / 'ui').mkdir(exist_ok=True)
        for name in ('index.html','library.css','library.js','signals.js','targets.js'):
            shutil.copyfile(PROJECT / 'ui' / name, cls.fixture_root / 'ui' / name)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='target_api_case_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'research_platform'
        shutil.copytree(self.fixture_root, self.root)
        self.target_id = self.published['target_id']
        self.materialization_id = self.published['materialization']['id']
        self.detail_path = '/api/target-library/' + self.target_id + '?materialization_id=' + self.materialization_id

    def catalog(self):
        return target_library.list_target_library(self.root)

    def test_actual_persisted_list_and_pinned_http_detail(self):
        catalog = self.catalog()
        self.assertEqual(catalog['schema_version'], '1.0.0')
        self.assertEqual(catalog['target_count'], 1)
        self.assertEqual(catalog['issues'], [])
        target = catalog['targets'][0]
        self.assertEqual(target['target_id'], self.target_id)
        self.assertEqual(target['return_basis'], 'price')
        self.assertEqual(target['representation'], 'simple')
        self.assertEqual(target['source_eligibility'], 'eligible')
        self.assertEqual(target['readiness'], 'historically_certified')
        self.assertEqual(target['materializations'][0]['id'], self.materialization_id)
        with running(self.root) as address:
            status, headers, body = request(address, self.detail_path)
            self.assertEqual(status, 200)
            self.assertEqual(headers['Cache-Control'], 'no-store')
            detail = json.loads(body)
            self.assertEqual(detail['definition']['id'], self.target_id)
            self.assertEqual(detail['manifest']['id'], self.materialization_id)
            self.assertGreater(len(detail['observations']), 0)
            self.assertTrue(detail['operand_lineage'])
            self.assertTrue(detail['source_metadata'])
            head_status, head_headers, head_body = request(address, self.detail_path, 'HEAD')
            self.assertEqual(head_status, 200)
            self.assertEqual(head_body, b'')
            self.assertEqual(head_headers['Content-Length'], headers['Content-Length'])

    def test_api_historical_training_cutoff_preserves_date_boundary(self):
        detail = target_library.get_target_detail(self.root,self.target_id,self.materialization_id)
        available = detail['observations'][0]['label_available_at']
        from datetime import date, timedelta
        next_date = (date.fromisoformat(available) + timedelta(days=1)).isoformat()
        with running(self.root) as address:
            before_status, _, before = request(address,self.detail_path + '&training_cutoff=' + available + '&cutoff_precision=date')
            after_status, _, after = request(address,self.detail_path + '&training_cutoff=' + next_date + '&cutoff_precision=date')
        self.assertEqual((before_status,after_status),(200,200))
        self.assertEqual(json.loads(before)['observations'], [])
        self.assertGreater(len(json.loads(after)['observations']), 0)

    def test_explicit_materialization_and_canonical_query_required(self):
        base = '/api/target-library/' + self.target_id
        cases = [base,base+'?materialization_id=',base+'?materialization_id=latest',
                 self.detail_path+'&materialization_id='+self.materialization_id,
                 self.detail_path+'&training_cutoff=2024-01-10',
                 self.detail_path+'&cutoff_precision=date',
                 self.detail_path+'&training_cutoff=2024-01-10&cutoff_precision=timestamp',
                 self.detail_path+'&training_cutoff=2024-01-10T00:00:00Z&cutoff_precision=utc_timestamp',
                 self.detail_path+'&training_cutoff=2024-02-30&cutoff_precision=date',
                 self.detail_path+'&anything=x','/api/target-library?anything=x']
        with running(self.root) as address:
            for path in cases:
                with self.subTest(path=path):
                    status, _, body = request(address,path)
                    self.assertEqual(status,400)
                    self.assertEqual(json.loads(body)['error']['code'],'UNSUPPORTED_QUERY')

    def test_unknown_ids_and_paths_are_not_available(self):
        cases = ['/api/target-library/TARGET_x','/api/target-library/%2e%2e/.env',
                 '/api/target-library/'+'TARGET_'+'a'*64+'?materialization_id='+self.materialization_id,
                 '/api/target-library/'+self.target_id+'?materialization_id='+'MATERIALIZATION_'+'0'*64]
        with running(self.root) as address:
            for path in cases:
                with self.subTest(path=path):
                    status, _, body = request(address,path)
                    self.assertEqual(status,404)
                    self.assertNotIn(str(self.root).encode(),body)

    def test_empty_catalog_keeps_disabled_categories_without_fabricated_binding(self):
        with tempfile.TemporaryDirectory(prefix='empty_target_api_') as empty:
            catalog = target_library.list_target_library(empty)
            self.assertEqual(catalog,{'schema_version':'1.0.0','target_count':0,'targets':[],'issues':[], 'instruments':[], 'instrument_count':0})
            with running(empty) as address:
                status, _, body = request(address,'/api/target-library')
            self.assertEqual(status,200)
            self.assertEqual(json.loads(body),catalog)
            view = selector(catalog)
            self.assertTrue(view['disabled'])
            assert_categories(self, view)
            self.assertTrue(all(item['disabled'] for item in view['options']))
            self.assertEqual(view['dataset'],{})

    def test_unmaterialized_definition_keeps_all_categories_disabled(self):
        shutil.rmtree(self.root / 'storage/catalog/target_store')
        catalog = self.catalog()
        self.assertEqual(catalog['targets'][0]['readiness'],'unmaterialized')
        view = selector(weekday_family_catalog(catalog))
        self.assertTrue(view['disabled'])
        assert_categories(self, view)
        self.assertTrue(all(option['disabled'] for option in view['options']))
        self.assertEqual(view['dataset'],{})

    def test_certified_family_selects_all_five_registry_bindings(self):
        catalog = weekday_family_catalog(self.catalog())
        initial = selector(catalog)
        self.assertFalse(initial['disabled'])
        self.assertEqual(initial['value'], '')
        self.assertEqual(initial['dataset'], {})
        assert_categories(self, initial)
        view = selector(catalog, selection='price')
        self.assertEqual(view['value'], 'price')
        self.assertEqual(view['dataset']['returnBasis'], 'price')
        self.assertEqual(json.loads(view['dataset']['horizons']), HORIZONS)
        self.assertEqual(view['dataset']['horizonUnit'], 'scheduled_weekdays')
        self.assertNotIn('materializationId', view['dataset'])
        bindings = json.loads(view['dataset']['targetBindings'])
        expected = [{'target_id':target['target_id'], 'definition_version':target['definition_version'],
                     'materialization_id':self.materialization_id, 'horizon':target['horizon']}
                    for target in catalog['targets']]
        self.assertCountEqual(bindings, expected)
        self.assertIn('training cutoff',view['status'])
        self.assertEqual([option['text'] for option in view['options'] if not option['disabled']], ['Price Return'])

    def test_refresh_keeps_category_but_replaces_only_verified_family_bindings(self):
        initial = weekday_family_catalog(self.catalog())
        refreshed = weekday_family_catalog(self.catalog(), tag='refreshed')
        views = selector(initial, selection='price', history=True,
                         steps=[{'action':'refresh','catalog':refreshed,'hold':True},
                                {'action':'settle','index':0}])
        before, pending, after = views
        self.assertTrue(pending['disabled'])
        self.assertEqual(pending['value'], '')
        self.assertEqual(pending['dataset'], {})
        self.assertEqual(after['value'], 'price')
        self.assertNotEqual(before['dataset']['targetBindings'], after['dataset']['targetBindings'])
        self.assertEqual({item['target_id'] for item in json.loads(after['dataset']['targetBindings'])},
                         {item['target_id'] for item in refreshed['targets']})
        self.assertTrue(all(request == {'url':'/api/target-library','method':'GET'} for request in after['requests']))

    def test_incomplete_or_failed_refresh_revokes_selected_category(self):
        initial = weekday_family_catalog(self.catalog())
        incomplete = deepcopy(initial)
        incomplete['targets'].pop()
        incomplete['target_count'] -= 1
        for change in ({'catalog':incomplete}, {'fail':True}):
            with self.subTest(change=change):
                view = selector(initial, selection='price', steps=[{'action':'refresh', **change}])
                self.assertTrue(view['disabled'])
                self.assertEqual(view['value'], '')
                self.assertEqual(view['dataset'], {})
                self.assertTrue(all(request['method'] == 'GET' for request in view['requests']))

    def test_late_catalog_response_cannot_restore_retired_target_bindings(self):
        initial = weekday_family_catalog(self.catalog())
        empty = {'schema_version':'1.0.0','target_count':0,'targets':[],'issues':[]}
        views = selector(initial, selection='price', history=True,
                         steps=[{'action':'refresh','hold':True},
                                {'action':'refresh','catalog':empty},
                                {'action':'settle','index':0,'catalog':initial}])
        current, late = views[-2:]
        self.assertTrue(late['disabled'])
        self.assertEqual(late['dataset'], {})
        self.assertEqual(late['value'], '')
        self.assertEqual(current['options'], late['options'])
        self.assertEqual(current['status'], late['status'])
        self.assertTrue(late['aborted'][1])

    def test_unrelated_persisted_session_target_cannot_enable_weekday_family(self):
        view = selector(self.catalog())
        self.assertTrue(view['disabled'])
        assert_categories(self, view)
        self.assertEqual(view['dataset'], {})

    def test_uncertified_numeric_materialization_is_not_selectable(self):
        other = Path(self.temp.name) / 'uncertified'
        other.mkdir()
        inputs = persistence_fixture(other,selection='pinned_later',availability_basis='unknown')
        materialize(other,inputs['request'])
        catalog = target_library.list_target_library(other)
        self.assertEqual(catalog['targets'][0]['readiness'],'uncertified')
        view = selector(weekday_family_catalog(catalog))
        self.assertTrue(view['disabled'])
        self.assertTrue(all(option['disabled'] for option in view['options']))

    def test_multiple_materializations_have_deterministic_binding_per_family_member(self):
        arguments = deepcopy(self.arguments['request'])
        arguments['knowledge_cutoff'] = '2024-01-11'
        another = materialize(self.root,arguments)
        catalog = self.catalog()
        self.assertEqual(catalog['target_count'],1)
        self.assertEqual(len(catalog['targets'][0]['materializations']),2)
        projected = weekday_family_catalog(catalog)
        view = selector(projected, selection='price')
        bindings = json.loads(view['dataset']['targetBindings'])
        self.assertEqual(len(bindings),5)
        self.assertEqual({item['materialization_id'] for item in bindings},
                         {max(self.materialization_id,another['materialization']['id'])})
        projected['targets'].reverse()
        for target in projected['targets']:
            target['materializations'].reverse()
        self.assertEqual(selector(projected, selection='price')['dataset'],view['dataset'])
        self.assertNotIn('materializationId',view['dataset'])
        self.assertNotIn('latest',view['status'].lower())

    def test_integrity_failure_excluded_and_generic_http_error(self):
        detail = target_library.get_target_detail(self.root,self.target_id,self.materialization_id)
        blob = detail['manifest']['observations']['blob_sha256']
        path = self.root / f'storage/payloads/sha256/{blob[:2]}/{blob}.jsonl'
        path.write_bytes(path.read_bytes()+b'LOCAL_PATH_SECRET')
        catalog = self.catalog()
        self.assertEqual(catalog['target_count'],0)
        self.assertEqual(len(catalog['issues']),1)
        with running(self.root) as address:
            status, _, body = request(address,self.detail_path)
        self.assertEqual(status,503)
        self.assertEqual(json.loads(body)['error']['code'],'TARGET_UNAVAILABLE')
        self.assertNotIn(b'LOCAL_PATH_SECRET',body)
        self.assertNotIn(str(self.root).encode(),body)

    def test_failed_selector_exposes_retry_without_replacement_data(self):
        view = selector(fail=True)
        self.assertTrue(view['disabled'])
        self.assertFalse(view['retryHidden'])
        assert_categories(self, view)
        self.assertTrue(all(option['disabled'] for option in view['options']))
        self.assertEqual(view['dataset'],{})
        self.assertNotIn('mock', (PROJECT/'ui/index.html').read_text().split('<label for="target">')[1].split('<label for="scope">')[0].lower())

    def test_read_only_host_methods_assets_and_existing_libraries(self):
        before = inventory(self.root)
        with running(self.root) as address:
            for path in ('/api/target-library',self.detail_path,'/api/signal-library','/api/pit-library','/targets.js'):
                status, _, _ = request(address,path)
                self.assertEqual(status,200)
            for method in ('POST','PUT','PATCH','DELETE','OPTIONS','TRACE','CONNECT'):
                status, headers, _ = request(address,'/api/target-library',method)
                self.assertEqual(status,405)
                self.assertEqual(headers['Allow'],'GET, HEAD')
            for headers in ({'Host':'evil.example'},{'Origin':'https://evil.example'}):
                status, _, _ = request(address,'/api/target-library',headers=headers)
                self.assertEqual(status,403)
        self.assertEqual(inventory(self.root),before)


if __name__ == '__main__':
    unittest.main()
