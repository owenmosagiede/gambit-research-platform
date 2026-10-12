"""Offline source resolution and rejection tests; mutations use isolated copies."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from data.stored_pit_source import load_source, SourceResolutionError

ROOT=Path(__file__).resolve().parents[1]

class StoredPITSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request=json.loads((ROOT/'config/first_signal_trial.json').read_text())
        cls.workspace=tempfile.TemporaryDirectory(prefix='stored_pit_source_',dir='/private/tmp')
        cls.addClassCleanup(cls.workspace.cleanup)
        cls.fixture=Path(cls.workspace.name)/'fixture';cls.fixture.mkdir()
        cls.completion_path='storage/catalog/pit_store/full_history/completions/'+cls.request['source']['pit_snapshot']['id']+'.json'
        complete=json.loads((ROOT/cls.completion_path).read_text())
        run=json.loads((ROOT/complete['run_path']).read_text())
        cls.pit_payload=next(p for p in run['payload_paths'] if p.endswith('.jsonl'))
        paths=run['record_paths']+run['payload_paths']+[complete['run_path'],cls.completion_path]
        paths += ['specs/schemas/'+name for name in ['platform.schema.json','onboarding.schema.json','alfred_pit_rows.schema.json']]
        for relative in paths:
            destination=cls.fixture/relative;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/relative,destination)
    def setUp(self):
        self.case=tempfile.TemporaryDirectory(prefix='stored_pit_source_case_',dir='/private/tmp')
        self.addCleanup(self.case.cleanup)
        self.root=Path(self.case.name)/'root';shutil.copytree(self.fixture,self.root)
        self.request=deepcopy(type(self).request)
    def test_actual_registered_metadata_mapping_and_no_writes_or_downloads(self):
        inventory=lambda:{str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        before=inventory()
        with patch('urllib.request.urlopen',side_effect=AssertionError('Network forbidden')):
            source=load_source(self.root,self.request)
        self.assertEqual(before,inventory())
        self.assertEqual(source['dataset']['id'],self.request['source']['dataset']['id'])
        self.assertEqual(source['source_view']['id'],self.request['source']['source_view']['id'])
        self.assertEqual(source['provider']['body']['native_series_id'],self.request['source']['native_series_id'])
        self.assertEqual(source['mapping']['constant_fields'],[{'field':'series_id','value':self.request['source']['native_series_id']}])
        self.assertEqual(source['mapping']['fields']['available_at'],'vintage_date')
        self.assertEqual(source['mapping']['cadence']['frequency'],'monthly')
        self.assertEqual(source['mapping']['temporal_precision'],'date')
        self.assertEqual(source['source_metadata']['unit'],'USD_per_hour')
        self.assertEqual(source['source_metadata']['seasonal_adjustment'],'Seasonally Adjusted')
        self.assertEqual(len(source['rows']),1587)
        self.assertEqual(sum(r['status']=='missing' for r in source['rows']),36)
        self.assertEqual(len({r['vintage_date'] for r in source['rows']}),187)
        self.assertEqual(source['publication_eligibility'],'not_established')
        self.assertEqual(len(source['metadata_evidence_refs']),2)
        self.assertEqual({p['role'] for p in source['source_policy_bindings']},{'availability','revision','quality','selection','alignment','readiness'})
    def test_unapproved_evaluation_does_not_block_read_only_source_resolution(self):
        self.request['evaluation_policy']=None
        source=load_source(self.root,self.request)
        self.assertEqual(source['publication_eligibility'],'not_established')
        self.assertNotIn('cutoffs',source)
        self.assertNotIn('release_events',source)
    def test_native_id_must_be_resolved_from_actual_registry(self):
        self.request['source']['native_series_id']='NOT_THE_REGISTERED_NATIVE_SERIES'
        with self.assertRaises(SourceResolutionError):load_source(self.root,self.request)
    def test_exact_dataset_view_snapshot_hashes_are_mandatory(self):
        for name in ('dataset','source_view','pit_snapshot'):
            with self.subTest(reference=name):
                request=deepcopy(self.request);request['source'][name]['content_sha256']='0'*64
                with self.assertRaises(SourceResolutionError):load_source(self.root,request)
    def test_entity_dimensions_measure_and_profile_rejections(self):
        requests=[]
        for selection in [{'measure':'value','entity_id':'CA','dimensions':[]},{'measure':'other','entity_id':'US','dimensions':[]},{'measure':'value','entity_id':'US','dimensions':[{'name':'invented','value':'dimension'}]}]:
            request=deepcopy(self.request);request['selection']=selection;requests.append(request)
        request=deepcopy(self.request);request['source']['profile']='unsupported';requests.append(request)
        for request in requests:
            with self.subTest(request=request['selection']):
                with self.assertRaises(SourceResolutionError):load_source(self.root,request)
    def test_missing_completion_and_corrupted_package_locator_reject(self):
        path=self.root/self.completion_path
        marker=json.loads(path.read_text());marker['run_sha256']='0'*64;path.write_text(json.dumps(marker))
        with self.assertRaises(SourceResolutionError):load_source(self.root,self.request)
        path.unlink()
        with self.assertRaises(SourceResolutionError):load_source(self.root,self.request)
    def test_missing_or_corrupt_pit_payload_never_becomes_eligible(self):
        path=self.root/self.pit_payload;original=path.read_bytes();path.write_bytes(original+b'\n')
        with self.assertRaises(SourceResolutionError):load_source(self.root,self.request)
        path.unlink()
        with self.assertRaises(SourceResolutionError):load_source(self.root,self.request)
    def test_provider_registry_tampering_is_detected(self):
        dataset_path=self.root/f"definitions/datasets/{self.request['source']['dataset']['id']}/{self.request['source']['dataset']['version']}.json"
        provider=json.loads(dataset_path.read_text())['body']['source_contract']
        path=self.root/f"definitions/providers/{provider['id']}/{provider['version']}.json"
        record=json.loads(path.read_text());record['body']['seasonal_adjustment']='Not Seasonally Adjusted';path.write_text(json.dumps(record))
        with self.assertRaises(SourceResolutionError):load_source(self.root,self.request)
    def test_no_series_id_or_legacy_paths_are_hardcoded_in_resolver(self):
        text=(ROOT/'src/data/stored_pit_source.py').read_text()
        self.assertNotIn(self.request['source']['native_series_id'],text)
        self.assertNotIn('/Data/',text)
        self.assertNotIn('calculate(',text)

if __name__=='__main__':unittest.main()
