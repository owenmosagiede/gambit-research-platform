"""Website snapshots never wait for intake or repair scientific authority."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid

from api.application import ApplicationRoutes
from api.catalog_cache import CatalogCache
from api.experiment_views import ExperimentView, _metadata_cache, get_experiment, list_experiments
from research.contracts import canonical, digest
from research.store import install_bytes, lock
from runtime.experiment_identity import IdentityIndex, save
from runtime.research_jobs import ResearchJobs
from test_research_runtime import Adapter, KernelSpy, intent, profile


class ExperimentViewsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'config').mkdir()
        (self.root / 'config/research_execution.json').write_text(json.dumps(profile()))
        self.jobs = ResearchJobs(self.root, adapter=Adapter(), kernels=KernelSpy())
        self.addCleanup(self.jobs.close)

    def submit(self, direction='POSITIVE'):
        request = intent(mode='TS'); request['expected_direction'] = direction
        self.jobs.submit(request)
        return request['request_id']

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def read(self, path):
        route = ApplicationRoutes(self.root, self.jobs, CatalogCache(), 'GET', path)
        route.read()
        return route.response[0], json.loads(route.response[1])

    def test_queue_and_detail_return_while_another_writer_holds_lock(self):
        first, second = self.submit(), self.submit('NEGATIVE')
        self.jobs._update(first, status='p1', stage='P1 research')
        before = self.files()
        with patch.object(self.jobs, 'get', side_effect=AssertionError('repairing command path')), \
             patch.object(self.jobs, '_received', side_effect=AssertionError('receipt recovery')), \
             patch.object(self.jobs, '_event_snapshot', wraps=self.jobs._event_snapshot) as snapshots:
            # Real OS flock held across the requests, not a mocked lock.
            with ThreadPoolExecutor(max_workers=2) as pool:
                with lock(self.root, 'research-writer'):
                    listing = pool.submit(self.read, '/api/experiments').result(timeout=2)
                    detail = pool.submit(self.read, '/api/experiments/' + first).result(timeout=2)
            self.assertEqual(snapshots.call_count, 2)  # once per request, not per job
        self.assertEqual(listing[0], 200); self.assertEqual(detail[0], 200)
        self.assertEqual([row['job']['request_id'] for row in listing[1]['items']], [first, second])
        self.assertEqual([row['queue_position'] for row in listing[1]['items']], [None, 1])
        self.assertEqual(detail[1]['job']['status'], 'p1')
        self.assertEqual(before, self.files())

    def test_missing_projection_and_receipt_are_not_repaired(self):
        rid = self.submit(); index = IdentityIndex(self.jobs)
        self.jobs._job_path(rid).unlink()
        (index.base / 'receipts' / (rid + '.json')).unlink()
        before = self.files(); value = get_experiment(self.jobs, rid)
        self.assertEqual(value['status'], 'queued')
        self.assertTrue(value['submission_receipt_pending'])
        self.assertNotIn('submission_receipt', value)
        self.assertEqual(before, self.files())

    def test_journal_only_reservation_is_visible_without_publication(self):
        request = intent(mode='TS')
        with patch.object(self.jobs, '_ensure_recorded', side_effect=OSError('interrupted publication')):
            with self.assertRaises(OSError): self.jobs.submit(request)
        before = self.files(); value = list_experiments(self.jobs)
        self.assertEqual(value['items'], [])
        self.assertEqual(value['issues'][0]['request_id'], request['request_id'])
        self.assertEqual(before, self.files())

    def test_partial_corruption_is_reported_without_hiding_other_records(self):
        bad, good = self.submit(), self.submit('NEGATIVE')
        self.jobs._submission_path(bad).write_text('broken')
        before = self.files(); value = list_experiments(self.jobs)
        self.assertEqual([row['job']['request_id'] for row in value['items']], [good])
        self.assertEqual(value['issues'][0]['request_id'], bad)
        self.assertEqual(before, self.files())

    def test_event_tampering_is_not_a_completed_trial(self):
        rid = self.submit()
        path = next((self.root / 'storage/catalog/attempts').glob('*/events/*.json'))
        event = json.loads(path.read_bytes()); event['job']['status'] = 'succeeded'
        path.write_text(json.dumps(event)); before = self.files()
        value = list_experiments(self.jobs)
        self.assertEqual(value['items'], []); self.assertEqual(value['issues'][0]['request_id'], rid)
        self.assertEqual(before, self.files())

    def test_existing_integrity_incident_survives_a_broken_submission(self):
        rid = self.submit(); path = self.jobs._submission_path(rid)
        path.write_text('broken')
        incident = self.jobs._incident(path, ValueError('bad envelope'))
        before = self.files(); value = list_experiments(self.jobs)
        self.assertEqual(value['issues'], [])
        self.assertEqual(value['items'][0]['job']['incident'], incident)
        self.assertTrue(value['items'][0]['job']['operational_failure'])
        self.assertIsNone(value['items'][0]['intent'])
        self.assertEqual(before, self.files())

    def test_new_event_appears_next_refresh_and_finished_trials_remain_visible(self):
        rid = self.submit()
        self.assertEqual(list_experiments(self.jobs)['items'][0]['job']['status'], 'queued')
        self.jobs.run_pending_once()
        value = list_experiments(self.jobs)['items'][0]['job']
        self.assertEqual(value['status'], 'succeeded'); self.assertEqual(len(value['horizons']), 5)
        self.assertEqual(len(value['results']), 5)

    def test_alias_reads_canonical_job_without_duplicate_trial(self):
        rid = self.submit()
        original = self.jobs._submission(rid)
        alias = str(uuid.uuid4())
        self.jobs.submit(dict(original['intent'], request_id=alias))
        before = self.files(); value = get_experiment(self.jobs, alias)
        self.assertEqual(value['request_id'], rid)
        self.assertEqual(value['submission_receipt']['request_id'], alias)
        self.assertEqual(len(list_experiments(self.jobs)['items']), 1)
        self.assertEqual(before, self.files())

    def test_bad_receipt_or_journal_is_not_silently_repaired(self):
        rid = self.submit(); index = IdentityIndex(self.jobs)
        path = index.base / 'receipts' / (rid + '.json')
        record = json.loads(path.read_bytes()); record['canonical_request_id'] = str(uuid.uuid4())
        save(path, record, mutable=True); before = self.files()
        value = list_experiments(self.jobs)
        self.assertEqual(value['items'], []); self.assertTrue(value['issues'])
        self.assertEqual(before, self.files())

    def test_mismatched_alias_is_an_issue_not_an_extra_trial(self):
        rid = self.submit(); original = self.jobs._submission(rid); alias = str(uuid.uuid4())
        self.jobs.submit(dict(original['intent'], request_id=alias))
        index = IdentityIndex(self.jobs); record = index.journal(alias)
        record['intent']['expected_direction'] = 'NEGATIVE'
        save(index.journal_path(alias), record, mutable=True)
        before = self.files(); value = list_experiments(self.jobs)
        self.assertEqual([item['job']['request_id'] for item in value['items']], [rid])
        self.assertEqual(value['issues'][0]['request_id'], alias)
        self.assertEqual(before, self.files())

    def test_verified_compact_metadata_is_reused_but_events_remain_fresh(self):
        rid = self.submit(); journal_reader = IdentityIndex.journal
        with patch.object(self.jobs, '_submission', wraps=self.jobs._submission) as envelopes, \
             patch.object(IdentityIndex, 'journal', autospec=True,
                          side_effect=journal_reader) as journals, \
             patch.object(self.jobs, '_event_snapshot', wraps=self.jobs._event_snapshot) as events:
            first = self.read('/api/experiments')
            second = self.read('/api/experiments')
            self.assertEqual(first[0], 200); self.assertEqual(second[0], 200)
            self.assertEqual(envelopes.call_count, 1)
            self.assertEqual(journals.call_count, 1)
            self.assertEqual(events.call_count, 2)
        view = ExperimentView(self.jobs); view.get(rid)
        self.assertNotIn('members', view.originals[rid]['frozen_plan'])
        self.assertNotIn('implementation', view.originals[rid])
        self.assertEqual(set(view.journals[rid]['submission']), {'record_sha256'})
        self.assertEqual(view.cache.limit, 1024)
        self.assertEqual(_metadata_cache.cache_info().maxsize, 4)
        self.jobs._update(rid, status='p1', stage='P1 research')
        self.assertEqual(get_experiment(self.jobs, rid)['status'], 'p1')

    def test_cached_envelope_tamper_with_restored_mtime_is_not_accepted(self):
        rid = self.submit(); self.assertEqual(len(list_experiments(self.jobs)['items']), 1)
        path = self.jobs._submission_path(rid); old = path.stat()
        record = json.loads(path.read_bytes())
        record['created_at'] = '2000-01-01T00:00:00.000000+00:00'
        record['record_sha256'] = digest({key: value for key, value in record.items() if key != 'record_sha256'})
        replacement = canonical(record) + b'\n'
        self.assertEqual(len(replacement), old.st_size)
        path.write_bytes(replacement); os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
        before = self.files(); value = list_experiments(self.jobs)
        self.assertEqual(value['items'], []); self.assertTrue(value['issues'])
        self.assertEqual(before, self.files())

    def test_atomic_metadata_replacement_revalidates_and_bad_journal_is_rejected(self):
        rid = self.submit(); index = IdentityIndex(self.jobs)
        self.assertEqual(len(list_experiments(self.jobs)['items']), 1)
        path = self.jobs._submission_path(rid)
        install_bytes(path, path.read_bytes(), mutable=True)
        with patch.object(self.jobs, '_submission', wraps=self.jobs._submission) as reader:
            self.assertEqual(len(list_experiments(self.jobs)['items']), 1)
            self.assertEqual(reader.call_count, 1)
        journal = index.journal(rid); journal['scientific_identity'] = '0' * 64
        save(index.journal_path(rid), journal, mutable=True)
        before = self.files(); value = list_experiments(self.jobs)
        self.assertEqual(value['items'], []); self.assertTrue(value['issues'])
        self.assertEqual(before, self.files())

    def test_absent_journal_is_not_cached_across_publication(self):
        rid = self.submit(); index = IdentityIndex(self.jobs)
        path = index.journal_path(rid); journal_bytes = path.read_bytes(); path.unlink()
        first = get_experiment(self.jobs, rid)
        self.assertNotIn('submission_receipt', first)
        install_bytes(path, journal_bytes)
        second = get_experiment(self.jobs, rid)
        self.assertEqual(second['submission_receipt']['request_id'], rid)

    def test_retargeted_submission_directory_does_not_reuse_old_verification(self):
        rid = self.submit(); directory = self.jobs._submission_path(rid).parent
        first = directory.with_name('submissions_first'); directory.rename(first)
        directory.symlink_to(first.name, target_is_directory=True)
        self.assertEqual(len(list_experiments(self.jobs)['items']), 1)
        second = directory.with_name('submissions_second'); second.mkdir()
        (second / (rid + '.json')).write_text('broken')
        directory.unlink(); directory.symlink_to(second.name, target_is_directory=True)
        value = list_experiments(self.jobs)
        self.assertEqual(value['items'], []); self.assertTrue(value['issues'])

    def test_legacy_envelope_without_frozen_plan_remains_visible(self):
        rid = self.submit(); index = IdentityIndex(self.jobs)
        index.journal_path(rid).unlink()
        original = self.jobs._submission(rid); original.pop('frozen_plan')
        original['record_sha256'] = digest({key: value for key, value in original.items() if key != 'record_sha256'})
        install_bytes(self.jobs._submission_path(rid), canonical(original) + b'\n', mutable=True)
        status, value = self.read('/api/experiments')
        self.assertEqual(status, 200); self.assertEqual(len(value['items']), 1)
        self.assertEqual(value['items'][0]['presentation']['state'], 'unavailable')


if __name__ == '__main__': unittest.main()
