"""Exact maintenance-release reuse, with immutable completed research preserved."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid

from research.contracts import digest, ResearchConflict
from runtime.experiment_identity import release_relation, release_reviews
from runtime.research_jobs import ResearchJobs, implementation
from test_research_runtime import Adapter, KernelSpy, intent, profile

ROOT = Path(__file__).resolve().parents[1]


def reviewed_pair():
    evidence = json.loads((ROOT / 'tests/fixtures/batch_retirement_review.json').read_text())
    current = implementation()
    current['numeric_environment'] = {'python': evidence['python']}
    previous = deepcopy(current)
    for name in evidence['added_files']:
        previous['files'].pop(name)
    previous['files'].update(evidence['before_changed_files'])
    previous['fingerprint'] = digest(previous['files'])
    return evidence, previous, current


class BatchRetirementReleaseTests(unittest.TestCase):
    def setUp(self):
        self.evidence, self.old, self.new = reviewed_pair()
        temp = TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'config').mkdir()
        (self.root / 'config/research_execution.json').write_text(json.dumps(profile()))
        self.spy = KernelSpy()
        self.jobs = ResearchJobs(self.root, adapter=Adapter(), kernels=self.spy)
        self.addCleanup(self.jobs.close)

    def test_review_binds_exact_source_and_recorded_cloud_python(self):
        self.assertEqual(self.old['fingerprint'], self.evidence['before_fingerprint'])
        self.assertEqual(self.new['fingerprint'], self.evidence['after_fingerprint'])
        self.assertEqual(digest(self.old), self.evidence['before_implementation_key'])
        self.assertEqual(digest(self.new), self.evidence['after_implementation_key'])
        review = [r for r in release_reviews() if r['from'] == digest(self.old) and r['to'] == digest(self.new)]
        self.assertEqual(len(review), 1)
        self.assertEqual(review[0]['decision'], 'equivalent')
        self.assertEqual(review[0]['evidence'], 'docs/batch-retirement-release.md')
        self.assertEqual(release_relation(self.old, self.new), 'equivalent')

    def test_review_does_not_change_numerical_modules_or_data_contracts(self):
        changed = {name for name in self.old['files'] if self.old['files'][name] != self.new['files'].get(name)}
        self.assertEqual(changed, {'runtime/research_jobs.py', 'runtime/research_batches.py',
                                   'data/fx_batch_reconciliation.py', 'data/fx_operational_retirement.py'})
        self.assertEqual(set(self.new['files']) - set(self.old['files']), {'data/legacy_batch_evidence.py'})
        self.assertFalse(set(self.old['files']) - set(self.new['files']))

    def test_existing_completed_research_is_linked_without_new_execution_or_history_edit(self):
        request = intent(direction='NEGATIVE')
        with patch('runtime.research_jobs.implementation', return_value=self.old):
            first, _ = self.jobs.submit(request)
            self.jobs.run_pending_once()
        result = self.jobs.get(first['request_id'])
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(len(result['results']), 5)
        original = self.jobs._submission_path(first['request_id']).read_bytes()
        calls = list(self.spy.calls)
        with patch('runtime.research_jobs.implementation', return_value=self.new):
            linked, created = self.jobs.submit(dict(request, request_id=str(uuid.uuid4())))
            self.jobs.run_pending_once()
        self.assertFalse(created)
        self.assertEqual(linked['request_id'], first['request_id'])
        self.assertEqual(linked['intake_action'], 'view_results')
        self.assertEqual(linked['results'], result['results'])
        self.assertEqual(self.spy.calls, calls)
        self.assertEqual(self.jobs._submission_path(first['request_id']).read_bytes(), original)
        self.assertEqual(len(self.jobs.list_jobs()['items']), 1)

    def test_exact_review_never_authorizes_resuming_old_execution(self):
        request = intent()
        with patch('runtime.research_jobs.implementation', return_value=self.old):
            first, _ = self.jobs.submit(request)
            self.jobs.cancel(first['request_id'])
        with patch('runtime.research_jobs.implementation', return_value=self.new):
            self.assertFalse(self.jobs.get(first['request_id'])['resumable'])
            with self.assertRaises(ResearchConflict):
                self.jobs.resume(first['request_id'])
        self.assertFalse(self.spy.calls)
        self.assertEqual(self.jobs._submission(first['request_id'])['implementation'], self.old)

    def test_other_code_environment_or_reverse_pair_remains_unreviewed(self):
        for part in ('files', 'numeric_environment'):
            changed = deepcopy(self.new)
            if part == 'files':
                changed['files']['research/unreviewed_change.py'] = 'a' * 64
                changed['fingerprint'] = digest(changed['files'])
            else:
                changed['numeric_environment']['python'] += ' different build'
            self.assertEqual(release_relation(self.old, changed), 'unreviewed')
        self.assertEqual(release_relation(self.new, self.old), 'unreviewed')
