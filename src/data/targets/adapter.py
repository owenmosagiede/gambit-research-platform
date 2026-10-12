"""Read existing canonical PIT snapshots; no downloads or second source store."""
from data.alfred_onboarding import strict_json
from data.transformations.contracts import normalize_input, normalize_selection, object_fields
from data.transformations.identity import digest, reference
from .store import TargetStore, TargetStoreError


def load_sources(root, definition, source_inputs):
    store=TargetStore(root)
    bindings=definition['body']['sources']
    if set(source_inputs)!={item['role'] for item in bindings}:
        raise TargetStoreError('Exactly the declared source roles must be supplied')
    sources, metadata, locators = {}, {}, {}
    for binding in bindings:
        role=binding['role']
        snapshot=store.resolve(source_inputs[role])
        view=store.resolve(binding['source_view'])
        economics=store.resolve(binding['economic_policy'])
        dataset=store.resolve(view['body']['dataset'])
        provider=store.resolve(dataset['body']['source_contract'])
        store.verify_closure([snapshot,view,economics,dataset,provider])
        if snapshot.get('layer')!='pit' or snapshot['definition']!=binding['source_view']:
            raise TargetStoreError('Target source must be the declared PIT SourceView snapshot')
        selection=normalize_selection(binding['selection'])
        fields={field['name']:field for field in dataset['body']['fields']}
        if selection['measure'] not in fields or selection['measure'] not in view['body']['fields']:
            raise TargetStoreError('Selected measure is outside its canonical Dataset/SourceView')
        if selection['entity_id'] not in dataset['body']['economic_entity_ids']:
            raise TargetStoreError('Selected investment entity is outside its Dataset')
        entity_selection=view['body']['entity_selection']
        if entity_selection['kind']!='fixed_entities' or selection['entity_id'] not in entity_selection['entity_ids']:
            raise TargetStoreError('Target adapter requires an exact admitted entity selection')
        if view['body']['filters']:
            raise TargetStoreError('SourceView filters must be resolved upstream into canonical partitions')
        econ=economics['body']
        if fields[selection['measure']]['unit']!=econ['unit']:
            raise TargetStoreError('Economic input unit conflicts with Dataset field')
        all_rows, rows, periods, role_locators=[],[],{},{}
        for member in snapshot['members']:
            if member['format']!='jsonl':
                raise TargetStoreError('Canonical Target adapter requires PIT JSONL observations')
            members=[strict_json(line) for line in store.payload(member).splitlines()]
            if len(members)!=member['row_count']:
                raise TargetStoreError('PIT payload row count mismatch')
            all_rows.extend(members)
            for index,row in enumerate(members):
                if {key:row.get(key) for key in ('measure','entity_id','dimensions')}!=selection:
                    continue
                copied=dict(row)
                if ('interval_start' in copied)!=('interval_end' in copied):
                    raise TargetStoreError('Incomplete canonical component interval')
                if 'interval_start' in copied:
                    periods[row['lineage']['id']]={key:copied.pop(key) for key in ('interval_start','interval_end')}
                lineage_id=row['lineage']['id']
                if lineage_id in role_locators:
                    raise TargetStoreError('Each contributing canonical record requires unique exact lineage')
                store.resolve(row['lineage'])
                role_locators[lineage_id]={'source_role':role,'dataset':reference(dataset),
                    'source_view':reference(view),'snapshot':reference(snapshot),
                    'payload_sha256':member['blob_sha256'],'row_index':index,'row_sha256':digest(row),
                    'lineage':row['lineage'],'selection':selection,'reference_time':row['reference_time'],
                    'available_at':row['available_at'],'vintage_id':row['vintage_id']}
                rows.append(copied)
        if digest(all_rows)!=snapshot['semantic_content_sha256'] or len(all_rows)!=snapshot['record_count']:
            raise TargetStoreError('Canonical source semantic integrity mismatch')
        series={'contract_version':'1.0.0','source_view':reference(view),'source_snapshots':[reference(snapshot)],
            'selection':selection,'unit':econ['unit'],'value_semantics':econ['value_semantics'],
            'cadence':econ['cadence'],'history_policy':econ['history_policy'],
            'capabilities':['revision_history' if econ['vintage_capability']=='complete_history' else 'resolved_state'],
            'temporal_precision':econ['temporal_precision'],
            'provenance':{'provider':provider.get('body',{}).get('provider',provider.get('display_name',provider['id'])),
                          'dataset_name':dataset['display_name']},'observations':rows}
        sources[role]={'series':normalize_input(series),'economics':economics,'periods':periods}
        metadata[role]={'dataset':dataset,'source_view':view,'provider':provider,'snapshot':snapshot,'economic_policy':economics}
        locators[role]=role_locators
    return {'sources':sources,'metadata':metadata,'locators':locators}
