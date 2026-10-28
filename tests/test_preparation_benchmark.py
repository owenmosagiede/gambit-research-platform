"""Fresh multi-member proof must reject changes beyond proven producer references."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from test_fresh_feature_benchmark import evidence

spec=importlib.util.spec_from_file_location('prep_benchmark',Path(__file__).resolve().parents[1]/'tools/benchmark_preparation.py')
bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)


def report(code):
    value=evidence(code)
    value['phases']={str(i):phase for i,phase in enumerate(value['phases'].values())}
    prepared={'plan_id':'frozen','phase':'P1','members':[{'instrument_id':'fixture',
        'materializations':sorted([bench.proof.reference(p['verified']['manifest']) for p in value['phases'].values()],key=lambda r:r['id'])}]}
    prepared['prepared_id']='PREPARED_'+bench.proof.digest(prepared)
    value.update(prepared=prepared,loaded=[{'lineage':{'prepared_id':prepared['prepared_id']},'target':'unchanged',
        'feature_materialization':p['verified']['manifest']['id'],
        'feature_lineage':bench.proof.reference(p['lineages'][0])} for p in value['phases'].values()],
        decisions=[{'admission':'rejected','artifacts':{'aligned_sample':[
            {'lineage':{'feature_lineage':bench.proof.reference(p['lineages'][0]),
                        'feature_materialization':p['verified']['manifest']['id']}}
            for p in value['phases'].values()]}}],dimensions={'fixture':True},cache_high_water_bytes=1024,
        performance={},source_admission_boundary='isolated synthetic')
    return value


class PreparationProofTests(unittest.TestCase):
    def test_full_source_gate_requires_repeated_preparation_improvement_not_moved_work(self):
        spec=importlib.util.spec_from_file_location('full_prep',bench.ROOT/'tools/benchmark_source_preparation.py')
        full=importlib.util.module_from_spec(spec);spec.loader.exec_module(full)
        row={'exact_scientific_equality':True,'source_verification_mocked':False,'baseline':{'wall_seconds':120},'candidate':{'wall_seconds':80},
             'baseline_preparation':{'timings':{'feature.preparation':{'wall_seconds':100},'source_prices.verify':{'calls':36}}},
             'candidate_preparation':{'timings':{'feature.preparation':{'wall_seconds':70},'source_prices.verify':{'calls':18}}}}
        self.assertTrue(full.performance_gate([row,row])['passed'])
        self.assertFalse(full.performance_gate([row])['passed'])
        for field in ('preparation','replays','total','science','mocked'):
            changed=deepcopy(row)
            if field=='preparation':changed['candidate_preparation']['timings']['feature.preparation']['wall_seconds']=101
            if field=='replays':changed['candidate_preparation']['timings']['source_prices.verify']['calls']=36
            if field=='total':changed['candidate']['wall_seconds']=130
            if field=='science':changed['exact_scientific_equality']=False
            if field=='mocked':changed['source_verification_mocked']=True
            with self.subTest(field=field):self.assertFalse(full.performance_gate([row,changed])['passed'])

    def test_child_rejects_external_existing_store_paths(self):
        with self.assertRaisesRegex(ValueError,'isolated temporary'):
            bench.isolated_child(Path('/srv/gambit/research_platform'),Path('/srv/gambit/research_platform'))

    def test_child_accepts_seeded_policy_files_but_no_added_storage(self):
        import json
        with TemporaryDirectory(prefix='gambit-fresh-preparation-') as folder:
            root=Path(folder);source=root/'baseline'
            manifest=bench.ROOT/'tests/fixtures/registry_support/manifest.json'
            dest=source/'tests/fixtures/registry_support/manifest.json';dest.parent.mkdir(parents=True)
            dest.write_bytes(manifest.read_bytes())
            for row in json.loads(manifest.read_text())['files']:
                target=source/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((manifest.parent/row['path']).read_bytes())
            bench.isolated_child(source,root/'run/store')
            (source/'storage/extra').write_text('unexpected')
            with self.assertRaisesRegex(ValueError,'beyond approved policy'):
                bench.isolated_child(source,root/'run/store')

    def test_derived_prepared_and_alignment_references_are_mapped_only_after_full_proof(self):
        self.assertTrue(bench.compare(report('old'),report('new'))['exact_scientific_equality'])

    def test_changed_science_unknown_identity_and_excess_memory_fail(self):
        for case in ('target','prepared','decision','memory','dimensions','missing_publication'):
            before,after=report('old'),report('new')
            if case=='target':after['loaded'][0]['target']='changed'
            elif case=='prepared':after['loaded'][0]['lineage']['prepared_id']='unknown'
            elif case=='decision':after['decisions'][0]['admission']='admitted'
            elif case=='memory':after['cache_high_water_bytes']=128*1024*1024+1
            elif case=='dimensions':after['dimensions']['fixture']=False
            else:after['phases'].pop('1')
            with self.subTest(case=case),self.assertRaises(ValueError):bench.compare(before,after)


if __name__=='__main__':unittest.main()
