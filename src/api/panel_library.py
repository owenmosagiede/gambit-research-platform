"""Presentation for stored panel projections; listing never decodes histories."""
from data import panel_import as panels
from data.transformations.identity import reference


def item(root, feature, *, metadata_only=False):
    store,snapshot,manifest,view,dataset = panels.resolved(root,feature,verify_database=False)
    if metadata_only:
        rows = [dict(feature['body']['projection']['summary']['latest'],value=None)]
        result = {'feature':feature,'manifest':manifest,'observations':rows,
            'metadata':{'dataset':dataset,'source_view':view}}
    else: result = panels.read(root,feature)
    return dict(result,signal_id=feature['body']['signal_id'],materialization_state='materialized',
        scientific_state='untested',native_panel_metadata_only=metadata_only)


def summary(store, selected, *, research=None):
    feature = selected['feature']; projection = feature['body']['projection']; saved = projection['summary']
    snapshot = store.resolve(feature['body']['snapshot']); manifest = selected['manifest']
    latest = selected['observations'][-1] if selected['observations'] and not selected.get('native_panel_metadata_only',False) else None
    layer = projection['layer']
    return {'signal_id':feature['body']['signal_id'],'name':feature['display_name'],
        'feature':reference(feature),'source':{'dataset':reference(selected['metadata']['dataset']),
            'name':projection['name'],'series_id':projection['entity_id'],
            'provider':'Frozen '+projection['package']+' package','frequency':projection['frequency'],
            'units':projection['unit_label'],'source_view':reference(selected['metadata']['source_view'])},
        'transformations':[{'node':'stored_field','operator':reference(panels.operator_record()),
            'label':'Stored panel field (original formula)','parameters':[]}],
        'materialization_state':'materialized','scientific_state':'results_linked' if research else 'untested',
        'materialization_count':1,'default_materialization_id':manifest['id'],
        'verification_state':'catalog_metadata_only' if selected.get('native_panel_metadata_only') else 'selected_operands_verified',
        'row_count':saved['row_count'],'status_counts':{'valid':saved['valid_count'],
            'missing':saved['row_count']-saved['valid_count'],'invalid':0},
        'coverage':{'cutoff_start':saved['cutoff_start'],'cutoff_end':saved['cutoff_end'],
                    'reference_start':None,'reference_end':None},
        'latest_observation':{k:latest[k] for k in ('evaluation_cutoff','reference_time','value','status','reason_code')} if latest else None,
        'unit':projection['unit_label'],'value_semantics':'original eligible field; missing and held states retained',
        'availability_semantics':'frozen_package_'+layer,
        'readiness_capabilities':{'retrospective_research':{'decision':'blocked' if layer=='capture' else 'provisional',
            'reason':'Capture is context only.' if layer=='capture' else 'Original package timing, masks and frozen ceiling apply.'},
            'historical_replay':{'decision':'unresolved','reason':'Original intraday publication is not certified.'},
            'live_use':{'decision':'blocked','reason':'Frozen package; refresh required.'}},
        'panel_families':projection['panel_ids'],'source_layer':layer,
        'frozen_max_asof':snapshot['body']['frozen_max_asof']}


