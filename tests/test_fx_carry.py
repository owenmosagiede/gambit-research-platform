"""Independent carry arithmetic, causal windows, missing states and native routing."""
from copy import deepcopy
from datetime import date, timedelta
import math
from pathlib import Path
from statistics import mean, stdev
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from data import fx_carry as carry
from data.transformations.identity import canonical_bytes, digest, reference
from data.feature_store import FeatureStore
from research import inputs


def fixture(count=1400):
    prices=[]; rates={'EUR': [], 'USD': []}; days=[]; day=date(2010, 1, 4)
    while len(days)<count:
        if day.weekday()<5: days.append(day.isoformat())
        day+=timedelta(days=1)
    for i, day in enumerate(days):
        prices.append({'reference_time':day, 'status':'valid', 'value':str(math.exp(0.0001*i+0.01*math.sin(i/7)))})
        for c, v in [('EUR', str(2+i/10000)), ('USD','1')]:
            rates[c].append({'date':day,'rate_pct':v,'observation_status':'A: Normal value','source_row_sha256':digest([c,day,v])})
    return prices,rates,days


class CarryCalculationTests(unittest.TestCase):
    def test_five_fixed_distinct_definitions_and_no_PIT_claim(self):
        self.assertEqual(len(carry.FAMILIES),5)
        records=[carry.recipe(f) for f in carry.FAMILIES]
        self.assertEqual(len({r['id'] for r in records}),5)
        for r in records:
            self.assertEqual(carry.validate_record(r),r)
            self.assertFalse(r['body']['historical_pit_certified'])
            changed=deepcopy(r); changed['body']['rules']['unit']='invented'
            with self.assertRaises(ValueError): carry.validate_record(changed)

    def test_nominal_level_and_pair_reversal(self):
        p,r,d=fixture(80)
        a=carry.scores(p,r,'EURUSD','level'); b=carry.scores(p,r,'USDEUR','level')
        self.assertAlmostEqual(float(a[79]['value']),1+79/10000)
        self.assertAlmostEqual(float(a[79]['value']),-float(b[79]['value']))
        self.assertEqual(a[79]['first_anchor'],carry.next_weekday(d[-1]))

    def test_change_uses_exact_63_weekday_endpoint(self):
        p,r,d=fixture(80); rows=carry.scores(p,r,'EURUSD','change_63')
        self.assertTrue(all(x['value'] is None for x in rows[:63]))
        self.assertAlmostEqual(float(rows[63]['value']),63/10000)
        self.assertEqual(rows[63]['operands']['lookback_differential'],1)

    def test_zscore_uses_prior_1260_complete_values_excluding_current(self):
        p,r,d=fixture(1262); rows=carry.scores(p,r,'EURUSD','relative_1260')
        history=[1+i/10000 for i in range(1260)]
        self.assertIsNone(rows[1259]['value'])
        self.assertAlmostEqual(float(rows[1260]['value']),((1+1260/10000)-mean(history))/stdev(history),places=10)
        r['EUR'][100]['rate_pct']=None
        self.assertIsNone(carry.scores(p,r,'EURUSD','relative_1260')[1260]['value'])

    def test_rate_lookbacks_use_available_history_before_pair_prices_begin(self):
        p,r,d=fixture(1400)
        late_prices=p[1300:]
        row=carry.scores(late_prices,r,'EURUSD','relative_1260',end_exclusive=d[1301])[0]
        history=[1+i/10000 for i in range(40,1300)]
        self.assertEqual(row['date'],d[1300])
        self.assertAlmostEqual(float(row['value']),((1+1300/10000)-mean(history))/stdev(history),places=10)
        change=carry.scores(late_prices,r,'EURUSD','change_63',end_exclusive=d[1301])[0]
        self.assertAlmostEqual(float(change['value']),63/10000,places=10)
        risk=carry.scores(late_prices,r,'EURUSD','risk_63',end_exclusive=d[1301])[0]
        self.assertIsNone(risk['value'])

    def test_risk_uses_prices_before_the_first_available_rate(self):
        p,r,d=fixture(170)
        late_rates={'EUR':r['EUR'][100:],'USD':r['USD'][80:]}
        rows=carry.scores(p,late_rates,'EURUSD','risk_63',end_exclusive=d[101])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['date'],d[100])
        self.assertIsNotNone(rows[0]['value'],'Available prior prices must warm volatility at the first rate date')
        returns=[math.log(float(p[i]['value'])/float(p[i-1]['value'])) for i in range(37,100)]
        expected=((1+100/10000)/100)/(stdev(returns)*math.sqrt(252))
        self.assertAlmostEqual(float(rows[0]['value']),expected,places=10)
        changed=deepcopy(p);changed[100]['value']='999'
        self.assertEqual(rows,carry.scores(changed,late_rates,'EURUSD','risk_63',end_exclusive=d[101]))
        missing=deepcopy(p);missing[99].update(status='missing',value=None)
        self.assertIsNone(carry.scores(missing,late_rates,'EURUSD','risk_63',end_exclusive=d[101])[0]['value'])

    def test_risk_denominator_excludes_current_close(self):
        p,r,d=fixture(80); rows=carry.scores(p,r,'EURUSD','risk_63')
        changes=[math.log(float(p[i]['value'])/float(p[i-1]['value'])) for i in range(1,64)]
        expected=((1+64/10000)/100)/(stdev(changes)*math.sqrt(252))
        self.assertAlmostEqual(float(rows[64]['value']),expected,places=10)
        changed=deepcopy(p); changed[64]['value']='999'
        self.assertEqual(rows[64],carry.scores(changed,r,'EURUSD','risk_63')[64])
        self.assertNotEqual(rows[65]['value'],carry.scores(changed,r,'EURUSD','risk_63')[65]['value'])

    def test_unknown_null_resets_but_nonexistent_day_carries_without_backfill(self):
        p,r,d=fixture(10); r['EUR'][3]['rate_pct']=None
        rows=carry.scores(p,r,'EURUSD','level'); self.assertIsNone(rows[3]['value']); self.assertIsNotNone(rows[4]['value'])
        r['EUR'][3]['observation_status']='M: Missing value; data cannot exist'
        self.assertEqual(carry.scores(p,r,'EURUSD','level')[3]['value'],rows[2]['value'])
        r['EUR'][3]['observation_status']='A: Normal value'; r['EUR'][3]['rate_pct']='4'
        self.assertEqual(rows[2],carry.scores(p,r,'EURUSD','level')[2])

    def test_future_rates_cannot_change_a_prefix(self):
        p,r,d=fixture(80)
        for f in ('level','risk_63','change_63'):
            original=carry.scores(p,r,'EURUSD',f,end_exclusive=d[70])
            changed=deepcopy(r); changed['EUR'][70]['rate_pct']='99'
            self.assertEqual(original,carry.scores(p,changed,'EURUSD',f,end_exclusive=d[70]))

    def test_real_proxy_waits_for_common_actual_year_and_freezes_first_actual(self):
        p,r,d=fixture(10)
        def inflation(c, edition, year, available, value, actual=1):
            return {'currency':c,'edition':edition,'year':year,'available_on':available,'value_pct':value,'is_actual':actual,'actual_evidence':'synthetic_publication'}
        inflation_rows=[inflation('EUR','2009-oct',2009,d[1],'2'),inflation('USD','2009-oct',2009,d[3],'1'),
            inflation('EUR','2010-apr',2009,d[5],'9'),inflation('EUR','2010-apr',2010,d[5],'0.1',0)]
        rows=carry.scores(p,r,'EURUSD','real_actual',inflation_rows)
        self.assertIsNone(rows[2]['value']); self.assertAlmostEqual(float(rows[3]['value']),3/10000)
        self.assertEqual(rows[6]['operands']['inflation']['base']['value_pct'],'2')
        self.assertEqual(rows[6]['operands']['inflation']['reference_year'],2009)

    def test_missing_price_breaks_exact_return_window_and_constant_vol_is_unavailable(self):
        p,r,d=fixture(80)
        for x in p:x['value']='1'
        self.assertIsNone(carry.scores(p,r,'EURUSD','risk_63')[70]['value'])
        p,r,d=fixture(80);p[20]['status']='missing';p[20]['value']=None
        self.assertIsNone(carry.scores(p,r,'EURUSD','risk_63')[70]['value'])


