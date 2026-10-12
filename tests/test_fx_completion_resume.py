"""Exact completed-run reuse over isolated persisted scientific fixtures."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from data.alfred_onboarding import stable_read
from data.targets.fx import materialize
from data.targets.store import TargetStore,materialization_path
from data.transformations.identity import canonical_bytes,digest
from test_fx_targets import fixture,add,approve

PROJECT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('fx_batch_reuse_test',PROJECT/'tools/fx_batch.py')
BATCH=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(BATCH)


class CompletedFXRunReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);shutil.copytree(PROJECT/'specs/schemas',self.root/'specs/schemas')
        self.snapshot,self.policy,_=fixture(self.root);self.store=TargetStore(self.root)
        self.alignment={'id':'TEST_REUSE_ALIGNMENT','version':'1.0.0','mode':'retrospective_date_label',
            'approval_state':'approved','approval_evidence':self.policy['approval_evidence'],
            'max_date_gap':0,'max_valuation_gap_seconds':None}
        self.bundle={'return_policy':self.policy,'alignment_policy':self.alignment,'knowledge_cutoff':'2026-10-09'}
        body={'kind':'fx_instrument_registration','instrument_id':'EURUSD','price_snapshot':self.snapshot}
        registration=add(self.store,'onboarding_evidence',body)
        completion=add(self.store,'onboarding_evidence',{'kind':'fx_universe_completion','alignment_policy':self.alignment,
            'source_snapshots':{},'instruments':[registration]})
        self.construction={'completion':completion,'instruments':[dict(body,registration=registration)]}
        self.outputs=materialize(self.root,self.snapshot,self.policy,knowledge_cutoff=self.bundle['knowledge_cutoff'])
        self.cached={'construction':deepcopy(self.construction),'targets':deepcopy(self.outputs),'blockers':[]}

    def reuse(self,**kwargs):
        return BATCH.reuse_completed_targets(self.root,kwargs.get('construction',self.construction),
            kwargs.get('policy_bundle',self.bundle),kwargs.get('cached_run',self.cached))

    def inventory(self):
        return {str(p.relative_to(self.root)):(p.stat().st_mtime_ns,digest(p.read_bytes().hex()))
            for p in self.root.rglob('*') if p.is_file()}

    def test_verified_repeat_reuses_exact_refs_without_writes_or_recalculation(self):
        before=self.inventory()
        with patch.object(BATCH,'materialize',side_effect=AssertionError('must not recompute')):
            first=self.reuse();second=self.reuse()
        self.assertEqual(first,second)
        self.assertEqual(first,[dict(output,reused=True) for output in self.outputs])
        self.assertEqual(before,self.inventory())

    def test_changed_cutoff_rejected(self):
        bundle=deepcopy(self.bundle);bundle['knowledge_cutoff']='2026-10-10'
        with self.assertRaisesRegex(ValueError,'cutoff'):self.reuse(policy_bundle=bundle)

    def test_changed_approved_return_policy_rejected(self):
        bundle=deepcopy(self.bundle)
        bundle['return_policy']=approve(self.store,dict(self.policy,representation='log'))
        bundle['alignment_policy']['approval_evidence']=bundle['return_policy']['approval_evidence']
        with self.assertRaises(ValueError):self.reuse(policy_bundle=bundle)

    def test_changed_active_price_or_completion_rejected(self):
        construction=deepcopy(self.construction)
        construction['instruments'][0]['price_snapshot']=construction['completion']
        with self.assertRaisesRegex(ValueError,'immutable registration'):self.reuse(construction=construction)
        construction=deepcopy(self.construction);construction['completion']=self.snapshot
        with self.assertRaisesRegex(ValueError,'completion differ'):self.reuse(construction=construction)

    def test_changed_current_implementation_rejected_without_publishing_new_artifacts(self):
        before=self.inventory()
        def changed_read(path,*args,**kwargs):
            data=stable_read(path,*args,**kwargs)
            return data+b'\n# changed scientific implementation\n' if str(path).endswith('/targets/fx.py') else data
        with patch('data.targets.service.stable_read',side_effect=changed_read):
            with self.assertRaisesRegex(ValueError,'implementation differs'):self.reuse()
        self.assertEqual(before,self.inventory())

    def test_missing_materialization_rejected(self):
        path=self.store.path(materialization_path(self.outputs[0]['materialization']['id']))
        path.unlink()
        with self.assertRaises((ValueError,OSError)):self.reuse()

    def test_corrupt_materialization_rejected(self):
        path=self.store.path(materialization_path(self.outputs[0]['materialization']['id']))
        path.write_bytes(b'{"corrupt":true}')
        with self.assertRaises((ValueError,KeyError,OSError)):self.reuse()

    def test_corrupt_target_payload_rejected_even_with_unchanged_manifest(self):
        manifest=self.store.resolve(self.outputs[0]['materialization']);member=manifest['partitions'][0]
        path=self.store.path(f"storage/payloads/sha256/{member['blob_sha256'][:2]}/{member['blob_sha256']}.{member['format']}")
        path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaises(ValueError):self.reuse()

    def test_exact_count_unique_targets_and_materializations_required(self):
        for values in (self.cached['targets'][:1],self.cached['targets']+[self.cached['targets'][0]],
                       [self.cached['targets'][0],self.cached['targets'][0]]):
            cached=deepcopy(self.cached);cached['targets']=deepcopy(values)
            with self.subTest(count=len(values)),self.assertRaises(ValueError):self.reuse(cached_run=cached)

    def test_changed_cached_summary_or_reference_rejected(self):
        cached=deepcopy(self.cached);cached['targets'][0]['row_count']+=1
        with self.assertRaisesRegex(ValueError,'summary differs'):self.reuse(cached_run=cached)
        cached=deepcopy(self.cached);cached['targets'][0]['materialization']['content_sha256']='f'*64
        with self.assertRaises(ValueError):self.reuse(cached_run=cached)

    def test_incomplete_or_blocked_prior_run_rejected(self):
        cached=deepcopy(self.cached);cached['blockers']=['UNRESOLVED']
        with self.assertRaisesRegex(ValueError,'completed prior run'):self.reuse(cached_run=cached)


if __name__=='__main__':unittest.main()
