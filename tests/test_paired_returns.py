"""Real synthetic Target/store/feature paths with isolated orchestration kernels."""
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4
import json

from data import fx_funding
from data.targets import fx_total
from data.targets.service import read_materialization,retrieve_target
from data.transformations.identity import reference
from research import inputs
from research.contracts import DISCOVERY_DIRECTION
from runtime.research_jobs import ResearchJobs
from test_fx_funding import captures
import test_research_inputs as research_fixture
from test_research_runtime import KernelSpy

class PairedTests(TestCase):
    def setUp(self):
        self.fixture=research_fixture.ResearchInputsTests(methodName='runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown);self.root=self.fixture.root
        self.funding=fx_funding.install(self.root,*captures())
        self.base=self.fixture.plan();self.bindings={}
        for h,binding in self.base['members'][0]['targets'].items():
            self.bindings[h]=fx_total.materialize(self.root,binding['materialization'],self.funding)
        config={'schema':'fx_total_return_release_v1','funding_model':reference(fx_total.policy()),
                'funding_snapshot':self.funding,'materializations':{'EURUSD':self.bindings}}
        (self.root/'config/fx_total_return.json').write_text(json.dumps(config))
        self.intent=dict(self.fixture.intent,target_family='total_return',expected_direction=DISCOVERY_DIRECTION)

    def test_target_roundtrip_strict_read_and_phase_only_arithmetic(self):
        binding=self.bindings['1'];result=read_materialization(self.root,binding['materialization']['id'])
        self.assertEqual(result['definition']['body']['construction']['basis'],'total_return')
        self.assertTrue(any(r['status']=='valid' for r in result['observations']))
        strict=retrieve_target(self.root,binding['definition']['id'],binding['materialization']['id'],
                               training_cutoff='2024-05-02',cutoff_precision='date')
        self.assertEqual(strict['observations'],[])
        plan=inputs.resolve_plan(self.root,self.intent,self.fixture.profile)
        prepared=inputs.prepare_phase(self.root,plan,'P1')
        common=inputs.load_phase(self.root,plan,prepared,'P1',1)
        from research.paired_returns import branch_data
        total=branch_data(self.root,plan,common,'total_return','P1',1)
        self.assertEqual(len(total['rows']),len(common['rows']))
        self.assertTrue(all(r['target_end']<'2024-03-01' for r in total['rows']))
        self.assertNotEqual([r['target'] for r in total['rows']],[r['target'] for r in common['rows']])

    def test_external_update_coverage_counts_only_financed_valid_rows(self):
        from research.paired_returns import branch_data
        funding=fx_funding.install(self.root,*captures(start='2024-02-01'))
        bindings={h:fx_total.materialize(self.root,b['materialization'],funding)
                  for h,b in self.base['members'][0]['targets'].items()}
        config={'schema':'fx_total_return_release_v1','funding_model':reference(fx_total.policy()),
                'funding_snapshot':funding,'materializations':{'EURUSD':bindings}}
        (self.root/'config/fx_total_return.json').write_text(json.dumps(config))
        plan=inputs.resolve_plan(self.root,self.intent,self.fixture.profile)
        prepared=inputs.prepare_phase(self.root,plan,'P1')
        common=inputs.load_phase(self.root,plan,prepared,'P1',1)
        for row in common['rows']:
            row['lineage']['original_observation']={'source_update':row['date']}
        spot_valid=sum(r['valid'] for r in common['rows'])
        common['coverage'][0]['valid_distinct_source_update_count']=spot_valid
        total=branch_data(self.root,plan,common,'total_return','P1',1)
        total_valid=sum(r['valid'] for r in total['rows'])
        self.assertGreater(total_valid,0)
        self.assertLess(total_valid,spot_valid)
        self.assertEqual(total['coverage'][0]['valid_distinct_source_update_count'],total_valid)
        self.assertEqual(common['coverage'][0]['valid_distinct_source_update_count'],spot_valid)

    def test_p1_does_not_decode_validation_target_values_in_shared_year_partition(self):
        from research.paired_returns import branch_data
        from data.alfred_onboarding import strict_json
        plan=inputs.resolve_plan(self.root,self.intent,self.fixture.profile)
        prepared=inputs.prepare_phase(self.root,plan,'P1');common=inputs.load_phase(self.root,plan,prepared,'P1',1)
        def guarded(raw):
            if isinstance(raw,bytes) and b'"record_type":"target_observation"' in raw and b'"schema_version":"0.10.0"' in raw:
                import re
                when=re.search(rb'"prediction_anchor":"([^"]+)"',raw).group(1).decode()
                self.assertLess(when,'2024-03-01')
            return strict_json(raw)
        with patch('data.targets.fx_total.strict_json',side_effect=guarded):
            total=branch_data(self.root,plan,common,'total_return','P1',1)
        self.assertTrue(total['rows'])

    def test_acceptance_freezes_metadata_without_reading_funding_or_target_values(self):
        with patch('data.fx_funding.load',side_effect=AssertionError('Funding values read')):
            plan=inputs.resolve_plan(self.root,self.intent,self.fixture.profile)
        self.assertEqual(plan['paired_returns']['families'],['price_return','total_return'])
        self.assertEqual(plan['members'][0]['targets'],self.base['members'][0]['targets'])
        self.assertEqual(plan['periods'],self.base['periods'])
        changed=deepcopy(self.intent);changed['expected_direction']='POSITIVE'
        with self.assertRaises(inputs.InputsBlocked):inputs.resolve_plan(self.root,changed,self.fixture.profile)

    def test_catalog_exposes_modelled_basis_without_claiming_historical_certification(self):
        from api.target_catalog import list_target_catalog
        catalog=list_target_catalog(self.root)
        modelled=[t for t in catalog['targets'] if t.get('return_model')=='modelled_total_return']
        self.assertEqual(len(modelled),5)
        self.assertTrue(all(t['return_basis']=='total_return' and t['readiness'] in ('uncertified','no_valid_labels') for t in modelled))
        self.assertFalse(any(issue.get('target_id') in {t['target_id'] for t in modelled} for issue in catalog['issues']))

    def test_release_gate_refuses_queued_work_and_never_adds_jobs(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
        from fx_total_return_release import idle
        from research.contracts import digest
        p=self.root/'storage/catalog/operations/jobs';p.mkdir(parents=True,exist_ok=True)
        rid=str(uuid4());aid=str(uuid4())
        base={'request_id':rid,'attempt_id':aid,'status':'queued'}
        event={'request_id':rid,'sequence':1,'job':base};sha=digest(event)
        ep=self.root/f'storage/catalog/attempts/{aid}/events/RESEVENT_{sha}.json'
        ep.parent.mkdir(parents=True);ep.write_text(json.dumps(event))
        (p/(rid+'.json')).write_text(json.dumps(dict(base,sequence=1,event_sha256=sha)))
        before={f.name:f.read_bytes() for f in p.glob('*.json')}
        with self.assertRaisesRegex(ValueError,'1 requests remain'):idle(self.root)
        self.assertEqual(before,{f.name:f.read_bytes() for f in p.glob('*.json')})

    def test_one_request_shares_preparation_and_keeps_independent_admission_and_signs(self):
        class Kernels(KernelSpy):
            def run_p1(self,rows,**kw):
                index=len([x for x in self.calls if x[0]=='P1']);total=index%2==1
                value=super().run_p1(rows,**kw)
                value['metrics']['primary_effect']=-2 if total else 1
                value['admission']='admitted' if kw['horizon']==1 or total and kw['horizon']==7 else 'rejected'
                return value
            def run_p2(self,rows,**kw):
                value=super().run_p2(rows,**kw);value['expected_direction']=kw['expected_direction'];return value
        kernel=Kernels();jobs=ResearchJobs(self.root,kernels=kernel);self.addCleanup(jobs.close)
        (self.root/'config/research_execution.json').write_text(json.dumps(self.fixture.profile))
        request=dict(self.intent,request_id=str(uuid4()))
        prepare=inputs.prepare_phase
        calls=[]
        def wrapped(*args,**kwargs):calls.append(args[2]);return prepare(*args,**kwargs)
        with (patch('research.contracts.profile_blockers',return_value=[]),
              patch('runtime.research_jobs.profile_blockers',return_value=[]),
              patch('research.inputs.prepare_phase',side_effect=wrapped)):
            jobs.submit(request);jobs.run_pending_once()
        job=jobs.get(request['request_id']);self.assertEqual(job['status'],'succeeded',job)
        self.assertEqual(calls,['P1','P2'])
        self.assertEqual(kernel.calls[:10],[('P1',h) for h in (1,7,21,63,252) for _ in range(2)])
        self.assertEqual(kernel.calls[10:],[('P2',1),('P2',1),('P2',7)])
        results=jobs.store.results_for_recipe(self.intent['feature']['id'])
        self.assertEqual(len(results),10)
        signs={(r['horizon'],r['target_family']):r['validation_direction'] for r in results}
        self.assertEqual(signs[(1,'price_return')],'POSITIVE');self.assertEqual(signs[(1,'total_return')],'NEGATIVE')
        self.assertEqual(job['horizons'][1]['paired_targets']['price_return']['p2_status'],'not_admitted')
        self.assertEqual(job['horizons'][1]['paired_targets']['total_return']['p2_status'],'VALIDATED')
        # Retrying the same accepted UUID never adds another pair of tests.
        again,created=jobs.submit(request);self.assertFalse(created);self.assertEqual(again['request_id'],request['request_id'])