class CarryRoutingTests(unittest.TestCase):
    def setUp(self):
        from test_research_inputs import ResearchInputsTests
        self.fixture=ResearchInputsTests(methodName='runTest');self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
        self.root=self.fixture.root; store=FeatureStore(self.root); self.feature=carry.recipe('level');store.install_record(self.feature)
        from data.fx_funding import install
        from test_fx_funding import captures
        self.funding=install(self.root,*captures())
        from research.feature_applications import install_binding,CARRY_PAIR
        install_binding(self.root,self.feature,CARRY_PAIR)
        # Source capture acquisition is the fixture boundary; arithmetic/window
        # tests above are independent. Native plan, phase and Target routing run.
        self.rows=[{'date':'2024-01-01','first_anchor':'2024-01-02','value':'1','reason':None,'operands':{}},
                   {'date':'2024-01-02','first_anchor':'2024-01-03','value':None,'reason':'RATE_STATE_UNAVAILABLE','operands':{}},
                   {'date':'2024-01-03','first_anchor':'2024-01-04','value':'2','reason':None,'operands':{}},
                   {'date':'2024-03-01','first_anchor':'2024-03-04','value':'99','reason':None,'operands':{}}]
        self.replay=patch.object(carry,'calculate',side_effect=lambda *a,**kw:([r for r in self.rows if r['date']<kw['end_exclusive']],{}))
        self.replay.start();self.addCleanup(self.replay.stop)
        snapshot=carry.record('snapshot_manifest',{'kind':'fx_carry_feature_snapshot_v1','family':'level','pair':'EURUSD',
            'recipe':reference(self.feature),'price_snapshot':self.fixture.fx.snapshot,'funding_snapshot':self.funding,
            'inflation_capture':None,'observations':store.io.blob(b''.join(canonical_bytes(r)+b'\n' for r in self.rows),'jsonl','carry_observations',len(self.rows)),
            'row_count':len(self.rows),'first_anchor':'2024-01-02','coverage':{str(h):{'exclusion':None} for h in (1,7,21,63)},
            'source_timing':'retrospective_rate_and_spot_date_labels_not_PIT'})
        store.install_record(snapshot);self.snapshot=reference(snapshot)
        p=self.root/'storage/catalog/fx_carry'/self.feature['id']/'EURUSD.json';p.parent.mkdir(parents=True);p.write_bytes(canonical_bytes({'snapshot':self.snapshot})+b'\n')
        from research.schedule import apply_schedule
        profile=dict(self.fixture.profile,exposure_classification={'untouched_holdout_claim':False})
        schedule={'id':'TEST_CARRY_SCHEDULE','version':'1.0.0','horizons':[1,7,21,63],
            'price_time_series':{'default':profile['periods'],'63':profile['periods']}}
        self.profile=apply_schedule(profile,schedule,price_time_series=True)
        intent=deepcopy(self.fixture.intent);intent['feature']={k:self.feature[k] for k in ('id','version')}
        self.intent=intent;self.plan=inputs.resolve_plan(self.root,intent,self.profile)

    def test_frozen_plan_binds_new_adapter_pair_and_exact_sources(self):
        self.assertEqual(self.plan['application_class'],'fx_carry_pair_ts')
        self.assertEqual(self.plan['carry_source']['snapshot'],self.snapshot)
        self.assertEqual(self.plan['members'][0]['feature'],reference(self.feature))
        self.assertEqual(self.plan['horizons'],[1,7,21,63]);inputs._validate_plan(self.plan)
        changed=deepcopy(self.plan);changed['carry_source']['pair']='USDJPY';changed['plan_id']=inputs._plan_id(changed)
        with self.assertRaises(ValueError):
            inputs.prepare_phase(self.root,changed,'P1')

    def test_phase_loader_never_decodes_P2_feature_scores_and_requires_exact_anchor(self):
        from data.alfred_onboarding import strict_json
        def guard(raw):
            r=strict_json(raw)
            if 'date' in r:self.assertLess(r['date'],'2024-03-01')
            return r
        with patch('data.alfred_onboarding.strict_json',side_effect=guard):
            prepared=inputs.prepare_phase(self.root,self.plan,'P1');data=inputs.load_phase(self.root,self.plan,prepared,'P1',1)
        rows={r['date']:r for r in data['rows']}
        self.assertEqual(rows['2024-01-02']['feature'],'1')
        self.assertIsNone(rows['2024-01-03']['feature'])
        self.assertEqual(rows['2024-01-04']['feature'],'2')
        self.assertIsNone(rows['2024-01-05']['feature'])
        self.assertTrue(all(not r['historical_eligibility_certified'] for r in data['rows']))

    def test_registry_list_and_signal_presentation(self):
        from api.feature_library import list_feature_library
        from api.signal_summaries import _registered_entry,_output_candidates
        listed=list_feature_library(self.root)
        self.assertIn(self.feature['id'],[r['id'] for r in listed['features']])
        entry=_registered_entry(FeatureStore(self.root),self.feature)
        self.assertEqual(entry['name'],self.feature['display_name']);self.assertEqual(_output_candidates(self.root,self.feature),{})

    def test_paired_target_branches_share_features_and_preserve_funding_lineage(self):
        import json
        from data.targets import fx_total
        from research.contracts import DISCOVERY_DIRECTION
        from research.paired_returns import branch_data
        bindings={h:fx_total.materialize(self.root,b['materialization'],self.funding)
                  for h,b in self.plan['members'][0]['targets'].items()}
        (self.root/'config/fx_total_return.json').write_text(json.dumps({'schema':'fx_total_return_release_v1',
            'funding_model':reference(fx_total.policy()),'funding_snapshot':self.funding,
            'materializations':{'EURUSD':bindings}}))
        intent=dict(self.intent,target_family='total_return',expected_direction=DISCOVERY_DIRECTION)
        plan=inputs.resolve_plan(self.root,intent,self.profile)
        self.assertEqual(plan['carry_source']['funding_snapshot'],plan['paired_returns']['funding_snapshot'])
        prepared=inputs.prepare_phase(self.root,plan,'P1')
        spot=inputs.load_phase(self.root,plan,prepared,'P1',1)
        total=branch_data(self.root,plan,spot,'total_return','P1',1)
        self.assertEqual([r['feature'] for r in spot['rows']],[r['feature'] for r in total['rows']])
        self.assertEqual([r['date'] for r in spot['rows']],[r['date'] for r in total['rows']])
        self.assertTrue(all(r['lineage']['funding_snapshot']==self.funding for r in total['rows']))
        self.assertNotEqual([r['target'] for r in spot['rows']],[r['target'] for r in total['rows']])

    def test_universe_application_and_unapproved_profile_block(self):
        from research.feature_applications import resolve,ApplicationBlocked
        with self.assertRaises(ApplicationBlocked):resolve(self.root,self.intent['feature'],dict(self.fixture.scope,kind='universe'))
        profile=deepcopy(self.profile);profile['approvals']['retrospective_alignment']=False
        with self.assertRaises(inputs.InputsBlocked):inputs.resolve_plan(self.root,self.intent,profile)


if __name__=='__main__':unittest.main()
