"""Synthetic package contracts, actual immutable publication and UTC TS reads."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from data import panel_import as panels
from data.feature_store import FeatureStore,read_materialization,retrieve_signal
from data.transformations.identity import canonical_bytes,reference
from research import panel_features,external_features,feature_applications

CAP='2021-03-10T20:00:00Z'


def fixture(folder,kind):
    folder.mkdir()
    db=sqlite3.connect(folder/panels.FILES[kind][1])
    if kind in ('common','expansion'):
        db.executescript('''CREATE TABLE series(series_id INTEGER PRIMARY KEY,series_key TEXT,name TEXT,frequency TEXT,unit TEXT,block TEXT);
        INSERT INTO series VALUES(1,'TEST','Synthetic series','D','percent per annum','RATES');
        CREATE TABLE feature_states(state_id INTEGER PRIMARY KEY,series_id INTEGER,layer TEXT,
          available_from TEXT,available_until TEXT,period_start TEXT,period_end TEXT,reference_date TEXT,reference_end TEXT,
          frequency TEXT,unit TEXT,values_json TEXT,input_ids_json TEXT,lineage_json TEXT,missing_json TEXT,block_mask INTEGER,warning_mask INTEGER);
        CREATE INDEX lookup ON feature_states(series_id,layer,available_from);''')
        db.execute('CREATE TABLE bindings(series_id INTEGER,panel_id TEXT)');db.execute("INSERT INTO bindings VALUES(1,'G01')")
        states=[('archive','2020-01-01T12:00:00Z','2020-01-03T12:00:00Z','2020-01-01',2.0,0),
                ('archive','2020-01-03T12:00:00Z',None,'2020-01-03',3.0,4),
                ('capture',CAP,None,'2021-03-10',4.0,0),
                ('retrospective','2020-01-01T18:00:00Z',None,'2020-01-01',1.0,0)]
        if kind=='common':states=states[:-1]
        for i,(layer,at,until,day,value,mask) in enumerate(states,1):
            db.execute('INSERT INTO feature_states VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (i,1,layer,at,until,day,day,day,day,'D','percent per annum',json.dumps({'level':value,'change_1':None}),
                 json.dumps({'level':[i]}),json.dumps({'current_observation_id':i}),json.dumps({'change_1':'lookback absent'}),mask,2))
        if kind=='common':(folder/'engineering.json').write_text(json.dumps({'capture_at':CAP}))
        else:
            db.execute('CREATE TABLE metadata(key TEXT,value_json TEXT)')
            db.execute('INSERT INTO metadata VALUES(?,?)',('input_freeze',json.dumps({'capture_at':CAP})))
    elif kind=='etf':
        db.executescript('''CREATE TABLE feature_vectors(vector_id INTEGER PRIMARY KEY,panel_id TEXT,entity TEXT,date TEXT,frequency TEXT,
            assumed_available_from TEXT,observed_from TEXT,retro_eligible INTEGER,source_class TEXT,values_json TEXT,missing_json TEXT,lineage_json TEXT);
            CREATE INDEX lookup ON feature_vectors(panel_id,entity,frequency,assumed_available_from,date);''')
        for i,day,value,retro in [(1,'2020-01-01',1,1),(2,'2020-01-02',None,1),(3,'2021-03-10',4,0)]:
            db.execute('INSERT INTO feature_vectors VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (i,'G08_ETF','TEST',day,'D',day+'T12:00:00Z',CAP,retro,'Synthetic filed/estimated flow',
                 json.dumps({'flow_usd':value}),json.dumps({'flow_usd':'source gap'} if value is None else {}),json.dumps({'input_flow_id':i})))
        (folder/'input-freeze.json').write_text(json.dumps({'capture_at':CAP}))
    else:
        db.executescript('''CREATE TABLE features(feature_id INTEGER PRIMARY KEY,name TEXT,panel_id TEXT,metric TEXT,description TEXT);
            INSERT INTO features VALUES(0,'inflation_gap','C06','yoy','Inflation differential');
            CREATE TABLE currencies(currency_id INTEGER PRIMARY KEY,currency TEXT);
            INSERT INTO currencies VALUES(0,'JPY'),(1,'USD');
            CREATE TABLE modes(mode_id INTEGER PRIMARY KEY,name TEXT);INSERT INTO modes VALUES(0,'archive'),(1,'capture');
            CREATE TABLE asofs(asof_id INTEGER PRIMARY KEY,asof_utc TEXT);
            INSERT INTO asofs VALUES(0,'2020-01-01T12:00:00Z'),(1,'2020-01-02T12:00:00Z'),(2,'2021-03-10T20:00:00Z');
            CREATE TABLE dates(ordinal INTEGER PRIMARY KEY,iso_date TEXT);INSERT INTO dates VALUES(0,'2019-12-01');
            CREATE TABLE country_features(mode_id INTEGER,asof_id INTEGER,feature_id INTEGER,currency_id INTEGER,
              candidate_value REAL,model_value REAL,period_ordinal INTEGER,frequency TEXT,lineage_id INTEGER,
              missing_mask INTEGER,blocker_mask INTEGER,warning_mask INTEGER);
            CREATE TABLE pair_features_data(mode_id INTEGER,asof_id INTEGER,feature_id INTEGER,base_id INTEGER,quote_id INTEGER,
              candidate_value REAL,model_value REAL,missing_mask INTEGER,blocker_mask INTEGER,warning_mask INTEGER);''')
        for mode,a in [(0,0),(0,1),(1,2)]:
            for cid in (0,1):
                db.execute('INSERT INTO country_features VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(mode,a,0,cid,2-cid,2-cid,0,'M',100+cid,0,0,1))
            db.execute('INSERT INTO pair_features_data VALUES(?,?,?,?,?,?,?,?,?,?)',(mode,a,0,0,1,1,1 if a!=1 else None,0,0 if a!=1 else 1,1))
    db.commit();db.close()
    archive=folder.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w') as z:
        for f in folder.iterdir():z.write(f,folder.name+'/'+f.name)
    return panels.package_plan(folder,kind,archive)


class PanelImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.root=self.base/'platform';self.root.mkdir()
        self.packages=[fixture(self.base/k,k) for k in ('macro','common','etf','expansion')]
        self.plan=panels.make_plan(self.packages)
        with patch.dict(os.environ,GAMBIT_ISOLATED_TEST='1'):
            self.receipt=panels.install(self.root,self.plan,self.plan['plan_sha256'],isolated=True)
        self.features=[]
        for p in (self.root/'definitions/features').glob('*/*.json'):self.features.append(json.loads(p.read_text()))

    def chosen(self,kind,layer='archive',pair=False):
        return next(f for f in self.features if f['body']['projection']['package']==kind
            and f['body']['projection']['layer']==layer and bool(f['body']['projection']['pair'])==pair)

    def test_all_packages_are_native_immutable_sources_without_jobs(self):
        self.assertEqual(len(self.receipt['packages']),4)
        self.assertFalse((self.root/'storage/catalog/operations/jobs').exists())
        for f in self.features:
            manifest=panels.manifest_for(f)
            read=read_materialization(self.root,manifest['id'])
            self.assertEqual(read['feature'],f)
            signal=retrieve_signal(self.root,f['body']['signal_id'])
            self.assertEqual(signal['scientific_state'],'untested')
        with patch.dict(os.environ,GAMBIT_ISOLATED_TEST='1'):
            self.assertEqual(panels.install(self.root,self.plan,self.plan['plan_sha256'],isolated=True),self.receipt)

    def test_original_masks_null_updates_and_validity_bounds(self):
        rows=panels.read(self.root,self.chosen('expansion'))['observations']
        self.assertEqual([r['value'] for r in rows],['2.0',None])
        self.assertEqual(rows[1]['reason_code'],'SOURCE_HELD')
        state,_,reason=external_features.state_at(rows,'2020-01-03',panel_features.policy())
        self.assertEqual(state['value'],'2.0');self.assertIsNone(reason)
        _,_,reason=external_features.state_at(rows,'2020-01-06',panel_features.policy())
        self.assertEqual(reason,'SOURCE_HELD')
        _,_,reason=external_features.state_at(rows,'2021-03-11',panel_features.policy())
        self.assertEqual(reason,'FROZEN_SOURCE_REFRESH_REQUIRED')
        with self.assertRaisesRegex(ValueError,'frozen capture'):
            panels.read(self.root,self.chosen('expansion'),end='2022-01-01T00:00:00Z')

    def test_macro_integer_lookup_preserves_between_cutoff_eligibility(self):
        f=self.chosen('macro',pair=True)
        rows=panels.read(self.root,f,start='2020-01-02T00:00:00Z',end='2020-01-02T13:00:00Z')['observations']
        self.assertEqual([r['available_at'] for r in rows],['2020-01-01T12:00:00Z','2020-01-02T12:00:00Z'])
        state,_,reason=panel_features.state_at(rows,'2020-01-02',panel_features.policy())
        self.assertEqual(state['value'],'1.0');self.assertIsNone(reason)
        state,_,reason=panel_features.state_at(rows,'2020-01-03',panel_features.policy())
        self.assertIsNone(state['value']);self.assertEqual(reason,'SOURCE_MISSING_OR_HELD')
        self.assertNotIn('differential',self.chosen('macro')['display_name'])
        self.assertIn('differential',f['display_name'])

    def test_ETF_capture_is_latest_only_and_filed_rows_are_not_retrospective(self):
        capture=panels.read(self.root,self.chosen('etf','capture'))['observations']
        retro=panels.read(self.root,self.chosen('etf','retrospective'))['observations']
        self.assertEqual(len(capture),1);self.assertEqual(capture[0]['value'],'4')
        self.assertEqual(len(retro),2);self.assertIsNone(retro[1]['value'])
        self.assertEqual(panels.read(self.root,self.chosen('etf','capture'),end='2020-01-01T00:00:00Z')['observations'],[])
        _,_,reason=panel_features.state_at(retro,'2020-01-24',panel_features.policy())
        self.assertEqual(reason,'source gap')

    def test_capture_blocked_pair_scope_guard_and_reverse_orientation(self):
        from research.contracts import ref
        p=panel_features.policy();policy_path=self.root/'definitions/alignment_policies'/p['id']/'1.0.0.json'
        policy_path.parent.mkdir(parents=True);policy_path.write_bytes(canonical_bytes(p)+b'\n')
        profile={'external_alignment_policy':ref(p)}
        pair=self.chosen('macro',pair=True)
        source=panel_features.resolve_source(self.root,pair,profile,'USDJPY')
        self.assertEqual(source['pair_orientation_multiplier'],-1)
        with self.assertRaisesRegex(ValueError,'another currency pair'):panel_features.resolve_source(self.root,pair,profile,'EURUSD')
        with self.assertRaisesRegex(ValueError,'capture-only'):panel_features.resolve_source(self.root,self.chosen('etf','capture'),profile,'EURUSD')
        scope={'kind':'universe','members':['EURUSD','USDJPY']}
        with self.assertRaises(feature_applications.ApplicationBlocked):
            feature_applications.resolve(self.root,{k:pair[k] for k in ('id','version')},scope)

    def test_phase_decoding_excludes_future_values_and_keeps_one_prior_state(self):
        f=self.chosen('expansion');manifest=panels.manifest_for(f)
        self.assertNotIn('value',f['body']['projection']['summary']['latest'])
        self.assertNotIn('lineage',f['body']['projection']['summary']['latest'])
        from research.contracts import ref
        p=panel_features.policy();path=self.root/'definitions/alignment_policies'/p['id']/'1.0.0.json'
        path.parent.mkdir(parents=True);path.write_bytes(canonical_bytes(p)+b'\n')
        source=panel_features.resolve_source(self.root,f,{'external_alignment_policy':ref(p)},'EURUSD')
        rows=panel_features.phase_rows(self.root,source,{'start_inclusive':'2020-01-02','end_exclusive':'2020-01-03'})
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['value'],'2.0')
        self.assertLess(rows[0]['available_at'],'2020-01-03T00:00:00Z')
        changed=deepcopy(source);changed['pair_orientation_multiplier']=-1
        with self.assertRaisesRegex(ValueError,'alignment semantics differ'):
            panel_features.phase_rows(self.root,changed,{'start_inclusive':'2020-01-02','end_exclusive':'2020-01-03'})

    def test_catalog_list_is_metadata_only_and_detail_checks_operands(self):
        from api.signal_library import list_signal_library,get_signal_detail
        from api.feature_library import list_feature_library
        # No reusable registry is present in this minimal source fixture.
        from data.reusable_features import ReusableRecipeNotFound
        with patch('data.reusable_features.list_reusable_fx_recipes',side_effect=ReusableRecipeNotFound('fixture')):
            result=list_feature_library(self.root)
        historical=sum(f['body']['projection']['layer']!='capture' for f in self.features)
        self.assertEqual(result['feature_count'],historical,result['issues'])
        with patch('data.panel_import.read',side_effect=AssertionError('List decoded history')):
            result=list_signal_library(self.root)
        self.assertEqual(result['signal_count'],historical,result['issues'])
        context=self.chosen('etf','capture')
        context_detail=get_signal_detail(self.root,context['body']['signal_id'])
        self.assertEqual(context_detail['signal']['source_layer'],'capture')
        f=self.chosen('expansion');detail=get_signal_detail(self.root,f['body']['signal_id'])
        self.assertEqual(detail['statistics']['valid_count'],1)
        self.assertEqual(detail['research']['state'],'untested')
        snapshot=FeatureStore(self.root).resolve(f['body']['snapshot'])
        payload=panels.payload_path(self.root,snapshot['body']['database'],'sqlite')
        payload.chmod(0o640)
        with payload.open('r+b') as out:out.seek(100);out.write(b'BAD')
        with self.assertRaisesRegex(ValueError,'hash differs'):get_signal_detail(self.root,f['body']['signal_id'])

    def test_plan_hash_and_source_drift_abort(self):
        with self.assertRaisesRegex(ValueError,'reviewed plan'):
            panels.install(self.root,self.plan,'0'*64,isolated=True)
        archive=Path(self.packages[0]['archive_path']);archive.write_bytes(b'changed')
        with patch.dict(os.environ,GAMBIT_ISOLATED_TEST='1'),self.assertRaisesRegex(ValueError,'fingerprint drift'):
            panels.install(self.root,self.plan,self.plan['plan_sha256'],isolated=True)

    def test_UI_membership_reuse_does_not_hide_new_definition_ambiguity(self):
        from data.catalog_reads import catalog_reads
        from data.feature_store import PublicationError
        feature=self.chosen('expansion');store=FeatureStore(self.root)
        with catalog_reads(self.root) as dependencies:
            self.assertEqual(store.resolve(reference(feature)),feature)
            duplicate=self.root/'definitions/providers'/feature['id']/'1.0.0.json'
            duplicate.parent.mkdir(parents=True);duplicate.write_bytes(canonical_bytes(feature)+b'\n')
            self.assertFalse(dependencies.unchanged())
        with catalog_reads(self.root),self.assertRaisesRegex(PublicationError,'Ambiguous definition'):
            FeatureStore(self.root).resolve(reference(feature))

    def test_unit_regime_boundary_never_carries_an_old_unit_forward(self):
        folder=self.base/'common'
        db=sqlite3.connect(folder/'common.sqlite');db.row_factory=sqlite3.Row
        db.execute("UPDATE feature_states SET unit='basis points',block_mask=0 WHERE state_id=2")
        db.commit()
        projections=list(panels.projections(db,'common',CAP))
        regimes=[p for p in projections if p['layer']=='archive']
        self.assertEqual(len(regimes),2)
        percent=next(p for p in regimes if p['selector']['native_unit']=='percent per annum')
        bp=next(p for p in regimes if p['selector']['native_unit']=='basis points')
        old=list(panels.source_rows(db,percent));new=list(panels.source_rows(db,bp));db.close()
        self.assertEqual([r['value'] for r in old],['2.0',None])
        self.assertEqual([r['value'] for r in new],[None,'3.0'])
        self.assertEqual(old[-1]['reason_code'],'NATIVE_UNIT_OR_CADENCE_REGIME_CHANGED')
        self.assertEqual(percent['summary']['row_count'],2)
        with self.assertRaisesRegex(ValueError,'differs from original archive'):
            panels.package_plan(folder,'common',folder.with_suffix('.zip'))

    def test_real_target_plan_preparation_and_phase_load(self):
        from test_research_inputs import ResearchInputsTests
        from research import inputs
        target=ResearchInputsTests(methodName='runTest');target.setUp();self.addCleanup(target.tearDown)
        folder=self.base/'target-panel';fixture(folder,'expansion')
        db=sqlite3.connect(folder/'market.sqlite')
        for key in ('available_from','available_until','period_start','period_end','reference_date','reference_end'):
            db.execute('UPDATE feature_states SET '+key+'=replace('+key+",'2020-','2024-')")
        db.execute("UPDATE metadata SET value_json=? WHERE key='input_freeze'",(json.dumps({'capture_at':'2024-05-02T20:00:00Z'}),))
        db.commit();db.close()
        with zipfile.ZipFile(folder.with_suffix('.zip'),'w') as z:
            for source in folder.iterdir():z.write(source,folder.name+'/'+source.name)
        package=panels.package_plan(folder,'expansion',folder.with_suffix('.zip'))
        plan=panels.make_plan([package])
        with patch.dict(os.environ,GAMBIT_ISOLATED_TEST='1'):panels.install(target.root,plan,plan['plan_sha256'],isolated=True)
        f=next(json.loads(p.read_text()) for p in (target.root/'definitions/features').glob('*/*.json')
            if json.loads(p.read_text()).get('schema_version')==panels.SCHEMA and
            json.loads(p.read_text())['body']['projection']['layer']=='archive')
        policy=panel_features.policy();path=target.root/'definitions/alignment_policies'/policy['id']/'1.0.0.json'
        path.parent.mkdir(parents=True);path.write_bytes(canonical_bytes(policy)+b'\n')
        from research.contracts import ref
        profile=dict(target.profile,external_alignment_policy=ref(policy))
        intent=dict(target.intent,feature={k:f[k] for k in ('id','version')})
        resolved=inputs.resolve_plan(target.root,intent,profile)
        inputs._validate_plan(resolved)
        prepared=inputs.prepare_phase(target.root,resolved,'P1')
        loaded=inputs.load_phase(target.root,resolved,prepared,'P1',1)
        self.assertTrue(loaded['rows'])
        self.assertTrue(any(row['feature']=='2.0' for row in loaded['rows']))
        self.assertTrue(all(row['feature'] is None for row in loaded['rows'] if row['date']>='2024-01-04'))
        self.assertTrue(all(row['lineage']['panel_alignment']['source_layer']=='archive' for row in loaded['rows']))


if __name__=='__main__':unittest.main()
