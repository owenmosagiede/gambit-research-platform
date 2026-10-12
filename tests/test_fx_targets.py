"""Persisted compact FX Target integration; all data/approvals here are fixtures."""
import copy
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
import tempfile
import unittest

from data.fx_records import make_record, write_rows, read_rows
from data.transformations.identity import reference,digest,canonical_bytes
from data.targets.store import TargetStore,InterruptedTargetPublication
from data.targets.fx import materialize,read_materialization,validate_batch_policy,affected_labels,construct_rows,approved_choices,validate_row,validate_manifest,validate_alignment_evidence
from data.targets.service import retrieve_target,list_targets

PROJECT=Path(__file__).resolve().parents[1]


def add(store,kind,body):
    record=make_record(kind,body);store.install_record(record);return reference(record)


def approve(store, policy):
    # These records exist only in an isolated temporary test store. They are not
    # evidence of a production approval and are never copied to the real project.
    policy=copy.deepcopy(policy)
    evidence=add(store,'onboarding_evidence',{'kind':'fx_research_approval','authority':'user_explicit_decision',
        'decision_text':'ISOLATED TEST FIXTURE ONLY: approve this exact example configuration.',
        'decision_time':'2024-01-01T00:00:00.000000Z','approved_policy':approved_choices(policy)})
    policy['approval_evidence']=evidence
    policy['retrospective_policy']=add(store,'policy_definition',{'kind':'fx_retrospective_policy','approval':evidence,
        'mode':'retrospective_date_label','historical_replay':False,'live_use':False,
        'unknown_availability':'preserve_null','source_selection':'pinned_original_capture'})
    return policy


def fixture(root):
    from data.transformations.fx import recipe,construct_prices,normalize_legs
    store=TargetStore(root)
    policy=approve(store,{'approval_state':'approved','representation':'simple','horizons':[1,3],
        'calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0','clock':'scheduled_bars',
        'entry':{'rule':'anchor_mark','delay':{'amount':0,'unit':'calendar_days'}},
        'endpoint':{'rule':'exact','tolerance':{'amount':0,'unit':'calendar_days'}}})
    evidence=add(store,'onboarding_evidence',{'kind':'fx_requested_single_source_construction','authority':'isolated_test_fixture'})
    alignment={'id':'FX_SINGLE_SOURCE','version':'1.0.0','mode':'single_source_observation','approval_state':'approved',
        'approval_evidence':evidence,'max_date_gap':0,'max_valuation_gap_seconds':None}
    meta={'base_currency':'EUR','quote_currency':'USD','unit':'USD_per_EUR','price_field':'close','price_basis':'unknown',
        'timing':{'timezone':None,'bar_boundary':None,'session_convention':None,'synchronization':'unverified'}}
    # Reuse the actual onboarding adapter over isolated raw/provider fixtures.
    from test_fx_onboarding import build_fixture
    from data.fx_onboarding import onboard,read_source
    native_root=root/'fixture_sources';native_root.mkdir()
    unused,legacy,audit_path,audit=build_fixture(native_root)
    (root/'config').mkdir(exist_ok=True)
    shutil.copyfile(unused/'config/storage.local.json',root/'config/storage.local.json')
    onboarded=onboard(root,legacy,audit_path,migration_time='2026-10-09T10:00:00Z')
    source_entry=next(item for item in onboarded['sources'] if item['symbol']=='EUR/USD')
    source=source_entry['pit_snapshot'];view=source_entry['source_view']
    native=read_source(root,source)['observations']
    inputs={'EUR/USD':[{k:r[k] for k in ('reference_time','value','status','reason_code','lineage','available_at','original_ingested_at','vintage_id')} for r in native]}
    for row in inputs['EUR/USD']:
        row['original_ingested_at']=row['original_ingested_at'].replace('Z','.000000Z')
    metadata={'EUR/USD':dict(meta,source_view=view)}
    spec=recipe('EURUSD',metadata,alignment)
    recipe_ref=add(store,'transformation_definition',{'profile':'fx_price.1.0.0',**spec['body']})
    dataset=add(store,'dataset_definition',{'kind':'fx_constructed_dataset','profile':'fx_price.1.0.0','instrument_id':'EURUSD',
        'economic_id':'FX_EUR_USD','recipe':recipe_ref,'source_metadata':meta})
    view=add(store,'source_view_definition',{'kind':'fx_constructed_view','profile':'fx_price.1.0.0','dataset':dataset,'recipe':recipe_ref,'source_metadata':meta})
    legs=normalize_legs(inputs,source_metadata=metadata)['EUR']
    leg=add(store,'snapshot_manifest',{'kind':'fx_normalized_leg','profile':'fx_price.1.0.0','currency':'EUR','upstream_snapshots':[source],
        'members':write_rows(store,legs,'normalized_fx_leg'),'semantic_content_sha256':digest(legs),'record_count':len(legs)})
    rows=construct_prices('EURUSD',inputs,source_metadata=metadata,alignment_policy=alignment)
    body={'kind':'fx_constructed_prices','profile':'fx_price.1.0.0','instrument_id':'EURUSD','economic_id':'FX_EUR_USD',
        'definition':view,'recipe':recipe_ref,'members':write_rows(store,rows,'canonical_fx_price'),'record_count':len(rows),
        'upstream_snapshots':[source],'normalized_legs':[leg],'semantic_content_sha256':digest(rows),
        'coverage':{'start':rows[0]['reference_time'],'end':rows[-1]['reference_time']},
        'valid_coverage':{'start':rows[0]['reference_time'],'end':rows[-1]['reference_time']},'status_counts':{'valid':len(rows)},'reason_counts':{},
        'construction':{'method':'direct','version':'1.0.0','price_basis':'unknown','alignment':'single_source_observation','policy':recipe_ref},'source_metadata':meta}
    return add(store,'snapshot_manifest',body),policy,rows


class FXTargetPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        shutil.copytree(PROJECT/'specs/schemas',self.root/'specs/schemas')
        self.snapshot,self.policy,self.prices=fixture(self.root)
    def tearDown(self):self.temp.cleanup()
    def build(self,**kw):return materialize(self.root,self.snapshot,self.policy,knowledge_cutoff='2026-10-09',**kw)
    def test_persisted_returns_missing_endpoints_and_weekday_horizon(self):
        outputs=self.build();self.assertEqual(len(outputs),2)
        result=read_materialization(self.root,outputs[0]['materialization']['id']);rows=result['observations']
        self.assertEqual(len(rows),4)
        self.assertEqual(rows[0]['value'],'0.05')
        missing=next(r for r in rows if r['prediction_anchor']=='2020-01-07')
        self.assertEqual((missing['exit_time'],missing['value'],missing['reason_code']),('2020-01-08',None,'MISSING_ENDPOINT'))
        self.assertEqual(rows[-1]['status'],'missing')
        self.assertTrue(all(not r['historical_eligibility_certified'] and r['label_available_at'] is None for r in rows))
    def test_repeat_reuses_same_materializations_and_payloads(self):
        first=self.build();files={str(p):p.stat().st_mtime_ns for p in self.root.rglob('*') if p.is_file()};second=self.build()
        self.assertEqual([x['materialization'] for x in first],[x['materialization'] for x in second]);self.assertTrue(all(x['reused'] for x in second))
        for p,stamp in files.items():
            if not p.endswith('.lock'):self.assertEqual(Path(p).stat().st_mtime_ns,stamp)
    def test_interruption_does_not_publish_ready_and_resumes(self):
        with self.assertRaises(InterruptedTargetPublication):self.build(fail_at='payloads')
        self.assertEqual(list(self.root.glob('storage/catalog/target_store/*/manifest.json')),[])
        self.assertEqual(len(self.build()),2)
    def test_unknown_availability_cannot_enter_historical_training(self):
        output=self.build()[0]
        result=retrieve_target(self.root,output['target_id'],output['materialization']['id'],training_cutoff='2025-01-01',cutoff_precision='date')
        self.assertEqual(result['observations'],[])
    def test_fresh_process_retrieval(self):
        output=self.build()[0]
        code='from data.targets.service import retrieve_target;import sys,json;r=retrieve_target(sys.argv[1],sys.argv[2],sys.argv[3]);print(json.dumps([r["observations"][0]["value"],len(r["observations"])]))'
        result=subprocess.run([sys.executable,'-c',code,str(self.root),output['target_id'],output['materialization']['id']],env=dict(os.environ,PYTHONPATH=str(PROJECT/'src'),PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout),['0.05',4])
    def test_targeted_endpoint_repair_keeps_interior_labels_and_identity(self):
        out=self.build()[1];result=read_materialization(self.root,out['materialization']['id']);before=result['observations']
        changed=self.prices[1]['id'];affected=affected_labels(before,[changed])
        row0=before[0];self.assertEqual(row0['exit_time'],'2020-01-07');self.assertNotIn(row0['id'],affected)
        repaired=copy.deepcopy(self.prices);repaired[1]['value']='115';repaired[1]['id']='FXPRICE_'+digest({k:v for k,v in repaired[1].items() if k not in ('id','duplicate_input_count')})
        after=construct_rows(result['definition'],repaired,result['schedule']['schedule'],result['schedule']['anchors'],'2026-10-09')
        for a,b in zip(before,after):
            if a['id'] not in affected:self.assertEqual(a,b)
        self.assertTrue(affected)
    def test_approved_weekday_calendar_zero_delay_and_no_holiday_exclusion(self):
        from data.targets.fx import _schedule,_definition
        from data.targets.scheduling import resolve_intervals
        store=TargetStore(self.root)
        policy=approve(store,dict(self.policy,horizons=[1,7,21,63,252]))
        config,anchors,schedule_policy=_schedule(store,policy,'2024-12-23','2025-01-03')
        self.assertIn('2024-12-25',[m['time'] for m in config['marks']])
        self.assertTrue(all(date.fromisoformat(m['time']).weekday()<5 for m in config['marks']))
        for horizon,anchor,expected in [(1,'2024-12-23','2024-12-24'),(1,'2024-12-27','2024-12-30'),(7,'2024-12-23','2025-01-01')]:
            definition=_definition(store,store.resolve(self.snapshot),policy,horizon,schedule_policy)
            body=definition['body'];intervals=resolve_intervals(config,anchors,body['entry'],body['horizon'],body['endpoint'])
            row=next(r for r in intervals if r['prediction_anchor']==anchor)
            self.assertEqual((row['entry_time'],row['exit_time']),(anchor,expected))
            self.assertEqual(approved_choices(policy)['schedule_semantics']['entry_interpretation'],'return_anchoring_only')
            self.assertFalse(approved_choices(policy)['alignment_semantics']['live_execution_certification'])
        # A declared holiday remains an expected missing endpoint; no skipping.
        definition=_definition(store,store.resolve(self.snapshot),policy,1,schedule_policy)
        prices=[]
        for when,value in [('2024-12-24','100'),('2024-12-26','102')]:
            prices.append(dict(self.prices[0],reference_time=when,value=value))
        rows=construct_rows(definition,prices,config,anchors,'2026-10-09')
        holiday=next(r for r in rows if r['prediction_anchor']=='2024-12-24')
        self.assertEqual((holiday['exit_time'],holiday['value'],holiday['reason_code']),('2024-12-25',None,'MISSING_ENDPOINT'))

    def test_approval_and_clock_required(self):
        policy=copy.deepcopy(self.policy);policy['approval_state']='pending'
        with self.assertRaises(ValueError):validate_batch_policy(policy)
        policy=copy.deepcopy(self.policy);policy['clock']='trading_sessions'
        with self.assertRaises(ValueError):validate_batch_policy(policy)
    def test_log_returns_supported_explicitly(self):
        self.policy['representation']='log';self.policy=approve(TargetStore(self.root),self.policy);out=self.build()[0];result=read_materialization(self.root,out['materialization']['id'])
        self.assertAlmostEqual(float(result['observations'][0]['value']),0.048790164169432)
    def test_catalog_retrospective_readiness_never_historical(self):
        self.build();items=list_targets(self.root)['targets'];self.assertEqual(len(items),2)
        self.assertTrue(all(x['readiness']=='uncertified' and x['readiness_capabilities']['retrospective_research']['decision']=='ready' for x in items))

    def test_same_day_capture_is_pending_and_next_day_is_eligible_only_retrospectively(self):
        out=self.build()[0];result=read_materialization(self.root,out['materialization']['id'])
        for cutoff in ('2025-01-01','2026-09-06'):
            rows=construct_rows(result['definition'],self.prices,result['schedule']['schedule'],result['schedule']['anchors'],cutoff)
            self.assertEqual((rows[0]['status'],rows[0]['reason_code'],rows[0]['value']),('pending','ENDPOINT_NOT_AVAILABLE',None))
            self.assertEqual(rows[0]['maturity'],'elapsed_endpoint')
            validate_row(rows[0])
        rows=construct_rows(result['definition'],self.prices,result['schedule']['schedule'],result['schedule']['anchors'],'2026-09-07')
        self.assertEqual(rows[0]['value'],'0.05');self.assertIsNone(rows[0]['label_available_at'])

    def test_known_source_defect_is_not_disguised_as_unknown_capture(self):
        output=self.build()[0];result=read_materialization(self.root,output['materialization']['id'])
        for status,reason,expected in [('missing','MISSING_REQUIRED_OBSERVATION','SOURCE_MISSING'),('invalid','CONFLICTING_OBSERVATIONS','SOURCE_INVALID')]:
            prices=copy.deepcopy(self.prices)
            prices[0].update(status=status,reason_code=reason,value=None,original_ingested_at=None)
            row=construct_rows(result['definition'],prices,result['schedule']['schedule'],result['schedule']['anchors'],'2026-10-09')[0]
            self.assertEqual((row['status'],row['reason_code'],row['value']),(status,expected,None))
            self.assertFalse(row['historical_eligibility_certified'])

    def test_unknown_capture_cannot_become_current_knowledge(self):
        out=self.build()[0];result=read_materialization(self.root,out['materialization']['id'])
        prices=copy.deepcopy(self.prices);prices[0]['original_ingested_at']=None
        rows=construct_rows(result['definition'],prices,result['schedule']['schedule'],result['schedule']['anchors'],'2026-10-09')
        self.assertEqual(rows[0]['reason_code'],'ENDPOINT_NOT_AVAILABLE');self.assertIsNone(rows[0]['original_capture_complete_at'])

    def test_date_endpoint_is_pending_through_same_day(self):
        out=self.build()[0];result=read_materialization(self.root,out['materialization']['id'])
        prices=copy.deepcopy(self.prices)
        for row in prices:row['original_ingested_at']='2019-01-01T00:00:00.000000Z'
        rows=construct_rows(result['definition'],prices,result['schedule']['schedule'],result['schedule']['anchors'],'2020-01-03')
        self.assertEqual((rows[0]['status'],rows[0]['reason_code'],rows[0]['maturity']),('pending','FUTURE_ENDPOINT','future_endpoint'))
        self.assertTrue(all(row['value'] is None for row in rows))

    def test_existing_approval_cannot_authorize_new_horizon_or_representation(self):
        for key,value in (('horizons',[1,5]),('representation','log')):
            policy=copy.deepcopy(self.policy);policy[key]=value
            with self.assertRaisesRegex(ValueError,'recorded approval'):materialize(self.root,self.snapshot,policy,knowledge_cutoff='2026-10-09')
        self.assertEqual(list(self.root.glob('storage/catalog/target_store/*/manifest.json')),[])

    def test_arbitrary_evidence_cannot_authorize_returns(self):
        store=TargetStore(self.root);policy=copy.deepcopy(self.policy)
        policy['approval_evidence']=add(store,'onboarding_evidence',{'kind':'not_a_scientific_approval'})
        with self.assertRaises(ValueError):materialize(self.root,self.snapshot,policy,knowledge_cutoff='2026-10-09')

    def test_retrospective_policy_must_preserve_unknown_availability(self):
        store=TargetStore(self.root);policy=copy.deepcopy(self.policy)
        body=copy.deepcopy(store.resolve(policy['retrospective_policy'])['body']);body['historical_replay']=True
        policy['retrospective_policy']=add(store,'policy_definition',body)
        with self.assertRaisesRegex(ValueError,'preserving unknown'):materialize(self.root,self.snapshot,policy,knowledge_cutoff='2026-10-09')

    def test_alignment_requires_its_specific_approved_choice(self):
        store=TargetStore(self.root)
        alignment={'id':'TEST_ALIGNMENT','version':'1.0.0','mode':'retrospective_date_label','approval_state':'approved',
            'approval_evidence':self.policy['approval_evidence'],'max_date_gap':0,'max_valuation_gap_seconds':None}
        self.assertEqual(validate_alignment_evidence(store,alignment),alignment)
        evidence=copy.deepcopy(store.resolve(self.policy['approval_evidence'])['body']);evidence['approved_policy']['retrospective_alignment']['max_date_gap']=1
        alignment['approval_evidence']=add(store,'onboarding_evidence',evidence)
        with self.assertRaisesRegex(ValueError,'does not authorize'):validate_alignment_evidence(store,alignment)

    def test_snapshot_cannot_claim_unrelated_source_view_or_currency(self):
        store=TargetStore(self.root);original=store.resolve(self.snapshot)['body']
        for key,value in (('economic_id','FX_GBP_USD'),('definition',original['upstream_snapshots'][0])):
            body=copy.deepcopy(original);body[key]=value
            bad=add(store,'snapshot_manifest',body)
            with self.assertRaises((ValueError,KeyError)):materialize(self.root,bad,self.policy,knowledge_cutoff='2026-10-09')

    def test_self_consistent_price_digest_cannot_hide_wrong_arithmetic(self):
        store=TargetStore(self.root);body=copy.deepcopy(store.resolve(self.snapshot)['body']);rows=copy.deepcopy(self.prices)
        rows[0]['value']='99';rows[0]['id']='FXPRICE_'+digest({k:v for k,v in rows[0].items() if k not in ('id','duplicate_input_count')})
        body['members']=write_rows(store,rows,'canonical_fx_price');body['semantic_content_sha256']=digest(rows)
        bad=add(store,'snapshot_manifest',body)
        with self.assertRaisesRegex(ValueError,'canonical operands'):materialize(self.root,bad,self.policy,knowledge_cutoff='2026-10-09')

    def test_price_coverage_cannot_omit_or_add_dates(self):
        store=TargetStore(self.root);body=copy.deepcopy(store.resolve(self.snapshot)['body']);body['coverage']['end']='2020-01-08'
        bad=add(store,'snapshot_manifest',body)
        with self.assertRaisesRegex(ValueError,'coverage'):materialize(self.root,bad,self.policy,knowledge_cutoff='2026-10-09')

    def test_compact_row_rejects_wrong_precision_operands_capture_and_decimal(self):
        output=self.build()[0];good=read_materialization(self.root,output['materialization']['id'])['observations'][0]
        variants=[('temporal_precision','utc_timestamp'),('value','5e-2'),('original_capture_complete_at','2026-09-06'),
            ('maturity','future_endpoint'),('operands',list(reversed(good['operands']))),('historical_eligibility_certified',True)]
        for key,value in variants:
            row=copy.deepcopy(good);row[key]=value;row['id']='TARGETOBS_'+digest({k:v for k,v in row.items() if k!='id'})
            with self.assertRaises(Exception):validate_row(row)

    def test_read_recalculates_rows_even_with_forged_consistent_payload_hash(self):
        output=self.build()[0];result=read_materialization(self.root,output['materialization']['id']);store=TargetStore(self.root)
        rows=copy.deepcopy(result['observations']);rows[0]['value']='42';rows[0]['id']='TARGETOBS_'+digest({k:v for k,v in rows[0].items() if k!='id'})
        manifest=copy.deepcopy(result['manifest']);manifest['partitions']=write_rows(store,rows,'target_observations')
        manifest['semantic_content_sha256']=digest(rows);manifest['input_key']['output_sha256']=digest(rows)
        manifest['id']='MATERIALIZATION_'+digest(manifest['input_key']);store.install_record(manifest)
        with self.assertRaisesRegex(ValueError,'pinned endpoints'):read_materialization(self.root,manifest['id'])

    def test_read_detects_forged_coverage_and_does_not_write(self):
        output=self.build()[0];identifier=output['materialization']['id']
        before={str(p):p.stat().st_mtime_ns for p in self.root.rglob('*') if p.is_file()}
        result=read_materialization(self.root,identifier)
        self.assertEqual(before,{str(p):p.stat().st_mtime_ns for p in self.root.rglob('*') if p.is_file()})
        manifest=copy.deepcopy(result['manifest']);manifest['coverage']['end']='2020-01-08'
        path=self.root/'storage/catalog/target_store'/identifier/'manifest.json';path.write_bytes(canonical_bytes(manifest))
        with self.assertRaisesRegex(ValueError,'coverage'):read_materialization(self.root,identifier)

    def test_manifest_rejects_wrong_binding_and_false_readiness(self):
        output=self.build()[0];good=read_materialization(self.root,output['materialization']['id'])['manifest']
        for key,value in (('definition',self.snapshot),('research_readiness','historically_certified'),('row_count',True)):
            bad=copy.deepcopy(good);bad[key]=value
            with self.assertRaises(Exception):validate_manifest(bad)

    def test_invalid_policy_shapes_fail_before_any_publication(self):
        for value in (None,{},[],True):
            with self.assertRaises(ValueError):validate_batch_policy(value)
        for horizons in (True,[True],[0],[-1],[1,1],[],[1.5],'1'):
            policy=copy.deepcopy(self.policy);policy['horizons']=horizons
            with self.assertRaises(ValueError):validate_batch_policy(policy)

if __name__=='__main__':unittest.main()
