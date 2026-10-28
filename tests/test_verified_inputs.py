"""Verified reuse equivalence, isolation, corruption and measured work reduction."""
from contextlib import nullcontext
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from time import perf_counter
import unittest
from unittest.mock import patch

from data.verified_inputs import execution_inputs, phase_inputs, memo, fresh_inputs, compact_memo, probe, retain_price_inputs
from data.transformations.identity import reference, digest
from data.fx_records import make_record
from data import fx_feature_store as fx
from data.targets.fx import materialize
from research import inputs
from research.p1_discovery import run_p1
from research.p2_validation import run_p2
import test_research_inputs as fixture
from data.transformations.contracts import decimal_text
from decimal import Decimal


class ContextTests(unittest.TestCase):
    def test_price_bytes_preserve_exact_values_private_copies_and_dependency_checks(self):
        from data.verified_inputs import verified_prices, retained_size
        from data.alfred_onboarding import stable_read
        from types import SimpleNamespace
        with TemporaryDirectory() as folder:
            root=Path(folder);path=root/'source';path.write_bytes(b'good')
            plan={'plan_id':'test','periods':{'P1':{'end_exclusive':'2020-01-01'}}}
            original=({'id':'exact'},[{'value':'1.2345678901234567890123456789','available_at':None,
                'input_dependencies':[{'id':str(i),'flag':True,'integer':2**64}]} for i in range(200)])
            calls=[]
            def load(*args):
                calls.append(1)
                if stable_read(path)!=b'good':raise ValueError('tampered source')
                return deepcopy(original)
            with execution_inputs(root,'code') as context,phase_inputs(root,plan,'P1'):
                first=verified_prices(SimpleNamespace(root=root),'snapshot','policy',load)
                self.assertEqual(first,original)
                first[1][0]['input_dependencies'][0]['id']='caller mutation'
                self.assertEqual(verified_prices(SimpleNamespace(root=root),'snapshot','policy',load),original)
                entry=next(v for k,v in context.entries.items() if k[1]=='prices')
                self.assertIsInstance(entry[0],bytes)
                self.assertLess(retained_size(entry[0]),retained_size(original))
                self.assertEqual(len(calls),1)
                path.write_bytes(b'evil')
                with self.assertRaisesRegex(ValueError,'tampered'):
                    verified_prices(SimpleNamespace(root=root),'snapshot','policy',load)

    def test_current_price_survives_pressure_without_extending_budget_or_skipping_witnesses(self):
        from data.alfred_onboarding import stable_read
        with TemporaryDirectory() as folder:
            root=Path(folder); path=root/'source'; path.write_bytes(b'good')
            plan={'plan_id':'test','periods':{'P1':{'end_exclusive':'2020-01-01'}}}
            key={'snapshot':'exact','policy':'fixed'}; calls=[]
            def load():
                calls.append(1)
                if stable_read(path)!=b'good':raise ValueError('tampered source')
                return list(range(40))
            with execution_inputs(root,'code',max_bytes=5000) as context, phase_inputs(root,plan,'P1'):
                with retain_price_inputs(root,'exact','fixed'):
                    memo(root,'prices',key,load)
                    for index in range(12):
                        memo(root,'bulk',index,lambda:list(range(60)))
                        compact_memo(root,'compact',index,lambda:list(range(20)))
                        self.assertLessEqual(context.bytes,5000)
                        self.assertLessEqual(context.compact_bytes,2500)
                    value=memo(root,'prices',key,load); value.append('private')
                    self.assertEqual(memo(root,'prices',key,load),list(range(40)))
                    self.assertEqual(len(calls),1)
                    self.assertEqual(context.counts['prices.evictions'],0)
                    self.assertGreater(context.counts['retention_bypasses'],0)
                    path.write_bytes(b'evil')
                    with self.assertRaisesRegex(ValueError,'tampered'):memo(root,'prices',key,load)
                self.assertIsNone(context.retained_price)
                path.write_bytes(b'good'); memo(root,'prices',key,load)
                for index in range(12):memo(root,'bulk',index,lambda:list(range(60)))
                memo(root,'prices',key,load)
                self.assertEqual(len(calls),4) # invalidated failure and normal eviction still reload

    def test_retention_is_exact_scoped_and_oversize_falls_back(self):
        with TemporaryDirectory() as root:
            plan={'plan_id':'test','periods':{p:{'end_exclusive':e} for p,e in
                  [('P1','2020-01-01'),('P2','2021-01-01')]}}
            with execution_inputs(root,'code',max_bytes=1000) as context, phase_inputs(root,plan,'P1'):
                with self.assertRaisesRegex(RuntimeError,'cancelled'):
                    with retain_price_inputs(root,'a','policy'):
                        first=context.retained_price
                        with retain_price_inputs(root,'b','policy'):
                            self.assertNotEqual(context.retained_price,first)
                        self.assertEqual(context.retained_price,first)
                        for _ in range(2):memo(root,'prices',{'snapshot':'a','policy':'policy'},lambda:list(range(1000)))
                        self.assertEqual(context.counts['prices.loads'],2)
                        self.assertEqual(context.bytes,0)
                        raise RuntimeError('cancelled')
                self.assertIsNone(context.retained_price)
                with retain_price_inputs(root,'a','policy'):
                    with phase_inputs(root,plan,'P2'):
                        self.assertIsNone(context.retained_price)
                self.assertIsNone(context.retained_price)

    def test_compact_private_snapshot_survives_bulk_evictions_with_same_total_bound(self):
        with TemporaryDirectory() as folder:
            plan={'plan_id':'test','periods':{'P1':{'end_exclusive':'2020-01-01'}}}
            original={'2020-01-01': ['value', {'id':'exact'}]}
            with execution_inputs(folder,'code',max_bytes=5000) as context, phase_inputs(folder,plan,'P1'):
                first=compact_memo(folder,'lookup',{},lambda:original)
                original['2020-01-01'][1]['id']='caller changed'
                with self.assertRaises(TypeError):first['2020-01-01'][1]['id']='mutation'
                for index in range(20):memo(folder,'bulk',index,lambda:list(range(25)))
                second=compact_memo(folder,'lookup',{},lambda:self.fail('Compact lookup evicted by bulk data'))
                self.assertIs(first,second)
                self.assertEqual(second['2020-01-01'][1]['id'],'exact')
                self.assertLessEqual(context.bytes,context.max_bytes)
                self.assertLessEqual(context.compact_bytes,context.compact_limit)
                self.assertGreater(context.counts['evictions'],0)
            self.assertEqual(context.bytes,0);self.assertFalse(context.compact_entries)

    def test_nested_dependency_witness_detects_tamper_missing_and_new_conflict(self):
        from data.alfred_onboarding import stable_read
        import os
        with TemporaryDirectory() as folder:
            root=Path(folder);path=root/'input';other=root/'conflict'
            path.write_bytes(b'good');before=path.stat()
            plan={'plan_id':'test','periods':{'P1':{'end_exclusive':'2020-01-01'}}}
            def source():
                probe(other)
                if other.exists():raise ValueError('conflicting record')
                data=stable_read(path)
                if data!=b'good':raise ValueError('tampered input')
                return {'value':data}
            def outer():return memo(root,'source',{},source)
            with execution_inputs(root,'code') as context, phase_inputs(root,plan,'P1'):
                self.assertEqual(compact_memo(root,'lookup',{},outer)['value'],b'good')
                path.write_bytes(b'evil');os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
                with self.assertRaisesRegex(ValueError,'tampered'):compact_memo(root,'lookup',{},outer)
                path.write_bytes(b'good');compact_memo(root,'lookup',{},outer)
                other.write_text('new')
                with self.assertRaisesRegex(ValueError,'conflicting'):compact_memo(root,'lookup',{},outer)
                other.unlink();compact_memo(root,'lookup',{},outer);path.unlink()
                with self.assertRaises(FileNotFoundError):compact_memo(root,'lookup',{},outer)
                self.assertGreaterEqual(context.counts['lookup.invalidations'],3)

    def test_exact_keys_phase_root_isolation_private_copies_and_restart(self):
        with TemporaryDirectory() as folder:
            root=Path(folder); plan={'plan_id':'test','periods':{'P1':{'end_exclusive':'2020-01-01'},'P2':{'end_exclusive':'2021-01-01'}}}
            calls=[]
            def load():calls.append(1);return {'rows':[1]}
            with execution_inputs(root, 'code1') as context:
                with phase_inputs(root,plan,'P1'):
                    first=memo(root,'test',{'hash':'a','version':1},load);first['rows'].append(2)
                    self.assertEqual(memo(root,'test',{'hash':'a','version':1},load),{'rows':[1]})
                    memo(root,'test',{'hash':'b','version':1},load)
                    memo(root,'test',{'hash':'a','version':2},load)
                    memo(root/'other','test',{'hash':'a','version':1},load)
                    with fresh_inputs():memo(root,'test',{'hash':'a','version':1},load)
                with phase_inputs(root,plan,'P2'):memo(root,'test',{'hash':'a','version':1},load)
                self.assertEqual(len(calls),6)
            self.assertEqual(context.bytes,0);self.assertFalse(context.entries)
            with execution_inputs(root,'code2'), phase_inputs(root,plan,'P1'):
                memo(root,'test',{'hash':'a','version':1},load)
            self.assertEqual(len(calls),7)

    def test_failure_not_cached_and_memory_budget_evicts(self):
        with TemporaryDirectory() as folder:
            plan={'plan_id':'test','periods':{'P1':{'end_exclusive':'2020-01-01'}}}
            with execution_inputs(folder,'code',max_bytes=1000) as context, phase_inputs(folder,plan,'P1'):
                with self.assertRaises(ValueError):memo(folder,'bad',{},lambda:(_ for _ in ()).throw(ValueError('broken')))
                self.assertFalse(context.entries)
                for n in range(20):memo(folder,'good',{'id':n},lambda:list(range(5)))
                self.assertLessEqual(context.bytes,1000);self.assertGreater(context.counts['evictions'],0)
                memo(folder,'large',{},lambda:list(range(1000)))
                self.assertEqual(context.counts['oversize'],1)


