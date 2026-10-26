"""A provenance translation must not hide any changed scientific evidence."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('fresh_benchmark',Path(__file__).resolve().parents[1]/'tools/benchmark_fresh_features.py')
proof=importlib.util.module_from_spec(spec);spec.loader.exec_module(proof)


def evidence(code, *, value='0.12', status='valid', prefix=4, environment='fixed', code_path='src/data/verified_inputs.py'):
    raw=code.encode();member={'role':code_path.replace('/','_'),'format':'txt',
        'blob_sha256':proof.sha256(raw).hexdigest(),'byte_count':len(raw),'row_count':None}
    impl=proof.identified({'record_type':'implementation_manifest','version':'1.0.0',
        'code_artifacts':[member],'environment_artifacts':[environment],'entrypoint_id':'prepare_fx_feature'},'IMPLEMENTATION_')
    result={'schema':'fresh_feature_evidence_v1','fixture':{'recipe':'fixed','source':'fixed','phases':'fixed'},
            'lineage_storage_mode':'packed_v1','phases':{}}
    files={'data/verified_inputs.py':member['blob_sha256']}
    result['source_implementation']={'files':files,'fingerprint':proof.digest(files)}
    prior=[]
    for phase,day in [('P1','2020-01-02'),('P2','2021-01-04')]:
        lineage=proof.identified({'record_type':'fx_feature_lineage_record','version':'1.0.0',
            'body':{'implementation':proof.reference(impl),'prefix_count':prefix,'reference_time':day,
                    'scheduled_input':{'id':'unchanged-source','version':'1.0.0','content_sha256':'a'*64}}},'LINEAGE_')
        key={'implementation':proof.reference(impl),'period':{'phase':phase},'source':'fixed'}
        mid='MATERIALIZATION_'+proof.digest({'identity_profile':'fixed','input_key':key})
        row={'materialization_id':mid,'reference_time':day,'lineage':proof.reference(lineage),
             'value':value if status=='valid' else None,'status':status,
             'reason_code':None if status=='valid' else 'MISSING_PERIOD','available_at':None}
        data=proof.canonical(row)+b'\n'
        manifest={'record_type':'materialization_manifest','version':'1.0.0','id':mid,
            'identity_profile':'fixed','input_key':key,'lineage':[proof.reference(lineage)],
            'semantic_content_sha256':proof.digest([row]),'partitions':[{'role':'fx_feature_observations',
                'format':'jsonl','blob_sha256':proof.sha256(data).hexdigest(),'byte_count':len(data),'row_count':1}]}
        prior.append(proof.reference(manifest))
        entry=proof.identified({'record_type':'signal_library_entry','version':'1.0.0',
            'feature_materializations':sorted(deepcopy(prior),key=lambda r:r['id']),'feature':'fixed'},'LIBRARYENTRY_')
        result['phases'][phase]={'implementation':deepcopy(impl),'code_sources':{member['role']:{
            'path':code_path,'sha256':member['blob_sha256'],'bytes':len(raw)}},
            'verified':{'manifest':manifest,'observations':[row],'feature':{'recipe':'fixed'},
                        'operands':{'scheduled_source':'fixed'},'metadata':{'unit':'fixed'}},
            'lineages':[lineage],'entry':entry,'publication':{'reused':False,
                'materialization':proof.reference(manifest),'entry':proof.reference(entry)}}
    return result


class FreshFeatureProofTests(unittest.TestCase):
    def test_consistent_code_leaf_forgery_cannot_override_actual_source_fingerprint(self):
        before=evidence('old');after=evidence('changed producer bytes')
        after['source_implementation']=deepcopy(before['source_implementation'])
        with self.assertRaisesRegex(ValueError,'actual source implementation'):
            proof.compare_reports(before,after)
        after=evidence('new');after['source_implementation']['fingerprint']='0'*64
        with self.assertRaisesRegex(ValueError,'fingerprint differs'):proof.compare_reports(before,after)
        before=evidence('old schema',code_path='specs/schemas/platform.schema.json')
        after=evidence('new schema',code_path='specs/schemas/platform.schema.json')
        with self.assertRaisesRegex(ValueError,'outside the implementation fingerprint'):
            proof.compare_reports(before,after)

    def test_only_proven_code_leaves_and_derived_references_are_mapped(self):
        before,after=evidence('old'),evidence('changed producer bytes')
        result=proof.compare_reports(before,after)
        self.assertTrue(result['exact_scientific_equality'])
        self.assertEqual([p['mapped_lineages'] for p in result['phases']],[1,1])
        self.assertEqual(result['phases'][0]['changed_producer_code_paths'],['src/data/verified_inputs.py'])

    def test_internally_consistent_value_status_lineage_or_environment_changes_fail(self):
        before=evidence('old')
        for kw in ({'value':'0.13'},{'status':'missing'},{'prefix':5},{'environment':'different'}):
            with self.subTest(change=kw),self.assertRaises(ValueError):
                proof.compare_reports(before,evidence('new',**kw))

    def test_source_metadata_unknown_ids_or_unfresh_publication_cannot_be_hidden(self):
        before=evidence('old')
        for kind in ('fixture','operand','metadata','unknown_lineage','unfresh','code_proof'):
            after=evidence('new');phase=after['phases']['P1']
            if kind=='fixture':after['fixture']['source']='different'
            elif kind=='operand':phase['verified']['operands']['scheduled_source']='different'
            elif kind=='metadata':phase['verified']['metadata']['unit']='different'
            elif kind=='unknown_lineage':phase['verified']['observations'][0]['lineage']['id']='unknown'
            elif kind=='unfresh':phase['publication']['reused']=True
            else:phase['code_sources']['src_data_verified_inputs.py']['sha256']='0'*64
            with self.subTest(change=kind),self.assertRaises(ValueError):proof.compare_reports(before,after)


if __name__=='__main__':unittest.main()
