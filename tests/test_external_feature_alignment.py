"""Isolated external alignment certification. No production research or data writes."""
from copy import deepcopy
from pathlib import Path
from datetime import date, timedelta
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch

from data.feature_store import FeatureStore, publish_feature
from data.transformations.identity import canonical_bytes, digest, reference
from research import external_features as external, inputs
from research.contracts import canonical, ref
from test_feature_store import persistence_fixture

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT/'definitions/alignment_policies/POL_EXTERNAL_STORED_DAILY_STATE/1.0.0.json').read_text())


def install_policy(root, profile):
    policy_path = root/'definitions/alignment_policies'/POLICY['id']/(POLICY['version']+'.json')
    policy_path.parent.mkdir(parents=True, exist_ok=True); policy_path.write_bytes(canonical(POLICY)+b'\n')
    profile = dict(profile, external_alignment_policy=ref(POLICY), id='RSPEC_ISOLATED_EXTERNAL_TS')
    path = root/'definitions/research_specs'/profile['id']/(profile['version']+'.json')
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(canonical(profile)+b'\n')
    (root/'config').mkdir(exist_ok=True)
    (root/'config/external_feature_alignment.json').write_bytes(canonical({'research_spec':ref(profile)})+b'\n')
    return profile


def merge_external(root, cutoffs=None):
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder)
        args = persistence_fixture(source, cutoffs=cutoffs)
        saved = publish_feature(source, **args)
        shutil.copytree(source, root, dirs_exist_ok=True)
    from research.feature_applications import install_binding, SINGLE_SERIES
    install_binding(root, args["feature"], SINGLE_SERIES)
    return args, saved


def state(when, value='1', *, evaluation=None, reference_time='1990-01-01', status='valid'):
    return {'available_at':when, 'evaluation_cutoff':evaluation or when, 'reference_time':reference_time,
            'value':value if status=='valid' else None,'status':status,
            'reason_code':None if status=='valid' else 'MISSING_VALUE'}


class AlignmentSemanticsTests(unittest.TestCase):
    def test_friday_monday_and_both_temporal_conditions(self):
        row=state('2020-03-06', evaluation='2020-03-09')
        for day in ('2020-03-06','2020-03-09'):
            self.assertEqual(external.state_at([row],day,POLICY)[2], 'FEATURE_NOT_AVAILABLE')
        self.assertEqual(external.state_at([row],'2020-03-10',POLICY)[:2],(row,1))
        self.assertEqual(external.next_weekday('2020-03-06'),'2020-03-09')
        friday=state('2020-03-06')
        self.assertIsNone(external.state_at([friday],'2020-03-06',POLICY)[0])
        self.assertIs(external.state_at([friday],'2020-03-09',POLICY)[0],friday)

    def test_reference_month_never_backdates_and_future_revision_never_changes_past(self):
        rows=[state('2020-03-06'),state('2020-04-06','2')]
        self.assertIsNone(external.state_at(rows,'2020-03-02',POLICY)[0])
        first=external.state_at(rows[:1],'2020-03-10',POLICY)
        self.assertEqual(first,external.state_at(rows,'2020-03-10',POLICY))
        self.assertIs(external.state_at(rows,'2020-03-11',POLICY)[0],rows[0])

    def test_new_invalid_or_null_supersedes_without_resurrection(self):
        for status in ('invalid','missing'):
            rows=[state('2020-03-06'),state('2020-03-10',status=status)]
            chosen,age,reason=external.state_at(rows,'2020-03-11',POLICY)
            self.assertIs(chosen,rows[1]);self.assertEqual(reason,'MISSING_VALUE');self.assertEqual(age,1)
            self.assertIs(external.state_at(rows,'2021-03-11',POLICY)[0],rows[1])

    def test_age_basis_max_age_boundaries_and_event_only(self):
        row=state('2020-03-06',evaluation='2020-03-09')
        policy=deepcopy(POLICY);fresh=policy['freshness_rule']
        fresh.update(mode='MAX_AGE',maximum=3,boundary='inclusive',age_basis='available_at')
        self.assertEqual(external.state_at([row],'2020-03-10',policy)[2],'FEATURE_STALE')
        fresh['age_basis']='evaluation_cutoff'
        self.assertIsNone(external.state_at([row],'2020-03-12',policy)[2])
        fresh['boundary']='exclusive'
        self.assertEqual(external.state_at([row],'2020-03-12',policy)[2],'FEATURE_STALE')
        policy=deepcopy(POLICY);policy['freshness_rule']['mode']='EVENT_ONLY'
        self.assertIsNone(external.state_at([row],'2020-03-10',policy)[2])
        self.assertEqual(external.state_at([row],'2020-03-11',policy)[2],'NOT_FEATURE_EVENT_ANCHOR')

    def test_duplicate_candidates_and_conflicting_policy_rejected(self):
        with self.assertRaisesRegex(inputs.InputsBlocked,'Duplicate'):
            external.state_at([state('2020-03-06'),state('2020-03-06','2')],'2020-03-09',POLICY)
        for changes in ({'mode':'MAX_AGE'}, {'age_basis':'reference_time'}, {'unit':'observations'}, {'maximum':2}):
            policy=deepcopy(POLICY);policy['freshness_rule'].update(changes)
            with self.assertRaises(inputs.InputsBlocked):external.validate_policy(policy)
        policy=deepcopy(POLICY);policy['invalid_update_rule']='fallback_valid'
        with self.assertRaises(inputs.InputsBlocked):external.validate_policy(policy)


class ExternalStoredReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.args=persistence_fixture(self.root);self.saved=publish_feature(self.root,**self.args)
        from test_research_inputs import approved_profile
        self.profile=install_policy(self.root,approved_profile())
        self.feature=self.args['feature'];self.store=FeatureStore(self.root)
        self.source=external.resolve_source(self.root,self.feature,self.profile)

    def test_minimum_preperiod_context_and_no_crossphase_value_decode(self):
        original=external.strict_json;decoded=[]
        def guarded(raw):
            value=original(raw)
            if isinstance(value,dict) and 'materialization_id' in value:
                self.assertLess(value['evaluation_cutoff'],'2020-03-10');decoded.append(value)
            return value
        with patch.object(external,'strict_json',side_effect=guarded):
            rows=external.phase_rows(self.root,self.source,{'start_inclusive':'2020-03-04','end_exclusive':'2020-03-10'})
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['evaluation_cutoff'],'2020-03-01')
        self.assertEqual(len(decoded),1)
        later=external.phase_rows(self.root,self.source,{'start_inclusive':'2020-03-16','end_exclusive':'2020-03-20'})
        self.assertEqual([r['evaluation_cutoff'] for r in later],['2020-03-15'])

    def test_readonly_plan_metadata_does_not_decode_observation_values(self):
        original=external.strict_json
        def guarded(raw):
            value=original(raw)
            if isinstance(value,dict) and ('materialization_id' in value or 'amount' in value):raise AssertionError('numeric row decoded')
            return value
        before={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(external,'strict_json',side_effect=guarded):external.resolve_source(self.root,self.feature,self.profile)
        after={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_semantic_integrity_cannot_be_bypassed_by_repointing_partition(self):
        manifest=self.store.resolve(self.source['materialization']);part=manifest['partitions'][0]
        raw=self.store.payload(part);altered=raw.replace(b'"value":"0.10000000000000009"',b'"value":"0.9"')
        self.assertNotEqual(raw,altered)
        with patch.object(self.store,'payload',return_value=altered):
            with self.assertRaisesRegex(inputs.InputsBlocked,'semantic checksum'):
                external.observation_headers(self.store,manifest)

    def test_series_and_availability_headers_rejected_before_value_decode(self):
        manifest=self.store.resolve(self.source['materialization']);raw=self.store.payload(manifest['partitions'][0])
        for before,after in ((b'"entity_id":"ENTITY_A"',b'"entity_id":"OTHER"'),
                             (b'"measure":"amount"',b'"measure":"other"'),
                             (b'"dimensions":[]',b'"dimensions":[{"name":"x","value":"y"}]'),
                             (b'"available_at":"2020-03-01"',b'"available_at":null')):
            with self.subTest(after=after),patch.object(self.store,'payload',return_value=raw.replace(before,after)):
                with self.assertRaises(ValueError):external.observation_headers(self.store,manifest)

    def test_canonical_dimension_labels_with_brackets_are_supported(self):
        manifest=self.store.resolve(self.source['materialization']);part=manifest['partitions'][0]
        rows=[json.loads(line) for line in self.store.payload(part).splitlines()]
        dimensions=[{'name':'category','value':'rate [adjusted]'}]
        manifest['metadata']['selection']['dimensions']=dimensions
        for row in rows:row['dimensions']=dimensions
        raw=b''.join(canonical_bytes(row)+b'\n' for row in rows)
        manifest['semantic_rows_sha256']=digest([{k:v for k,v in r.items() if k!='materialization_id'} for r in rows])
        with patch.object(self.store,'payload',return_value=raw):
            self.assertEqual(len(external.observation_headers(self.store,manifest)),3)

    def test_lineage_tamper_is_detected_before_research(self):
        rows=external.phase_rows(self.root,self.source,{'start_inclusive':'2020-03-04','end_exclusive':'2020-03-10'})
        row=rows[0];lineage=self.store.resolve(row['lineage']);lineage['inputs'][0]['artifact']['content_sha256']='0'*64
        with self.assertRaises(ValueError):external.verify_selected_lineage(self.store,lineage,row,self.source)

    def test_ambiguous_materializations_and_unsupported_precision_fail_closed(self):
        original_glob=Path.glob
        def duplicate(path, pattern):
            values=list(original_glob(path,pattern))
            return iter(values+values) if str(path).endswith('catalog/feature_store') else iter(values)
        with patch.object(Path,'glob',duplicate):
            with self.assertRaisesRegex(inputs.InputsBlocked,'Exactly one external'):
                external.resolve_source(self.root,self.feature,self.profile)
        manifest=self.store.resolve(self.source['materialization'])
        manifest['metadata']['temporal_precision']='utc_timestamp'
        with patch.object(external,'normalize_materialization',return_value=manifest):
            with self.assertRaisesRegex(inputs.InputsBlocked,'date-only'):
                external.resolve_source(self.root,self.feature,self.profile)

    def test_duplicate_temporal_candidates_rejected_even_with_valid_checksums(self):
        manifest=self.store.resolve(self.source['materialization']);part=manifest['partitions'][0]
        rows=[json.loads(line) for line in self.store.payload(part).splitlines()]
        rows[-1]['evaluation_cutoff']=rows[-1]['available_at']=rows[-2]['evaluation_cutoff']
        raw=b''.join(canonical_bytes(row)+b'\n' for row in rows)
        manifest['input_key']['output_index']=[{k:r[k] for k in ('reference_time','evaluation_cutoff')} for r in rows]
        manifest['semantic_rows_sha256']=digest([{k:v for k,v in r.items() if k!='materialization_id'} for r in rows])
        with patch.object(self.store,'payload',return_value=raw):
            with self.assertRaisesRegex(inputs.InputsBlocked,'Duplicate eligible'):
                external.observation_headers(self.store,manifest)

    def test_event_only_weekend_collision_is_explicitly_rejected(self):
        policy=deepcopy(POLICY);policy['freshness_rule']['mode']='EVENT_ONLY'
        with self.assertRaisesRegex(inputs.InputsBlocked,'event collisions'):
            external.state_at([state('2020-03-07'),state('2020-03-08')],'2020-03-09',policy)



class ExternalInputsIntegrationTests(unittest.TestCase):
    def setUp(self):
        from test_research_inputs import ResearchInputsTests
        self.fixture=ResearchInputsTests(methodName='runTest');self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
        self.root=self.fixture.root;self.args,self.saved=merge_external(self.root)
        self.profile=install_policy(self.root,self.fixture.profile)
        self.intent=dict(self.fixture.intent,feature={k:self.args['feature'][k] for k in ('id','version')})

    def test_real_target_alignment_reuse_identity_counts_and_gaps(self):
        plan=inputs.resolve_plan(self.root,self.intent,self.profile)
        with patch('research.inputs.prepare_fx_feature',side_effect=AssertionError('No Feature cloning')):
            prepared=inputs.prepare_phase(self.root,plan,'P1')
        result=inputs.load_phase(self.root,plan,prepared,'P1',7)
        self.assertTrue(result['rows']);self.assertEqual(result['mode'],'TS')
        self.assertEqual(prepared,inputs.prepare_phase(self.root,plan,'P1'))
        self.assertEqual(result['coverage'][0]['distinct_source_update_count'],1)
        self.assertGreater(result['coverage'][0]['aligned_weekday_rows'],1)
        original_refs={digest(r['lineage']['original_observation']) for r in result['rows']}
        self.assertEqual(len(original_refs),1)
        for row in result['rows']:
            self.assertEqual(row['lineage']['source_selection']['entity_id'],'ENTITY_A')
            self.assertEqual(row['instrument'],'EURUSD')
            self.assertEqual(row['lineage']['feature_definition'],reference(self.args['feature']))
            self.assertLess(row['target_end'],plan['periods']['P1']['end_exclusive'])
        self.assertTrue(any(not r['valid'] for r in result['rows']))
        seven=next(r for r in result['rows'] if r['date']==self.fixture.fx.days[10])
        self.assertEqual(seven['target_end'],self.fixture.fx.days[17])
        self.assertFalse(seven['valid']) # Missing exact endpoint: never shifted.
        self.assertEqual(len(list((self.root/'definitions/features').glob(self.args['feature']['id']+'/*.json'))),1)

    def test_universe_rejected_and_p2_admission_required(self):
        plan=inputs.resolve_plan(self.root,self.intent,self.profile)
        with self.assertRaises(inputs.InputsBlocked):inputs.prepare_phase(self.root,plan,'P2')
        admitted={'plan_id':plan['plan_id'],'direction':'POSITIVE','admitted_horizons':[1]}
        prepared=inputs.prepare_phase(self.root,plan,'P2',admission=admitted)
        result=inputs.load_phase(self.root,plan,prepared,'P2',1,admission=admitted)
        self.assertTrue(all(r['date']>='2024-03-01' for r in result['rows']))
        with self.assertRaises(inputs.InputsBlocked):inputs.load_phase(self.root,plan,prepared,'P2',7,admission=admitted)
        self.fixture.scope['kind']='universe'
        with self.assertRaisesRegex(inputs.InputsBlocked,'universe broadcasting'):inputs.resolve_plan(self.root,self.intent,self.profile)

    def test_policy_changes_change_plan_and_preparation_identity(self):
        first=inputs.resolve_plan(self.root,self.intent,self.profile)
        p1=inputs.prepare_phase(self.root,first,'P1')
        policy=dict(POLICY,version='1.0.1');policy['freshness_rule']=dict(POLICY['freshness_rule'],age_basis='available_at')
        path=self.root/'definitions/alignment_policies'/policy['id']/'1.0.1.json';path.write_bytes(canonical(policy)+b'\n')
        profile=dict(self.profile,external_alignment_policy=ref(policy))
        second=inputs.resolve_plan(self.root,self.intent,profile);p2=inputs.prepare_phase(self.root,second,'P1')
        self.assertNotEqual(first['plan_id'],second['plan_id']);self.assertNotEqual(p1['prepared_id'],p2['prepared_id'])
        self.assertEqual(first['recipe'],second['recipe'])

    def test_source_materialization_and_code_participate_in_identity(self):
        plan=inputs.resolve_plan(self.root,self.intent,self.profile)
        prepared=inputs.prepare_phase(self.root,plan,'P1')
        for field in ('materialization','feature'):
            changed=deepcopy(plan);changed['external_source'][field]['content_sha256']='f'*64
            self.assertNotEqual(inputs._plan_id(changed),plan['plan_id'])
        changed=deepcopy(plan);changed['external_source']['source_snapshots'][0]['content_sha256']='f'*64
        self.assertNotEqual(inputs._plan_id(changed),plan['plan_id'])
        with patch('runtime.research_jobs.implementation',return_value={'fingerprint':'different_code'}):
            newer=inputs.prepare_phase(self.root,plan,'P1')
            self.assertNotEqual(newer['prepared_id'],prepared['prepared_id'])
            with self.assertRaisesRegex(inputs.InputsBlocked,'implementation has changed'):
                inputs.load_phase(self.root,plan,prepared,'P1',1)



if __name__=='__main__':unittest.main()
