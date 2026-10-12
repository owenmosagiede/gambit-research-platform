"""HTTP Submit → real queue/worker → external alignment → real P1/P2 → authority.

All numerical inputs are deterministic synthetic fixtures in temporary stores.
Source admission/Scope discovery are fixture boundaries, not research mocks.
"""
from copy import deepcopy
from decimal import Decimal
from http.client import HTTPConnection
from pathlib import Path
import json
import math
import shutil
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from api.server import make_server
from data.feature_store import publish_feature
from data.targets.fx import materialize
from data.transformations.contracts import decimal_text
from data.transformations.identity import digest, reference
from research import external_features, inputs
from research.contracts import canonical
from runtime.research_jobs import ResearchJobs
from test_feature_store import persistence_fixture
from test_pit_feature_adapter import fixture as source_template
from test_external_feature_alignment import install_policy
import test_research_end_to_end as existing_fixture
from test_research_policy_inputs import scheduled_profile


def long_external(root):
    source=source_template();template=source['rows'][0];native=[];level=Decimal('100')
    # One source state per month, known the following month, with a varying
    # deterministic fractional change. No research outcome is mocked or supplied.
    for index in range(32):
        year,month=divmod(2019*12+11+index,12);month+=1
        ny,nm=divmod(year*12+month,12);nm+=1
        change=Decimal(str(.02*math.sin(index*.8)+.004*math.cos(index*.23)))
        level*=1+change
        native.append(dict(template,period=f'{year:04d}-{month:02d}-01',known=f'{ny:04d}-{nm:02d}-02',
            amount=decimal_text(level),raw_field=f'VALUE_{ny:04d}{nm:02d}02',next_known=None,entity='US'))
    source['rows']=native;source['dataset']['body']['economic_entity_ids']=['US']
    source['source_view']['body']['entity_selection']['entity_ids']=['US'];source['mapping']['entity_id']='US'
    with tempfile.TemporaryDirectory() as folder:
        src=Path(folder)
        args=persistence_fixture(src,source_fixture=source,cutoffs=[row['known'] for row in native],
            snapshot_period={'start_inclusive':'2019-12-01T00:00:00.000000Z','end_exclusive':'2022-08-01T00:00:00.000000Z'},
            information_cutoff='2022-09-01T00:00:00.000000Z')
        saved=publish_feature(src,**args)
        shutil.copytree(src,root,dirs_exist_ok=True)
    from research.feature_applications import install_binding, SINGLE_SERIES
    install_binding(root, args["feature"], SINGLE_SERIES)
    return args,saved


