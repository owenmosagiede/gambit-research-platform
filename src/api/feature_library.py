"""Registered selectable Feature definitions and read-only Scope coverage.

FX recipes are source independent. Historical source-bound definitions remain
addressable through the Signal Library but are not duplicate selectable recipes.
"""
import re
from pathlib import Path
from data.catalog_reads import catalog_glob

from data.alfred_onboarding import stable_read, strict_json
from data.feature_store import FeatureStore, record_path, PublicationError
from data.transformations.identity import reference, feature_id, signal_id
from api.scope_library import SCOPE_ID, SCOPE_VERSION

FEATURE_ID = re.compile(r'(?:FEATURE_RECIPE|FEATURE)_[0-9a-f]{64}\Z', re.ASCII)


class InvalidFeatureQuery(ValueError):
    pass


class FeatureNotFound(ValueError):
    pass


def _legacy_non_fx(store, record):
    recipe=record['body']['recipe']
    # Known FX capture-specific recipes are immutable compatibility records.
    if recipe.get('evaluation_policy',{}).get('id')=='POL_TRANSFORM_EVALUATION_FX_SNAPSHOT':
        return False
    for source in recipe['sources']:
        view=store.resolve(source['source_view']);dataset=store.resolve(view['body']['dataset'])
        if dataset['body'].get('kind')=='fx_constructed_dataset':return False
    store._validate(record)
    if record['id']!=feature_id(recipe) or record['body']['signal_id']!=signal_id(recipe):
        raise PublicationError('Source-bound Feature identity differs')
    store.verify_closure([record])
    return True


def _item(store, record, kind):
    body=record['body'];recipe=body if kind=='reusable_fx_recipe' else body['recipe']
    transformations=[]
    for step in recipe['steps']:
        operator=store.resolve(step['operator'])
        transformations.append({'operator':step['operator'],'label':operator['display_name'],
                                'parameters':step['parameters']})
    return {'id':record['id'],'version':record['version'],'reference':reference(record),
        'name':record['display_name'],'kind':kind,'registration_state':'registered',
        'transformations':transformations,'signal_id':None if kind=='reusable_fx_recipe' else body['signal_id']}


def list_feature_library(root, *, store=None):
    from data.reusable_features import list_reusable_fx_recipes, ReusableRecipeNotFound
    store=store or FeatureStore(root)
    # New definitions can make a formerly unique reference ambiguous. Include
    # membership across all definition types, not only currently selected files.
    tuple(catalog_glob(store.path('definitions'), '*/*/*.json'))
    try:native=list_reusable_fx_recipes(root)
    except ReusableRecipeNotFound:
        if any(catalog_glob(store.path('storage/catalog/feature_recipes'), '*/manifest.json')):raise
        native=[]
    features=[_item(store,record,'reusable_fx_recipe') for record in native]
    issues=[]
    for path in sorted(catalog_glob(store.path('definitions/features'), '*/*.json')):
        try:
            record=strict_json(stable_read(path))
            if not _legacy_non_fx(store,record):continue
            if record_path(record)!=str(path.relative_to(store.root)):raise PublicationError('Feature path differs')
            features.append(_item(store,record,'stored_feature'))
        except (ValueError,KeyError,TypeError,OSError):
            issues.append({'code':'UNAVAILABLE_FEATURE_DEFINITION','id':path.parent.name,'version':path.stem})
    features.sort(key=lambda item:(item['name'].casefold(),item['id'],item['version']))
    if len({(item['id'],item['version']) for item in features})!=len(features):
        raise PublicationError('Duplicate selectable Feature definition')
    return {'schema_version':'1.0.0','feature_count':len(features),'features':features,'issues':issues}


