"""Source archive and deployment transactions use disposable files and services."""
from contextlib import ExitStack
from datetime import datetime, timezone, timedelta
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT/'tools'))
import release_bundle as bundle
spec = importlib.util.spec_from_file_location('release_server_test', PROJECT/'deploy/release_server.py')
server = importlib.util.module_from_spec(spec); spec.loader.exec_module(server)


def artifact(files):
    return {'schema': 'gambit_code_release_v1', 'commit': 'a'*40,
            'repository': 'owenmosagiede/gambit-research-platform',
            'files': [{'path': n, 'sha256': bundle.sha(d), 'bytes': len(d)} for n,d in files.items()]}


class FakeMachine(server.Machine):
    def __init__(self, base):
        super().__init__(base/'project', base/'releases', base/'backup')
        self.root.mkdir(); self.backup.mkdir()
        (self.backup/'status.json').write_text(json.dumps({'status': 'succeeded',
            'snapshot_id': 'verified-test-backup', 'finished_at': datetime.now(timezone.utc).isoformat()}))
        self.states = dict.fromkeys(server.UNITS, 'active'); self.events=[]; self.jobs=[]
        self.after_stop = False; self.fail_write = False; self.failed = False; self.fail_health = 0
    def queue(self): return list(self.jobs)
    def status(self, unit): return self.states[unit]
    def stop(self, unit):
        self.events.append(('stop', unit)); self.states[unit]='inactive'
        if self.after_stop and unit==server.UNITS[0]: self.jobs=['racing-request']
    def start(self, unit): self.events.append(('start', unit)); self.states[unit]='active'
    def health(self):
        if self.fail_health: self.fail_health-=1; raise RuntimeError('injected health failure')
    def write(self, path, data):
        if self.fail_write and not self.failed: self.failed=True; raise RuntimeError('injected write failure')
        server.atomic(path, data)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.base=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup); self.m=FakeMachine(self.base)
        (self.m.root/'src').mkdir(); (self.m.root/'src/example.py').write_bytes(b'old code\n')
        (self.m.root/'storage').mkdir(); self.data=self.m.root/'storage/research-history.json'
        self.data.write_bytes(b'authoritative observations and historical results')
        self.files={'src/example.py': b'new code\n'}; self.manifest=artifact(self.files)
    def proposal(self): return server.plan(self.m.root,self.manifest,self.files)
    def apply(self): return server.apply(self.m,self.manifest,self.files,self.proposal()['plan_sha256'])
    def archive(self, files=None, extra=None):
        files=files or self.files; output=self.base/'source.tar.gz'
        with tarfile.open(output,'w:gz') as tar:
            payloads=dict(files, **{'release-manifest.json':bundle.canonical(artifact(files))})
            if extra: payloads.update(extra)
            for name,data in payloads.items():
                member=tarfile.TarInfo(name);member.size=len(data);tar.addfile(member,io.BytesIO(data))
        return output
    def test_archive_checksums_and_manifest_verified(self):
        p=self.archive();manifest,files=bundle.verify(p,bundle.sha(p.read_bytes()))
        self.assertEqual(manifest,self.manifest);self.assertEqual(files,self.files)
        with self.assertRaisesRegex(ValueError,'checksum'):bundle.verify(p,'0'*64)
    def test_storage_secrets_traversal_and_unlisted_members_rejected(self):
        for name in ('storage/observations.json','auth/auth.sqlite3','config/storage.local.json',
                     'src/../storage/raw.json','/tmp/escape','deploy/private/key','config/.env','config/.gitkeep'):
            with self.subTest(name=name):self.assertFalse(bundle.safe_path(name))
        p=self.archive(extra={'src/not-in-manifest.py':b'x'})
        with self.assertRaisesRegex(ValueError,'inventory'):bundle.verify(p,bundle.sha(p.read_bytes()))
    def test_secret_material_rejected(self):
        p=self.archive({'src/bad.py':('ghp_'+'x'*40).encode()})
        with self.assertRaisesRegex(ValueError,'verification'):bundle.verify(p,bundle.sha(p.read_bytes()))
    def test_tar_link_rejected(self):
        p=self.base/'link.tar.gz'
        with tarfile.open(p,'w:gz') as tar:
            member=tarfile.TarInfo('src/link');member.type=tarfile.SYMTYPE;member.linkname='../storage';tar.addfile(member)
        with self.assertRaisesRegex(ValueError,'Unsafe'):bundle.verify(p,bundle.sha(p.read_bytes()))
    def test_plan_is_read_only_and_requires_separate_policy_migration(self):
        self.files['definitions/policies/test.json']=b'new policy';self.manifest=artifact(self.files)
        before=self.data.read_bytes();p=self.proposal()
        self.assertTrue(p['blockers']);self.assertEqual(self.m.events,[]);self.assertEqual(self.data.read_bytes(),before)
        with self.assertRaisesRegex(RuntimeError,'migration'):self.apply()
    def test_existing_code_removal_blocked(self):
        (self.m.root/'src/extra.py').write_bytes(b'existing')
        self.assertTrue(self.proposal()['blockers'])
    def test_schema_dependencies_and_service_changes_require_explicit_migration(self):
        for name in ('specs/schema.json','requirements-cloud.lock','deploy/systemd/gambit-worker.service',
                     'deploy/backup_cloud.py','deploy/gunicorn.conf.py','deploy/install_services.sh'):
            with self.subTest(name=name):
                files=dict(self.files);files[name]=b'changed contract or service'
                proposal=server.plan(self.m.root,artifact(files),files)
                self.assertTrue(any(row['path']==name for row in proposal['blockers']))
    def test_symlink_parent_cannot_redirect_code_into_storage(self):
        (self.m.root/'tools').symlink_to(self.m.root/'storage',target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'Unsafe'):server.safe_target(self.m.root,'tools/file.py')
    def test_success_preserves_data_and_supports_rollback(self):
        before=self.data.read_bytes();result=self.apply()
        self.assertEqual(result['status'],'succeeded');self.assertEqual(self.data.read_bytes(),before)
        self.assertEqual((self.m.root/'src/example.py').read_bytes(),b'new code\n')
        folder=next(self.m.state.glob('*/receipt.json')).parent
        restored=server.rollback(self.m,folder.name)
        self.assertEqual(restored['status'],'rolled_back')
        self.assertEqual((self.m.root/'src/example.py').read_bytes(),b'old code\n')
        self.assertEqual(self.data.read_bytes(),before)
    def test_packed_history_prevents_loose_only_deployment_and_rollback(self):
        self.files.update({'src/data/feature_store.py': b'from data.lineage_packs import PackedLineage',
                           'src/data/lineage_packs.py': b"FORMAT = 'fx_row_lineage_pack_v1'"})
        self.manifest=artifact(self.files)
        released=self.apply()
        catalog=self.m.root/'storage/catalog/lineage_packs/example.json'
        catalog.parent.mkdir(parents=True);catalog.write_text('{}')
        events=list(self.m.events)
        with self.assertRaisesRegex(RuntimeError,'compatible reader'):
            server.rollback(self.m,released['release_id'])
        self.assertEqual(self.m.events,events)
        old=dict(self.files);old['src/data/feature_store.py']=b'loose only reader'
        self.assertTrue(server.plan(self.m.root,artifact(old),old)['blockers'])

    def test_running_or_queued_work_is_never_stopped(self):
        self.m.jobs=['existing-request']
        with self.assertRaisesRegex(RuntimeError,'research exists'):self.apply()
        self.assertFalse(self.m.events);self.assertEqual((self.m.root/'src/example.py').read_bytes(),b'old code\n')
    def test_submit_racing_with_web_stop_restores_web_without_stopping_worker(self):
        self.m.after_stop=True
        with self.assertRaisesRegex(RuntimeError,'research exists'):self.apply()
        self.assertNotIn(('stop',server.UNITS[1]),self.m.events)
        self.assertTrue(all(s=='active' for s in self.m.states.values()))
    def test_changed_review_plan_blocked(self):
        p=self.proposal();(self.m.root/'src/example.py').write_bytes(b'unreviewed edit')
        with self.assertRaisesRegex(RuntimeError,'plan changed'):
            server.apply(self.m,self.manifest,self.files,p['plan_sha256'])
        self.assertFalse(self.m.events)
    def test_old_backup_blocks_before_service_changes(self):
        p=self.m.backup/'status.json';v=json.loads(p.read_text())
        v['finished_at']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat();p.write_text(json.dumps(v))
        with self.assertRaisesRegex(RuntimeError,'backup'):self.apply()
        self.assertFalse(self.m.events)
    def test_backup_lock_blocks_before_service_changes(self):
        with ExitStack() as stack:
            server.guard(stack,self.m.backup/'backup.lock')
            with self.assertRaisesRegex(RuntimeError,'owns'):self.apply()
        self.assertFalse(self.m.events)
    def test_failed_install_restores_code_and_services(self):
        self.m.fail_write=True
        with self.assertRaisesRegex(RuntimeError,'write failure'):self.apply()
        self.assertEqual((self.m.root/'src/example.py').read_bytes(),b'old code\n')
        self.assertTrue(all(s=='active' for s in self.m.states.values()))
    def test_failed_health_rolls_back_when_queue_still_empty(self):
        self.m.fail_health=1
        with self.assertRaisesRegex(RuntimeError,'previous code restored'):self.apply()
        self.assertEqual((self.m.root/'src/example.py').read_bytes(),b'old code\n')
    def test_failed_health_does_not_interrupt_new_research(self):
        def health(): self.m.jobs=['new-request'];raise RuntimeError('health failure')
        self.m.health=health
        with self.assertRaisesRegex(RuntimeError,'deferred safely'):self.apply()
        self.assertTrue(all(s=='active' for s in self.m.states.values()))
        self.assertEqual((self.m.root/'src/example.py').read_bytes(),b'new code\n')
        receipt=json.loads(next(self.m.state.glob('*/receipt.json')).read_text())
        self.assertEqual(receipt['status'],'rollback_required')
    def test_duplicate_apply_is_noop(self):
        self.apply();events=list(self.m.events)
        self.assertEqual(self.apply()['status'],'already_installed');self.assertEqual(self.m.events,events)
    def test_release_can_be_applied_again_after_a_successful_rollback(self):
        first=self.apply();server.rollback(self.m,first['release_id']);second=self.apply()
        self.assertEqual(second['status'],'succeeded')
        self.assertNotEqual(first['release_id'],second['release_id'])
        self.assertEqual(len(list(self.m.state.glob('*/receipt.json'))),2)
    def test_failed_restoration_leaves_services_stopped(self):
        def broken_write(path, data): raise RuntimeError('disk unavailable')
        self.m.write=broken_write
        with self.assertRaisesRegex(RuntimeError,'disk unavailable'):self.apply()
        self.assertTrue(all(s=='inactive' for s in self.m.states.values()))
        receipt=json.loads(next(self.m.state.glob('*/receipt.json')).read_text())
        self.assertEqual(receipt['status'],'rollback_required')
    def test_real_authoritative_queue_read_does_not_reenter_writer_lock(self):
        from runtime.research_jobs import ResearchJobs
        from test_research_runtime import Adapter, intent, profile
        (self.m.root/'config').mkdir()
        (self.m.root/'config/research_execution.json').write_text(json.dumps(profile()))
        request=intent();ResearchJobs(self.m.root,adapter=Adapter()).submit(request)
        before={str(p):p.read_bytes() for p in (self.m.root/'storage').rglob('*') if p.is_file()}
        with ExitStack() as stack:
            server.guard(stack,self.m.root/'storage/catalog/operations/research-writer.lock')
            actual=server.Machine(self.m.root,self.m.state,self.m.backup).queue()
        self.assertEqual(actual,[request['request_id']])
        self.assertEqual(before,{str(p):p.read_bytes() for p in (self.m.root/'storage').rglob('*') if p.is_file()})