class SourceEvidenceTests(unittest.TestCase):
    """Real provider/closure/price replay, independent of synthetic price mocks."""
    def setUp(self):
        from test_fx_targets import fixture as real_fixture, PROJECT
        from data.feature_store import FeatureStore
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(PROJECT/'specs/schemas',self.root/'specs/schemas')
        self.binding,self.policy,self.prices = real_fixture(self.root)
        self.store = FeatureStore(self.root)
        self.plan = {'plan_id':'isolated-proof','periods':{
            'P1':{'end_exclusive':'2021-01-01'},'P2':{'end_exclusive':'2022-01-01'}}}

    def read(self):
        from data.verified_inputs import verified_prices
        from data.targets.fx import _price_snapshot
        return verified_prices(self.store,self.binding,self.policy,_price_snapshot)

    def evict_prices(self,cache):
        # Real ordinary-LRU pressure: proofs are small but still budgeted.
        for i in range(4): memo(self.root,'pressure',i,lambda:b'x'*(1024*1024))
        self.assertFalse(any(k[1]=='prices' for k in cache.entries))

    def test_source_proof_survives_buffer_eviction_with_exact_private_reload(self):
        with execution_inputs(self.root,'code',max_bytes=3*1024*1024) as cache,phase_inputs(self.root,self.plan,'P1'):
            first=self.read(); self.evict_prices(cache)
            second=self.read(); self.assertEqual(first,second)
            second[1][0]['value']='caller mutation'
            self.evict_prices(cache); self.assertEqual(self.read(),first)
            self.assertEqual(cache.counts['price_proof.loads'],1)
            self.assertEqual(cache.counts['price_proof.hits'],2)
            self.assertEqual(cache.counts['prices.loads'],3)
            self.assertLessEqual(cache.high_water_bytes,3*1024*1024)
            self.assertLessEqual(cache.compact_bytes,cache.compact_limit)

    def test_changed_upstream_raw_bytes_invalidate_proof_even_with_restored_mtime(self):
        import os
        with execution_inputs(self.root,'code',max_bytes=3*1024*1024) as cache,phase_inputs(self.root,self.plan,'P1'):
            self.read(); self.evict_prices(cache)
            # Select the EUR/USD raw dependency, not another unrelated fixture.
            raw=next(p for p in (self.root/'fixture_sources/legacy/raw').rglob('*.json') if b'EUR/USD' in p.read_bytes())
            stamp=raw.stat(); data=raw.read_bytes(); raw.write_bytes(data.replace(b'"1"',b'"9"',1))
            if raw.read_bytes()==data: raw.write_bytes(data+b' ')
            os.utime(raw,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            with self.assertRaises(ValueError): self.read()
            self.assertEqual(cache.counts['price_proof.invalidations'],1)

    def test_standalone_and_new_phase_repeat_full_independent_source_verification(self):
        from data.targets import fx as target_fx
        original=target_fx._price_snapshot
        with patch.object(target_fx,'_price_snapshot',wraps=original) as full:
            with execution_inputs(self.root,'code') as cache:
                for phase in ('P1','P2'):
                    with phase_inputs(self.root,self.plan,phase): self.read(); self.read()
                with fresh_inputs(): self.read()
            self.read()
            self.assertEqual(full.call_count,4)

    def test_compact_evidence_eviction_falls_back_to_full_verifier(self):
        with execution_inputs(self.root,'code',max_bytes=3*1024*1024) as cache,phase_inputs(self.root,self.plan,'P1'):
            expected=self.read(); self.evict_prices(cache)
            for index in range(3): compact_memo(self.root,'proof-pressure',index,lambda:b'z'*(1024*1024))
            self.assertFalse(any(k[1]=='price_proof' for k in cache.compact_entries))
            self.assertEqual(self.read(),expected)
            self.assertEqual(cache.counts['price_proof.loads'],2)
            self.assertLessEqual(cache.high_water_bytes,3*1024*1024)

    def test_proof_reload_dependencies_propagate_to_enclosing_entry(self):
        with execution_inputs(self.root,'code',max_bytes=3*1024*1024) as cache,phase_inputs(self.root,self.plan,'P1'):
            self.read(); self.evict_prices(cache)
            memo(self.root,'enclosing','key',lambda:self.read()[1][0]['value'])
            self.assertEqual(cache.counts['price_proof.hits'],1)
            raw=next(p for p in (self.root/'fixture_sources/legacy/raw').rglob('*.json') if b'EUR/USD' in p.read_bytes())
            raw.write_bytes(raw.read_bytes()+b' ')
            with self.assertRaises(ValueError): memo(self.root,'enclosing','key',lambda:self.read()[1][0]['value'])
            self.assertEqual(cache.counts['enclosing.invalidations'],1)

    def test_new_ambiguous_definition_invalidates_source_proof(self):
        from data.transformations.identity import canonical_bytes
        with execution_inputs(self.root,'code',max_bytes=3*1024*1024) as cache,phase_inputs(self.root,self.plan,'P1'):
            snapshot,_=self.read(); self.evict_prices(cache)
            view=self.store.resolve(snapshot['body']['definition'])
            alias=self.root/'definitions/datasets'/view['id']/(view['version']+'.json')
            alias.parent.mkdir(parents=True); alias.write_bytes(canonical_bytes(view)+b'\n')
            with self.assertRaisesRegex(ValueError,'Ambiguous definition identity'): self.read()
            self.assertEqual(cache.counts['price_proof.invalidations'],1)

    def test_change_during_reload_is_rejected_before_publication(self):
        from data import fx_records
        original=fx_records.read_rows
        with execution_inputs(self.root,'code',max_bytes=3*1024*1024) as cache,phase_inputs(self.root,self.plan,'P1'):
            self.read(); self.evict_prices(cache)
            def changing(store,members):
                rows=original(store,members)
                raw=next(p for p in (self.root/'fixture_sources/legacy/raw').rglob('*.json') if b'EUR/USD' in p.read_bytes())
                raw.write_bytes(raw.read_bytes()+b' ')
                return rows
            with patch.object(fx_records,'read_rows',side_effect=changing),self.assertRaisesRegex(ValueError,'changed before cache publication'):
                self.read()
            self.assertFalse(any(k[1]=='prices' for k in cache.entries))

    def test_reload_must_equal_the_entire_proven_record_and_price_rows(self):
        from data import fx_records
        original=fx_records.read_rows
        with execution_inputs(self.root,'code',max_bytes=3*1024*1024) as cache,phase_inputs(self.root,self.plan,'P1'):
            self.read(); self.evict_prices(cache)
            def wrong(store,members):
                rows=original(store,members); rows[0]['value']='42'; return rows
            with patch.object(fx_records,'read_rows',side_effect=wrong),self.assertRaisesRegex(ValueError,'Reloaded prices differ'):
                self.read()


class VerifiedPreparationTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ResearchInputsTests(methodName='runTest');self.f.setUp();self.addCleanup(self.f.tearDown)
        self.root=self.f.root

    def expanded_fixture(self, mode='TS'):
        f=self.f
        f.fx.days=list(fx._dates('2020-01-02','2022-04-22'))
        # Include invalid values and a missing scheduled weekday in the proof.
        prices=[]
        import math
        for i,day in enumerate(f.fx.days):
            if i==17:continue
            row={'reference_time':day,'value':decimal_text(Decimal(str(100+math.sin(i*.3)*3+i*.04))),'status':'valid','reason_code':None,
                 'available_at':None,'original_ingested_at':'2024-05-01T12:00:00.000000Z',
                 'input_dependencies':[{'original_ingested_at':'2024-05-01T12:00:00Z'}]}
            row['id']='FXPRICE_'+digest(row);prices.append(row)
        f.fx.prices=prices
        body=deepcopy(f.fx.snapshot_record['body']);body['coverage']={'start':f.fx.days[0],'end':f.fx.days[-1]}
        f.fx.snapshot_record=make_record('snapshot_manifest',body);f.fx.snapshot=f.store.install_record(f.fx.snapshot_record)
        materialize(self.root,f.fx.snapshot,f.fx.batch,knowledge_cutoff='2024-05-02')
        f.profile['periods']={'P1':{'start_inclusive':'2020-01-02','end_exclusive':'2022-01-01'},
                              'P2':{'start_inclusive':'2022-01-01','end_exclusive':'2022-04-23'}}
        plan=f.plan()
        if mode=='CS':
            # Three actual distinct instrument bindings, sharing only the reusable recipe.
            from data.fx_feature_recipes import build_fx_feature
            from data.transformations.registry import Registry
            members=[deepcopy(plan['members'][0])];states={f.fx.snapshot['id']:(f.fx.snapshot_record,prices)}
            step=f.fx.feature['body']['recipe']['steps'][-1]
            variant={'operator':step['operator'],'parameters':step['parameters'],'grid_policy':step['grid_policy'],
                     'mode':'log_first','parameter_frequency':'daily'}
            for n,symbol in enumerate(['GBPUSD','AUDUSD'],1):
                meta=dict(f.fx.meta,unit='USD_per_'+symbol[:3],base_currency=symbol[:3])
                ds=f.fx.install('dataset_definition',{'kind':'fx_constructed_dataset','instrument_id':symbol,'source_metadata':meta})
                view=f.fx.install('source_view_definition',{'kind':'fx_constructed_view','dataset':ds,'source_metadata':meta})
                b=dict(body,instrument_id=symbol,economic_id='FX_'+symbol[:3]+'_USD',definition=view,source_metadata=meta)
                snap=make_record('snapshot_manifest',b);binding=f.store.install_record(snap)
                data=deepcopy(prices)
                for i,row in enumerate(data):
                    row['value']=decimal_text(Decimal(str(float(row['value'])+n*math.sin(i*.13+n)*5)));row['id']='FXPRICE_'+digest({k:v for k,v in row.items() if k!='id'})
                states[binding['id']]=(snap,data)
                def source(store,binding,policy,verify_rows=True):
                    snap,rows=states[binding['id']];return store.resolve(binding),deepcopy(rows) if verify_rows else None
                with patch('data.targets.fx._price_snapshot',side_effect=source):
                    saved=materialize(self.root,binding,f.fx.batch,knowledge_cutoff='2024-05-02')
                feature=build_fx_feature(self.root,{'instrument_id':symbol,'price_snapshot':binding},variant,registry=Registry(self.root));f.store.install_record(feature)
                m=deepcopy(members[0]);m.update(instrument_id=symbol,feature=reference(feature),signal_id=feature['body']['signal_id'],price_snapshot=binding,source_view=view)
                m['targets']=inputs._target_metadata(inputs.TargetStore(self.root),snap,f.fx.batch,'2024-05-02',{})
                members.append(m)
            f.scope['kind']='universe';f.scope['members']=[m['instrument_id'] for m in members]
            for target in ('data.fx_feature_store._price_snapshot','research.inputs._price_snapshot'):
                p=patch(target,side_effect=source);p.start();self.addCleanup(p.stop)
            for target,value in [('research.inputs.list_instruments', [{'instrument_id':m['instrument_id'],'price_snapshot':m['price_snapshot']} for m in members]),
                ('research.inputs.legacy_bindings_for_recipe', [{'instrument_id':m['instrument_id'],'feature':m['feature'],'source_view':m['source_view']} for m in members])]:
                p=patch(target,return_value=value);p.start();self.addCleanup(p.stop)
            plan=f.plan()
        return plan

    def compare(self, mode):
        plan=self.expanded_fixture(mode)
        with TemporaryDirectory() as folder:
            other=Path(folder)/'store';shutil.copytree(self.root,other)
            outputs=[]; measurements=[]
            for root,enabled in [(self.root,False),(other,True)]:
                with (execution_inputs(root,{'fixture_implementation':'exact'},max_bytes=128*1024*1024) if enabled else nullcontext()) as context:
                    with patch.object(fx,'_calculate',wraps=fx._calculate) as calculate, patch.object(inputs,'_schedule',wraps=inputs._schedule) as schedules:
                        start=perf_counter();prepared=inputs.prepare_phase(root,plan,'P1');prepared_at=perf_counter()
                        loaded=[inputs.load_phase(root,plan,prepared,'P1',h) for h in (1,7,21,63,252)];loaded_at=perf_counter()
                        admission={'plan_id':plan['plan_id'],'direction':'POSITIVE','admitted_horizons':[1,7]}
                        p2=inputs.prepare_phase(root,plan,'P2',admission=admission);p2_at=perf_counter()
                        validation=[inputs.load_phase(root,plan,p2,'P2',h,admission=admission) for h in (1,7)]
                        elapsed=perf_counter()-start
                        measurements.append({'mode':mode,'optimized':enabled,'seconds':elapsed,
                            'feature_series_calculations':calculate.call_count,'target_schedule_builds':schedules.call_count,
                            'p1_preparation_seconds':prepared_at-start,'p1_horizon_load_seconds':loaded_at-prepared_at,
                            'p2_preparation_seconds':p2_at-loaded_at,'p2_horizon_load_seconds':perf_counter()-p2_at,
                            'cache_load_seconds':dict(context.seconds) if context else {},
                            'cache_counts':dict(context.counts) if context else {}})
                        outputs.append((prepared,loaded,p2,validation))
                        if enabled:
                            self.assertEqual(context.counts['prices.loads'],2*len(plan['members']))
                            self.assertEqual(context.counts['calculated_series.loads'],2*len(plan['members']))
                            self.assertEqual(context.counts['verified_series.loads'],2*len(plan['members']))
                            self.assertEqual(context.counts['evictions'],0)
            self.assertEqual(digest(list(outputs[0])),digest(list(outputs[1])))  # exact IDs, values, nulls, lineage and coverage
            self.assertLess(measurements[1]['feature_series_calculations'],measurements[0]['feature_series_calculations'])
            self.assertEqual(measurements[1]['target_schedule_builds'],2*len(plan['members']))
            kernel={'kernel_policy':'scheduled_weekday_hac_v2','spacing':1,'horizon_unit':'scheduled_weekdays',
                    'clock_compatibility':'approved','missing_evidence':'unresolved_required_v1',
                    'structural_common_start':plan['structural_common_start']}
            for index,h in enumerate((1,7,21,63,252)):
                a,b=[run_p1(o[1][index]['rows'],mode=mode,horizon=h,members=plan['scope']['members'],expected_direction='POSITIVE',profile=dict(kernel,window_start=plan['periods']['P1']['start_inclusive'],window_end_exclusive=plan['periods']['P1']['end_exclusive'])) for o in outputs]
                self.assertEqual(a,b)
            for index,h in enumerate((1,7)):
                a,b=[run_p2(o[3][index]['rows'],mode=mode,horizon=h,members=plan['scope']['members'],expected_direction='POSITIVE',discovery_effect=.1,profile=dict(kernel,window_start=plan['periods']['P2']['start_inclusive'],window_end_exclusive=plan['periods']['P2']['end_exclusive'])) for o in outputs]
                self.assertEqual(a,b)
            path=Path(__file__).resolve().parents[1]/'outputs'/('verified_inputs_benchmark_'+mode+'.json')
            path.write_text(json.dumps(measurements,indent=2))

    def test_ts_multiyear_equivalence_and_reduced_work(self):self.compare('TS')
    def test_cs_multimember_equivalence_and_reduced_work(self):self.compare('CS')

    def test_packed_multimember_warmup_follows_all_publications(self):
        import os
        plan=self.expanded_fixture('CS')
        with patch.dict(os.environ,GAMBIT_FX_LINEAGE_STORAGE='packed_v1'),execution_inputs(self.root,'code') as context:
            prepared=inputs.prepare_phase(self.root,plan,'P1')
            self.assertTrue(all(len(m['materializations'])>1 for m in prepared['members']))
            for h in (1,7,21,63,252):inputs.load_phase(self.root,plan,prepared,'P1',h)
            self.assertEqual(context.counts['feature_lookup.loads'],len(plan['members']))
            self.assertEqual(context.counts['feature_lookup.invalidations'],0)
            self.assertIsNone(context.retained_price)

    def test_fresh_inspection_and_new_execution_reject_tampered_payload(self):
        plan=self.f.plan()
        with execution_inputs(self.root,'code'), phase_inputs(self.root,plan,'P1'):
            prepared=inputs.prepare_phase(self.root,plan,'P1');binding=prepared['members'][0]['materializations'][0]
            original=inputs._verified_feature(self.root,binding)
            part=original['manifest']['partitions'][0];h=part['blob_sha256']
            p=self.root/'storage/payloads/sha256'/h[:2]/(h+'.'+part['format']);p.write_bytes(b'corrupted')
            # Warm entries must not hide a changed persisted dependency.
            with self.assertRaises(Exception):inputs._verified_feature(self.root,binding)
            with self.assertRaises(Exception):fx.read_fx_materialization(self.root,binding['id'])
        with execution_inputs(self.root,'code'), phase_inputs(self.root,plan,'P1'):
            with self.assertRaises(Exception):inputs._verified_feature(self.root,binding)

    def test_admission_and_cancellation_checked_even_with_warm_cache(self):
        plan=self.f.plan()
        with execution_inputs(self.root,'code'):
            inputs.prepare_phase(self.root,plan,'P1')
            with self.assertRaises(inputs.InputsBlocked):inputs.prepare_phase(self.root,plan,'P2')
            with self.assertRaises(inputs.InputsCancelled):inputs.prepare_phase(self.root,plan,'P1',cancelled=lambda:True)

    def test_feature_lookup_is_reused_for_five_horizons_with_fresh_output_lineage(self):
        plan=self.f.plan()
        with execution_inputs(self.root,'code') as context:
            prepared=inputs.prepare_phase(self.root,plan,'P1')
            # Ordinary scientific publication does not change any input identity.
            (self.root/'storage/catalog/new_unrelated_trials').mkdir()
            loaded=[inputs.load_phase(self.root,plan,prepared,'P1',h) for h in (1,7,21,63,252)]
            self.assertEqual(context.counts['feature_lookup.loads'],1)
            self.assertEqual(context.counts['feature_lookup.hits'],5)
            self.assertEqual(context.counts['feature_lookup.invalidations'],0)
            self.assertEqual(context.counts['target_endpoints.loads'],1)
            self.assertEqual(context.counts['target_endpoints.hits'],5)
            self.assertLessEqual(context.bytes,context.max_bytes)
            saved=deepcopy(loaded[0])
            loaded[0]['rows'][0]['lineage']['feature_lineage']['id']='caller mutation'
            self.assertEqual(inputs.load_phase(self.root,plan,prepared,'P1',1),saved)
            binding=prepared['members'][0]['materializations'][0]
            path=inputs.FeatureStore(self.root).path('storage/catalog/feature_store/'+binding['id']+'/manifest.json')
            path.write_bytes(b'{}')
            with self.assertRaises(Exception):inputs.load_phase(self.root,plan,prepared,'P1',1)

    def test_compact_target_endpoints_keep_exact_phase_and_source_witness(self):
        from data.feature_store import record_path
        plan=self.f.plan();period=plan['periods']['P1'];member=plan['members'][0]
        with execution_inputs(self.root,'code'),phase_inputs(self.root,plan,'P1'):
            selected=inputs._target_prices(self.root,member,plan,period)
            self.assertTrue(selected['prices'])
            self.assertTrue(all(period['start_inclusive']<=r['reference_time']<period['end_exclusive']
                                for r in selected['prices']))
            self.assertEqual(dict(selected['prices'][0]),{k:self.f.fx.prices[0][k]
                for k in ('id','reference_time','value','status','original_ingested_at')})
            with self.assertRaises(TypeError):selected['prices'][0]['value']='changed'
            snapshot=self.f.store.resolve(member['price_snapshot'])
            self.f.store.path(record_path(snapshot)).write_bytes(b'{}')
            with self.assertRaises(Exception):inputs._target_prices(self.root,member,plan,period)

    def test_warm_feature_lookup_rejects_new_ambiguous_definition(self):
        plan=self.f.plan()
        with execution_inputs(self.root,'code'):
            prepared=inputs.prepare_phase(self.root,plan,'P1')
            inputs.load_phase(self.root,plan,prepared,'P1',1)
            feature=plan['members'][0]['feature']
            original=self.root/'definitions/features'/feature['id']/(feature['version']+'.json')
            conflict=self.root/'definitions/datasets'/feature['id']/(feature['version']+'.json')
            conflict.parent.mkdir(parents=True);conflict.write_bytes(original.read_bytes())
            with self.assertRaisesRegex(Exception,'Ambiguous definition'):
                inputs.load_phase(self.root,plan,prepared,'P1',7)

    def test_local_lineage_reuse_is_confined_to_one_checked_capture(self):
        from data.feature_store import FeatureStore, record_path
        from data.verified_inputs import ChangedInput
        plan=self.f.plan();prepared=inputs.prepare_phase(self.root,plan,'P1')
        item=inputs._verified_feature(self.root,prepared['members'][0]['materializations'][0])
        binding=item['manifest']['lineage'][0];store=FeatureStore(self.root)
        original=store.resolve(binding);path=store.path(record_path(original));data=path.read_bytes()
        def altered_during_verification():
            store.resolve(binding)
            path.write_bytes(b'{}')
            # The same verifier can use its earlier snapshot, but its result
            # cannot be accepted because the final witness check detects this.
            self.assertEqual(store.resolve(binding),original)
            return original
        with execution_inputs(self.root,'code'),phase_inputs(self.root,plan,'P1'):
            with self.assertRaises(ChangedInput):
                memo(self.root,'capture',{},altered_during_verification)
            path.write_bytes(data)
            self.assertEqual(memo(self.root,'capture',{},lambda:store.resolve(binding)),original)
            path.write_bytes(b'{}')
            with self.assertRaises(Exception):
                memo(self.root,'different_capture',{},lambda:store.resolve(binding))

    def test_warm_packed_lookup_detects_appended_conflicting_lineage_catalog(self):
        import os
        from data.transformations.identity import canonical_bytes
        plan=self.f.plan()
        with patch.dict(os.environ,GAMBIT_FX_LINEAGE_STORAGE='packed_v1'),execution_inputs(self.root,'code'):
            prepared=inputs.prepare_phase(self.root,plan,'P1')
            inputs.load_phase(self.root,plan,prepared,'P1',1)
            folder=self.root/'storage/catalog/lineage_packs'
            pack=json.loads(next(folder.glob('*.json')).read_text())
            pack['references'][0]['content_sha256']='0'*64
            (folder/(digest(pack)+'.json')).write_bytes(canonical_bytes(pack)+b'\n')
            with self.assertRaisesRegex(Exception,'conflicting|conflicts'):
                inputs.load_phase(self.root,plan,prepared,'P1',7)

    def test_different_cutoff_and_snapshot_cannot_hit_prices(self):
        from data.verified_inputs import verified_prices
        plan=self.f.plan();store=self.f.store;calls=[]
        def loader(store,binding,policy):calls.append((binding,policy));return ({'binding':binding},[])
        with execution_inputs(self.root,'code'),phase_inputs(self.root,plan,'P1'):
            for binding,policy in [('a','policy1'),('a','policy1'),('b','policy1'),('a','policy2')]:
                verified_prices(store,binding,policy,loader)
        self.assertEqual(len(calls),3)

    def test_interrupted_publication_and_resume_keep_one_complete_output(self):
        plan=self.f.plan();member=plan['members'][0]
        kwargs={'price_snapshot':member['price_snapshot'],'batch_policy':plan['batch_policy'],
                'knowledge_cutoff':plan['knowledge_cutoff'],'start':'2024-01-02','end':'2024-02-29'}
        with execution_inputs(self.root,'code'),phase_inputs(self.root,plan,'P1'):
            with self.assertRaisesRegex(fx.PublicationError,'Injected interruption'):
                fx.prepare_fx_feature(self.root,member['feature'],**kwargs,fail_at='payloads')
            self.assertFalse(list((self.root/'storage/catalog/feature_store').glob('*/manifest.json')))
            saved=fx.prepare_fx_feature(self.root,member['feature'],**kwargs)
            repeated=fx.prepare_fx_feature(self.root,member['feature'],**kwargs)
            self.assertEqual(saved['materialization'],repeated['materialization']);self.assertTrue(repeated['reused'])
            self.assertEqual(len(list((self.root/'storage/catalog/feature_store').glob('*/manifest.json'))),1)
        independent=fx.read_fx_materialization(self.root,saved['materialization']['id'])
        self.assertEqual(len(independent['observations']),43)


class CausalChainTests(unittest.TestCase):
    def test_approved_fx_chains_preserve_prefixes_including_missing_and_nonpositive_inputs(self):
        from data.fx_feature_recipes import configurations
        from data.transformations.registry import Registry
        import math
        root=Path(__file__).resolve().parents[1];registry=Registry(root)
        dates=list(fx._dates('2020-01-01','2021-08-01'))[:400]
        prices=[{'status':'valid','value':str(100+math.sin(i*.17)*4+i*.03)} for i in range(len(dates))]
        prices[25]=None;prices[96]={'status':'valid','value':'0'}
        log=registry.operator('TR_BASE_level_log');count=0
        for variant in configurations(registry):
            entry=registry.operator(variant['operator']['id'],variant['operator']['version'])
            params={p['name']:(int(p['value']['value']) if p['value']['kind']=='integer' else
                float(p['value']['value']) if p['value']['kind']=='decimal' else p['value']['value']) for p in variant['parameters']}
            steps=([{'entry':log,'parameters':{}}] if variant['mode']=='log_first' else [])+[{'entry':entry,'parameters':params}]
            compiled={'steps':steps}
            with self.subTest(operator=entry['id'],parameters=params):
                full=fx._calculate(compiled,dates,prices)
                for end in (63,270):
                    self.assertEqual(full[:end],fx._calculate(compiled,dates[:end],prices[:end]))
            count+=1
        self.assertEqual(count,180)