def _legacy_resolution(root, identifier, version, scope_id, scope_version):
    """Use the same read-only external compatibility planner as Submit."""
    from data.scopes import resolve_scope
    from research import external_features, inputs
    from research.contracts import ref as research_ref
    feature=external_features.definition(root, {'id':identifier, 'version':version})
    scope=resolve_scope(root,scope_id,scope_version);source_outputs=[];issues=[]
    # Source observations exist independently of whether the chosen Scope is compatible.
    from data.feature_store_contracts import normalize_materialization
    store=FeatureStore(root)
    for path in sorted(store.path('storage/catalog/feature_store').glob('*/manifest.json')):
        value=strict_json(stable_read(path))
        if value.get('definition')!=reference(feature):continue
        try:
            manifest=normalize_materialization(value)
            external_features.verify_metadata_closure(store,manifest)
            headers=external_features.observation_headers(store,manifest)
            periods=[x['reference_time'] for x in manifest['input_key']['output_index'] if x['reference_time']]
            source_outputs.append({'reference':reference(manifest),'legacy_feature':reference(feature),
                'signal_id':feature['body']['signal_id'],'row_count':manifest['row_count'],
                'status_counts':manifest['status_counts'],'readiness_capabilities':{},
                'coverage':{'reference_start':min(periods) if periods else None,'reference_end':max(periods) if periods else None,
                            'cutoff_start':headers[0][0],'cutoff_end':headers[-1][0]}})
        except (ValueError,KeyError,TypeError,OSError):issues.append({'code':'UNAVAILABLE_SOURCE_MATERIALIZATION'})
    compatible=False;policy=None
    try:
        from research.schedule import apply_schedule, load_schedule
        profile=apply_schedule(external_features.load_profile(root),load_schedule(root),price_time_series=False)
        intent={'feature':{'id':identifier,'version':version},
                'scope':{'id':scope_id,'version':scope_version},
                'target_family':'price_return','expected_direction':'POSITIVE'}
        # Direction does not affect compatibility. Submit freezes the user's actual hypothesis.
        plan=inputs.resolve_plan(root,intent,profile)
        source=plan['external_source'];policy=source['alignment_policy'];compatible=True
        source_outputs=[{'reference':source['materialization'],'legacy_feature':reference(feature),
            'signal_id':feature['body']['signal_id'],'row_count':source['row_count'],
            'status_counts':source['status_counts'],'coverage':source['coverage'],'readiness_capabilities':{}}]
        reason=('Compatible for individual-instrument retrospective TS. Daily state; date-only observations become eligible '
                'on the next scheduled weekday after both availability and evaluation. Persist until superseded, including '
                'invalid updates. Alignment is prepared only after Submit. Historical timing and live readiness remain unverified.')
    except (ValueError,KeyError,TypeError,OSError) as exc:
        reason=('External alignment policy is not installed.' if isinstance(exc,FileNotFoundError) else str(exc));issues.append({'code':'EXTERNAL_ALIGNMENT_BLOCKED','message':reason})
    readiness={name:{'decision':('provisional' if compatible else 'blocked') if name=='retrospective_research' else 'unresolved',
                     'reason':reason} for name in ('retrospective_research','historical_replay','live_use')}
    members=[{'instrument_id':symbol,'state':'missing' if compatible else 'blocked','reason':reason,
              'materializations':[],'readiness':readiness} for symbol in scope['members']]
    return {'schema_version':'1.0.0','recipe':{'reference':reference(feature),'name':feature['display_name'],'kind':'stored_feature'},
        'scope':{key:scope[key] for key in ('id','version','reference','display_name','membership_snapshot')},
        'registration_state':'registered','selection_read_only':True,'member_count':len(members),'members':members,
        'summary':{'materialized_member_count':0,'missing_member_count':len(members) if compatible else 0,
                   'blocked_member_count':0 if compatible else len(members)},
        'source_materializations':source_outputs,'source_application_note':reason,'issues':issues,
        'submission_compatible':compatible,'alignment_policy':policy,
        'research_spec':(research_ref(profile) if compatible else None)}


def get_feature_resolution(root, identifier, version, scope_id, scope_version):
    if not isinstance(identifier,str) or not FEATURE_ID.fullmatch(identifier):raise InvalidFeatureQuery('Invalid Feature identity')
    if not isinstance(version,str) or not SCOPE_VERSION.fullmatch(version):raise InvalidFeatureQuery('Exact Feature version required')
    if not isinstance(scope_id,str) or not SCOPE_ID.fullmatch(scope_id):raise InvalidFeatureQuery('Invalid Scope identity')
    if not isinstance(scope_version,str) or not SCOPE_VERSION.fullmatch(scope_version):raise InvalidFeatureQuery('Exact Scope version required')
    from research import feature_applications
    from data.scopes import resolve_scope
    selection={'id':identifier,'version':version}
    try:definition=feature_applications.load_definition(root,selection)
    except (ValueError,OSError) as exc:raise FeatureNotFound(str(exc)) from exc
    if definition['record_type']=='feature_recipe_definition':
        from data.feature_resolution import resolve_feature_scope
        result=resolve_feature_scope(root,identifier,scope_id,scope_version,version=version)
    else:
        result=_legacy_resolution(root,identifier,version,scope_id,scope_version)
    try:
        application=feature_applications.resolve(root,selection,resolve_scope(root,scope_id,scope_version))
        result['application']=application
        result['submission_compatible']=result.get('submission_compatible',True)
    except (ValueError,KeyError,TypeError,OSError) as exc:
        result['application']=None
        result['submission_compatible']=False
        result['source_application_note']=str(exc)
        result['issues'].extend(getattr(exc,'blockers',[{'code':'FEATURE_APPLICATION_BLOCKED','message':str(exc)}]))
    return result
