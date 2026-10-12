"""Adapter acceptance uses synthetic registered metadata and native PIT rows.

No provider clients, downloads or production store mutations occur in these tests.
Historical cutoffs below are explicit fixture facts, not a proposed live schedule.
"""
from copy import deepcopy
import unittest

from data.pit_feature_adapter import adapt_pit_history, AdapterError
from data.feature_store_contracts import normalize_pit_operand
from data.pit_selection import select_asof
from data.transformations.contracts import ContractError, normalize_input
from data.transformations.identity import digest, reference
from data.transformations.registry import Registry
from data.transformations.engine import execute_recipe, InputError
from test_transformation_engine import recipe_for


def binding(identifier):
    return {'id':identifier,'version':'1.0.0','content_sha256':'a'*64}


def fixture(*, numeric_type='decimal'):
    registry=Registry()
    dataset={'schema_version':'0.2.0','record_type':'dataset_definition','id':'DATASET_SYNTHETIC',
        'version':'1.0.0','display_name':'Synthetic economic level','body':{
        'economic_entity_ids':['ENTITY_A'],
        'fields':[{'name':'period','data_type':'token','unit':'source_calendar_date','nullable':False},
                  {'name':'known','data_type':'token','unit':'source_calendar_date','nullable':False},
                  {'name':'amount','data_type':numeric_type,'unit':'units','nullable':True}],
        'event_time_field':'period','availability_time_field':'known','revision_key_fields':['period','known'],
        'availability_policy':binding('POL_SOURCE_AVAILABILITY'),'revision_policy':binding('POL_SOURCE_REVISION'),
        'quality_policy':binding('POL_SOURCE_QUALITY'),'source_contract':binding('PROVIDER_SYNTHETIC')}}
    view={'schema_version':'0.2.0','record_type':'source_view_definition','id':'VIEW_SYNTHETIC',
        'version':'1.0.0','display_name':'Synthetic native history','body':{'dataset':reference(dataset),
        'entity_selection':{'kind':'fixed_entities','entity_ids':['ENTITY_A']},'fields':['period','known','amount'],
        'filters':[],'alignment_policy':binding('POL_SOURCE_ALIGNMENT'),'selection_policy':binding('POL_SOURCE_SELECTION')}}
    def snapshot(layer,definition,upstream,rows,count):
        body={'schema_version':'0.2.0','record_type':'snapshot_manifest','version':'1.0.0','layer':layer,
            'definition':definition,'period':{'start_inclusive':'2020-01-01T00:00:00.000000Z','end_exclusive':'2020-05-01T00:00:00.000000Z'},
            'information_cutoff':'2020-06-01T00:00:00.000000Z',
            'members':[{'role':'synthetic_native','blob_sha256':'b'*64 if layer=='raw' else 'c'*64,'format':'json' if layer=='raw' else 'jsonl','byte_count':1,'row_count':count}],
            'semantic_content_sha256':digest(rows),'record_count':count,'upstream_snapshots':upstream,
            'policy_bindings':[{'role':'availability','artifact':dataset['body']['availability_policy']}],
            'implementation':binding('IMPLEMENTATION_SYNTHETIC'),'lineage':[binding('LINEAGE_SYNTHETIC')]}
        return dict(body,id='SNAPSHOT_'+digest({k:v for k,v in body.items() if k!='members'}))
    raw=snapshot('raw',reference(dataset),[],[],4)
    rows=[]
    for period,known,value,next_date in [('2020-01-01','2020-02-01','100','2020-03-15'),
            ('2020-02-01','2020-03-01','110',None),('2020-01-01','2020-03-15','105',None),
            ('2020-03-01','2020-04-01','121',None)]:
        rows.append({'period':period,'known':known,'amount':value,'state':'valid','entity':'ENTITY_A',
            'native_series':'SYNTHETIC_SERIES','view':reference(view),'raw':reference(raw),'blob':'b'*64,
            'raw_field':'VALUE_'+known.replace('-',''),'precision':'date','next_known':next_date})
    pit=snapshot('pit',reference(view),[reference(raw)],rows,len(rows))
    mapping={'measure':'amount','entity_id':'ENTITY_A','dimension_fields':[],
        'constant_fields':[{'field':'native_series','value':'SYNTHETIC_SERIES'}],
        'fields':{'reference_time':'period','available_at':'known','value':'amount','status':'state','entity_id':'entity',
                  'raw_snapshot':'raw','source_view':'view','raw_blob_sha256':'blob','raw_value_field':'raw_field','temporal_precision':'precision'},
        'pit_row_key_fields':['native_series','period','known'],
        'raw_row_key_fields':[{'raw_field':'date','pit_field':'period'}],
        'temporal_precision':'date','value_semantics':'numeric_level',
        'cadence':{'frequency':'monthly','ordering':'reference_time','gap_policy':'explicit_missing','calendar':'gregorian'}}
    return {'dataset':dataset,'source_view':view,'pit_snapshot':pit,'raw_snapshots':[raw],
            'rows':rows,'mapping':mapping,'history_policy':reference(registry.get_policy('POL_TRANSFORM_HISTORY')),
            'provenance':{'provider':'Synthetic Provider A','seasonal_adjustment':'Not Seasonally Adjusted'}}


