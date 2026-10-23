"""Synthetic list references, narrow preparation retirement, and online preflight."""
import json
import os
import time
import uuid
from pathlib import Path
from unittest.mock import patch
import unittest
from data.fx_currency_migration import plan,apply,RETIRED,_identities
from data.fx_catalog_preflight import catalog_preflight
from data.fx_preparation_retirement import PREFIX,INPUTS,SCHEMA,validate_request,watch_options,retirement_selection
from data.fx_migration_index import MigrationIndex,inventory,file_commitment
from data.fx_migration_manifest import manifest_digest
from data.scopes import PAIR_IDS
from data.transformations.identity import reference
from research.contracts import digest
import test_fx_currency_migration as baseline
from test_scopes import files


class PreparationTests(unittest.TestCase):
    def setUp(self):
        baseline.CurrencyDeletionTests.setUp(self)
        from data.fx_migration_index import HEARTBEAT
        self.heartbeat={'workspace':str(self.root),'pid':os.getpid(),'session_id':str(uuid.uuid4()),'monotonic_ns':time.monotonic_ns(),
            'health':{'healthy':True,'state':'idle','worker_alive':True,'supervisor_alive':True,'restart_count':0,'restart_limit':3,'last_error':None,'last_diagnostic':None}}
        self.put(HEARTBEAT,self.heartbeat)
    put=baseline.CurrencyDeletionTests.put
    completed_batch=baseline.CurrencyDeletionTests.completed_batch

    def tick_worker(self):
        from data.fx_migration_index import HEARTBEAT
        self.heartbeat['monotonic_ns']=time.monotonic_ns()
        (self.root/HEARTBEAT).write_text(json.dumps(self.heartbeat))

    def operational_bundle(self):
        from data.fx_operational_retirement import PROGRESS,PILOT,PILOT_FILES
        from runtime.research_batches import checked
        request,_=self.bundle();batches,bid=self.completed_batch();directory=batches.directory(bid)
        manifest=checked(directory/'manifest.json');preview=batches.status(bid)
        preview.pop('read_only');preview.pop('reconciliation')
        preview.update(approved=False,job_counts={})
        state={'state':'ready','updated_at':manifest['created_at']};state['sha256']=digest(state);preview['state']=state
        preview['items']=[{k:v for k,v in row.items() if k not in ('sha256','packet_sha256')} for row in batches._rows(directory)]
        self.put(PILOT+'manifest.json',manifest['request']);self.put(PILOT+'ready-preview.json',preview)
        paths=set(PILOT_FILES);ts_path=None
        for row in batches._rows(directory):
            dispatch=checked(directory/'dispatch'/f"{row['index']}.json");rid=dispatch['request_id']
            job=batches.jobs._read_job(rid);plan=batches.jobs.store.resolve('plan',job['plan'])['body']
            path=PROGRESS+rid+'.json'
            value={'request_id':rid,'attempt_id':job['attempt_id'],'plan':job['plan'],'plan_id':plan['plan_id'],
                'phase':'P1','state':'complete','members_total':len(plan['members']),'members_completed':len(plan['members']),
                'batches_completed':1,'instrument':None,'start':None,'end':None,'updated_at':job['updated_at']}
            self.put(path,value)
            if row['intent']['scope']['id'] in RETIRED:paths.add(path)
            else:ts_path=path
        request['operational_files']={p:file_commitment(self.root/p) for p in paths}
        self.tick_worker()
        return request,ts_path,batches,bid

    def test_exact_operational_retirement_preserves_ts_research_and_original_approval(self):
        from data.fx_operational_retirement import PILOT_FILES
        request,ts_path,batches,bid=self.operational_bundle();before=files(self.root)
        result=self.retirement_plan(request)
        self.assertEqual(result['blockers'],[])
        self.assertTrue(set(request['operational_files'])<=result['delete'].keys())
        self.assertNotIn(ts_path,result['delete'])
        with MigrationIndex(self.root) as index:
            for p in PILOT_FILES:self.assertFalse(index.db.execute('SELECT 1 FROM owners WHERE path=?',(p,)).fetchone())
        with patch('data.fx_preparation_retirement.runtime_blockers',return_value=[]):apply(self.root,result,result['sha256'])
        after=files(self.root)
        for p in before:
            if p not in result['delete'] and p not in result['replace']:self.assertEqual(before[p],after[p],p)
        self.assertEqual(batches.status(bid)['job_counts'],{'succeeded':1})
        self.assertEqual(before[ts_path],after[ts_path])
        approval=f'storage/catalog/operations/research_batches/{bid}/approval.json'
        self.assertEqual(before[approval],after[approval])

    def test_operational_retirement_rejects_ts_changed_unknown_and_active_records(self):
        from data.fx_operational_retirement import PROGRESS
        from copy import deepcopy
        request,ts_path,_,_=self.operational_bundle()
        bad=deepcopy(request);bad['operational_files'][ts_path]=file_commitment(self.root/ts_path)
        self.assertFalse(self.preflight(bad)['catalog_ready'])
        old=next(p for p in request['operational_files'] if p.startswith(PROGRESS));original=(self.root/old).read_bytes()
        for change in ({'state':'preparing_batch'},{'attempt_id':str(uuid.uuid4())},{'plan_id':'WRONG'},{'unexpected':'data'}):
            value=json.loads(original);value.update(change);(self.root/old).write_text(json.dumps(value))
            bad=deepcopy(request);bad['operational_files'][old]=file_commitment(self.root/old)
            self.tick_worker()
            result=self.preflight(bad);self.assertFalse(result['catalog_ready']);self.assertEqual(result['operational_files_selected'],0)
            self.assertTrue(any('Unverifiable preparation evidence' in b for b in result['blockers']))
        (self.root/old).write_bytes(original)
        (self.root/old).write_text('{}');self.assertFalse(self.preflight(request)['catalog_ready'])

    def test_pilot_unreviewed_path_or_mismatched_export_blocks(self):
        from data.fx_operational_retirement import PILOT
        request,_,_,_=self.operational_bundle()
        p=PILOT+'ready-preview.json';value=json.loads((self.root/p).read_text());value['items'][0]['intent']['scope']['id']='WRONG'
        (self.root/p).write_text(json.dumps(value));request['operational_files'][p]=file_commitment(self.root/p)
        self.assertFalse(self.preflight(request)['catalog_ready'])
        request['operational_files']['storage/catalog/trial_ledger/records/fake.json']={'sha256':'a'*64,'bytes':1}
        with self.assertRaises(ValueError):validate_request(request)

    def test_external_operational_path_and_hash_consumers_block(self):
        request,_,_,_=self.operational_bundle();p=next(iter(request['operational_files']))
        self.put('storage/catalog/auxiliary/external.json',{'command':'inspect '+str(self.root/p),'hash':request['operational_files'][p]['sha256']})
        result=self.preflight(request)
        self.assertFalse(result['catalog_ready']);self.assertEqual(result['operational_files_selected'],0)
        self.assertTrue(result['preparation_dependencies'])

    def test_preparation_reference_never_owns_a_published_research_artifact(self):
        from research.contracts import ref
        request,_=self.bundle();artifact=self.store.artifact({'owner':'published'},{'rows':[7,8]})
        p=PREFIX+INPUTS[1];value=json.loads((self.root/p).read_text());value.append({'artifact':ref(artifact)})
        (self.root/p).write_text(json.dumps(value));request['files'][p]=file_commitment(self.root/p)
        hashes={n:request['files'][PREFIX+n]['sha256'] for n in INPUTS}
        # A changed frozen input requires a new consistent synthetic program.
        old=next(p for p in request['files'] if p.endswith('/program.json'));base=old.rsplit('/',1)[0]
        for name in ('program.json','status.json'):(self.root/base/name).unlink();request['files'].pop(base+'/'+name)
        program={'kind':'momentum_discovery_preparation_v1','inputs':hashes,'research_executed':False};base=PREFIX+'progress/'+digest(program)
        self.put(base+'/program.json',program);self.put(base+'/status.json',{'status':'paused','research_executed':False})
        request['files']={p:v for p,v in inventory(self.root).items() if p.startswith(PREFIX)};request['bundle_sha256']=digest(hashes)
        result=self.retirement_plan(request);self.assertEqual(result['blockers'],[])
        self.assertFalse(any(artifact['id'] in p for p in result['delete']))
    def bundle(self):
        self.put(PREFIX+INPUTS[0],{'scopes':[{'id':s} for s in sorted(RETIRED|set(PAIR_IDS))]})
        self.put(PREFIX+INPUTS[1],[{'historical_feature':{'id':'PUBLISHED_FEATURE'},'sha256':'f'*64}])
        self.put(PREFIX+INPUTS[2],[{'scope_id':s} for s in sorted(RETIRED|set(PAIR_IDS))])
        hashes={n:file_commitment(self.root/PREFIX/n)['sha256'] for n in INPUTS}
        program={'kind':'momentum_discovery_preparation_v1','inputs':hashes,'research_executed':False}
        program_id=digest(program)
        self.put(PREFIX+'progress/'+program_id+'/program.json',program)
        self.put(PREFIX+'progress/'+program_id+'/status.json',{'status':'paused','research_executed':False})
        request={'schema':SCHEMA,'prefix':PREFIX,'files':{p:v for p,v in inventory(self.root).items() if p.startswith(PREFIX)},'bundle_sha256':digest(hashes)}
        return request,program_id

    def preflight(self,request):
        with patch('data.fx_preparation_retirement.runtime_blockers',return_value=[]),patch('data.fx_catalog_preflight.runtime_blockers',return_value=[]):
            return catalog_preflight(self.root,reference(self.release),retirement=request)

    def retirement_plan(self,request):
        with patch('data.fx_preparation_retirement.runtime_blockers',return_value=[]):
            return plan(self.root,reference(self.release),retirement=request)

    def test_list_references_are_not_owners_and_still_block_without_retirement(self):
        request,_=self.bundle()
        self.put('storage/catalog/auxiliary/published.json',{'id':'PUBLISHED_FEATURE'})
        with MigrationIndex(self.root) as index:
            self.assertEqual(_identities(index.records[PREFIX+INPUTS[1]]),set())
            self.assertFalse(index.db.execute('SELECT 1 FROM owners WHERE path=?',(PREFIX+INPUTS[1],)).fetchone())
            index.select(['storage/catalog/auxiliary/published.json'])
            self.assertIn(PREFIX+INPUTS[1],index.related())
        result=plan(self.root,reference(self.release))
        self.assertIn('Retained consumer references deletion: '+PREFIX+INPUTS[2],result['blockers'])
        self.assertNotIn(PREFIX+INPUTS[1],result['delete'])

    def test_only_frozen_bundle_retired_preserves_published_data_and_ts_results(self):
        request,_=self.bundle()
        self.put('storage/catalog/auxiliary/published-feature.json',{'id':'PUBLISHED_FEATURE'})
        self.put('storage/catalog/auxiliary/published-target.json',{'id':'PUBLISHED_TARGET'})
        # A payload referenced solely by a prep table is still not prep-owned.
        blob=self.root/'storage/payloads/sha256/ff'/('f'*64+'.json');blob.parent.mkdir(parents=True,exist_ok=True);blob.write_text('preserved')
        before=files(self.root);result=self.retirement_plan(request)
        self.assertEqual(result['blockers'],[])
        self.assertEqual(set(request['files']),{p for p in result['delete'] if p.startswith(PREFIX)})
        self.assertEqual(len(result['protected_ts']),86)
        with patch('data.fx_preparation_retirement.runtime_blockers',return_value=[]):apply(self.root,result,result['sha256'])
        after=files(self.root)
        for p in before:
            if p not in result['delete'] and p not in result['replace']:self.assertEqual(before[p],after[p],p)
        self.assertTrue(blob.exists())
        self.assertTrue(any(self.ts_trial['id'] in p for p in after))

    def test_changed_extra_and_missing_files_each_block(self):
        request,_=self.bundle();path=self.root/PREFIX/INPUTS[0];original=path.read_bytes()
        path.write_text('{}');self.assertTrue(self.preflight(request)['blockers']);path.write_bytes(original)
        self.put(PREFIX+'extra.json',{});self.assertTrue(self.preflight(request)['blockers']);(self.root/PREFIX/'extra.json').unlink()
        path.unlink();self.assertTrue(self.preflight(request)['blockers'])

    def test_incoming_path_hash_program_and_list_consumers_all_block(self):
        request,program_id=self.bundle()
        values=[PREFIX+INPUTS[0],str(self.root/PREFIX/INPUTS[1]),request['bundle_sha256'],request['files'][PREFIX+INPUTS[2]]['sha256'],program_id]
        for n,value in enumerate(values):
            self.put(f'storage/catalog/auxiliary/consumer-{n}.json',{'input':value})
        self.put('storage/catalog/operations/momentum-preparation-2026-10-18/instrument-preparation-matrix.json',[{'id':program_id}])
        self.put('config/consumer.json',{'command':'use '+str(self.root/PREFIX)})
        self.put('storage/catalog/auxiliary/key-consumer.json',{program_id:'cache'})
        self.put('storage/catalog/auxiliary/command-consumer.json',{'command':'prepare --expected-bundle-sha256 '+request['bundle_sha256']})
        result=self.preflight(request)
        self.assertFalse(result['catalog_ready']);self.assertEqual(result['preparation_files_selected'],0)
        self.assertEqual(len(result['preparation_dependencies']),9)

    def test_active_preparer_blocks_and_runtime_is_rechecked(self):
        request,_=self.bundle()
        with patch('data.fx_preparation_retirement.runtime_blockers',return_value=['Preparation unit may run']):
            result=plan(self.root,reference(self.release),retirement=request)
        self.assertIn('Preparation unit may run',result['blockers'])
        self.assertFalse(set(request['files'])&set(result['delete']))
        result=self.retirement_plan(request)
        with patch('data.fx_preparation_retirement.runtime_blockers',return_value=['active']),self.assertRaisesRegex(ValueError,'inactive'):
            apply(self.root,result,result['sha256'])

    def test_online_preflight_is_read_only_not_numerical_not_applyable(self):
        request,_=self.bundle();before=files(self.root)
        with patch('data.fx_currency_release.validate_release',side_effect=AssertionError('numerical replay forbidden')):
            result=self.preflight(request)
        self.assertTrue(result['catalog_ready'],result['blockers']);self.assertEqual(before,files(self.root))
        self.assertFalse(result['scientific_validation_performed']);self.assertFalse(result['apply_authorized'])
        result['sha256']=manifest_digest(result)
        with self.assertRaisesRegex(ValueError,'manifest'):apply(self.root,result,result['sha256'])

    def test_drift_during_online_scan_is_a_blocker(self):
        request,_=self.bundle()
        with patch('data.fx_catalog_preflight.inventory',return_value={}):result=self.preflight(request)
        self.assertIn('Catalog changed during online preflight; repeat on a stable view',result['blockers'])

    def test_unknown_shape_names_and_nonobject_rows_fail_with_path(self):
        for name,value in [('storage/catalog/auxiliary/unknown.json',[]),(PREFIX+INPUTS[1],[None]),(PREFIX+INPUTS[2],42)]:
            self.put(name,value)
            with self.assertRaisesRegex(ValueError,name):
                with MigrationIndex(self.root):pass
            (self.root/name).unlink()

    def test_request_cannot_include_scientific_records_or_arbitrary_paths(self):
        request,_=self.bundle()
        for path in ('definitions/scopes/EURUSD.json',PREFIX+'research-results.json',PREFIX+'../other.json'):
            bad=dict(request,files=dict(request['files']));bad['files'][path]={'sha256':'a'*64,'bytes':1}
            with self.assertRaises(ValueError):validate_request(bad)

    def test_research_executed_or_corrupt_program_is_never_retired(self):
        request,program_id=self.bundle();path=self.root/PREFIX/'progress'/program_id/'status.json'
        path.write_text(json.dumps({'status':'paused','research_executed':True}))
        request['files'][path.relative_to(self.root).as_posix()]=file_commitment(path)
        result=self.preflight(request)
        self.assertFalse(result['catalog_ready']);self.assertEqual(result['preparation_files_selected'],0)

    def test_online_heartbeat_updates_are_explicit_but_offline_hashes_still_pin_it(self):
        from data.fx_migration_index import HEARTBEAT
        request,_=self.bundle()
        original=inventory
        def changing(root,**kwargs):
            self.heartbeat['monotonic_ns']=time.monotonic_ns()
            (self.root/HEARTBEAT).write_text(json.dumps(self.heartbeat))
            return original(root,**kwargs)
        with patch('data.fx_catalog_preflight.inventory',side_effect=changing):result=self.preflight(request)
        self.assertTrue(result['catalog_ready'],result['blockers'])
        self.assertNotEqual(result['volatile_projection']['before']['sha256'],result['volatile_projection']['after']['sha256'])
        manifest=self.retirement_plan(request)
        self.assertIn(HEARTBEAT,manifest['inventory'])
        changing(self.root)
        with patch('data.fx_preparation_retirement.runtime_blockers',return_value=[]),self.assertRaisesRegex(ValueError,'changed'):
            apply(self.root,manifest,manifest['sha256'])

    def test_unhealthy_active_or_dependency_bearing_heartbeat_never_gets_ignored(self):
        from data.fx_migration_index import HEARTBEAT
        from copy import deepcopy
        request,_=self.bundle()
        for field,value in [('state','running'),('last_diagnostic',{'reference':request['bundle_sha256']}),('healthy',False),('unreviewed_field','anything')]:
            candidate=deepcopy(self.heartbeat);candidate['health'][field]=value
            (self.root/HEARTBEAT).write_text(json.dumps(candidate))
            result=self.preflight(request)
            self.assertFalse(result['catalog_ready']);self.assertIn(HEARTBEAT,' '.join(result['blockers']))

    def test_catalog_checksum_error_names_the_exact_record(self):
        from data.fx_migration_index import Records
        file='storage/catalog/auxiliary/checksum.json';self.put(file,{'id':'ORIGINAL'})
        records=Records(self.root,inventory(self.root));(self.root/file).write_text('{"id":"CHANGED"}')
        with self.assertRaisesRegex(ValueError,file+': source checksum mismatch'):records[file]


