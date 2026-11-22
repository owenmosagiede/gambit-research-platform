"""Currency orientation and persisted price replay in isolated provider fixtures."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import shutil
import tempfile
import unittest
from data.feature_store import FeatureStore
from data.fx_currency_catalog import publish_prices,resolve_prices
from data.transformations.identity import reference
from data.transformations import fx_currency as currency
from data.targets.fx import _price_snapshot
from test_fx_onboarding import build_fixture
from test_fx_targets import approve
from data.fx_onboarding import onboard

class CurrencyPriceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.root,legacy,audit,_=build_fixture(Path(cls.temp.name))
        sources=onboard(cls.root,legacy,audit,migration_time='2026-10-09T10:00:00Z')['sources']
        cls.sources={s['symbol']:s['pit_snapshot'] for s in sources}
        cls.policy=approve(FeatureStore(cls.root),{'approval_state':'approved','representation':'simple','horizons':[1,7,21,63,252],
            'calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0','clock':'scheduled_bars',
            'entry':{'rule':'anchor_mark','delay':{'amount':0,'unit':'calendar_days'}},
            'endpoint':{'rule':'exact','tolerance':{'amount':0,'unit':'calendar_days'}}})
        cls.catalog=publish_prices(cls.root,cls.sources,cls.policy,'ISOLATED TEST: replace the old CS universes')
        _,cls.instruments=resolve_prices(cls.root,reference(cls.catalog),verify_rows=True)

    def test_all_seven_memberships_are_fixed(self):
        self.assertEqual(len(currency.CURRENCIES),19)
        self.assertEqual(len(self.instruments),126)
        for q in currency.REFERENCES:
            members=currency.members(q)
            self.assertEqual(len(members),18)
            self.assertEqual(members,sorted(members))
            self.assertNotIn(q+q,members)
            self.assertIn('NZD'+q,members)
            self.assertIn('CNH'+q,members)
            self.assertNotIn('CNY'+q,members)
        self.assertIn('MXNUSD',self.instruments)
        self.assertIn('NOKGBP',self.instruments)

    def test_reciprocal_and_cross_orientation(self):
        store=FeatureStore(self.root)
        def value(s):
            _,rows=_price_snapshot(store,self.instruments[s]['price_snapshot'],self.policy)
            return Decimal(rows[0]['value'])
        self.assertAlmostEqual(float(value('EURUSD')*value('USDEUR')),1)
        self.assertAlmostEqual(float(value('MXNEUR')),float(value('MXNUSD')/value('EURUSD')))
        self.assertAlmostEqual(float(value('NOKGBP')),float(value('NOKUSD')/value('GBPUSD')))

    def test_catalog_rerun_is_identical(self):
        again=publish_prices(self.root,self.sources,self.policy,'ISOLATED TEST: replace the old CS universes')
        self.assertEqual(again,self.catalog)

    def test_incomplete_sources_do_not_shrink_universe(self):
        with self.assertRaises(ValueError):publish_prices(self.root,{},self.policy,'test')

    def test_source_mismatch_is_rejected(self):
        bad=deepcopy(self.sources);bad['EUR/USD']=bad['GBP/USD']
        with self.assertRaises(ValueError):publish_prices(self.root,bad,self.policy,'test')

class CurrencyReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        from data.fx_currency_release import stage
        from data.scopes import register_fx_scopes
        from test_scopes import metadata_fixture,WHEN
        from test_research_inputs import approved_profile
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.root,legacy,audit,_=build_fixture(Path(cls.temp.name),days=('2020-01-02','2020-01-03','2020-01-06','2020-01-07','2020-01-08','2020-01-09','2020-01-10'))
        project=Path(__file__).resolve().parents[1]
        shutil.copytree(project/'definitions',cls.root/'definitions',dirs_exist_ok=True)
        shutil.rmtree(cls.root/'definitions/scopes')
        for path in (cls.root/'definitions/policies').glob('POLICY_FX_FIXED_RESEARCH_*'):shutil.rmtree(path)
        shutil.copytree(project/'storage',cls.root/'storage',dirs_exist_ok=True)
        sources=onboard(cls.root,legacy,audit,migration_time='2026-10-09T10:00:00Z')['sources']
        cls.sources={s['symbol']:s['pit_snapshot'] for s in sources}
        cls.policy=approve(FeatureStore(cls.root),{'approval_state':'approved','representation':'simple','horizons':[1,7,21,63,252],
            'calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0','clock':'scheduled_bars',
            'entry':{'rule':'anchor_mark','delay':{'amount':0,'unit':'calendar_days'}},
            'endpoint':{'rule':'exact','tolerance':{'amount':0,'unit':'calendar_days'}}})
        p=approved_profile();p['periods']={'P1':{'start_inclusive':'2020-01-02','end_exclusive':'2022-01-01'},
            'P2':{'start_inclusive':'2022-01-01','end_exclusive':'2023-01-01'}}
        p['target_selection']['knowledge_cutoff']='2026-10-09';p['exposure_classification']='previously_exposed'
        (cls.root/'config/research_execution.json').write_text(json.dumps(p))
        (cls.root/'config/fx_retrospective_completion.json').write_text(json.dumps({'knowledge_cutoff':'2026-10-09','return_policy':cls.policy}))
        metadata_fixture(cls.root);register_fx_scopes(cls.root,'isolated scopes',registered_at=WHEN)
        cls.release=stage(cls.root,cls.sources,cls.policy,'ISOLATED TEST: implement currency migration and delete legacy CS history')

    def test_complete_migration_and_frozen_inputs(self):
        from data.fx_currency_migration import plan,apply,check_staged_request,verify_applied
        from data.fx_currency_release import load_profile
        from data.scopes import list_scopes,resolve_scope
        from data.fx_currency_features import records
        from research.inputs import resolve_plan
        from research.feature_applications import resolve,ApplicationBlocked
        # Staging does not expose the seven new Scopes prematurely.
        self.assertEqual(list_scopes(self.root)['scope_count'],61)
        request={'source_snapshots':self.sources,'return_policy':self.policy}
        self.assertEqual(check_staged_request(self.root,reference(self.release),request),self.release)
        changed=deepcopy(request);changed['return_policy']['representation']='log'
        with self.assertRaisesRegex(ValueError,'frozen'):check_staged_request(self.root,reference(self.release),changed)
        manifest=plan(self.root,reference(self.release))
        self.assertEqual(manifest['blockers'],[])
        self.assertEqual(len(manifest['protected_ts']),86)
        apply(self.root,manifest,manifest['sha256'])
        verified=verify_applied(self.root,manifest)
        self.assertEqual(verified['active_ts_scopes'],43)
        self.assertEqual(verified['active_cs_scopes'],7)
        self.assertTrue(verified['sample_target_read'])
        result=list_scopes(self.root)
        self.assertEqual(result['issues'],[])
        self.assertEqual(result['scope_count'],50)
        self.assertEqual(sum(s['kind']=='universe' for s in result['scopes']),7)
        recipe=next(r for r in records(self.root).values() if r['body']['steps'][-1]['operator']['id']=='TR_BASE_change_diff'
            and r['body']['steps'][-1]['parameters']==[{'name':'k','unit':'observations','value':{'kind':'integer','value':'5'}}])
        selection={k:recipe[k] for k in ('id','version')}
        with self.assertRaises(ApplicationBlocked):resolve(self.root,selection,resolve_scope(self.root,'EURUSD','1.0.0'))
        intent={'feature':selection,'scope':{'id':'FX_CCY_VS_USD','version':'1.0.0'},'target_family':'price_return','expected_direction':'NEGATIVE'}
        frozen=resolve_plan(self.root,intent,load_profile(self.root))
        self.assertEqual(frozen['mode'],'CS');self.assertEqual(len(frozen['members']),18)
        self.assertEqual(frozen['scope']['reference_currency'],'USD')
        self.assertEqual(frozen['intent']['expected_direction'],'NEGATIVE')
        self.assertEqual(frozen['horizons'],[1,7,21,63,252])
        from research.feature_applications import validate_frozen
        damaged=deepcopy(frozen['scope']);damaged['reference_currency']='EUR'
        with self.assertRaises(ApplicationBlocked):validate_frozen(frozen['feature_application'],frozen['recipe'],damaged,'CS')
        from data.fx_feature_store import prepare_fx_feature,read_fx_materialization
        member=frozen['members'][0]
        saved=prepare_fx_feature(self.root,member['feature'],price_snapshot=member['price_snapshot'],
            batch_policy=frozen['batch_policy'],knowledge_cutoff=frozen['knowledge_cutoff'],start='2020-01-02',end='2020-01-10')
        output=read_fx_materialization(self.root,saved['materialization']['id'])
        self.assertEqual(output['manifest']['input_key']['source_snapshots'],[member['price_snapshot']])
        self.assertTrue(all(r['entity_id']==member['instrument_id'] for r in output['observations']))
        import math
        _,prices=_price_snapshot(FeatureStore(self.root),member['price_snapshot'],frozen['batch_policy'])
        self.assertAlmostEqual(float(output['observations'][-1]['value']),math.log(float(prices[-1]['value'])/float(prices[1]['value'])))
        self.assertTrue(apply(self.root,manifest,manifest['sha256'])['reused'])

    def test_momentum_catalog_preserves_inputs_without_numerical_replay(self):
        from unittest.mock import patch
        from data.fx_currency_features import build_momentum_catalog,records,bindings
        from data.fx_currency_catalog import activate,add
        from data.fx_currency_release import validate_release
        from data.fx_feature_recipes import MOMENTUM_CONFIGURATION_PROFILE
        from data.fx_records import make_record
        store=FeatureStore(self.root)
        original=store.resolve(self.release['body']['feature_catalog'])
        catalog=build_momentum_catalog(self.root,reference(original))
        self.assertEqual(catalog['body']['configuration_profile'],MOMENTUM_CONFIGURATION_PROFILE)
        self.assertEqual(len(catalog['body']['recipes']),53)
        self.assertEqual(len(catalog['body']['bindings']),6678)
        self.assertEqual(catalog['body']['price_catalog'],original['body']['price_catalog'])
        self.assertTrue(all(b in original['body']['bindings'] for b in catalog['body']['bindings']))
        store.install_record(catalog)
        body=deepcopy(self.release['body']);body['feature_catalog']=reference(catalog)
        release=add(store,'onboarding_evidence',body);activate(self.root,release)
        self.addCleanup(activate,self.root,self.release)
        with patch('data.fx_currency_release.read_materialization',side_effect=AssertionError('Bulk numerical replay forbidden in metadata mode')):
            validate_release(self.root,release,numerical=False)
        self.assertEqual(len(records(self.root)),53)
        first=catalog['body']['recipes'][0]['recipe']
        self.assertEqual(len(bindings(self.root,first)),126)
        self.assertEqual(release['body']['research_spec'],self.release['body']['research_spec'])
        bad_body=deepcopy(catalog['body']);bad_body['recipes'].pop()
        bad=make_record('onboarding_evidence',bad_body);store.install_record(bad)
        bad_release=add(store,'onboarding_evidence',dict(body,feature_catalog=reference(bad)))
        activate(self.root,bad_release)
        with self.assertRaisesRegex(ValueError,'Incomplete currency Feature family'):records(self.root)

    def _funded_fixture(self):
        """One real, small persisted CS release reused by these adapter checks."""
        import csv,io,json,sys
        from zipfile import ZipFile,ZIP_DEFLATED
        from unittest.mock import patch
        from data import fx_funding
        from data.fx_currency_catalog import activate
        from data.targets import fx_total
        from research.contracts import canonical,ref
        from test_fx_funding import captures
        from test_research_schedule import SCHEDULE_PATH
        activate(self.root,self.release)
        schedule=json.loads(SCHEDULE_PATH.read_bytes())
        (self.root/'config/research_schedule.json').write_bytes(canonical(ref(schedule))+b'\n')
        if not hasattr(type(self),'funded_config'):
            raw,sora=captures('2020-01-01','2020-01-15')
            with ZipFile(io.BytesIO(raw)) as archive:
                rows=list(csv.reader(io.StringIO(archive.read(archive.namelist()[0]).decode())))
            for row in rows[1:]:
                if row[1].split(':')[0]==fx_funding.CURRENCIES['EUR'] and row[2]=='2020-01-09':
                    row[3]='';row[6]='L: Missing value; not collected'
            text=io.StringIO();csv.writer(text).writerows(rows);blob=io.BytesIO()
            with ZipFile(blob,'w',ZIP_DEFLATED) as archive:archive.writestr('WS_CBPOL_csv_flat.csv',text.getvalue())
            funding=fx_funding.install(self.root,blob.getvalue(),sora)
            ts={'schema':'fx_total_return_release_v1','funding_model':reference(fx_total.policy()),
                'funding_snapshot':funding,'materializations':{}}
            (self.root/'config/fx_total_return.json').write_text(json.dumps(ts))
            request={'currency_release':reference(self.release),'funding_snapshot':funding,
                'funding_model':reference(fx_total.policy()),
                'request_text':'ISOLATED TEST: matched seventeen-member Spot and Total Return currency universes; preserve the original eighteen-member universes.'}
            sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
            import fx_total_return_cs_release as tool
            preview=tool.migrate(self.root,request)
            original=(self.root/'config/fx_total_return.json').read_bytes()
            with self.assertRaisesRegex(ValueError,'reviewed'):
                tool.migrate(self.root,request,apply=True,expected_plan_sha256='0'*64)
            with patch.object(tool,'admissions_closed',return_value=False):
                with self.assertRaisesRegex(ValueError,'admissions'):
                    tool.migrate(self.root,request,apply=True,expected_plan_sha256=preview['plan_sha256'])
            self.assertFalse((self.root/'config/fx_total_return_cs.json').exists())
            with patch.object(tool,'admissions_closed',return_value=True):
                installed=tool.migrate(self.root,request,apply=True,expected_plan_sha256=preview['plan_sha256'])
            self.assertEqual(installed['research_jobs_created'],0)
            self.assertEqual((self.root/'config/fx_total_return.json').read_bytes(),original)
            type(self).funded_config=(self.root/'config/fx_total_return_cs.json').read_bytes()
        (self.root/'config/fx_total_return_cs.json').write_bytes(type(self).funded_config)
        from data.fx_currency_features import records
        recipe=next(r for r in records(self.root).values() if r['body']['steps'][-1]['operator']['id']=='TR_BASE_change_diff'
            and r['body']['steps'][-1]['parameters']==[{'name':'k','unit':'observations','value':{'kind':'integer','value':'5'}}])
        from research.contracts import DISCOVERY_DIRECTION
        intent={'feature':{k:recipe[k] for k in ('id','version')},
            'scope':{'id':'FX_CCY_FUNDED_VS_USD','version':'1.0.0'},
            'target_family':'total_return','expected_direction':DISCOVERY_DIRECTION}
        self.addCleanup((self.root/'config/research_schedule.json').unlink,missing_ok=True)
        return intent

    def test_total_return_fixed_companions_and_metadata_freeze(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from data.scopes import resolve_scope,list_scopes
        from data.fx_total_return_cs import load_release
        from runtime.experiment_identity import freeze
        from runtime.research_jobs import implementation
        intent=self._funded_fixture();config=load_release(self.root)
        self.assertEqual(len(config['materializations']),119)
        self.assertEqual(sum(map(len,config['materializations'].values())),476)
        for quote in currency.REFERENCES:
            original=resolve_scope(self.root,'FX_CCY_VS_'+quote,'1.0.0')
            funded=resolve_scope(self.root,'FX_CCY_FUNDED_VS_'+quote,'1.0.0')
            self.assertEqual(len(original['members']),18)
            self.assertEqual(funded['members'],[s for s in original['members'] if not s.startswith('CNH')])
            self.assertEqual(funded['member_count'],17)
            self.assertEqual(funded['price_catalog'],original['price_catalog'])
        self.assertEqual(list_scopes(self.root)['scope_count'],57)
        with patch('data.fx_funding.load',side_effect=AssertionError('Acceptance decoded funding values')):
            packet=freeze(SimpleNamespace(root=self.root,adapter=None),intent,implementation())
        plan=packet['frozen_plan']
        self.assertEqual(plan['mode'],'CS');self.assertEqual(plan['horizons'],[1,7,21,63])
        self.assertEqual(len(plan['members']),17)
        self.assertEqual(plan['paired_returns']['comparison_membership'],plan['scope']['membership_snapshot'])
        from research.paired_returns import branch_plan
        total=branch_plan(plan,'total_return')
        self.assertEqual(total['scope'],plan['scope'])
        for member in total['members']:
            self.assertEqual(member['targets'],config['materializations'][member['instrument_id']])
        # USD against EUR must earn USD funding and pay EUR funding, using its
        # reciprocal spot Target rather than a sign-flipped EURUSD return.
        from data.targets.fx_total import read as read_total
        from decimal import localcontext
        from datetime import date
        sample=read_total(self.root,config['materializations']['USDEUR']['1']['materialization']['id'])
        row=next(r for r in sample['observations'] if r['status']=='valid')
        days=(date.fromisoformat(row['exit_time'])-date.fromisoformat(row['entry_time'])).days
        with localcontext() as context:
            context.prec=50
            expected=(1+Decimal(row['spot_return']))*(1+Decimal('.05')/365)**days-(1+Decimal('.04')/365)**days
        self.assertLess(abs(Decimal(row['value'])-expected),Decimal('1e-45'))
        self.assertEqual(row['currency'],'EUR')
        from research import inputs
        wrong=dict(intent,scope={'id':'FX_CCY_VS_USD','version':'1.0.0'})
        with self.assertRaisesRegex(inputs.InputsBlocked,'seventeen-member'):
            freeze(SimpleNamespace(root=self.root,adapter=None),wrong,implementation())
        import json
        changed=deepcopy(config);changed['materializations']['EURUSD']['1']=changed['materializations']['AUDUSD']['1']
        path=self.root/'config/fx_total_return_cs.json';path.write_text(json.dumps(changed))
        try:
            with self.assertRaisesRegex(inputs.InputsBlocked,'frozen spot'):
                freeze(SimpleNamespace(root=self.root,adapter=None),intent,implementation())
        finally:path.write_bytes(type(self).funded_config)

    def test_total_return_all_members_phase_boundaries_and_missing_funding(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from data import fx_funding
        from data.targets import fx_total
        from data.verified_inputs import execution_inputs
        from runtime.experiment_identity import freeze
        from runtime.research_jobs import implementation
        from research.inputs import _load_target
        from research.paired_returns import branch_data
        intent=self._funded_fixture()
        plan=freeze(SimpleNamespace(root=self.root,adapter=None),intent,implementation())['frozen_plan']
        period=plan['periods']['P1'];rows=[];coverage=[]
        for index,member in enumerate(plan['members']):
            spots,_=_load_target(self.root,member,plan,period,1)
            for spot in spots:
                rows.append({'date':spot['prediction_anchor'],'instrument':member['instrument_id'],
                    'feature':str(index),'target':spot['value'],'target_end':spot['exit_time'],
                    'valid':spot['status']=='valid','status':spot['status'],'reason_codes':[],
                    'lineage':{'target_row_id':spot['id']}})
            coverage.append({'instrument_id':member['instrument_id'],'scheduled_rows':len(spots)})
        common={'members':plan['scope']['members'][:],'rows':rows,'coverage':coverage,'lineage':{}}
        before=deepcopy(common)
        with execution_inputs(self.root,{'test':'matched-CS'},max_bytes=32*1024*1024):
            with patch('data.fx_funding._load',wraps=fx_funding._load) as funding_reads:
                total=branch_data(self.root,plan,common,'total_return','P1',1)
                self.assertEqual(funding_reads.call_count,1)
        self.assertEqual(common,before)
        self.assertEqual(total['members'],common['members']);self.assertEqual(len(total['rows']),len(rows))
        self.assertEqual(len(total['coverage']),17)
        selected=lambda data:[r for r in data['rows'] if r['date']=='2020-01-09']
        self.assertEqual(len(selected(total)),17)
        self.assertTrue(all(r['valid'] for r in selected(common)))
        self.assertEqual([r['instrument'] for r in selected(total) if not r['valid']],['EURUSD'])
        self.assertEqual(next(r for r in selected(total) if not r['valid'])['reason_codes'],['FUNDING_NOT_AVAILABLE'])
        self.assertTrue(all(r['lineage']['target_materialization']==
            plan['paired_returns']['total_targets'][r['instrument']]['1']['materialization'] for r in total['rows']))
        # An otherwise usable CS date loses completeness; no member disappears.
        complete=lambda data:{d for d in {r['date'] for r in data['rows']}
            if len([r for r in data['rows'] if r['date']==d and r['valid']])==17}
        self.assertEqual(complete(total),complete(common)-{'2020-01-09'})
        # P1 must not decode P2 values sharing the same stored year partition.
        bounded=deepcopy(plan);bounded['periods']['P1']['end_exclusive']='2020-01-08'
        from research.inputs import _plan_id
        bounded['plan_id']=_plan_id(bounded)
        bounded_common=deepcopy(common);bounded_common['rows']=[r for r in rows if r['date']<'2020-01-07']
        from data.alfred_onboarding import strict_json
        def guarded(raw):
            if isinstance(raw,bytes) and b'"record_type":"target_observation"' in raw and b'"schema_version":"0.10.0"' in raw:
                import re
                when=re.search(rb'"prediction_anchor":"([^"]+)"',raw).group(1).decode()
                self.assertLess(when,'2020-01-08')
            return strict_json(raw)
        with patch('data.targets.fx_total.strict_json',side_effect=guarded):
            limited=branch_data(self.root,bounded,bounded_common,'total_return','P1',1)
        self.assertEqual(limited['members'],common['members'])

    def test_total_return_cs_orchestration_keeps_independent_decisions(self):
        from unittest.mock import patch
        from uuid import uuid4
        from runtime.research_jobs import ResearchJobs
        from research import inputs
        from test_research_runtime import KernelSpy
        intent=self._funded_fixture()
        class Kernels(KernelSpy):
            def run_p1(self,rows,**kw):
                self_mode=kw['mode'];assert self_mode=='CS'
                total=len([c for c in self.calls if c[0]=='P1'])%2==1
                value=super().run_p1(rows,**kw);value['metrics']['primary_effect']=-.5 if total else .5
                value['admission']='admitted' if kw['horizon']==1 or total and kw['horizon']==7 else 'rejected'
                return value
            def run_p2(self,rows,**kw):
                value=super().run_p2(rows,**kw);value['expected_direction']=kw['expected_direction'];return value
        kernel=Kernels();jobs=ResearchJobs(self.root,kernels=kernel);self.addCleanup(jobs.close)
        request=dict(intent,request_id=str(uuid4()));calls=[];prepare=inputs.prepare_phase
        def wrapped(*args,**kwargs):calls.append(args[2]);return prepare(*args,**kwargs)
        with patch('research.inputs.prepare_phase',side_effect=wrapped):
            jobs.submit(request);jobs.run_pending_once()
        job=jobs.get(request['request_id']);self.assertEqual(job['status'],'succeeded',job)
        self.assertEqual(job['mode'],'CS');self.assertEqual(calls,['P1','P2'])
        self.assertEqual(kernel.calls[:8],[('P1',h) for h in (1,7,21,63) for _ in range(2)])
        self.assertEqual(kernel.calls[8:],[('P2',1),('P2',1),('P2',7)])
        results=jobs.store.results_for_recipe(intent['feature']['id'])
        signs={(r['horizon'],r['target_family']):r['validation_direction'] for r in results}
        self.assertEqual(signs[(1,'price_return')],'POSITIVE')
        self.assertEqual(signs[(1,'total_return')],'NEGATIVE')
        again,created=jobs.submit(request);self.assertFalse(created)
        self.assertEqual(again['request_id'],request['request_id'])

class CurrencySemanticsTests(unittest.TestCase):
    def test_downside_is_recomputed_on_inverse_price_not_sign_flipped(self):
        from data.transformations.numeric import calculate
        prices=[10.,8.,12.,9.,13.]
        inverse=[1/p for p in prices]
        params={'w':4,'basis':'log'}
        downside=calculate('vol.downside',prices,params)[-1]['value']
        inverse_downside=calculate('vol.downside',inverse,params)[-1]['value']
        upside=calculate('vol.upside',prices,params)[-1]['value']
        self.assertAlmostEqual(inverse_downside,upside)
        self.assertNotAlmostEqual(inverse_downside,-downside)

    def test_simple_inverse_return_is_not_negative_forward_return(self):
        initial,final=10.,12.
        forward=final/initial-1
        inverse=(1/final)/(1/initial)-1
        self.assertAlmostEqual(inverse,-forward/(1+forward))
        self.assertNotAlmostEqual(inverse,-forward)
