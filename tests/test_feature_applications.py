"""Application foundation: explicit metadata, fail-closed routing and no writes."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research import feature_applications as apps
from data.feature_store import FeatureStore
from data.transformations.identity import reference, canonical_bytes, digest
from test_feature_store import persistence_fixture


def inventory(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


class ApplicationContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.feature=persistence_fixture(self.root)['feature']
        FeatureStore(self.root).install_record(self.feature)
        self.scope={'kind':'instrument','members':['USDJPY']}

    def install(self):
        return apps.install_binding(self.root,self.feature,apps.SINGLE_SERIES)

    def test_registration_is_explicit_missing_binding_fails_closed(self):
        before=inventory(self.root)
        with self.assertRaisesRegex(apps.ApplicationBlocked,'not registered'):
            apps.resolve(self.root,self.feature,self.scope)
        self.assertEqual(inventory(self.root),before)

    def test_registration_is_idempotent_and_does_not_rewrite_existing_data(self):
        before=inventory(self.root);binding=self.install();after=inventory(self.root)
        self.assertEqual({k:after[k] for k in before},before)
        self.assertEqual(self.install(),binding);self.assertEqual(inventory(self.root),after)
        self.assertEqual(binding['feature'],reference(self.feature))

    def test_single_source_entity_is_preserved_no_currency_specific_definition(self):
        self.install();before=inventory(self.root)
        a=apps.resolve(self.root,self.feature,self.scope)
        b=apps.resolve(self.root,self.feature,{'kind':'instrument','members':['EURUSD']})
        self.assertEqual(a,b);self.assertEqual(a['mode'],'TS');self.assertIsNone(a['entity_mapping'])
        self.assertEqual(inventory(self.root),before)

    def test_no_universe_broadcast_or_ts_fanout(self):
        self.install()
        with self.assertRaisesRegex(apps.ApplicationBlocked,'individual instrument TS only'):
            apps.resolve(self.root,self.feature,{'kind':'universe','members':['EURUSD','USDJPY']})

    def test_ambiguous_and_empty_members_fail(self):
        self.install()
        for members in ([],['EURUSD','EURUSD'],['EURUSD','USDJPY']):
            with self.subTest(members=members),self.assertRaises(apps.ApplicationBlocked):
                apps.resolve(self.root,self.feature,{'kind':'instrument','members':members})

    def test_future_entity_mapping_remains_disabled_even_for_registered_feature(self):
        with self.assertRaisesRegex(apps.ApplicationBlocked,'provider onboarding'):
            apps.install_binding(self.root,self.feature,apps.ENTITY_MAPPED)
        self.assertEqual(apps.contract(apps.ENTITY_MAPPED)['scope_modes'],{})
        self.assertFalse((self.root/'definitions/feature_applications').exists())

    def test_wrong_adapter_and_changed_contract_are_rejected(self):
        with self.assertRaises(apps.ApplicationBlocked):apps.install_binding(self.root,self.feature,apps.PER_MEMBER)
        binding=self.install()
        path=self.root/'definitions/feature_applications/contracts'/binding['contract']['id']/'1.0.0.json'
        bad=apps.contract(apps.SINGLE_SERIES);bad['scope_modes']['universe']='CS';path.write_bytes(canonical_bytes(bad))
        with self.assertRaisesRegex(apps.ApplicationBlocked,'differs'):
            apps.resolve(self.root,self.feature,self.scope)

    def test_frozen_semantics_cannot_change_or_gain_mapping(self):
        self.install();value=apps.resolve(self.root,self.feature,self.scope)
        apps.validate_frozen(value,reference(self.feature),self.scope,'TS')
        changed=deepcopy(value);changed['entity_mapping']={'US':'USDJPY'}
        with self.assertRaises(apps.ApplicationBlocked):apps.validate_frozen(changed,reference(self.feature),self.scope,'TS')
        changed=deepcopy(value);changed['contract']['orientation']='invert_quote'
        self.assertNotEqual(digest(value),digest(changed))
        with self.assertRaises(apps.ApplicationBlocked):apps.validate_frozen(changed,reference(self.feature),self.scope,'TS')


class NativeApplicationIntegrationTests(unittest.TestCase):
    def setUp(self):
        from test_research_inputs import ResearchInputsTests
        self.fixture=ResearchInputsTests(methodName='runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root=self.fixture.root

    def test_same_recipe_ts_and_cs_metadata_resolution_no_preparation(self):
        f=self.fixture
        before=inventory(self.root)
        a=apps.resolve(self.root,f.intent['feature'],f.scope)
        scope=dict(f.scope,kind='universe',members=['EURUSD','USDJPY'])
        b=apps.resolve(self.root,f.intent['feature'],scope)
        self.assertEqual(a['binding'],b['binding']);self.assertEqual((a['mode'],b['mode']),('TS','CS'))
        self.assertEqual(inventory(self.root),before)

    def test_api_and_planner_freeze_same_application_for_negative_direction(self):
        from api.feature_library import get_feature_resolution
        f=self.fixture;f.intent['expected_direction']='NEGATIVE'
        with patch('data.scopes.resolve_scope',return_value=f.scope), patch('data.feature_resolution.resolve_feature_scope',return_value={'issues':[]}):
            result=get_feature_resolution(self.root,f.recipe['id'],f.recipe['version'],f.scope['id'],f.scope['version'])
        plan=f.plan()
        self.assertEqual(result['application'],plan['feature_application'])
        self.assertTrue(result['submission_compatible'])
        self.assertEqual(plan['intent']['expected_direction'],'NEGATIVE')
        self.assertEqual(plan['feature_application']['entity_mapping'],None)
        from research import inputs
        inputs._validate_plan(plan)
        historical=deepcopy(plan);historical.pop('feature_application')
        historical['plan_id']=inputs._plan_id(historical)
        inputs._validate_plan(historical)  # historical plans remain readable
        changed=deepcopy(plan);changed['feature_application']['entity_mapping']={'US':'USDJPY'}
        changed['plan_id']=inputs._plan_id(changed)
        with self.assertRaises(apps.ApplicationBlocked):inputs._validate_plan(changed)

    def test_native_submit_freezes_metadata_plan_without_observations(self):
        import json,uuid
        from runtime.research_jobs import ResearchJobs
        f=self.fixture
        (self.root/'config/research_execution.json').write_text(json.dumps(f.profile))
        jobs=ResearchJobs(self.root);self.addCleanup(jobs.close)
        request=dict(f.intent,request_id=str(uuid.uuid4()))
        with patch('research.inputs.read_materialization',side_effect=AssertionError('Submit must not read Feature observations')),patch('research.inputs._phase_target_rows',side_effect=AssertionError('Submit must not read Target observations')),patch('research.inputs.prepare_phase',side_effect=AssertionError('Submit must not prepare')):
            job,created=jobs.submit(request)
        self.assertTrue(created);self.assertEqual(job['status'],'queued')
        saved=jobs._submission(request['request_id'])
        self.assertEqual(saved['feature_application'],apps.resolve(self.root,f.intent['feature'],f.scope))
        self.assertIn('frozen_plan',saved)
        self.assertEqual(saved['frozen_plan']['feature_application'],saved['feature_application'])

    def test_missing_binding_rejected_before_job_is_written(self):
        import json,uuid
        from runtime.research_jobs import ResearchJobs
        from research.contracts import ResearchBlocked
        f=self.fixture
        (self.root/'config/research_execution.json').write_text(json.dumps(f.profile))
        apps._binding_path(self.root,f.recipe).unlink()  # isolated fixture only
        jobs=ResearchJobs(self.root);self.addCleanup(jobs.close)
        request=dict(f.intent,request_id=str(uuid.uuid4()))
        with self.assertRaises(ResearchBlocked):jobs.submit(request)
        self.assertFalse(list((self.root/'storage/catalog/submissions').glob('*.json')))


if __name__=='__main__':unittest.main()