if __name__=='__main__':unittest.main()

class RuntimeProbeTests(unittest.TestCase):
    def test_inactive_timer_and_backup_stop_are_safe_but_live_or_enabled_units_block(self):
        import tempfile
        from data.fx_preparation_retirement import runtime_blockers,SERVICE
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);units=base/'units';units.mkdir();proc=base/'proc';proc.mkdir();empty=base/'empty';empty.mkdir()
            (units/'old.timer').write_text('Unit='+SERVICE+'\n')
            backup=units/'backup.service.d';backup.mkdir()
            (backup/'stop.conf').write_text('ExecStartPre=/usr/bin/systemctl stop '+SERVICE+'\n')
            def path(value):
                return {'/etc/systemd/system':units,'/run/systemd/system':empty,'/usr/lib/systemd/system':empty,'/proc':proc}[value]
            safe='LoadState=loaded\nActiveState=inactive\nMainPID=0\nUnitFileState=disabled\nTriggeredBy=\n'
            with patch('data.fx_preparation_retirement.Path',side_effect=path),patch('data.fx_preparation_retirement.subprocess.check_output',return_value=safe) as show:
                self.assertEqual(runtime_blockers(),[])
                self.assertEqual({call.args[0][2] for call in show.call_args_list},{SERVICE,'old.timer'})
            for state in (safe.replace('inactive','active'),safe.replace('disabled','enabled'),safe.replace('MainPID=0','MainPID=12')):
                with patch('data.fx_preparation_retirement.Path',side_effect=path),patch('data.fx_preparation_retirement.subprocess.check_output',return_value=state):
                    self.assertTrue(runtime_blockers())
            (proc/'123').mkdir();(proc/'123/cmdline').write_bytes(b'python\x00tools/prepare_momentum_population.py')
            with patch('data.fx_preparation_retirement.Path',side_effect=path),patch('data.fx_preparation_retirement.subprocess.check_output',return_value=safe):
                self.assertIn('Preparation process is active: 123',runtime_blockers())
