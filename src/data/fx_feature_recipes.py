"""Additive FX recipe registrations in the existing canonical Feature registry.

A shared configuration is a catalog grouping, not a second predictor identity.
Canonical Feature/Signal identity continues to include its source and selection.
Registration never publishes Signal entries or calculates observations.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
import re

from data.alfred_onboarding import identified, stable_read, strict_json
from data.feature_store import FeatureStore, PublicationError, record_path
from data.fx_records import make_record
from data.fx_pipeline import list_instruments, _universe
from data.targets.fx import _approved_policy, _price_snapshot
from data.transformations.engine import _metadata, _parameters
from data.transformations.registry import Registry
from data.transformations.identity import (canonical_bytes, digest, reference,
    make_feature_definition, normalize_recipe)
from data.transformations.contracts import decimal_text

LOG_FIRST = tuple('TR_BASE_'+name for name in '''change_diff smooth_ew_change trend_ma_distance trend_ema_distance
trend_slope trend_slope_tstat momentum_skip_diff shock_standardized_change shock_change_zscore shock_change_percentile
accel_second_diff accel_slope_change vol_diff_sd volscale_diff volscale_trend distribution_skew distribution_kurtosis
distribution_iqr distribution_quantile_range distribution_quantile_skew extreme_range persistence_diff_autocorr
persistence_variance_ratio'''.split())
LOG_BASIS = tuple('TR_BASE_'+name for name in 'vol_ewma vol_abs_change vol_change vol_ratio vol_downside vol_upside vol_asymmetry'.split())
POLICY_ID = 'POL_TRANSFORM_EVALUATION_FX_SNAPSHOT'
POLICY_VERSION = '2.0.0'
CATALOG_KIND = 'fx_feature_recipe_registration'
RULES = {'interpretation':'retrospective_snapshot', 'calendar_id':'RESEARCH_WEEKDAYS',
    'calendar_version':'version_1.0.0','parameter_frequency':'daily','observation_clock':'scheduled_weekdays',
    'historical_availability':'preserve_unknown','missing_scheduled_price':'retain_null',
    'holiday_exclusions':'none','knowledge_state':'one_pinned_snapshot',
    'output_selection':'explicit_bounded_reference_dates','historical_replay':'uncertified','live_use':'uncertified'}


def _bytes_hash(path):return hashlib.sha256(stable_read(path)).hexdigest()


def verify_review(root, review_path):
    """Compare the supplied review and its exact audited registry against disk."""
    path=Path(review_path);text=stable_read(path).decode('utf-8')
    structured=strict_json(stable_read(path.with_suffix('.json')))
    groups={category['code']:category['ids'] for category in structured['categories']}
    errors=[]
    for code,expected in [('log_first_candidate',LOG_FIRST),('internal_log_basis',LOG_BASIS)]:
        if set(groups.get(code,[]))!=set(expected):errors.append('Requested '+code+' operator set differs')
        for identifier in expected:
            if identifier+'@2.0.0' not in text:errors.append('Text review omits '+identifier)
    registry=Registry(root)
    current={entry['id']:entry for entry in registry.all_operators()}
    for old in structured['operators']:
        entry=current.get(old['id'])
        if entry is None:errors.append('Missing '+old['id']);continue
        contract=entry['body']['execution_contract']
        source=Path(root)/'definitions/transformations'/entry['id']/(entry['version']+'.json')
        if _bytes_hash(source)!=old['source']['file_sha256']:errors.append('Definition changed: '+entry['id'])
        for name in ('formula','kernel','input_semantics','output_semantics','output_unit_rule','temporal_mode','parameter_grid'):
            if contract[name]!=old[name]:errors.append(entry['id']+': changed '+name)
    if set(current)!={item['id'] for item in structured['operators']}:errors.append('Executable registry membership differs from review')
    result={'review_sha256':_bytes_hash(path),'review_json_sha256':_bytes_hash(path.with_suffix('.json')),
        'reviewed_operator_count':len(current),'requested_operator_count':30,'discrepancies':errors}
    if errors:raise PublicationError('Review discrepancies: '+'; '.join(errors))
    return result


def _policy_records(root, request_text, review):
    store=FeatureStore(root)
    config=strict_json(stable_read(store.path('config/fx_retrospective_completion.json')))
    batch=_approved_policy(store,config['return_policy'])
    evidence_body={'title':'Explicitly requested FX log recipe registration and bounded preparation',
        'authority':'user_explicit_request','request_text':request_text,'review':review,
        'rules':RULES,'source_retrospective_policy':batch['retrospective_policy'],
        'source_alignment_approval':batch['approval_evidence'],
        'registration_scope':'all_existing_approved_daily_grid_combinations_across_43_registered_fx_instruments',
        'materialization_scope':'explicit_small_verification_sample_only',
        'research_execution':'not_authorized_by_this_preparation_profile'}
    payload=canonical_bytes(evidence_body)+b'\n';sha=hashlib.sha256(payload).hexdigest()
    evidence=identified('onboarding_evidence',{'kind':'transform_execution_policy',
        'payload':{'sha256':sha,'byte_count':len(payload),'row_count':None},'media_type':'application/json',
        'description':'User-requested additive FX recipe variants and bounded snapshot-retrospective Feature preparation; historical availability stays unknown.'},'EVIDENCE_')
    parameters=[{'name':key,'unit':'policy_setting','value':{'kind':'token','value':value}} for key,value in sorted(RULES.items())]
    parameters.extend([{'name':'source_retrospective_policy','unit':'policy_reference','value':{'kind':'reference','value':batch['retrospective_policy']}},
        {'name':'source_alignment_approval','unit':'evidence_reference','value':{'kind':'reference','value':batch['approval_evidence']}}])
    policy={'schema_version':'0.2.0','record_type':'policy_definition','id':POLICY_ID,'version':POLICY_VERSION,
        'display_name':'FX snapshot-retrospective Feature preparation on the approved weekday grid',
        'body':{'kind':'selection','specification':reference(evidence),'parameters':parameters,'approval_state':'approved','compatibility_evidence':[]}}
    return policy,evidence,payload,batch


def get_fx_policy(root):
    registry=Registry(root);policy=registry.get_policy(POLICY_ID,POLICY_VERSION)
    registry.resolve_policy(reference(policy))
    rules={item['name']:item['value']['value'] for item in policy['body']['parameters']}
    if any(rules.get(key)!=value for key,value in RULES.items()):raise PublicationError('FX Feature evaluation rules differ')
    return policy


def _typed_parameters(entry, parameters):
    specs={item['name']:item for item in entry['body']['parameters']}
    result=[]
    for name,value in sorted(parameters.items()):
        spec=specs[name];kind=spec['value_kind']
        data=str(value) if kind=='integer' else decimal_text(value) if kind=='decimal' else value
        result.append({'name':name,'unit':spec['unit'],'value':{'kind':kind,'value':data}})
    return result


def configurations(registry):
    result=[]
    for identifier in sorted(LOG_FIRST+LOG_BASIS):
        entry=registry.operator(identifier);c=entry['body']['execution_contract'];grid=c['grid_profile']
        if grid!=reference(registry.get_policy('POL_TRANSFORM_GRID_BASE')):raise PublicationError('Unexpected parameter policy')
        for params in registry.enumerate_grid(entry,'daily',grid,max_combinations=10000):
            if identifier in LOG_BASIS and params.get('basis')!='log':continue
            parameters=_typed_parameters(entry,params)
            spec={'operator':reference(entry),'mode':'log_first' if identifier in LOG_FIRST else 'internal_log_basis',
                'parameters':parameters,'grid_policy':grid,'parameter_frequency':'daily'}
            result.append(dict(spec,id='FXCONFIG_'+digest(spec),display_name=entry['display_name']))
    if len({item['id'] for item in result})!=len(result):raise PublicationError('Duplicate FX recipe configuration')
    return result


def build_fx_feature(root, instrument, configuration, *, registry=None, evaluation_policy=None):
    registry=registry or Registry(root);store=FeatureStore(root)
    policy=evaluation_policy or get_fx_policy(root)
    snapshot=store.resolve(instrument['price_snapshot']);body=snapshot['body']
    view=store.resolve(body['definition']);dataset=store.resolve(view['body']['dataset'])
    if body.get('kind')!='fx_constructed_prices' or dataset['body'].get('kind')!='fx_constructed_dataset':raise PublicationError('FX recipe requires canonical FX prices')
    if body['instrument_id']!=instrument['instrument_id']:raise PublicationError('Instrument/source binding mismatch')
    entry=registry.resolve(configuration['operator']);identifier=entry['id']
    if identifier not in LOG_FIRST+LOG_BASIS:raise PublicationError('Operator outside explicitly requested FX variants')
    expected_mode='log_first' if identifier in LOG_FIRST else 'internal_log_basis'
    if configuration['mode']!=expected_mode or configuration['parameter_frequency']!='daily':raise PublicationError('Wrong FX chain mode or grid frequency')
    steps=[];unit=body['source_metadata']['unit'];semantics='price';previous='source'
    if expected_mode=='log_first':
        log=registry.operator('TR_BASE_level_log')
        steps.append({'node':'log_price','phase':'transformation','operator':reference(log),'inputs':['source'],
            'parameters':[],'grid_policy':log['body']['execution_contract']['grid_profile']})
        previous='log_price';unit,semantics=_metadata(unit,semantics,log['body']['execution_contract'],{})
    step={'node':'fx_value','phase':'transformation','operator':reference(entry),'inputs':[previous],
        'parameters':configuration['parameters'],'grid_policy':configuration['grid_policy']}
    params=registry.validate_parameters(entry,_parameters(step,entry),'daily',step['grid_policy'])
    if identifier in LOG_BASIS and params.get('basis')!='log':raise PublicationError('Internal log variants require basis=log')
    unit,semantics=_metadata(unit,semantics,entry['body']['execution_contract'],params);steps.append(step)
    recipe=normalize_recipe({'sources':[{'alias':'source','source_view':body['definition']}],'steps':steps,'output_node':'fx_value',
        'output_unit':unit,'calculation_scope_requirement':'none','scope_policy':None,
        'selection':{'measure':'close','entity_id':body['instrument_id'],'dimensions':[]},'history_mode':'resolved_state',
        'history_policy':reference(registry.get_policy('POL_TRANSFORM_HISTORY')),
        'execution_policy':reference(registry.get_policy('POL_TRANSFORM_EXECUTION')),'evaluation_policy':reference(policy)})
    label=', '.join(p['name']+'='+str(p['value']['value']) for p in step['parameters'])
    mode_label='Log -> ' if expected_mode=='log_first' else ''
    return make_feature_definition(recipe,f"{body['instrument_id']} - {mode_label}{entry['display_name']} ({label})")


def validate_fx_recipe(root, feature):
    registry=Registry(root);store=FeatureStore(root)
    store._validate(feature)
    normalized=normalize_recipe(feature['body']['recipe'])
    if reference(make_feature_definition(normalized,feature['display_name']))!=reference(feature):raise PublicationError('FX Feature canonical identity mismatch')
    if len(normalized['sources'])!=1 or normalized['sources'][0]['alias']!='source' or normalized['history_mode']!='resolved_state' or normalized['calculation_scope_requirement']!='none' or normalized['scope_policy'] is not None:
        raise PublicationError('FX recipes require exactly one price source and the resolved-state profile')
    policy=get_fx_policy(root)
    if normalized.get('evaluation_policy')!=reference(policy):raise PublicationError('Wrong FX Feature evaluation policy')
    for field,name in [('history_policy','POL_TRANSFORM_HISTORY'),('execution_policy','POL_TRANSFORM_EXECUTION')]:
        if normalized[field]!=reference(registry.get_policy(name)):raise PublicationError('Wrong '+field)
    view=store.resolve(normalized['sources'][0]['source_view']);dataset=store.resolve(view['body']['dataset'])
    if view['body'].get('kind')!='fx_constructed_view' or dataset['body'].get('kind')!='fx_constructed_dataset':raise PublicationError('FX recipes only accept canonical FX price sources')
    symbol=dataset['body']['instrument_id'];meta=dataset['body']['source_metadata']
    if view['body']['source_metadata']!=meta or normalized['selection']!={'measure':'close','entity_id':symbol,'dimensions':[]}:
        raise PublicationError('FX source semantics/selection mismatch')
    terminal=registry.resolve(normalized['steps'][-1]['operator']);identifier=terminal['id']
    if identifier not in LOG_FIRST+LOG_BASIS:raise PublicationError('Excluded FX recipe operator')
    if identifier in LOG_FIRST:
        if len(normalized['steps'])!=2 or normalized['steps'][0]['operator']!=reference(registry.operator('TR_BASE_level_log')) or normalized['steps'][0]['parameters']!=[]:
            raise PublicationError('Requested FX chain is exactly Log then approved BASE transformation')
    elif len(normalized['steps'])!=1:raise PublicationError('Internal log basis must consume price directly')
    previous='source'
    for index,step in enumerate(normalized['steps']):
        expected_node='log_price' if identifier in LOG_FIRST and index==0 else 'fx_value'
        if step['node']!=expected_node or step['inputs']!=[previous] or step['phase']!='transformation':
            raise PublicationError('FX recipe wiring must follow its exact approved price/log chain')
        previous=step['node']
    if normalized['output_node']!=previous:raise PublicationError('FX recipe output must be the terminal transformation')
    unit=meta['unit'];semantics='price';compiled=[]
    for step in normalized['steps']:
        entry=registry.resolve(step['operator']);c=entry['body']['execution_contract']
        if c['certification']['status']!='approved' or c['temporal_mode']!='reference_state' or c['capabilities']:
            raise PublicationError('FX snapshot profile cannot satisfy this operator contract')
        if step.get('grid_policy')!=c['grid_profile']:raise PublicationError('Explicit approved grid binding required')
        params=registry.validate_parameters(entry,_parameters(step,entry),'daily',step['grid_policy'])
        unit,semantics=_metadata(unit,semantics,c,params)
        compiled.append({'entry':entry,'parameters':params})
    if identifier in LOG_BASIS and compiled[-1]['parameters'].get('basis')!='log':raise PublicationError('Internal log basis required')
    if normalized['output_unit']!=unit:raise PublicationError('FX output unit differs from contract composition')
    return {'unit':unit,'value_semantics':semantics,'steps':compiled,'grid_policy':reference(registry.get_policy('POL_TRANSFORM_GRID_BASE')),
        'evaluation_policy':policy,'source_view':view,'dataset':dataset,'instrument_id':symbol}


def register_fx_recipes(root, *, review_path, request_path):
    root=Path(root).resolve();store=FeatureStore(root)
    audit=verify_review(root,review_path);request_text=stable_read(Path(request_path)).decode('utf-8')
    if not request_text.strip():raise PublicationError('Explicit request evidence is required')
    policy,evidence,payload,batch=_policy_records(root,request_text,audit)
    registry=Registry(root);variants=configurations(registry);instruments=list_instruments(root)
    if len(instruments)!=43 or len({i['instrument_id'] for i in instruments})!=43:raise PublicationError('Expected the existing43FX instruments exactly')
    features=[];bindings=[]
    for instrument in instruments:
        if instrument['price_snapshot'] is None:raise PublicationError('FX source snapshot absent: '+instrument['instrument_id'])
        snapshot,_=_price_snapshot(store,instrument['price_snapshot'],batch,verify_rows=False)
        for variant in variants:
            feature=build_fx_feature(root,instrument,variant,registry=registry,evaluation_policy=policy)
            features.append(feature)
            bindings.append({'configuration_id':variant['id'],'instrument_id':instrument['instrument_id'],
                'feature':reference(feature),'price_snapshot':reference(snapshot),'source_view':snapshot['body']['definition']})
    if len({f['id'] for f in features})!=len(features):raise PublicationError('Duplicate canonical FX recipe binding')
    # Validate and reject conflicts before publishing any definition. Display-name
    # differences are presentation only and never create a second identity.
    pending=[];reused=[]
    for record in [evidence,policy,*features]:
        path=store.path(record_path(record))
        if path.exists():
            old=strict_json(stable_read(path));store._validate(old)
            if reference(old)!=reference(record):raise PublicationError('Conflicting existing definition: '+record['id'])
            reused.append(record['id'])
        else:
            store._validate(record);pending.append(record)
    catalog=make_record('onboarding_evidence',{'kind':CATALOG_KIND,'profile':'fx_feature_recipes.1.0.0',
        'evaluation_policy':reference(policy),'review':audit,'configurations':variants,'bindings':bindings,
        'configuration_count':len(variants),'instrument_count':len(instruments),'binding_count':len(bindings),
        'materialization_state':'registered_only','research_state':'not_executed',
        'identity_note':'Shared configurations are catalog groupings; canonical predictor identities include source view and instrument selection.'},
        'Registered FX log recipe configurations and exact instrument bindings')
    with store.writer():
        store.io.blob(payload,'json','approved_fx_feature_preparation_policy',None)
        for record in pending:store.install_record(record)
        # This completion index is published last and contains references only.
        store.install_record(catalog)
    from api.signal_library import list_signal_library
    materialized={item['feature']['id'] for item in list_signal_library(root)['signals']}
    return {'catalog':reference(catalog),'configuration_count':len(variants),'instrument_count':len(instruments),'binding_count':len(bindings),
        'added_recipe_definitions':sum(f['id'] not in reused for f in features),
        'reused_recipe_definitions':sum(f['id'] in reused for f in features),
        'registered_unmaterialized':sum(f['id'] not in materialized for f in features),'blocked_combinations':[],
        'operator_counts':{identifier:sum(v['operator']['id']==identifier for v in variants) for identifier in sorted(LOG_FIRST+LOG_BASIS)},
        'review_verification':audit,'evaluation_policy':reference(policy)}


def _catalog_bindings(root):
    store=FeatureStore(root);configurations_by_id={};bindings={};catalogs=[]
    registry=None;expected_variants=None;snapshots={};batch=None
    for path in sorted(store.path('storage/catalog/onboarding/evidence').glob('EVIDENCE_*.json')):
        record=strict_json(stable_read(path));body=record.get('body',{})
        if body.get('kind')!=CATALOG_KIND:continue
        store._validate(record)
        if path.name!=record['id']+'.json':raise PublicationError('FX recipe catalog path mismatch')
        if body['profile']!='fx_feature_recipes.1.0.0':raise PublicationError('Unknown FX recipe catalog profile')
        if registry is None:
            registry=Registry(root)
            expected_variants={item['id']:item for item in configurations(registry)}
            config=strict_json(stable_read(store.path('config/fx_retrospective_completion.json')))
            batch=_approved_policy(store,config['return_policy'])
        policy=store.resolve(body['evaluation_policy'])
        if reference(policy)!=reference(get_fx_policy(root)):raise PublicationError('Wrong catalog policy')
        found={item['id']:item for item in body['configurations']}
        if found!=expected_variants or len(found)!=len(body['configurations']) or body['configuration_count']!=len(found):
            raise PublicationError('Catalog configurations differ from the approved parameter grid')
        keys=set();symbols=set()
        for item in body['bindings']:
            if set(item)!={'configuration_id','instrument_id','feature','price_snapshot','source_view'}:
                raise PublicationError('Invalid FX recipe binding fields')
            key=(item['configuration_id'],item['instrument_id'])
            if key in keys or item['configuration_id'] not in found:raise PublicationError('Duplicate or unknown configuration binding')
            keys.add(key);symbols.add(item['instrument_id'])
            snap_key=canonical_bytes(item['price_snapshot'])
            if snap_key not in snapshots:
                snapshot,_=_price_snapshot(store,item['price_snapshot'],batch,verify_rows=False)
                snapshots[snap_key]=snapshot
            detail=snapshots[snap_key]['body']
            if detail['instrument_id']!=item['instrument_id'] or detail['definition']!=item['source_view']:
                raise PublicationError('Catalog instrument/source binding differs from its snapshot')
            existing=bindings.setdefault(item['feature']['id'],item)
            if existing!=item:raise PublicationError('Conflicting instrument binding')
        if symbols!=set(_universe()) or body['instrument_count']!=len(symbols) or body['binding_count']!=len(keys) or keys!={(identifier,symbol) for identifier in found for symbol in symbols}:
            raise PublicationError('Catalog counts or configuration/instrument coverage differ')
        catalogs.append(reference(record));configurations_by_id.update(found)
    return store,configurations_by_id,bindings,catalogs


def _verify_binding(root,store,binding,variant,registry,policy):
    feature=store.resolve(binding['feature'])
    instrument={'instrument_id':binding['instrument_id'],'price_snapshot':binding['price_snapshot']}
    expected=build_fx_feature(root,instrument,variant,registry=registry,evaluation_policy=policy)
    if reference(feature)!=reference(expected):raise PublicationError('Recipe binding does not resolve its declared configuration and instrument')
    return feature


def list_fx_recipes(root, instrument_id=None, limit=100, offset=0):
    if instrument_id is not None and not re.fullmatch('[A-Z]{6}',instrument_id):raise ValueError('Invalid instrument ID')
    if type(limit) is not int or not 1<=limit<=500 or type(offset) is not int or offset<0:raise ValueError('Invalid pagination')
    store,variants,all_bindings,catalogs=_catalog_bindings(root)
    bindings=sorted((b for b in all_bindings.values() if instrument_id is None or b['instrument_id']==instrument_id),key=lambda b:(b['instrument_id'],b['configuration_id']))
    # Only successfully verified materializations are ready for selection.
    from api.signal_library import list_signal_library
    signals=list_signal_library(root)['signals']
    materialized={s['feature']['id']:s for s in signals}
    rows=[]
    registry=Registry(root) if bindings else None;policy=get_fx_policy(root) if bindings else None
    for binding in bindings[offset:offset+limit]:
        variant=variants[binding['configuration_id']]
        feature=_verify_binding(root,store,binding,variant,registry,policy)
        rows.append({**binding,'name':feature['display_name'],'operator':variant['operator'],'parameters':variant['parameters'],
            'mode':variant['mode'],'state':'materialized' if feature['id'] in materialized else 'registered_unmaterialized',
            'selectable':feature['id'] in materialized,'signal_id':feature['body']['signal_id'],
            'materialization_ids':[materialized[feature['id']]['default_materialization_id']] if feature['id'] in materialized else []})
    ready=sum(b['feature']['id'] in materialized for b in bindings)
    return {'schema_version':'1.0.0','configuration_count':len(variants),'binding_count':len(all_bindings),'registered_count':len(bindings),
        'materialized_count':ready,'unmaterialized_count':len(bindings)-ready,'instrument_count':len({b['instrument_id'] for b in all_bindings.values()}),
        'limit':limit,'offset':offset,'next_offset':offset+limit if offset+limit<len(bindings) else None,'recipes':rows,'catalogs':catalogs,'issues':[]}


def resolve_fx_binding(root, *, instrument_id, operator_id, parameters):
    store,variants,bindings,_=_catalog_bindings(root);matches=[]
    for binding in bindings.values():
        variant=variants[binding['configuration_id']]
        if binding['instrument_id']!=instrument_id or variant['operator']['id']!=operator_id:continue
        entry=store.resolve(variant['operator'])
        step={'parameters':variant['parameters']}
        if _parameters(step,entry)==parameters:matches.append(binding)
    if len(matches)!=1:raise PublicationError('Select one exact registered FX recipe parameter binding')
    binding=matches[0]
    _verify_binding(root,store,binding,variants[binding['configuration_id']],Registry(root),get_fx_policy(root))
    return binding
