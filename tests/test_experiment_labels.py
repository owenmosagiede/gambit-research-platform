"""Saved display captions must follow frozen metadata, never active dropdowns."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from api.experiment_labels import with_experiment_labels
from test_research_http import submission


class ExperimentLabelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.intent = {k: v for k, v in submission().items() if k != 'request_id'}
        self.recipe_ref = dict(self.intent['feature'], content_sha256='a' * 64)
        self.scope_ref = dict(self.intent['scope'], content_sha256='b' * 64)
        self.membership = {'id': 'MEMBERSHIP_SAVED', 'version': '1.0.0', 'content_sha256': 'c' * 64}
        self.original = {'intent': self.intent, 'frozen_plan': {
            'recipe': self.recipe_ref, 'scope': {'reference': self.scope_ref, 'kind': 'instrument',
                'members': ['AUDUSD'], 'membership_snapshot': self.membership}, 'mode': 'TS'}}
        self.jobs = Mock(); self.jobs._submission.return_value = self.original
        self.value = {'items': [{'job': {'request_id': submission()['request_id']}, 'intent': self.intent}],
                      'issues': [], 'worker': {'healthy': True}}

    def render(self):
        with patch('api.experiment_labels.FeatureStore') as cls, \
             patch('api.experiment_labels.recipe_label', return_value='63-day log momentum'), \
             patch('api.experiment_labels.scope_label', return_value='Saved AUDUSD'):
            cls.return_value.resolve.side_effect = [{'body': {}}, {'body': {}}]
            result = with_experiment_labels(self.root, self.jobs, self.value)
            return result, cls.return_value.resolve.call_args_list

    def test_reads_exact_frozen_references_without_writes_or_execution(self):
        before = deepcopy(self.value)
        result, calls = self.render(); p = result['items'][0]['presentation']
        self.assertEqual([c.args[0] for c in calls], [self.recipe_ref, self.scope_ref])
        self.assertEqual(p['title'], '63-day log momentum · Saved AUDUSD')
        self.assertEqual(p['membership_snapshot'], self.membership)
        self.assertEqual(p['member_count'], 1)
        self.assertEqual(self.value, before)
        self.assertEqual(list(self.root.rglob('*')), [])
        self.jobs.submit.assert_not_called(); self.jobs.get.assert_not_called()

    def test_currency_scope_captions_use_frozen_membership(self):
        self.original['frozen_plan']['mode'] = 'CS'
        self.original['frozen_plan']['scope'].update(kind='universe', reference_currency='USD', members=['EUR_VS_USD','GBP_VS_USD'])
        p = self.render()[0]['items'][0]['presentation']
        self.assertEqual(p['subtitle'], 'Cross-sectional · 2 currencies · Positive hypothesis')

    def test_unavailable_or_mismatched_labels_do_not_hide_saved_jobs(self):
        for key in ('frozen_plan', 'intent'):
            original = deepcopy(self.original); original.pop(key)
            self.jobs._submission.return_value = original
            result, _ = self.render()
            self.assertEqual(result['items'][0]['presentation']['state'], 'unavailable')
            self.assertEqual(result['items'][0]['job'], self.value['items'][0]['job'])
        self.jobs._submission.return_value = deepcopy(self.original)
        self.jobs._submission.return_value['frozen_plan']['recipe']['content_sha256'] = 'd' * 64
        with patch('api.experiment_labels.FeatureStore') as cls:
            cls.return_value.resolve.side_effect = ValueError('Definition checksum mismatch')
            result = with_experiment_labels(self.root, self.jobs, self.value)
        self.assertEqual(result['items'][0]['presentation']['state'], 'unavailable')

    def test_frozen_selection_mismatch_is_not_presented_as_verified(self):
        self.original['frozen_plan']['recipe']['version'] = '2.0.0'
        result, calls = self.render()
        self.assertEqual(result['items'][0]['presentation']['state'], 'unavailable')
        self.assertEqual(calls, [])

    def test_operational_integrity_failure_never_reads_untrusted_selection(self):
        self.value['items'][0]['job']['operational_failure'] = True
        result, calls = self.render()
        self.assertEqual(result['items'][0]['presentation']['state'], 'unavailable')
        self.jobs._submission.assert_not_called(); self.assertEqual(calls, [])