def detail(store, loaded, identifier, materialization_id=None, research=None):
    selected = loaded[0]; manifest = selected['manifest']; feature = selected['feature']
    if materialization_id and materialization_id != manifest['id']:
        from api.signal_library import SignalNotFound
        raise SignalNotFound('Materialization is not linked to this Signal')
    from api.signal_library import descriptive_statistics, _coverage
    p = feature['body']['projection']; rows = selected['observations']
    return {'schema_version':'1.0.0','signal':summary(store,selected,research=research),
        'selected_materialization_id':manifest['id'],
        'materializations':[{'id':manifest['id'],'reference':reference(manifest),
            'row_count':len(rows),'status_counts':summary(store,selected)['status_counts'],
            'coverage':_coverage(rows),'href':'/api/signal-library/'+identifier}],
        'statistics':descriptive_statistics(rows,p['unit_label']),'recipe':feature['body']['recipe'],
        'source_metadata':dict(selected['metadata'],projection=p),
        'timing':{'precision':'UTC (source precision warnings retained)','history_mode':'emitted_history',
            'availability_semantics':'frozen_package_'+p['layer'],'evaluation_policy':panels.policy_record(),
            'description':'Original stored fields and source timing are preserved. Archive dates are conservative provider-date alignments; retrospective data use assumed lags and current vintages. Capture is context only. No intraday or live certification. Source validity intervals, quality masks, staleness and the frozen ceiling apply.',
            'retrospective_snapshot':p['layer']!='archive','evaluation_label':'Original availability cutoff',
            'coverage_label':'Stored state availability'},
        'provenance':{'feature':reference(feature),'materialization':reference(manifest),
            'source_snapshots':[feature['body']['snapshot']],'policy_bindings':[reference(panels.policy_record())],
            'implementation':reference(panels.operator_record())},
        'observations':rows,'research':research or {'state':'untested','relationship_count':0,'metrics':[],
            'description':'Stored input only. No research test has been run.'},'issues':[]}


def resolution(root, definition, scope):
    from research import inputs, panel_features
    from research.schedule import apply_schedule,load_schedule
    from research.contracts import ref
    store,snapshot,manifest,_,_ = panels.resolved(root,definition,verify_database=False)
    p = definition['body']['projection']; s = p['summary']; profile = None; policy = None
    outputs = [{'reference':reference(manifest),'legacy_feature':reference(definition),
        'signal_id':definition['body']['signal_id'],'row_count':s['row_count'],
        'status_counts':{'valid':s['valid_count'],'missing':s['row_count']-s['valid_count'],'invalid':0},
        'coverage':{'cutoff_start':s['cutoff_start'],'cutoff_end':s['cutoff_end'],
            'reference_start':None,'reference_end':None},'readiness_capabilities':{}}]
    issues=[]
    try:
        profile=apply_schedule(panel_features.load_profile(root),load_schedule(root),price_time_series=True)
        plan=inputs.resolve_plan(root,{'feature':{k:definition[k] for k in ('id','version')},
            'scope':{k:scope[k] for k in ('id','version')},'target_family':'price_return',
            'expected_direction':'DISCOVERY_SIGN_V1'},profile)
        policy=plan['external_source']['alignment_policy']; compatible=True
        reason='Compatible for individual-pair TS under original UTC intervals and frozen-source bounds. No test has been run.'
    except (ValueError,KeyError,TypeError,OSError) as exc:
        compatible=False; reason=str(exc); issues.append({'code':'PANEL_ALIGNMENT_BLOCKED','message':reason})
    readiness={'retrospective_research':{'decision':'provisional' if compatible else 'blocked','reason':reason},
        'historical_replay':{'decision':'unresolved','reason':'Original intraday availability is not certified.'},
        'live_use':{'decision':'blocked','reason':'Frozen package; refresh required.'}}
    return {'schema_version':'1.0.0','recipe':{'reference':reference(definition),'name':definition['display_name'],'kind':'stored_feature'},
        'scope':{k:scope[k] for k in ('id','version','reference','display_name','membership_snapshot')},
        'registration_state':'registered','selection_read_only':True,'member_count':len(scope['members']),
        'members':[{'instrument_id':x,'state':'missing' if compatible else 'blocked','reason':reason,
                    'materializations':[],'readiness':readiness} for x in scope['members']],
        'summary':{'materialized_member_count':0,'missing_member_count':len(scope['members']) if compatible else 0,
                    'blocked_member_count':0 if compatible else len(scope['members'])},
        'source_materializations':outputs,'source_application_note':reason,'issues':issues,
        'submission_compatible':compatible,'alignment_policy':policy,'research_spec':ref(profile) if compatible else None}
