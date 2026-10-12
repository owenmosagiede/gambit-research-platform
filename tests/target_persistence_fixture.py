"""Synthetic market evidence admitted through the production Target store/service.

Never invoked against the production root. All observations are marked fixtures.
"""
from copy import deepcopy
from pathlib import Path
import shutil

from data.targets.store import TargetStore
from data.targets.contracts import create_policy
from data.targets.service import create_target
from data.transformations.identity import canonical_bytes, digest, reference
from target_fixtures import fixture, rebind

PROJECT=Path(__file__).resolve().parents[1]


def evidence(store, value, kind='synthetic_test_policy'):
    member=store.io.blob(canonical_bytes(value),'json',kind,1)
    record={'schema_version':'0.1.0','record_type':'onboarding_evidence','version':'1.0.0',
        'body':{'kind':kind,'payload':{'sha256':member['blob_sha256'],'byte_count':member['byte_count'],'row_count':1},
                'media_type':'application/json','description':'Isolated synthetic acceptance evidence; not a production source certificate.'}}
    record['id']='EVIDENCE_'+digest(record)
    store.install_record(record)
    return record


def lineage(store, inputs, operation):
    record={'schema_version':'0.2.0','record_type':'lineage_manifest','version':'1.0.0',
            'inputs':inputs,'operation':operation,'implementation':None,'policy_bindings':[]}
    record['id']='LINEAGE_'+digest(record)
    store.install_record(record)
    return record


def snapshot(store, layer, definition, rows, upstream, policy, source_lineage):
    fmt='json' if layer=='raw' else 'jsonl'
    data=canonical_bytes(rows) if fmt=='json' else b''.join(canonical_bytes(row)+b'\n' for row in rows)
    member=store.io.blob(data,fmt,'fixture_'+layer,len(rows))
    record={'schema_version':'0.2.0','record_type':'snapshot_manifest','version':'1.0.0','layer':layer,
        'definition':definition,'period':{'start_inclusive':'2024-01-01T00:00:00.000000Z','end_exclusive':'2025-01-01T00:00:00.000000Z'},
        'information_cutoff':'2025-01-01T00:00:00.000000Z','members':[member],
        'semantic_content_sha256':digest(rows),'record_count':len(rows),'upstream_snapshots':upstream,
        'policy_bindings':[{'role':'availability','artifact':policy}],
        'implementation':None,'lineage':[source_lineage]}
    record['id']='SNAPSHOT_'+digest({k:v for k,v in record.items() if k!='members'})
    store.install_record(record)
    return record


def persist_source_rows(store, source, dataset, view, availability):
    base=lineage(store,[],availability)
    raw_rows=[]
    old_periods=source['periods']
    for row in source['series']['observations']:
        raw={key:value for key,value in row.items() if key!='lineage'}
        if row['lineage']['id'] in old_periods:raw.update(old_periods[row['lineage']['id']])
        raw_rows.append(raw)
    raw=snapshot(store,'raw',reference(dataset),raw_rows,[],availability,reference(base))
    canonical=[];periods={}
    for index,row in enumerate(raw_rows):
        locator=evidence(store,{'raw_snapshot':reference(raw),'row_index':index,'row_sha256':digest(row)},'canonical_record_locator')
        operand=lineage(store,[{'role':'raw','artifact':reference(raw)},{'role':'record_locator','artifact':reference(locator)}],availability)
        canonical.append(dict(row,lineage=reference(operand)))
        if 'interval_start' in row:
            periods[operand['id']]={k:row[k] for k in ('interval_start','interval_end')}
    pit=snapshot(store,'pit',reference(view),canonical,[reference(raw)],availability,reference(base))
    source['series']['observations']=[{k:v for k,v in row.items() if k not in {'interval_start','interval_end'}} for row in canonical]
    source['series']['source_snapshots']=[reference(pit)]
    source['periods']=periods
    return reference(pit)


