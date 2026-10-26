"""Synthetic wrapper tests: original metadata checks and program identity survive."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from research.contracts import digest, ResearchConflict
from runtime.execution_compatibility import make_proposal, install_approval
from runtime.program_intake_compatibility import manifest_view, bridge_class, load_operator, validate_entry_binding
from test_execution_compatibility import synthetic_implementation, synthetic_approval

RID = '00000000-0000-0000-0000-000000000001'


def require(condition, message):
    if not condition: raise ResearchConflict(message)


class OriginalBridge:
    """Stub tracks the unchanged original verification entry points."""
    def __init__(self, root): self.root = root; self.seen = []; self.original_checked = False
    def verify_global(self, manifest):
        self.seen.append(deepcopy(manifest)); self.original_checked = True
        require(manifest['global_pins']['scientific_pin'] == 'fixed', 'science drift')
    def validate_packet(self, manifest, row, packet):
        self.seen.append(('validate_packet', deepcopy(row)))
        return 'science'
    def accepted_entry(self, manifest, row):
        self.seen.append(('accepted_missing', row['request_id']))
        return None


def binding_fixture():
    from research import feature_applications as apps
    from research.inputs import _plan_id
    from research.contracts import HORIZONS, ref
    from data.transformations.fx_currency import members
    from data.transformations.identity import reference
    from test_research_runtime import profile, reference as synthetic_ref
    symbols = members('USD'); recipe = synthetic_ref('FEATURE_RECIPE_'+'a'*64)
    scope_ref = synthetic_ref('SCOPE_CURRENCY_USD'); price_catalog = synthetic_ref('PRICE_CATALOG')
    scope = {'id':scope_ref['id'],'version':'1.0.0','kind':'universe','reference':scope_ref,
             'membership_snapshot':synthetic_ref('MEMBERS'),'members':symbols,'reference_currency':'USD',
             'price_catalog':price_catalog,'research_basis':'currency_against_quote_reference'}
    contract = apps.contract(apps.CURRENCY_QUOTE)
    binding = {'schema_version':'1.0.0','feature':recipe,'contract':apps.contract_ref(contract)}
    application = {'binding':binding,'contract':contract,'mode':'CS','scope_kind':'universe','entity_mapping':None}
    policy = profile(); metadata = {}; bindings = []; plan_members = []
    for symbol in symbols:
        price = synthetic_ref('PRICE_'+symbol); feature = synthetic_ref('FEATURE_'+symbol)
        metadata[symbol] = {}; selected = {}; targets = {}
        for h in HORIZONS:
            record = {'id':'TARGET_MATERIAL_'+symbol+'_'+str(h),'version':'1.0.0',
                      'definition':synthetic_ref('TARGET_'+symbol+'_'+str(h)),'price_snapshot':price}
            metadata[symbol][str(h)] = record; selected[str(h)] = reference(record)
            targets[str(h)] = {'definition':record['definition'],'materialization':reference(record)}
        policy['target_selection']['materializations'][symbol] = selected
        member = {'instrument_id':symbol,'feature':feature,'price_snapshot':price,
                  'source_view':synthetic_ref('SOURCE_'+symbol),'structural_source_start':'2017-01-02','targets':targets}
        plan_members.append(member)
        bindings.append({k:member[k] for k in ('instrument_id','feature','price_snapshot','source_view')} |
                        {'configuration_id':'CONFIG_TEST'})
    configuration = {'id':'CONFIG_TEST','operation':'test'}
    catalog = {'id':'FEATURE_CATALOG_TEST','version':'1.0.0','body':{'bindings':bindings,
               'recipes':[{'recipe':recipe,'configuration':configuration}]}}
    request = {'feature':{k:recipe[k] for k in ('id','version')},'scope':{k:scope_ref[k] for k in ('id','version')},
               'target_family':'price_return','expected_direction':'POSITIVE'}
    plan = {'intent':request,'profile':policy,'recipe':recipe,'scope':scope,'mode':'CS',
            'horizons':list(HORIZONS),'periods':policy['periods'],'knowledge_cutoff':policy['target_selection']['knowledge_cutoff'],
            'structural_common_start':'2017-01-02','members':plan_members,'feature_application':application}
    plan['plan_id'] = _plan_id(plan)
    packet = {'intent':request,'research_spec':policy,'frozen_plan':plan,'feature_application':application}
    row = {'request_id':RID,'intent':request,'recipe_reference':recipe,'scope_reference':scope_ref,
           'membership_snapshot':scope['membership_snapshot'],'periods':plan['periods']}
    manifest = {'entries':[row],'scopes':[scope],'recipes':[{'reference':recipe,'configuration':configuration,
                'application_binding':binding}], 'global_pins':{'research_spec':ref(policy),
                'source_and_target_pins_sha256':digest(policy['target_selection']),
                'knowledge_cutoff':plan['knowledge_cutoff'],'feature_catalog':reference(catalog),
                'feature_bindings_sha256':digest(bindings)}}
    return manifest,row,packet,catalog,metadata


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.root = Path(self.temp.name)
        self.old, self.new = synthetic_implementation('old'), synthetic_implementation('new')
        self.intent = {'synthetic_science': 'fixed'}
        self.manifest = {'program_id': 'frozen-identity',
            'global_pins': {'implementation_digest': digest(self.old),
                            'implementation_fingerprint': self.old['fingerprint'], 'scientific_pin':'fixed'},
            'entries': [{'request_id': RID, 'intent': self.intent}]}
        self.proposal = make_proposal(manifest_sha256='a'*64, operator_sha256='b'*64,
            from_implementation=self.old, to_implementation=self.new,
            cohort=[{'request_id':RID, 'canonical_request_id':RID,'intent_sha256':digest(self.intent),
                     'scientific_identity':'c'*64, 'submission_sha256':None, 'committed_trials':[]}],
            evidence={'equivalence_sha256':'d'*64,'tests_sha256':'e'*64},
            source_archive_sha256='f'*64,target_archive_sha256='0'*64)
        self.approval = synthetic_approval(self.proposal); install_approval(self.root,self.approval)

    def tearDown(self): self.temp.cleanup()

    def test_view_only_changes_gate_and_retains_all_original_identity(self):
        before = deepcopy(self.manifest)
        view = manifest_view(self.manifest, self.approval, self.new)
        self.assertEqual(self.manifest, before)
        self.assertEqual(view['program_id'], self.manifest['program_id'])
        self.assertEqual(view['entries'], self.manifest['entries'])
        self.assertEqual(view['global_pins']['scientific_pin'], 'fixed')
        self.assertEqual(view['global_pins']['implementation_digest'], digest(self.new))
        with self.assertRaises(ResearchConflict): manifest_view(self.manifest,self.approval,self.old)
        changed = deepcopy(self.manifest); changed['entries'][0]['intent'] = {'different':'science'}
        with self.assertRaises(ResearchConflict): manifest_view(changed,self.approval,self.new)
        changed = deepcopy(self.manifest); changed['entries'].append(deepcopy(changed['entries'][0]))
        with self.assertRaises(ResearchConflict): manifest_view(changed,self.approval,self.new)

    def test_wrapper_runs_original_checks_and_requires_same_manifest_each_time(self):
        operator = SimpleNamespace(RuntimeBridge=OriginalBridge,require=require)
        cls = bridge_class(operator,self.approval,manifest_sha256='a'*64,
                           operator_sha256='b'*64,frozen_manifest=self.manifest)
        bridge = cls(self.root)
        with patch('runtime.research_jobs.implementation',return_value=self.new):
            bridge.verify_global(self.manifest)
            self.assertTrue(bridge.original_checked)
            self.assertEqual(bridge.seen[0],manifest_view(self.manifest,self.approval,self.new))
            changed = deepcopy(self.manifest); changed['global_pins']['scientific_pin'] = 'changed'
            with self.assertRaises(ResearchConflict): bridge.verify_global(changed)
        with patch('runtime.research_jobs.implementation',return_value=self.old),self.assertRaises(ResearchConflict):
            bridge.verify_global(self.manifest)

    def test_full_binding_validation_and_target_source_drift(self):
        from research.inputs import _plan_id
        from research.contracts import ResearchError
        manifest,row,packet,catalog,metadata = binding_fixture()
        validate_entry_binding(manifest,row,packet,feature_catalog=catalog,target_metadata=metadata)
        for change in ('period','member_order','feature','source','price','target','application',
                       'recipe_configuration','global_profile','global_targets','global_feature_bindings',
                       'global_cutoff','scope_quote','target_source'):
            changed = deepcopy(packet); changed_catalog = deepcopy(catalog)
            changed_manifest = deepcopy(manifest); changed_targets = deepcopy(metadata)
            plan = changed['frozen_plan']
            if change == 'period': plan['periods']['P1']['start_inclusive'] = '2017-03-01'
            elif change == 'member_order': plan['members'].reverse()
            elif change == 'feature': plan['members'][0]['feature']['content_sha256'] = 'f'*64
            elif change == 'source': plan['members'][0]['source_view']['content_sha256'] = 'f'*64
            elif change == 'price': plan['members'][0]['price_snapshot']['content_sha256'] = 'f'*64
            elif change == 'target': plan['members'][0]['targets']['1']['definition']['content_sha256'] = 'f'*64
            elif change == 'application': plan['feature_application']['entity_mapping'] = 'invented'
            elif change == 'recipe_configuration': changed_catalog['body']['recipes'][0]['configuration']['operation'] = 'different'
            elif change == 'global_profile': changed_manifest['global_pins']['research_spec']['content_sha256'] = 'f'*64
            elif change == 'global_targets': changed_manifest['global_pins']['source_and_target_pins_sha256'] = 'f'*64
            elif change == 'global_feature_bindings': changed_manifest['global_pins']['feature_bindings_sha256'] = 'f'*64
            elif change == 'global_cutoff': changed_manifest['global_pins']['knowledge_cutoff'] = '2026-10-08'
            elif change == 'scope_quote': changed_manifest['scopes'][0]['reference_currency'] = 'EUR'
            else: changed_targets[plan['members'][0]['instrument_id']]['1']['price_snapshot']['content_sha256'] = 'f'*64
            plan['plan_id'] = _plan_id(plan)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_entry_binding(changed_manifest,row,changed,feature_catalog=changed_catalog,target_metadata=changed_targets)

    def test_original_bytes_checked_before_any_execution(self):
        path = self.root/'operator.py'; marker = self.root/'marker'
        path.write_text('VALUE = 7\n')
        original = path.read_bytes(); expected = sha256(original).hexdigest()
        module = load_operator(path,expected)
        self.assertEqual(module.VALUE,7); self.assertEqual(path.read_bytes(),original)
        path.write_text('raise RuntimeError("must not execute")\n')
        with self.assertRaisesRegex(ResearchConflict,'bytes differ'):load_operator(path,expected)
        self.assertFalse(marker.exists())


if __name__ == '__main__': unittest.main()
