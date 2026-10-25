"""Retired batch execution cannot restart; ordinary research stays authoritative."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid

from research.contracts import ResearchConflict, ResearchError
from runtime.research_batches import ResearchBatches, checked, BASE
from runtime.research_jobs import ResearchJobs
from test_research_runtime import Adapter, KernelSpy, intent, profile
from legacy_batch_fixture import save as frozen_file

ROOT = Path(__file__).resolve().parents[1]


def manifest(**changes):
    """Historical request fixture only; never passed to a live batch service."""
    r = intent()
    return dict({'batch_id': str(uuid.uuid4()), 'name': 'Synthetic Momentum batch',
        'features': [r['feature']], 'scopes': [intent(mode='TS')['scope'], r['scope']],
        'target_family': 'price_return', 'expected_direction': 'POSITIVE', 'duplicate_policy': 'reuse_exact'}, **changes)


def inventory(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


class BatchRetirementTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'config').mkdir()
        (self.root/'config/research_execution.json').write_text(json.dumps(profile()))
        self.adapter, self.kernels = Adapter(), KernelSpy()
        self.jobs = ResearchJobs(self.root, adapter=self.adapter, kernels=self.kernels)
        self.addCleanup(self.jobs.close)

    def historical(self, state='approved'):
        request=manifest(); directory=self.root/BASE/request['batch_id']
        frozen_file(directory/'manifest.json', {'schema':'research_batch_v1', 'batch_id':request['batch_id'], 'request':request})
        frozen_file(directory/'state.json', {'state':state})
        frozen_file(directory/'approval.json', {'approval':{'preview_sha256':'a'*64,'exclude_blocked':False}})
        frozen_file(directory/'rows/0.json', {'index':0,'disposition':'new','intent':intent()})
        return directory

    def test_runtime_compatibility_is_read_only_and_construction_fails_before_access(self):
        import runtime.research_batches as module
        class NoAccess:
            def __getattr__(self, key):raise AssertionError('Retired batch accessed '+key)
        with self.assertRaisesRegex(ResearchConflict,'retired'):
            ResearchBatches(NoAccess())
        for name in ('create','approve','advance','control','status','_preview_row'):
            self.assertFalse(hasattr(ResearchBatches,name))
        self.assertFalse(hasattr(module,'save'))

    def test_old_approved_or_incomplete_batches_never_preview_or_dispatch(self):
        for state in ('approved','previewing','ready','dispatching','paused','needs_attention'):
            self.historical(state)
        before=inventory(self.root/BASE)
        with patch('runtime.research_batches.checked',side_effect=AssertionError('Worker read retired evidence')):
            self.jobs.run_pending_once()
            self.jobs.run_pending_once()
        self.assertEqual(inventory(self.root/BASE),before)
        self.assertFalse((self.root/'storage/catalog/submissions').exists())
        self.assertFalse((self.root/'storage/catalog/trial_ledger').exists())
        self.assertEqual(self.adapter.resolve_calls,0)
        self.assertFalse(self.adapter.preparations);self.assertFalse(self.kernels.calls)

    def test_background_worker_stays_idle_when_only_batch_history_exists(self):
        self.historical();before=inventory(self.root/BASE)
        with (patch.object(self.jobs,'_pending',side_effect=AssertionError('Batch directory woke research intake')),
              patch.object(self.jobs.wake,'wait',side_effect=lambda timeout:self.jobs.stop_event.set())):
            self.jobs._loop()
        self.assertEqual(self.jobs.worker_state,'idle')
        self.assertEqual(inventory(self.root/BASE),before)

    def test_ordinary_submission_and_exact_retry_work_beside_retired_history(self):
        self.historical();before=inventory(self.root/BASE)
        request=intent();first,created=self.jobs.submit(request)
        self.assertTrue(created);self.jobs.run_pending_once()
        result=self.jobs.get(first['request_id']);self.assertEqual(result['status'],'succeeded')
        self.assertEqual(len(result['results']),5)
        original=self.jobs._submission(first['request_id']);calls=list(self.kernels.calls)
        repeated,created=self.jobs.submit(dict(request,request_id=str(uuid.uuid4())))
        self.assertFalse(created);self.assertEqual(repeated['request_id'],first['request_id'])
        self.assertEqual(repeated['intake_action'],'view_results')
        self.jobs.run_pending_once()
        self.assertEqual(self.kernels.calls,calls)
        self.assertEqual(self.jobs._submission(first['request_id']),original)
        self.assertEqual(inventory(self.root/BASE),before)
        self.assertEqual(len(self.jobs.store.results_for_recipe(request['feature']['id'])),5)

    def test_ordinary_crash_recovery_keeps_original_request_and_batch_bytes(self):
        self.historical();before=inventory(self.root/BASE);request=intent()
        with patch.object(self.jobs,'_ensure_recorded',side_effect=OSError('Synthetic intake interruption')):
            with self.assertRaises(OSError):self.jobs.submit(request)
        self.jobs.run_pending_once()
        self.assertEqual(self.jobs.get(request['request_id'])['status'],'succeeded')
        self.assertEqual(len(self.jobs.list_jobs()['items']),1)
        self.assertEqual(inventory(self.root/BASE),before)

    def test_background_worker_recovers_journal_only_submission_after_restart(self):
        self.historical();before=inventory(self.root/BASE);request=intent()
        with patch.object(self.jobs,'_ensure_recorded',side_effect=OSError('Interrupted before envelope')):
            with self.assertRaises(OSError):self.jobs.submit(request)
        journal_path=self.root/'storage/catalog/operations/experiment_intake/requests'/(request['request_id']+'.json')
        journal_bytes=journal_path.read_bytes()
        frozen=json.loads(journal_bytes)['submission']
        self.assertFalse((self.root/'storage/catalog/submissions').exists())
        self.assertFalse((self.root/'storage/catalog/operations/jobs').exists())
        restarted=ResearchJobs(self.root,adapter=self.adapter,kernels=self.kernels)
        self.addCleanup(restarted.close)
        with patch.object(restarted.wake,'wait',side_effect=lambda timeout:restarted.stop_event.set()):
            restarted._loop()
        result=restarted.get(request['request_id'])
        self.assertEqual(result['status'],'succeeded')
        self.assertEqual(len(result['results']),5)
        self.assertEqual(restarted._submission(request['request_id']),frozen)
        self.assertEqual(len(restarted.list_jobs()['items']),1)
        self.assertEqual(self.adapter.resolve_calls,1)
        self.assertEqual(journal_path.read_bytes(),journal_bytes)
        self.assertEqual(inventory(self.root/BASE),before)

    def test_installed_controller_checksum_import_remains_strict_and_read_only(self):
        directory=self.historical();path=directory/'manifest.json';before=inventory(directory)
        value=checked(path);self.assertEqual(value['schema'],'research_batch_v1')
        self.assertEqual(inventory(directory),before)
        value['request']['name']='Changed without checksum';path.write_text(json.dumps(value))
        with self.assertRaises(ResearchError):checked(path)

    def test_every_old_cli_action_rejects_before_reading_or_writing_workspace(self):
        self.historical();before=inventory(self.root)
        output=self.root/'must-not-be-created.json'
        for action in ('preview','approve','pause','resume','status','list'):
            process=subprocess.run([sys.executable,str(ROOT/'tools/research_batch.py'),
                '--root',str(self.root),'--output',str(output),action,'malformed-or-missing'],
                text=True,capture_output=True,timeout=10)
            self.assertEqual(process.returncode,2)
            self.assertIn('batches have been retired',process.stderr)
            self.assertEqual(process.stdout,'')
        self.assertEqual(inventory(self.root),before)


if __name__=='__main__':unittest.main()