class PITFeatureAdapterTests(unittest.TestCase):
    def setUp(self):
        self.inputs=fixture()

    def adapted(self,**changes):
        return adapt_pit_history(**dict(self.inputs,**changes))

    def test_canonical_input_preserves_actual_reference_vintage_and_units(self):
        result=self.adapted();series=result['series']
        self.assertEqual(normalize_input(series),series)
        self.assertEqual(series['selection'],{'measure':'amount','entity_id':'ENTITY_A','dimensions':[]})
        self.assertEqual(series['unit'],'units')
        self.assertEqual(series['temporal_precision'],'date')
        self.assertEqual(series['capabilities'],['revision_history'])
        self.assertNotIn('release_events',series)
        self.assertEqual(len(series['observations']),4)
        self.assertEqual(result['facts'],{'reference_start':'2020-01-01','reference_end':'2020-03-01',
            'reference_count':3,'vintage_start':'2020-02-01','vintage_end':'2020-04-01','vintage_count':4,
            'native_row_count':4,'valid_row_count':4,'missing_row_count':0,'invalid_row_count':0,'temporal_precision':'date'})
        self.assertEqual(result['publication_eligibility'],'not_established')
        self.assertEqual(result['available_vintages'],['2020-02-01','2020-03-01','2020-03-15','2020-04-01'])

    def test_exact_compact_operand_locators_bind_raw_cell_and_full_pit_row(self):
        result=self.adapted();records={r['id']:r for r in result['operand_records']}
        native={(r['period'],r['known']):r for r in self.inputs['rows']}
        for row in result['series']['observations']:
            record=records[row['lineage']['id']];body=record['body'];original=native[(row['reference_time'],row['available_at'])]
            self.assertEqual(normalize_pit_operand(record),record)
            self.assertEqual(reference(record),row['lineage'])
            self.assertEqual(body['pit_row_sha256'],digest(original))
            self.assertEqual(body['pit_row_digest_profile'],'canonical_stored_row_v1')
            self.assertEqual(body['raw_cell'],{'blob_sha256':'b'*64,'field':original['raw_field'],
                'row_key':[{'field':'date','value':original['period']}]})
            self.assertEqual(body['raw_row_mapping'],[{'raw_field':'date','pit_field':'period'}])
            self.assertEqual(body['dataset'],reference(self.inputs['dataset']))
            self.assertEqual(body['pit_snapshot'],reference(self.inputs['pit_snapshot']))
            self.assertEqual(body['source_view'],reference(self.inputs['source_view']))
            self.assertEqual(len(body['source_policy_bindings']),5)
            self.assertNotIn('value',body)
            self.assertNotIn('status',body)
            self.assertNotIn('next_known',row)
            self.assertNotIn('evaluation_cutoff',row)

    def test_adapter_does_not_mutate_inputs_and_mapping_order_is_incidental(self):
        before=deepcopy(self.inputs);first=self.adapted()
        shuffled=deepcopy(self.inputs['mapping']);shuffled['pit_row_key_fields'].reverse()
        shuffled['fields']=dict(reversed(list(shuffled['fields'].items())))
        self.assertEqual(self.adapted(mapping=shuffled),first)
        self.assertEqual(self.inputs,before)
        first['series']['observations'][0]['value']='999'
        self.assertEqual(self.inputs,before)

    def test_incidental_provider_labels_do_not_change_arithmetic_or_operand_ids(self):
        a=self.adapted();b=self.adapted(provenance={'provider':'Unrelated Provider B'})
        self.assertEqual(a['operand_records'],b['operand_records'])
        registry=Registry()
        for result in [a,b]:
            series=result['series'];recipe=recipe_for(registry,series,[('TR_BASE_change_pct',{'k':1})],unit='dimensionless')
            calculated=execute_recipe(series,recipe,['2020-03-01'],registry=registry)
            self.assertAlmostEqual(float(calculated['observations'][0]['value']),110/100-1)

    def test_revision_selection_uses_same_cutoff_for_both_operands(self):
        series=self.adapted()['series'];registry=Registry()
        recipe=recipe_for(registry,series,[('TR_BASE_change_pct',{'k':1})],unit='dimensionless')
        result=execute_recipe(series,recipe,['2020-03-01','2020-03-15'],registry=registry)
        self.assertAlmostEqual(float(result['observations'][0]['value']),110/100-1)
        self.assertAlmostEqual(float(result['observations'][1]['value']),110/105-1)
        selected=select_asof(series['observations'],'2020-03-15',reference_cutoff='2020-03-15')
        self.assertEqual([r['value'] for r in selected],['105','110'])

    def test_future_append_and_unavailable_revisions_do_not_change_earlier_values(self):
        source=self.adapted()['series'];registry=Registry()
        earlier=[r for r in self.inputs['rows'] if r['known']<='2020-03-01']
        reduced=self.adapted(rows=earlier)['series']
        for series in [source,reduced]:
            recipe=recipe_for(registry,series,[('TR_BASE_change_pct',{'k':1})],unit='dimensionless')
            result=execute_recipe(series,recipe,['2020-03-01'],registry=registry)
            self.assertAlmostEqual(float(result['observations'][0]['value']),.1)

    def test_missing_values_preserved_without_filling_and_gap_cannot_be_skipped(self):
        rows=deepcopy(self.inputs['rows']);rows[1].update(amount=None,state='missing')
        missing=self.adapted(rows=rows);self.assertEqual(missing['facts']['missing_row_count'],1)
        series=missing['series'];registry=Registry()
        recipe=recipe_for(registry,series,[('TR_BASE_change_pct',{'k':1})],unit='dimensionless')
        result=execute_recipe(series,recipe,['2020-04-01'],registry=registry)
        self.assertIsNone(result['observations'][0]['value'])
        self.assertEqual(result['observations'][0]['reason_code'],'SOURCE_MISSING')
        gap=self.adapted(rows=[r for r in rows if r['period']!='2020-02-01'])['series']
        with self.assertRaises(InputError):execute_recipe(gap,recipe,['2020-04-01'],registry=registry)

    def test_wrong_dataset_view_snapshot_and_raw_membership_rejected(self):
        changes=[]
        bad=deepcopy(self.inputs['source_view']);bad['body']['dataset']=binding('OTHER_DATASET');changes.append({'source_view':bad})
        bad=deepcopy(self.inputs['pit_snapshot']);bad['definition']=binding('OTHER_VIEW');changes.append({'pit_snapshot':bad})
        bad=deepcopy(self.inputs['raw_snapshots']);bad[0]['definition']=binding('OTHER_DATASET');changes.append({'raw_snapshots':bad})
        rows=deepcopy(self.inputs['rows']);rows[0]['blob']='d'*64;changes.append({'rows':rows})
        rows=deepcopy(self.inputs['rows']);rows[0]['raw']=binding('OTHER_RAW');changes.append({'rows':rows})
        rows=deepcopy(self.inputs['rows']);rows[0]['view']=binding('OTHER_VIEW');changes.append({'rows':rows})
        for values in changes:
            with self.subTest(change=next(iter(values))),self.assertRaises((AdapterError,ContractError)):self.adapted(**values)

    def test_mixed_entities_dimensions_and_series_are_rejected(self):
        for field,value in [('entity','ENTITY_B'),('native_series','DIFFERENT_SERIES')]:
            rows=deepcopy(self.inputs['rows']);rows[0][field]=value
            with self.subTest(field=field),self.assertRaises(AdapterError):self.adapted(rows=rows)
        mapping=deepcopy(self.inputs['mapping']);mapping['dimension_fields']=[{'name':'adjustment','field':'adjustment','value':'SA'}]
        rows=deepcopy(self.inputs['rows'])
        for row in rows:row['adjustment']='SA'
        selected=self.adapted(rows=rows,mapping=mapping)
        self.assertEqual(selected['series']['selection']['dimensions'],[{'name':'adjustment','value':'SA'}])
        rows[-1]['adjustment']='NSA'
        with self.assertRaises(AdapterError):self.adapted(rows=rows,mapping=mapping)

    def test_no_precision_invention_or_numeric_status_coercion(self):
        cases=[{'precision':'utc_timestamp'}, {'known':'2020-02-01T00:00:00.000000Z'}, {'amount':100},
               {'amount':'NaN'}, {'amount':'100.0'}, {'state':'missing','amount':'100'}, {'state':'unknown'}]
        for change in cases:
            rows=deepcopy(self.inputs['rows']);rows[0].update(change)
            with self.subTest(change=change),self.assertRaises((AdapterError,ContractError)):self.adapted(rows=rows)

    def test_integer_measure_metadata_does_not_accept_fractional_values(self):
        inputs=fixture(numeric_type='integer');adapt_pit_history(**inputs)
        inputs['rows'][0]['amount']='100.5'
        with self.assertRaisesRegex(AdapterError,'integer dataset measure'):adapt_pit_history(**inputs)

    def test_duplicate_rows_and_incomplete_mapping_reject(self):
        with self.assertRaises(AdapterError):self.adapted(rows=self.inputs['rows']+[self.inputs['rows'][0]])
        with self.assertRaises(AdapterError):self.adapted(rows=[])
        mapping=deepcopy(self.inputs['mapping']);mapping['pit_row_key_fields']=['period']
        with self.assertRaises(AdapterError):self.adapted(mapping=mapping)
        mapping=deepcopy(self.inputs['mapping']);mapping['raw_row_key_fields']=[]
        with self.assertRaises(AdapterError):self.adapted(mapping=mapping)
        mapping=deepcopy(self.inputs['mapping']);mapping['raw_row_key_fields']=[{'raw_field':'date','pit_field':'unbound_field'}]
        with self.assertRaises(AdapterError):self.adapted(mapping=mapping)
        mapping=deepcopy(self.inputs['mapping']);mapping['fields']['value']='lambda row:row.value'
        with self.assertRaises(ContractError):self.adapted(mapping=mapping)


if __name__=='__main__':unittest.main()
