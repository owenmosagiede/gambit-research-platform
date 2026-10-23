"""Synthetic list references, narrow preparation retirement, and online preflight."""
import json
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
    setUp=baseline.CurrencyDeletionTests.setUp
    put=baseline.CurrencyDeletionTests.put
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