class ExternalFeatureEndToEndTests(unittest.TestCase):
    def test_external_submit_preflight_worker_real_p1_p2_results_and_reuse(self):
        fixture=existing_fixture.StoredResearchEndToEndTests(methodName='runTest');fixture.setUp();self.addCleanup(fixture.doCleanups)
        root=fixture.root;args,saved=long_external(root)
        profile=scheduled_profile(fixture.profile)
        profile=install_policy(root,profile)
        fixture.scope.update(id='USDJPY',kind='instrument',members=['USDJPY'],display_name='USDJPY')
        fixture.scope['reference']=dict(fixture.scope['reference'],id='USDJPY')
        self.addCleanup(patch.stopall)
        patch('data.scopes.resolve_scope',side_effect=lambda *a,**kw:deepcopy(fixture.scope)).start()
        source=external_features.resolve_source(root,args['feature'],profile)
        states=external_features.phase_rows(root,source,{'start_inclusive':'2020-10-01','end_exclusive':'2022-06-01'})
        # Retain the existing valid Target definitions/construction; synthesize
        # independently sourced prices with a noisy relationship to the state.
        snapshot,prices=next(v for v in fixture.states.values() if v[0]['body']['instrument_id']=='USDJPY')
        value=100.0
        for t,row in enumerate(prices):
            row['value']=decimal_text(Decimal(str(value)));row['id']='FXPRICE_'+digest({k:v for k,v in row.items() if k!='id'})
            state,_,reason=external_features.state_at(states,row['reference_time'],source['policy'])
            x=float(state['value']) if state and reason is None else 0
            value*=1+.08*x+.00015*math.sin(t*.71)
        # Remove one price: the canonical scheduled endpoint must remain missing.
        prices[:]=[r for r in prices if r['reference_time']!='2021-03-17']
        from data.fx_records import make_record
        body=deepcopy(snapshot['body'])
        body['recipe']=fixture.store.install_record(make_record('transformation_definition',{'kind':'ISOLATED_EXTERNAL_RELATIONSHIP_PRICE_FIXTURE'}))
        snapshot=make_record('snapshot_manifest',body);snapshot_ref=fixture.store.install_record(snapshot)
        fixture.states[snapshot_ref['id']]=(snapshot,prices)
        next(item for item in fixture.current if item['instrument_id']=='USDJPY')['price_snapshot']=snapshot_ref
        targets=materialize(root,snapshot_ref,fixture.fx.batch,knowledge_cutoff='2024-05-02')
        # Pin the synthetic updated target manifests instead of choosing among old/new captures.
        profile['target_selection']['materializations']={'USDJPY':{}}
        store=inputs.TargetStore(root)
        refs=targets
        for item in refs:
            binding=item.get('materialization',item)
            manifest=store.resolve(binding);definition=store.resolve(manifest['definition'])
            profile['target_selection']['materializations']['USDJPY'][str(definition['body']['horizon']['amount'])]=reference(manifest)
        path=root/'definitions/research_specs'/profile['id']/(profile['version']+'.json')
        path.write_bytes(canonical(profile)+b'\n')
        from research.contracts import ref
        (root/'config/external_feature_alignment.json').write_bytes(canonical({'research_spec':ref(profile)})+b'\n')
        request={'request_id':str(uuid.uuid4()),'feature':{k:args['feature'][k] for k in ('id','version')},
                 'scope':{'id':'USDJPY','version':'1.0.0'},'target_family':'price_return','expected_direction':'POSITIVE'}
        jobs=ResearchJobs(root);self.addCleanup(jobs.close)
        server=make_server(root,research_jobs=jobs);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def close():server.shutdown();server.server_close();thread.join(2)
        self.addCleanup(close)
        origin='http://127.0.0.1:'+str(server.server_address[1])
        def http(path,method='GET',body=None):
            connection=HTTPConnection('127.0.0.1',server.server_address[1],timeout=60)
            try:
                connection.request(method,path,None if body is None else json.dumps(body),
                                   {'Origin':origin,'Content-Type':'application/json'})
                response=connection.getresponse();return response.status,json.loads(response.read())
            finally:connection.close()
        query='/api/feature-resolution?feature_id='+request['feature']['id']+'&feature_version=1.0.0&scope_id=USDJPY&scope_version=1.0.0'
        with patch('research.inputs.prepare_phase',side_effect=AssertionError('Preflight must not prepare')):
            code,resolution=http(query);self.assertEqual(code,200,resolution);self.assertTrue(resolution['submission_compatible'],resolution)
            code,queue=http('/api/experiments');self.assertEqual(code,200)
        self.assertFalse((root/'storage/catalog/submissions').exists())
        # UI and backend agree: an external Feature cannot be broadcast to a universe.
        fixture.scope['kind']='universe'
        code,rejected=http(query);self.assertEqual(code,200);self.assertFalse(rejected['submission_compatible'])
        code,rejected=http('/api/experiments','POST',request);self.assertEqual(code,422,rejected)
        self.assertFalse(rejected['recorded']);self.assertFalse((root/'storage/catalog/submissions').exists())
        fixture.scope['kind']='instrument'
        original_features=len(list((root/'storage/catalog/feature_store').glob('*/manifest.json')))
        code,submitted=http('/api/experiments','POST',request);self.assertEqual(code,202,submitted)
        self.assertEqual(submitted['job']['status'],'queued')
        envelope=jobs._submission(request['request_id'])
        self.assertEqual(envelope['frozen_plan']['recipe'],reference(args['feature']))
        # Submit connection is closed. Worker executes independently of the UI.
        jobs.start();deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            job=jobs.get(request['request_id'])
            if job['status'] in ('succeeded','failed','blocked'):break
            time.sleep(.1)
        self.assertEqual(job['status'],'succeeded',job)
        self.assertEqual(job['mode'],'TS');self.assertEqual(len(job['horizons']),5)
        results=jobs.store.results_for_recipe(args['feature']['id'])
        self.assertEqual({r['horizon'] for r in results},{1,7,21,63,252})
        self.assertGreaterEqual(sum(x['stage']=='P2' for r in results for x in r['results']),1,results)
        p1=next(x for r in results if r['horizon']==1 for x in r['results'] if x['stage']=='P1')
        trial=jobs.store.resolve('trial',p1['authority'])
        artifact=jobs.store.verify_artifact(trial['body']['artifact_manifests'][0])
        aligned=next(m for m in artifact['members'] if m['role']=='aligned_sample');sha=aligned['blob_sha256']
        rows=json.loads((root/f'storage/payloads/sha256/{sha[:2]}/{sha}.json').read_bytes())
        self.assertTrue(rows)
        counts=p1['sample']['external_alignment']
        self.assertGreater(counts['aligned_weekday_rows'],counts['distinct_source_update_count'])
        self.assertGreater(counts['distinct_source_update_count'],1)
        self.assertTrue(all(r['lineage']['source_selection']['entity_id']=='US' and r['instrument']=='USDJPY' for r in rows))
        self.assertTrue(all(r['date']<'2022-01-01' and r['target_end']<'2022-01-01' for r in rows))
        code,detail=http('/api/signal-library/'+saved['signal_id']);self.assertEqual(code,200,detail)
        self.assertEqual(detail['research']['state'],'results_linked');self.assertEqual(detail['research']['relationship_count'],5)
        self.assertEqual(len(list((root/'storage/catalog/feature_store').glob('*/manifest.json'))),original_features)
        trial_count=len(list((root/'storage/catalog/trial_ledger').rglob('*.json')))
        code,again=http('/api/experiments','POST',request);self.assertEqual(code,200,again)
        self.assertEqual(len(list((root/'storage/catalog/trial_ledger').rglob('*.json'))),trial_count)
        # A different submission reuses exact scientific evidence, not only request IDs.
        repeat=dict(request,request_id=str(uuid.uuid4()))
        code,_=http('/api/experiments','POST',repeat);self.assertEqual(code,202)
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            job=jobs.get(repeat['request_id'])
            if job['status'] in ('succeeded','failed','blocked'):break
            time.sleep(.1)
        self.assertEqual(job['status'],'succeeded',job)
        self.assertEqual(len(list((root/'storage/catalog/trial_ledger').rglob('*.json'))),trial_count)
        # Selecting another instrument never changes the external Feature identity.
        fixture.scope.update(id='EURUSD',members=['EURUSD']);fixture.scope['reference']['id']='EURUSD'
        other=dict(request,scope={'id':'EURUSD','version':'1.0.0'});other.pop('request_id')
        otherprofile=deepcopy(profile);otherprofile['target_selection']['materializations']={}
        plan=inputs.resolve_plan(root,other,otherprofile)
        self.assertEqual(plan['recipe'],reference(args['feature']));self.assertEqual(plan['mode'],'TS')


if __name__=='__main__':unittest.main()
