"""Persistent Feature Store acceptance on isolated, entirely synthetic source data.

The copied production records are transformation definitions/policies and their
specification evidence only. No real dataset observations are calculated here.
"""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from data.alfred_onboarding import Store
from data.feature_store import (FeatureStore, PublicationError, InterruptedPublication,
    publish_feature, retrieve_signal, read_materialization, record_path)
from data.feature_store_contracts import make_pit_operand, make_materialization_id_from_key
from data.pit_feature_adapter import adapt_pit_history
from data.pit_selection import select_asof
from data.transformations.identity import canonical_bytes, digest, reference, make_feature_definition
from data.transformations.registry import Registry
from data.transformations.engine import execute_recipe
from test_pit_feature_adapter import fixture as adapter_fixture
from test_transformation_engine import recipe_for

ROOT=Path(__file__).resolve().parents[1]


def _copy_metadata_closure(root, records):
    """Copy only immutable transformation specification dependencies."""
    source=FeatureStore(ROOT);target=FeatureStore(root);seen=set()
    def visit(value):
        if isinstance(value,dict):
            if set(value)=={'id','version','content_sha256'}:
                key=tuple(value[k] for k in ('id','version','content_sha256'))
                if key in seen:return
                seen.add(key);record=source.resolve(value)
                if record['record_type'] not in ('transformation_definition','policy_definition','onboarding_evidence'):
                    raise AssertionError('Fixture must not copy actual data records')
                target.install_record(record);visit(record);return
            if value.get('record_type')=='onboarding_evidence':
                member=value['body']['payload'];data=source.payload({'blob_sha256':member['sha256'],'format':'json','byte_count':member['byte_count']})
                target.io.blob(data,'json','fixture_policy_evidence',member['row_count'])
            for item in value.values():visit(item)
        elif isinstance(value,list):
            for item in value:visit(item)
    for record in records:
        target.install_record(record);visit(record)


