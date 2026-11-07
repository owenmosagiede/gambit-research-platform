"""A follow-up release adapts bindings without replacing either frozen manifest."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deploy'))
from followup_manifest import binding_view
from research.contracts import digest,HORIZONS
from runtime.experiment_identity import scientific_key
from research.inputs import _plan_id
import test_research_inputs as fixtures


class FollowupBindingTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ResearchInputsTests(methodName='runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        plan=self.fixture.plan()
        self.original={'record_sha256':'parent-envelope','intent':plan['intent'],
                       'research_spec':plan['profile'],'frozen_plan':plan,'implementation':{'version':'original'}}
        self.child=deepcopy(self.original)
        self.child['intent']['expected_direction']='NEGATIVE'
        self.child['frozen_plan']['intent']['expected_direction']='NEGATIVE'
        self.child['frozen_plan']['plan_id']=_plan_id(self.child['frozen_plan'])
        self.child['implementation']={'fingerprint':'f'*64,'files':{'exact':'original'}}
        self.parent={'global_pins':{'implementation_digest':'old','implementation_fingerprint':'old'},
                     'entries':[{'request_id':'parent','recipe_reference':plan['recipe'],'intent':plan['intent']}],
                     'recipes':['immutable'],'scopes':['immutable']}
        self.parent_raw=json.dumps(self.parent).encode()
        self.manifest={'classification':'exploratory_post_selection_negative_direction_followup',
                      'parent_manifest_sha256':sha256(self.parent_raw).hexdigest(),
                      'expected_direction':'NEGATIVE','horizons':list(HORIZONS),'preserve_original_results':True,
                      'executor_digest':digest(self.child['implementation']),
                      'entries':[{'request_id':'child','parent_request_id':'parent','parent_record_sha256':'parent-envelope',
                                  'intent':deepcopy(self.child['intent']),'expected_scientific_identity':scientific_key(self.child)}]}
        self.raw=json.dumps(self.manifest).encode();self.state={'status':'succeeded'}
        self.mock=patch('runtime.research_jobs.ResearchJobs');jobs=self.mock.start().return_value
        self.addCleanup(self.mock.stop)
        jobs._submission.side_effect=lambda rid:{'parent':self.original,'child':self.child}[rid]
        jobs._read_job.return_value=self.state

    def view(self):return binding_view(self.fixture.root,self.raw,self.parent_raw)

    def test_exact_child_view_retains_both_manifest_bytes_and_parent_science(self):
        original=(self.raw,self.parent_raw,deepcopy(self.original),deepcopy(self.child))
        view=self.view()
        self.assertEqual(view['entries'][0]['request_id'],'child')
        self.assertEqual(view['entries'][0]['intent']['expected_direction'],'NEGATIVE')
        self.assertEqual(view['recipes'],self.parent['recipes'])
        self.assertEqual(view['global_pins']['implementation_digest'],self.manifest['executor_digest'])
        self.assertEqual(original,(self.raw,self.parent_raw,self.original,self.child))

    def test_parent_bytes_envelope_completion_and_child_pins_are_required(self):
        with self.assertRaisesRegex(RuntimeError,'parent manifest'):binding_view(self.fixture.root,self.raw)
        with self.assertRaisesRegex(RuntimeError,'parent manifest'):binding_view(self.fixture.root,self.raw,self.parent_raw+b' ')
        for field in ('parent_hash','completion','intent','executor','period'):
            old_parent,old_child,old_state=deepcopy(self.original),deepcopy(self.child),deepcopy(self.state)
            if field=='parent_hash':self.original['record_sha256']='changed'
            if field=='completion':self.state['status']='p2'
            if field=='intent':self.child['intent']['expected_direction']='POSITIVE'
            if field=='executor':self.child['implementation']['files']['exact']='changed'
            if field=='period':self.child['frozen_plan']['periods']['P2']['end_exclusive']='2030-01-01'
            with self.subTest(field=field),self.assertRaises(Exception):self.view()
            self.original,self.child=old_parent,old_child;self.state.clear();self.state.update(old_state)

    def test_accepted_child_inventory_is_retained_even_when_newer_than_parent(self):
        self.child['frozen_plan']['members'][0]['feature_materializations'].append({'frozen_child_cache':True})
        self.child['frozen_plan']['plan_id']=_plan_id(self.child['frozen_plan'])
        saved=deepcopy(self.child)
        self.view()
        self.assertEqual(self.child,saved)

    def test_duplicate_or_unknown_parent_and_unapproved_direction_rejected(self):
        for case in ('duplicate','parent','direction','horizons','preservation'):
            changed=deepcopy(self.manifest)
            if case=='duplicate':changed['entries']*=2
            if case=='parent':changed['entries'][0]['parent_request_id']='unknown'
            if case=='direction':changed['expected_direction']='POSITIVE'
            if case=='horizons':changed['horizons']=[1]
            if case=='preservation':changed['preserve_original_results']=False
            with self.subTest(case=case),self.assertRaises(Exception):
                binding_view(self.fixture.root,json.dumps(changed).encode(),self.parent_raw)


if __name__=='__main__':unittest.main()
