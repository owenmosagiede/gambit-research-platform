"""Approved policy installation/readiness tests; no production submission or data reads."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from research.contracts import canonical, load_profile, profile_blockers, readiness, ref, ResearchError
from runtime.research_jobs import ResearchJobs

ROOT=Path(__file__).resolve().parents[1]

class InstalledResearchPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.policy=load_profile(ROOT)
        self.definition=self.root/'definitions/research_specs'/self.policy['id']/(self.policy['version']+'.json')
        self.definition.parent.mkdir(parents=True)
        self.definition.write_bytes(canonical(self.policy)+b'\n')
        (self.root/'config').mkdir()
        (self.root/'config/research_execution.json').write_bytes(canonical({'research_spec':ref(self.policy)})+b'\n')
    def tearDown(self):self.temp.cleanup()
    def test_approved_periods_and_certification_are_exact(self):
        p=load_profile(self.root)
        self.assertEqual(p['version'],'2.0.0')
        self.assertEqual(p['periods'],{'P1':{'start_inclusive':None,'end_exclusive':'2022-01-01'},'P2':{'start_inclusive':'2022-01-01','end_exclusive':'2026-09-01'}})
        self.assertEqual(p['discovery_start_rule'],'scope_structural_start_v1')
        self.assertEqual(p['period_labels']['P2'],'Validation period')
        self.assertEqual(p['availability_mode'],'retrospective_date_label')
        self.assertFalse(p['historical_replay_certified']);self.assertFalse(p['live_certified'])
        self.assertFalse(p['exposure_classification']['untouched_holdout_claim'])
        self.assertEqual(p['exposure_classification']['selected_relationship_prior_use'],'not_established')
    def test_complete_exact_registry_pins(self):
        t=self.policy['target_selection']
        self.assertEqual(t['selection_scope'],'registered_fx_registry')
        self.assertEqual(len(t['source_snapshots']),43)
        self.assertEqual(set(t['source_snapshots']),set(t['materializations']))
        for rows in t['materializations'].values():
            self.assertEqual(set(rows),{'1','7','21','63','252'})
            for binding in rows.values():
                self.assertEqual(set(binding),{'id','version','content_sha256'})
                self.assertRegex(binding['content_sha256'],r'^[0-9a-f]{64}$')
    def test_readiness_and_worker_start_do_not_create_scientific_work(self):
        snapshot={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        adapter=Mock()
        with self.subTest('readiness'):
            value=readiness(self.root)
            self.assertTrue(value['execution_enabled']);self.assertEqual(value['blockers'],[])
            self.assertEqual(value['research_spec'],ref(self.policy))
        jobs=ResearchJobs(self.root,adapter=adapter,start_worker=True)
        jobs.close()
        self.assertEqual(adapter.mock_calls,[])
        self.assertFalse((self.root/'storage').exists())
        self.assertEqual(snapshot,{str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
    def test_modified_immutable_definition_cannot_enable_submit(self):
        value=deepcopy(self.policy);value['periods']['P2']['end_exclusive']='2027-01-01'
        self.definition.write_bytes(canonical(value)+b'\n')
        with self.assertRaisesRegex(ResearchError,'identity/content'):readiness(self.root)
    def test_noncanonical_definition_cannot_enable_submit(self):
        self.definition.write_text(json.dumps(self.policy,indent=2))
        with self.assertRaisesRegex(ResearchError,'Noncanonical'):readiness(self.root)
    def test_crossed_kernel_and_evidence_versions_block(self):
        for key,value in [('missing_evidence','legacy_failed_v1'),('horizon_unit','subsequent_valid_observations'),('spacing',True)]:
            with self.subTest(key=key):
                p=deepcopy(self.policy);p['kernel'][key]=value
                self.assertIn('KERNEL_COMPATIBILITY_UNRESOLVED',[x['code'] for x in profile_blockers(p)])
    def test_auto_start_only_available_with_new_versioned_policy(self):
        p=deepcopy(self.policy);p['kernel'].update(kernel_policy='retained_legacy_v1',missing_evidence='legacy_failed_v1')
        self.assertIn('RESEARCH_PERIODS_UNRESOLVED',[x['code'] for x in profile_blockers(p)])
    def test_malformed_kernel_blocks_readiness_without_attribute_error(self):
        p=deepcopy(self.policy);p['kernel']=None
        self.assertIn('KERNEL_COMPATIBILITY_UNRESOLVED',[x['code'] for x in profile_blockers(p)])
    def test_old_flat_profile_remains_readable(self):
        from test_research_runtime import profile
        old=profile()
        (self.root/'config/research_execution.json').write_bytes(canonical(old)+b'\n')
        self.assertEqual(load_profile(self.root),old)
        self.assertFalse(profile_blockers(old))
        self.assertNotEqual(ref(old),ref(self.policy))

if __name__=='__main__':unittest.main()