if __name__=='__main__':unittest.main()

class BatchReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.bid='a0000000-0000-4000-8000-000000000001'
        self.folder=self.root/'storage/catalog/operations/research_batches'/self.bid
        self.machine=server.Machine(self.root)

    def record(self,state='paused',schema='research_batch_v1'):
        from legacy_batch_fixture import save
        save(self.folder/'manifest.json',{'schema':schema,'batch_id':self.bid})
        if state is not None:save(self.folder/'state.json',{'state':state})

    def test_paused_batch_blocks_code_release_without_jobs(self):
        from legacy_batch_fixture import save
        self.record();before={str(path):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(self.machine.queue(),['batch:'+self.bid])
        self.assertEqual(before,{str(path):path.read_bytes() for path in self.root.rglob('*') if path.is_file()})
        save(self.folder/'state.json',{'state':'completed'},mutable=True)
        self.assertEqual(self.machine.queue(),[])

    def test_every_unfinished_state_and_missing_state_blocks(self):
        from legacy_batch_fixture import save
        self.record(state=None)
        self.assertEqual(self.machine.queue(),['batch:'+self.bid])
        for state in ('previewing','ready','approved','dispatching','paused','needs_attention'):
            with self.subTest(state=state):
                save(self.folder/'state.json',{'state':state},mutable=True)
                self.assertEqual(self.machine.queue(),['batch:'+self.bid])

    def test_completed_retained_ts_history_is_readable_without_scheduler(self):
        from unittest.mock import patch
        self.record('completed','research_batch_retained_ts_v1')
        with patch.dict(sys.modules,{'runtime.research_batches':None}):
            self.assertEqual(self.machine.queue(),[])

    def test_orphaned_or_corrupt_batch_history_fails_closed(self):
        from research.contracts import ResearchError
        self.folder.mkdir(parents=True)
        (self.folder/'state.json').write_text('{}')
        with self.assertRaisesRegex(ResearchError,'Incomplete'):self.machine.queue()
        (self.folder/'manifest.json').write_text('{}')
        with self.assertRaisesRegex(ResearchError,'checksum'):self.machine.queue()

    def test_unknown_schema_state_and_wrong_identity_fail_closed(self):
        from research.contracts import ResearchError
        from legacy_batch_fixture import save
        self.record('completed')
        for field,value in (('schema','unknown_batch_v9'),('batch_id','a0000000-0000-4000-8000-000000000002')):
            manifest={'schema':'research_batch_v1','batch_id':self.bid};manifest[field]=value
            save(self.folder/'manifest.json',manifest,mutable=True)
            with self.assertRaisesRegex(ResearchError,'identity or schema'):self.machine.queue()
        save(self.folder/'manifest.json',{'schema':'research_batch_v1','batch_id':self.bid},mutable=True)
        save(self.folder/'state.json',{'state':'retired'},mutable=True)
        with self.assertRaisesRegex(ResearchError,'Unknown legacy batch state'):self.machine.queue()

    def test_symlink_or_unexpected_namespace_file_fails_closed(self):
        from research.contracts import ResearchError
        self.folder.parent.mkdir(parents=True)
        target=self.root/'external';target.mkdir()
        self.folder.symlink_to(target,target_is_directory=True)
        with self.assertRaisesRegex(ResearchError,'Unexpected'):self.machine.queue()
        self.folder.unlink();self.folder.write_text('orphan evidence')
        with self.assertRaisesRegex(ResearchError,'Unexpected'):self.machine.queue()

    def test_legacy_preview_keeps_original_approval_hash_without_writes(self):
        from data.legacy_batch_evidence import preview
        from legacy_batch_fixture import save
        from research.contracts import digest
        manifest=save(self.folder/'manifest.json',{'schema':'research_batch_v1','batch_id':self.bid,
            'request':{'estimate_basis':{'description':'Synthetic calibration','seconds_per_experiment':[1,3],
                                       'bytes_per_experiment':[5,8]}}})
        for index,disposition in enumerate(('new','reuse','blocked')):
            save(self.folder/'rows'/f'{index}.json',{'index':index,'disposition':disposition,
                'scheduled_member_rows':{'P1':10,'P2':20}})
        before={str(path):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        # Captured from the pre-retirement ResearchBatches._preview implementation.
        self.assertEqual(digest(preview(self.folder,manifest)),
            '7bbc65ba729c09090c03bd0585d9ec5fdd44332bd09627bc4b4950cab450a44a')
        self.assertEqual(before,{str(path):path.read_bytes() for path in self.root.rglob('*') if path.is_file()})
