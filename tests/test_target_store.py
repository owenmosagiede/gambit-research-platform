"""Persistence, refresh, historical leakage and independent-process acceptance."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from data.targets.contracts import create_definition
from data.targets.service import (create_target,preflight_request,materialize,retrieve_target,
                                 list_targets,list_materializations,get_definition)
from data.targets.store import TargetStore,InterruptedTargetPublication,TargetNotFound
from data.transformations.identity import canonical_bytes,reference,digest
from target_persistence_fixture import persistence_fixture,refresh_fixture,PROJECT


def inventory(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class TargetStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='return_target_test_')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.setup=persistence_fixture(self.root)
        self.request=self.setup['request']

    def run_target(self):
        return materialize(self.root,self.request)

    def get(self,result,**kwargs):
        return retrieve_target(self.root,result['target_id'],result['materialization']['id'],**kwargs)

    def test_preflight_is_read_only_and_materialization_not_signal(self):
        before=inventory(self.root)
        self.assertEqual(preflight_request(self.root,self.request)['state'],'valid')
        self.assertEqual(before,inventory(self.root))
        self.assertEqual(list_targets(self.root)['targets'][0]['readiness'],'unmaterialized')
        self.run_target()
        self.assertFalse((self.root/'storage/catalog/signal_library').exists())

    def test_persisted_independent_decimal_reference_and_exact_lineage(self):
        saved=self.run_target();result=self.get(saved)
        row=result['observations'][0]
        self.assertEqual(Decimal(row['value']),Decimal(121)/Decimal(100)-1)
        self.assertEqual(row['entry_time'],'2024-01-02')
        self.assertEqual(row['exit_time'],'2024-01-04')
        self.assertEqual(row['label_available_at'],'2024-01-04')
        locators=result['operand_lineage'][0]['operands']
        self.assertEqual(len(locators),2)
        self.assertEqual({v['operand_role'] for v in locators},{'entry','exit'})
        for value in locators:
            self.assertEqual(value['snapshot'],self.request['sources']['instrument'])
            self.assertRegex(value['row_sha256'],r'^[0-9a-f]{64}$')
        self.assertEqual(result['source_metadata']['instrument']['dataset']['id'],'DS_FIXTURE_INSTRUMENT')

    def test_identical_request_reuses_every_immutable_artifact(self):
        first=self.run_target();before=inventory(self.root)
        second=self.run_target();after=inventory(self.root)
        self.assertFalse(first['reused']);self.assertTrue(second['reused'])
        self.assertEqual(first['materialization'],second['materialization'])
        self.assertEqual(before,after)

    def test_fresh_process_explicit_retrieval(self):
        result=self.run_target()
        command=[sys.executable,str(PROJECT/'tools/targets.py'),'--root',str(self.root),'get',
                 '--target-id',result['target_id'],'--materialization-id',result['materialization']['id']]
        proc=subprocess.run(command,capture_output=True,text=True,check=True,
                            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        fresh=json.loads(proc.stdout)
        self.assertEqual(fresh['observations'],self.get(result)['observations'])

    def test_historical_cutoff_blocks_future_and_ambiguous_same_date(self):
        result=self.run_target()
        for cutoff in ['2024-01-03','2024-01-04']:
            self.assertEqual(self.get(result,training_cutoff=cutoff,cutoff_precision='date')['observations'],[])
        self.assertEqual(len(self.get(result,training_cutoff='2024-01-05',cutoff_precision='date')['observations']),1)
        self.assertEqual(self.get(result,training_cutoff='2024-01-05T12:00:00.000000Z',cutoff_precision='utc_timestamp')['observations'],[])

    def test_explicit_materialization_and_matching_target_required(self):
        result=self.run_target()
        with self.assertRaises(ValueError):retrieve_target(self.root,result['target_id'],None)
        with self.assertRaises(ValueError):retrieve_target(self.root,'TARGET_'+'a'*64,result['materialization']['id'])
        with self.assertRaises(ValueError):self.get(result,training_cutoff='2024-01-10')

    def test_preserve_old_materialization_when_later_correction_arrives(self):
        # Same scientific Target uses pinned-later outcomes at explicit request cutoffs.
        self.temp2=tempfile.TemporaryDirectory();self.addCleanup(self.temp2.cleanup)
        self.root=Path(self.temp2.name)
        self.setup=persistence_fixture(self.root,selection='pinned_later')
        self.request=self.setup['request'];self.request['knowledge_cutoff']='2024-01-05'
        before=self.run_target();old=self.get(before)
        source=self.setup['fixture']['sources']['instrument']
        correction=deepcopy(source['series']['observations'][2])
        correction.update(value='125',available_at='2024-01-08',vintage_id='CORRECTION_1')
        # Fixture seeder generates actual fresh record lineage for the changed history.
        source['series']['observations'].append(correction)
        updated=refresh_fixture(self.root,self.setup)
        updated['request']['knowledge_cutoff']='2024-01-09'
        after=materialize(self.root,updated['request'])
        self.assertEqual(before['target_id'],after['target_id'])
        self.assertNotEqual(before['materialization'],after['materialization'])
        self.assertEqual(self.get(before)['observations'],old['observations'])
        new=self.get(after)
        self.assertEqual(new['observations'][0]['value'],'0.25')
        self.assertEqual(new['observations'][0]['label_available_at'],'2024-01-08')
        self.assertEqual(self.get(after,training_cutoff='2024-01-07',cutoff_precision='date')['observations'],[])
        self.assertEqual(len(self.get(before,training_cutoff='2024-01-07',cutoff_precision='date')['observations']),1)
        self.assertEqual(len(self.get(after,training_cutoff='2024-01-09',cutoff_precision='date')['observations']),1)

    def test_matured_outcome_new_materialization_same_target(self):
        early=deepcopy(self.request);early['knowledge_cutoff']='2024-01-03'
        first=materialize(self.root,early)
        self.assertEqual(self.get(first)['observations'][0]['reason_code'],'FUTURE_ENDPOINT')
        mature=self.run_target()
        self.assertEqual(first['target_id'],mature['target_id'])
        self.assertNotEqual(first['materialization'],mature['materialization'])
        self.assertEqual(self.get(mature)['observations'][0]['value'],'0.21')

    def test_unrelated_future_values_do_not_change_completed_label(self):
        first=self.run_target();row=self.get(first)['observations'][0]
        self.setup['fixture']['sources']['instrument']['series']['observations'][-1]['value']='999999'
        updated=refresh_fixture(self.root,self.setup)
        second=materialize(self.root,updated['request'])
        changed=self.get(second)['observations'][0]
        for name in ('value','entry_time','exit_time','label_available_at','status'):
            self.assertEqual(row[name],changed[name])

    def test_return_semantics_change_identity_display_does_not(self):
        original=get_definition(self.root,self.request['definition']['id'])
        renamed=create_target(self.root,original['body'],'Different incidental display name')
        self.assertEqual(reference(original),reference(renamed))
        body=deepcopy(original['body']);body['horizon']['amount']=1
        new=create_target(self.root,body)
        self.assertNotEqual(original['id'],new['id'])
        for field in ('feature','signal','research_spec','expected_direction'):
            bad=deepcopy(body);bad[field]='OUT_OF_SCOPE'
            with self.assertRaises(ValueError):create_definition(bad)

    def test_interrupted_publication_never_appears_ready_and_can_resume(self):
        for stage in ('dependencies','payloads'):
            with self.subTest(stage=stage):
                with self.assertRaises(InterruptedTargetPublication):materialize(self.root,self.request,fail_at=stage)
                self.assertEqual(list_materializations(self.root,self.request['definition']['id']),[])
                self.assertEqual(list_targets(self.root)['targets'][0]['readiness'],'unmaterialized')
        self.assertEqual(self.get(self.run_target())['observations'][0]['value'],'0.21')

    def test_missing_and_corrupt_payload_fail_closed(self):
        result=self.run_target();loaded=self.get(result)
        member=loaded['manifest']['observations']
        path=self.root/f"storage/payloads/sha256/{member['blob_sha256'][:2]}/{member['blob_sha256']}.jsonl"
        original=path.read_bytes();path.unlink()
        with self.assertRaises((ValueError,OSError)):self.get(result)
        path.write_bytes(original+b' ')
        with self.assertRaises((ValueError,OSError)):self.get(result)
        self.assertEqual(list_targets(self.root)['target_count'],0)

    def test_input_payload_integrity_is_verified_on_retrieval(self):
        result=self.run_target();loaded=self.get(result)
        source=loaded['source_metadata']['instrument']['snapshot'];member=source['members'][0]
        path=self.root/f"storage/payloads/sha256/{member['blob_sha256'][:2]}/{member['blob_sha256']}.jsonl"
        path.write_bytes(b'{}\n')
        with self.assertRaises((ValueError,OSError)):self.get(result)

    def test_shared_source_payload_is_not_copied_by_target_publication(self):
        source=TargetStore(self.root).resolve(self.request['sources']['instrument'])
        member=source['members'][0];before=inventory(self.root)
        self.run_target();after=inventory(self.root)
        matching=[path for path,value in after.items() if value==member['blob_sha256']]
        self.assertEqual(len(matching),1)
        for path,value in before.items():self.assertEqual(after[path],value)


class PersistedReturnCapabilityTests(unittest.TestCase):
    def test_every_construction_uses_the_same_persistence_and_read_path(self):
        cases=[('price','price','simple'),('price','price','log'),
               ('total_return','wealth_index','simple'),('total_return','wealth_index','log'),
               ('total_return','period_returns','simple'),('total_return','period_returns','log'),
               ('benchmark_excess','price','simple'),('benchmark_excess','price','log'),
               ('benchmark_excess','wealth_index','simple'),('benchmark_excess','wealth_index','log'),
               ('benchmark_excess','period_returns','simple'),('benchmark_excess','period_returns','log')]
        for basis,kind,representation in cases:
            with self.subTest(basis=basis,kind=kind,representation=representation),tempfile.TemporaryDirectory() as tmp:
                kwargs={'basis':basis,'kind':kind,'representation':representation}
                if kind=='period_returns':kwargs.update(values=['0.1']*6,benchmark_values=['0.02']*6)
                else:kwargs.update(benchmark_values=['100','102','104.04','106','108','110'])
                setup=persistence_fixture(Path(tmp),**kwargs)
                saved=materialize(tmp,setup['request'])
                row=retrieve_target(tmp,saved['target_id'],saved['materialization']['id'])['observations'][0]
                self.assertEqual(row['status'],'valid')
                self.assertTrue(row['historical_eligibility_certified'])

    def test_unknown_availability_persists_but_never_becomes_research_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            setup=persistence_fixture(Path(tmp),selection='pinned_later',availability_basis='unknown')
            saved=materialize(tmp,setup['request'])
            self.assertEqual(saved['research_readiness'],'uncertified')
            result=retrieve_target(tmp,saved['target_id'],saved['materialization']['id'],training_cutoff='2024-12-31',cutoff_precision='date')
            self.assertEqual(result['observations'],[])