def persistence_fixture(root, **kwargs):
    root=Path(root)
    shutil.copytree(PROJECT/'specs/schemas',root/'specs/schemas',dirs_exist_ok=True)
    case=fixture(**kwargs);store=TargetStore(root)
    spec=evidence(store,{'synthetic':True,'purpose':'Return Target acceptance only'})
    policies={}
    for kind in ('availability','revision','quality','source_contract','alignment','selection'):
        record={'schema_version':'0.2.0','record_type':'policy_definition','id':'POL_FIXTURE_'+kind.upper(),
            'version':'1.0.0','display_name':'Synthetic '+kind+' policy',
            'body':{'kind':kind,'specification':reference(spec),'parameters':[],
                    'approval_state':'approved','compatibility_evidence':[]}}
        store.install_record(record);policies[kind]=record
    dependencies={};inputs={}
    for role,source in case['sources'].items():
        series=source['series'];selection=series['selection']
        dataset={'schema_version':'0.2.0','record_type':'dataset_definition','id':'DS_'+selection['entity_id'],
            'version':'1.0.0','display_name':'SYNTHETIC '+role+' investment history',
            'body':{'economic_entity_ids':[selection['entity_id']],
                'fields':[{'name':'reference_time','data_type':'token','unit':'date','nullable':False},
                          {'name':'available_at','data_type':'token','unit':'date','nullable':False},
                          {'name':selection['measure'],'data_type':'decimal','unit':series['unit'],'nullable':True}],
                'event_time_field':'reference_time','availability_time_field':'available_at',
                'revision_key_fields':['reference_time','available_at'],
                **{key+'_policy':reference(policies[key]) for key in ('availability','revision','quality')},
                'source_contract':reference(policies['source_contract'])}}
        store.install_record(dataset)
        view={'schema_version':'0.2.0','record_type':'source_view_definition','id':'SVIEW_'+selection['entity_id'],
            'version':'1.0.0','display_name':'SYNTHETIC canonical investment history',
            'body':{'dataset':reference(dataset),'entity_selection':{'kind':'fixed_entities','entity_ids':[selection['entity_id']]},
                    'fields':['reference_time','available_at',selection['measure']],'filters':[],
                    'alignment_policy':reference(policies['alignment']),'selection_policy':reference(policies['selection'])}}
        store.install_record(view)
        series['source_view']=reference(view);series['history_policy']=reference(policies['revision'])
        econ=deepcopy(source['economics']['body'])
        econ.update(source_view=reference(view),history_policy=series['history_policy'],evidence=[reference(spec)])
        source['economics']=create_policy(econ,'SYNTHETIC certified investment source')
        store.install_record(source['economics'])
        inputs[role]=persist_source_rows(store,source,dataset,view,reference(policies['availability']))
        dependencies[role]={'dataset':dataset,'view':view,'availability':reference(policies['availability'])}
    for name in ('outcome_policy','validity_policy','schedule_policy','calculation'):
        store.install_record(case[name])
    rebind(case)
    schedule_evidence=evidence(store,{'kind':'canonical_market_schedule',
        'schedule':{k:v for k,v in case['schedule'].items() if k!='evidence'}},'canonical_market_schedule')
    case['schedule']['evidence']=reference(schedule_evidence)
    definition=create_target(root,case['definition']['body'],'SYNTHETIC stored investment return')
    case['definition']=definition
    request={'definition':reference(definition),'sources':inputs,'schedule':case['schedule'],
             'anchors':case['anchors'],'knowledge_cutoff':case['knowledge_cutoff']}
    return {'request':request,'fixture':case,'dependencies':dependencies}


def refresh_fixture(root, setup):
    """Persist deliberately amended fixture observations without changing source semantics."""
    setup=deepcopy(setup);store=TargetStore(root)
    for role,source in setup['fixture']['sources'].items():
        dep=setup['dependencies'][role]
        setup['request']['sources'][role]=persist_source_rows(store,source,dep['dataset'],dep['view'],dep['availability'])
    return setup
