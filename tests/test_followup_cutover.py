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
from tempfile import TemporaryDirectory


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


class FollowupCaptureTests(unittest.TestCase):
    def test_real_envelopes_and_history_reach_complete_binding_checks_read_only(self):
        import program_cutover as cutover
        from research.contracts import canonical
        from runtime.research_jobs import ResearchJobs
        from test_program_intake_compatibility import binding_fixture
        parent,row,packet,catalog,targets=binding_fixture()
        class CompleteAdapter:
            def resolve_plan(self,root,intent,profile):
                plan=deepcopy(packet['frozen_plan']);plan['intent']=deepcopy(intent)
                plan['plan_id']=_plan_id(plan);return plan
        with TemporaryDirectory() as folder:
            root=Path(folder);(root/'config').mkdir()
            (root/'config/research_execution.json').write_bytes(canonical(packet['research_spec']))
            jobs=ResearchJobs(root,adapter=CompleteAdapter())
            jobs.submit(dict(row['intent'],request_id=row['request_id']))
            original=jobs._submission(row['request_id'])
            # A synthetic terminal event isolates capture, not the numerical kernel.
            jobs._update(row['request_id'],status='succeeded',stage='complete')
            child_id='00000000-0000-0000-0000-000000000002'
            jobs.submit(dict(row['intent'],expected_direction='NEGATIVE',request_id=child_id))
            child=jobs._submission(child_id)
            parent['global_pins'].update(implementation_digest=digest(original['implementation']),
                                        implementation_fingerprint=original['implementation']['fingerprint'])
            parent_raw=canonical(parent)
            followup={'classification':'exploratory_post_selection_negative_direction_followup',
                'parent_manifest_sha256':sha256(parent_raw).hexdigest(),'expected_direction':'NEGATIVE',
                'horizons':list(HORIZONS),'preserve_original_results':True,'executor_digest':digest(child['implementation']),
                'entries':[{'request_id':child_id,'parent_request_id':row['request_id'],
                    'parent_record_sha256':original['record_sha256'],'intent':child['intent'],
                    'expected_scientific_identity':scientific_key(child)}]}
            raw=canonical(followup);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(cutover,'frozen_metadata',return_value=(catalog,targets)):
                result=cutover.capture(root,raw,parent_manifest_bytes=parent_raw)
                self.assertEqual(result['manifest_sha256'],sha256(raw).hexdigest())
                self.assertEqual(result['cohort'][0]['submission_sha256'],child['record_sha256'])
                self.assertEqual(result['states'][child_id]['status'],'queued')
                self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
                with self.assertRaisesRegex(RuntimeError,'parent manifest'):cutover.capture(root,raw)
                jobs._update(row['request_id'],status='queued')
                with self.assertRaisesRegex(RuntimeError,'parent research'):
                    cutover.capture(root,raw,parent_manifest_bytes=parent_raw)


if __name__=='__main__':unittest.main()