def persistence_fixture(root, *, cutoffs=None, source_fixture=None, snapshot_period=None, information_cutoff=None):
    """A complete tiny stored PIT chain, independent of provider runtime paths."""
    shutil.copytree(ROOT/'specs/schemas',root/'specs/schemas')
    approved=Registry(ROOT)
    _copy_metadata_closure(root,[approved.operator('TR_BASE_change_pct'),
        approved.get_policy('POL_TRANSFORM_EXECUTION'),approved.get_policy('POL_TRANSFORM_HISTORY')])
    io=Store(root);store=FeatureStore(root)
    evidence_member=io.blob(canonical_bytes({'fixture':'Synthetic policy evidence; never production approval.'}),'json','fixture_specification',1)
    evidence={'schema_version':'0.1.0','record_type':'onboarding_evidence','version':'1.0.0',
        'body':{'kind':'synthetic_test_policy','payload':{'sha256':evidence_member['blob_sha256'],
            'byte_count':evidence_member['byte_count'],'row_count':1},'media_type':'application/json',
            'description':'Synthetic test-only source and evaluation evidence.'}}
    evidence['id']='EVIDENCE_'+digest(evidence)
    records=[evidence];policies={}
    for role in ('availability','revision','quality','alignment','selection','source_contract','eligibility'):
        policy={'schema_version':'0.2.0','record_type':'policy_definition','id':'POL_FIXTURE_'+role.upper(),
            'version':'1.0.0','display_name':'Synthetic '+role+' policy','body':{'kind':role,
                'specification':reference(evidence),'parameters':[],'approval_state':'approved','compatibility_evidence':[]}}
        if role=='eligibility':
            policy.update(id='POL_TRANSFORM_FIXTURE_EVALUATION',version='2.0.0')
            policy['body'].update(kind='selection',specification=approved.get_policy('POL_TRANSFORM_HISTORY')['body']['specification'])
        records.append(policy);policies[role]=policy
    # A provider contract is upstream evidence, never a numeric execution switch.
    provider={'schema_version':'0.1.0','record_type':'provider_contract','id':'PROVIDER_SYNTHETIC','version':'1.0.0',
        'body':{'provider':'FRED_ALFRED','native_series_id':'SYNTHETIC_SERIES',
            'official_endpoints':[{'role':'series_metadata','url':'https://api.stlouisfed.org/fred/series'}],
            'official_documentation':['https://fred.stlouisfed.org/docs/api/fred/series.html'],
            'units':'Synthetic units','frequency':'Monthly','seasonal_adjustment':'Synthetic',
            'availability_policy':reference(policies['availability']),
            'vintage_limitations':[{'code':'synthetic_only','detail':'Synthetic test evidence only.'}],
            'requested_live_scope':{'capability':'live_api_daily_pull','cadence':'daily','decision_clock_ready':False}}}
    records.append(provider)
    code=io.blob(b'Synthetic fixture implementation bytes.','txt','fixture_code',None)
    environment=io.blob(canonical_bytes({'fixture_runtime':'synthetic'}),'json','fixture_environment',1)
    implementation={'schema_version':'0.2.0','record_type':'implementation_manifest','version':'1.0.0',
        'code_artifacts':[code],'environment_artifacts':[environment],'entrypoint_id':'fixture_change_pct',
        'determinism_policy':reference(approved.get_policy('POL_TRANSFORM_EXECUTION'))}
    implementation['id']='IMPLEMENTATION_'+digest(implementation);records.append(implementation)
    original=source_fixture or adapter_fixture();dataset=original['dataset'];dataset['id']='DS_SYNTHETIC'
    for role in ('availability','revision','quality'):dataset['body'][role+'_policy']=reference(policies[role])
    dataset['body']['source_contract']=reference(provider);records.append(dataset)
    view=original['source_view'];view['id']='SVIEW_SYNTHETIC';view['body']['dataset']=reference(dataset)
    for role in ('alignment','selection'):view['body'][role+'_policy']=reference(policies[role])
    records.append(view)
    source_bindings=[{'role':role,'artifact':reference(policies[role])} for role in ('availability','revision','quality','alignment','selection')]
    lineage={'schema_version':'0.2.0','record_type':'lineage_manifest','version':'1.0.0','inputs':[],
        'operation':reference(evidence),'implementation':reference(implementation),'policy_bindings':source_bindings}
    lineage['id']='LINEAGE_'+digest(lineage);records.append(lineage)
    native=deepcopy(original['rows'])
    raw_rows=[]
    for period in sorted({r['period'] for r in native}):
        row={'date':period}
        row.update({r['raw_field']:r['amount'] for r in native if r['period']==period});raw_rows.append(row)
    raw_member=io.blob(canonical_bytes(raw_rows),'json','synthetic_native_raw',len(raw_rows))
    def snapshot(layer,definition,upstream,rows,member):
        record={'schema_version':'0.2.0','record_type':'snapshot_manifest','version':'1.0.0','layer':layer,
            'definition':definition,'period':snapshot_period or {'start_inclusive':'2020-01-01T00:00:00.000000Z','end_exclusive':'2020-05-01T00:00:00.000000Z'},
            'information_cutoff':information_cutoff or '2020-06-01T00:00:00.000000Z','members':[member],'semantic_content_sha256':digest(rows),
            'record_count':len(rows),'upstream_snapshots':upstream,'policy_bindings':source_bindings,
            'implementation':reference(implementation),'lineage':[reference(lineage)]}
        record['id']='SNAPSHOT_'+digest({k:v for k,v in record.items() if k!='members'})
        records.append(record);return record
    raw=snapshot('raw',reference(dataset),[],raw_rows,raw_member)
    for row in native:row.update(raw=reference(raw),view=reference(view),blob=raw_member['blob_sha256'])
    pit_member=io.blob(b''.join(canonical_bytes(row)+b'\n' for row in native),'jsonl','synthetic_pit_observations',len(native))
    pit=snapshot('pit',reference(view),[reference(raw)],native,pit_member)
    for record in records:store.install_record(record)
    adapted=adapt_pit_history(dataset=dataset,source_view=view,pit_snapshot=pit,raw_snapshots=[raw],rows=native,
        mapping=original['mapping'],history_policy=reference(approved.get_policy('POL_TRANSFORM_HISTORY')))
    series=adapted['series'];registry=Registry(root)
    recipe=recipe_for(registry,series,[('TR_BASE_change_pct',{'k':1})],unit='dimensionless')
    recipe['evaluation_policy']=reference(policies['eligibility'])
    feature=make_feature_definition(recipe,'Synthetic stored fractional change')
    result=execute_recipe(series,recipe,cutoffs or ['2020-02-01','2020-03-01','2020-03-15'],
        registry=registry,implementation=reference(implementation))
    links=[]
    for row in result['observations']:
        selected=select_asof(series['observations'],row['evaluation_cutoff'],reference_cutoff=row['evaluation_cutoff'])
        links.append(dict([('numerator',selected[-1]['lineage'])] if len(selected)==1 else
            [('numerator',selected[-1]['lineage']),('denominator',selected[-2]['lineage'])]))
    bindings=[*source_bindings,{'role':'history','artifact':recipe['history_policy']},
        {'role':'execution','artifact':recipe['execution_policy']},{'role':'evaluation','artifact':recipe['evaluation_policy']}]
    metadata={'dataset':reference(dataset),'source_view':reference(view),'selection':series['selection'],'unit':'dimensionless',
        'value_semantics':'fractional_change','cadence':series['cadence'],'history_policy':series['history_policy'],
        'source_policy_bindings':source_bindings,'history_mode':'resolved_state','temporal_precision':'date','availability_semantics':'derived_at_cutoff'}
    return {'feature':feature,'input_series':series,'result':result,'metadata':metadata,'operand_links':links,
        'operand_records':adapted['operand_records'],'supporting_records':records,'implementation':implementation,'policy_bindings':bindings}


class FeatureStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.arguments=persistence_fixture(self.root)

    def publish(self,**changes):return publish_feature(self.root,**dict(self.arguments,**changes))

    def complete_paths(self):
        return sorted((self.root/'storage/catalog/feature_store').glob('*/manifest.json'))

    def library_paths(self):
        return sorted((self.root/'storage/catalog/signal_library/entries').glob('*/*.json'))

    def assert_unpublished(self):
        self.assertEqual(self.complete_paths(),[]);self.assertEqual(self.library_paths(),[])

    def test_fresh_signal_retrieval_is_unresearched_and_independently_checkable(self):
        publication=self.publish();fresh=retrieve_signal(self.root,publication['signal_id'])
        self.assertEqual(fresh['materialization_state'],'materialized');self.assertEqual(fresh['scientific_state'],'untested')
        self.assertEqual(fresh['library_entries'][0]['relationship_results'],[])
        rows=fresh['observations'];self.assertIsNone(rows[0]['value']);self.assertEqual(rows[0]['reason_code'],'INSUFFICIENT_HISTORY')
        for row,expected in zip(rows[1:],[Decimal('110')/Decimal('100')-1,Decimal('110')/Decimal('105')-1]):
            self.assertLess(abs(Decimal(row['value'])-expected),Decimal('1e-15'))
            self.assertEqual(row['available_at'],row['evaluation_cutoff'])
        self.assertEqual(fresh['manifest']['status_counts'],{'valid':2,'missing':0,'invalid':1})
        self.assertEqual(len(fresh['operands']),3)
        self.assertEqual(fresh['metadata']['dataset']['id'],'DS_SYNTHETIC')
        for entry in fresh['library_entries']:
            for field in ('metrics','scientific_status','target','research_spec'):self.assertNotIn(field,entry)

    def test_identical_rerun_reuses_definition_manifest_rows_and_projection(self):
        first=self.publish()
        before={p.relative_to(self.root):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        second=self.publish()
        after={p.relative_to(self.root):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        self.assertFalse(first['reused']);self.assertTrue(second['reused']);self.assertEqual(first['materialization'],second['materialization'])
        self.assertEqual(before,after);self.assertEqual(len(self.complete_paths()),1);self.assertEqual(len(self.library_paths()),1)

    def test_policy_binding_order_does_not_change_publication_identity(self):
        first=self.publish();second=self.publish(policy_bindings=list(reversed(self.arguments['policy_bindings'])))
        self.assertTrue(second['reused']);self.assertEqual(first['materialization'],second['materialization'])

    def test_missing_and_corrupt_observation_payloads_fail_closed(self):
        published=self.publish();loaded=read_materialization(self.root,published['materialization']['id'])
        part=loaded['manifest']['partitions'][0]
        path=self.root/f"storage/payloads/sha256/{part['blob_sha256'][:2]}/{part['blob_sha256']}.jsonl"
        original=path.read_bytes();path.unlink()
        with self.assertRaises((ValueError,OSError)):retrieve_signal(self.root,published['signal_id'])
        path.write_bytes(original+b' ')
        with self.assertRaises((ValueError,OSError)):retrieve_signal(self.root,published['signal_id'])

    def test_missing_or_corrupt_pit_operand_evidence_fails_closed(self):
        published=self.publish();body=self.arguments['operand_records'][0]['body']
        snapshot=FeatureStore(self.root).resolve(body['pit_snapshot']);part=snapshot['members'][0]
        path=self.root/f"storage/payloads/sha256/{part['blob_sha256'][:2]}/{part['blob_sha256']}.jsonl"
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises((ValueError,OSError)):retrieve_signal(self.root,published['signal_id'])

    def test_interruption_at_dependencies_recovers_without_partial_signal(self):
        self._interrupted('dependencies',False)

    def test_interruption_at_payloads_recovers_without_partial_signal(self):
        self._interrupted('payloads',False)

    def test_interruption_at_manifest_recovers_projection_from_verified_manifest(self):
        self._interrupted('manifest',True)

    def _interrupted(self,stage,complete):
        with self.assertRaises(InterruptedPublication):self.publish(interrupt_after=stage)
        self.assertEqual(len(self.complete_paths()),int(complete));self.assertEqual(self.library_paths(),[])
        with self.assertRaises(PublicationError):retrieve_signal(self.root,self.arguments['feature']['body']['signal_id'])
        result=self.publish();self.assertEqual(result['reused'],complete)
        self.assertEqual(len(retrieve_signal(self.root,result['signal_id'])['observations']),3)
        self.assertEqual(len(self.complete_paths()),1);self.assertEqual(len(self.library_paths()),1)

    def test_all_null_output_cannot_publish_complete_feature_or_signal(self):
        series=self.arguments['input_series'];recipe=self.arguments['feature']['body']['recipe']
        result=execute_recipe(series,recipe,['2020-02-01'],registry=Registry(self.root),implementation=reference(self.arguments['implementation']))
        with self.assertRaises(ValueError):self.publish(result=result,operand_links=self.arguments['operand_links'][:1])
        self.assert_unpublished()

    def test_unavailable_operand_cannot_be_committed(self):
        links=deepcopy(self.arguments['operand_links'])
        revised=next(record for record in self.arguments['operand_records'] if record['body']['key']['available_at']=='2020-03-15')
        links[1]['denominator']=reference(revised)
        with self.assertRaises(ValueError):self.publish(operand_links=links)
        self.assert_unpublished()

    def test_stale_revision_cannot_be_committed_as_latest_cutoff_operand(self):
        links=deepcopy(self.arguments['operand_links']);links[2]['denominator']=links[1]['denominator']
        with self.assertRaises(ValueError):self.publish(operand_links=links)
        self.assert_unpublished()

    def test_wrong_numerator_reference_or_denominator_period_cannot_commit(self):
        for role in ('numerator','denominator'):
            links=deepcopy(self.arguments['operand_links']);links[1][role]=links[1]['denominator' if role=='numerator' else 'numerator']
            with self.subTest(role=role),self.assertRaises(ValueError):self.publish(operand_links=links)
            self.assert_unpublished()

    def test_tampered_locator_context_cannot_override_stored_native_row(self):
        records=deepcopy(self.arguments['operand_records']);target=next(i for i,r in enumerate(records) if r['body']['key']['available_at']=='2020-03-01')
        old=reference(records[target]);body=records[target]['body'];body['key']['entity_id']='OTHER_ENTITY'
        records[target]=make_pit_operand(body);links=deepcopy(self.arguments['operand_links'])
        for mapping in links:
            for role,binding in list(mapping.items()):
                if binding==old:mapping[role]=reference(records[target])
        with self.assertRaises(ValueError):self.publish(operand_records=records,operand_links=links)
        self.assert_unpublished()

    def test_raw_row_selector_cannot_disagree_with_exact_pit_selector(self):
        body=deepcopy(self.arguments['operand_records'][0]['body'])
        body['raw_cell']['row_key'][0]['value']='1900-01-01'
        with self.assertRaises(ValueError):make_pit_operand(body)
        self.assert_unpublished()

    def _alternate_snapshot(self):
        old=self.arguments['operand_records'][0]['body']['pit_snapshot']
        alternate=FeatureStore(self.root).resolve(old)
        alternate['information_cutoff']='2020-07-01T00:00:00.000000Z'
        alternate['id']='SNAPSHOT_'+digest({k:v for k,v in alternate.items() if k not in ('id','members')})
        FeatureStore(self.root).install_record(alternate)
        return alternate

    def test_operand_snapshot_must_be_pinned_in_materialization_before_commit(self):
        alternate=self._alternate_snapshot();source=deepcopy(self.arguments['input_series'])
        source['source_snapshots']=[reference(alternate)]
        with self.assertRaisesRegex(PublicationError,'snapshot is not pinned'):self.publish(input_series=source)
        self.assert_unpublished()

    def test_fresh_read_rejects_checksummed_manifest_with_wrong_source_snapshot(self):
        published=self.publish();loaded=read_materialization(self.root,published['materialization']['id'])
        manifest=deepcopy(loaded['manifest']);alternate=self._alternate_snapshot()
        manifest['input_key']['source_snapshots']=[reference(alternate)]
        manifest['id']=make_materialization_id_from_key(manifest['input_key'])
        rows=[dict(row,materialization_id=manifest['id']) for row in loaded['observations']]
        member=Store(self.root).blob(b''.join(canonical_bytes(row)+b'\n' for row in rows),'jsonl','feature_observations',len(rows))
        manifest['partitions'][0].update(member)
        FeatureStore(self.root).install_record(manifest)
        with self.assertRaisesRegex(PublicationError,'snapshot is not pinned'):read_materialization(self.root,manifest['id'])
        self.assertEqual(len(retrieve_signal(self.root,published['signal_id'])['observations']),3)

    def test_signal_projection_requires_exact_feature_reference_not_just_feature_id(self):
        published=self.publish();path=self.library_paths()[0]
        entry=json.loads(path.read_text());path.unlink()
        entry['feature']['content_sha256']='0'*64
        entry['id']='LIBRARYENTRY_'+digest({k:v for k,v in entry.items() if k!='id'})
        FeatureStore(self.root).install_record(entry)
        with self.assertRaisesRegex(PublicationError,'reference mismatch'):retrieve_signal(self.root,published['signal_id'])


if __name__=='__main__':unittest.main()
