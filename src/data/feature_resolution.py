"""Read-only coverage resolution of a reusable Feature recipe against a Scope.

Selection never registers, prepares or materializes anything. Existing legacy
source-bound definitions and immutable outputs are inspected as evidence, and
only outputs matching the current source and configured policies count as ready.
"""
from copy import deepcopy
from pathlib import Path

from data.alfred_onboarding import stable_read, strict_json
from data.feature_store import FeatureStore, read_materialization, PublicationError
from data.feature_store_contracts import normalize_library_entry
from data.fx_feature_contracts import PROFILE
from data.fx_feature_recipes import get_fx_policy
from data.fx_pipeline import list_instruments
from data.scopes import resolve_scope
from data.targets.fx import _approved_policy, _price_snapshot
from data.transformations.contracts import normalize_time
from data.transformations.identity import digest, reference


class IncompatibleCoverage(ValueError):
    def __init__(self, code, message):
        self.code=code
        super().__init__(message)


def _issue(code, message, instrument_id=None, materialization=None):
    result={'code':code,'message':message}
    if instrument_id is not None: result['instrument_id']=instrument_id
    if materialization is not None: result['materialization']=deepcopy(materialization)
    return result


def _not_ready(reason):
    return {'retrospective_research':{'decision':'blocked','reason':reason},
        'historical_replay':{'decision':'blocked','reason':'Historical source availability and complete vintages are unknown.'},
        'live_use':{'decision':'unresolved','reason':'Valuation clock, price basis and live eligibility remain unverified.'}}


def _base_response(recipe, scope):
    return {'schema_version':'1.0.0','recipe':{'reference':reference(recipe),
        'name':recipe['display_name'],'kind':'reusable_fx_recipe'},
        'scope':{key:deepcopy(scope[key]) for key in
            ('reference','id','version','display_name','membership_snapshot')},
        'member_count':scope['member_count'],'members':[],
        'summary':{'materialized_member_count':0,'missing_member_count':0,'blocked_member_count':0},
        'issues':[],'selection_read_only':True,'registration_state':'registered',
        'coverage_semantics':'Only the explicitly listed stored output periods are available. This does not establish complete history or whole-Scope coverage.',
        'preparation_performed':False}


def _finish(response):
    response['summary']={state+'_member_count':sum(member['state']==state for member in response['members'])
                         for state in ('materialized','missing','blocked')}
    return response


def _blocked_members(response, symbols, code, message):
    response['issues'].append(_issue(code,message))
    for symbol in symbols:
        response['members'].append({'instrument_id':symbol,'state':'blocked','reason':message,'reason_code':code,
            'materializations':[],'unavailable_materializations':[],'current_price_snapshot':None,
            'preparation_bindings':[],'preparation_binding':None,'preparation_binding_reason':message,
            'readiness':_not_ready(message)})
    return _finish(response)


def _linked_materializations(store, feature):
    """Return unique explicitly published refs; never infer readiness from files."""
    signal=feature['body']['signal_id']; refs={}; issues=[]
    folder=store.path('storage/catalog/signal_library/entries/'+signal)
    for path in sorted(folder.glob('*.json')):
        try:
            entry=strict_json(stable_read(path)); normalize_library_entry(entry)
            if path.name!=digest(entry)+'.json' or entry['signal_id']!=signal or entry['feature']!=reference(feature):
                raise PublicationError('Signal projection reference mismatch')
            for binding in entry['feature_materializations']:
                previous=refs.setdefault(binding['id'],binding)
                if previous!=binding: raise PublicationError('Conflicting linked materialization reference')
        except Exception:
            issues.append(_issue('UNAVAILABLE_SIGNAL_PROJECTION','A stored Signal projection could not be verified.'))
    return sorted(refs.values(),key=lambda item:item['id']),issues


def _coverage(rows):
    references=[row['reference_time'] for row in rows if row['reference_time'] is not None]
    cutoffs=[row['evaluation_cutoff'] for row in rows]
    return {'reference_start':min(references) if references else None,
        'reference_end':max(references) if references else None,
        'cutoff_start':min(cutoffs) if cutoffs else None,'cutoff_end':max(cutoffs) if cutoffs else None}


def _same_semantics(feature, recipe):
    legacy=feature['body']['recipe'];reusable=recipe['body']
    fields=('steps','output_node','history_mode','history_policy','execution_policy','evaluation_policy')
    return (all(legacy.get(field)==reusable.get(field) for field in fields)
        and legacy.get('calculation_scope_requirement')=='none' and legacy.get('scope_policy') is None)


def _usable_output(item, expected_ref, recipe, feature, symbol, snapshot, batch, cutoff):
    """Check current selection compatibility after the independent stored reader."""
    manifest=item['manifest']; key=manifest['input_key']; meta=manifest['metadata']
    if reference(manifest)!=expected_ref or reference(item['feature'])!=reference(feature):
        raise IncompatibleCoverage('MATERIALIZATION_REFERENCE_MISMATCH','Stored output references differ from their published Feature binding.')
    if manifest.get('identity_profile')!=PROFILE or manifest.get('schema_version')!='0.6.0':
        raise IncompatibleCoverage('UNSUPPORTED_MATERIALIZATION_PROFILE','This output does not use the supported retrospective FX preparation profile.')
    if not _same_semantics(item['feature'],recipe):
        raise IncompatibleCoverage('MATERIALIZATION_RECIPE_MISMATCH','Stored output belongs to another recipe or parameter configuration.')
    if key['source_snapshots']!=[reference(snapshot)]:
        raise IncompatibleCoverage('STALE_SOURCE_SNAPSHOT','Stored output uses an older or different price snapshot than the current instrument registry.')
    if meta['source_view']!=snapshot['body']['definition'] or meta['selection']!={'measure':'close','entity_id':symbol,'dimensions':[]}:
        raise IncompatibleCoverage('INCOMPATIBLE_SOURCE_BINDING','Stored output is bound to a different instrument or SourceView.')
    if meta['value_semantics']!=recipe['body']['output_contract']['value_semantics']:
        raise IncompatibleCoverage('INCOMPATIBLE_OUTPUT_SEMANTICS','Stored output has different value semantics from the selected reusable recipe.')
    if key['batch_policy']!=batch:
        raise IncompatibleCoverage('INCOMPATIBLE_PREPARATION_POLICY','Stored output does not match the currently configured approved preparation policy.')
    if key['knowledge_cutoff']!=cutoff:
        raise IncompatibleCoverage('STALE_KNOWLEDGE_CUTOFF','Stored output uses a different snapshot knowledge cutoff than the current preparation configuration.')
    capabilities=manifest['readiness_capabilities']
    retrospective=capabilities.get('retrospective_research',{})
    if retrospective.get('decision')!='ready' or retrospective.get('policy')!=batch['retrospective_policy'] or not manifest['status_counts'].get('valid'):
        raise IncompatibleCoverage('OUTPUT_NOT_RESEARCH_READY','Stored output has no valid observations authorized for retrospective research.')
    rows=item['observations']; period=key['period']
    if any(row['entity_id']!=symbol or row['evaluation_cutoff']!=cutoff or row['available_at'] is not None or
           row['historical_eligibility_certified'] is not False or not period['start_inclusive']<=row['reference_time']<=period['end_inclusive'] for row in rows):
        raise IncompatibleCoverage('INCOMPATIBLE_OUTPUT_TIMING','Stored rows do not preserve the declared instrument, output interval and unknown historical availability.')
    return {'reference':reference(manifest),'row_count':manifest['row_count'],
        'status_counts':deepcopy(manifest['status_counts']),'coverage':_coverage(rows),
        'readiness_capabilities':deepcopy(capabilities),'legacy_feature':reference(feature),
        'signal_id':feature['body']['signal_id'],'source_snapshot':reference(snapshot),
        'knowledge_cutoff':cutoff,'output_period':deepcopy(period),
        'coverage_state':'stored_bounded_output','historical_availability':'unknown'}


def resolve_feature_scope(root, identifier, scope_id, scope_version, *, version='1.0.0'):
    """Resolve all Scope members without changing definitions, outputs or state."""
    from data.reusable_features import load_reusable_recipe, legacy_bindings_for_recipe, legacy_recipe_projector
    root=Path(root).resolve();store=FeatureStore(root)
    recipe=load_reusable_recipe(root,identifier,version)
    scope=resolve_scope(root,scope_id,scope_version)
    response=_base_response(recipe,scope);symbols=scope['members']
    if len(symbols)!=len(set(symbols)) or len(symbols)!=scope['member_count']:
        raise PublicationError('Resolved Scope membership is ambiguous')
    try:
        config=strict_json(stable_read(store.path('config/fx_retrospective_completion.json')))
        batch=_approved_policy(store,config['return_policy']);cutoff=normalize_time(config['knowledge_cutoff'],'date')
        if recipe['body']['input_contract']['source_profile']=='fx_currency_price.1.0.0':
            from data.fx_currency_features import get_policy
            policy=get_policy(root)
        else:policy=get_fx_policy(root)
        if recipe['body']['evaluation_policy']!=reference(policy):
            raise PublicationError('Recipe evaluation policy differs from the configured preparation policy')
        values={item['name']:item['value']['value'] for item in policy['body']['parameters']}
        if values.get('source_retrospective_policy')!=batch['retrospective_policy'] or values.get('source_alignment_approval')!=batch['approval_evidence']:
            raise PublicationError('Configured preparation approval differs from the recipe')
    except Exception:
        return _blocked_members(response,symbols,'PREPARATION_CONFIGURATION_UNAVAILABLE',
            'The current approved preparation configuration could not be verified for this recipe.')
    response['preparation_context']={'knowledge_cutoff':cutoff,'evaluation_policy':reference(policy),
        'retrospective_policy':batch['retrospective_policy'],'output_period_requested':None}
    try:
        from research.feature_applications import resolve as resolve_application
        resolve_application(root,{'id':identifier,'version':version},scope)
        if scope.get('price_catalog'):
            from data.fx_currency_catalog import resolve_prices
            _,instruments=resolve_prices(root,scope['price_catalog']);rows=list(instruments.values())
        else:rows=list_instruments(root)
        current={row['instrument_id']:row for row in rows}
        if len(current)!=len(rows):raise PublicationError('Ambiguous current instrument registry')
        bindings=legacy_bindings_for_recipe(root,reference(recipe),verify_features=False);by_symbol={}
        for binding in bindings:by_symbol.setdefault(binding['instrument_id'],[]).append(binding)
        project_feature=legacy_recipe_projector(root,recipe)
    except Exception:
        return _blocked_members(response,symbols,'FEATURE_BINDINGS_UNAVAILABLE',
            'Current instrument or registered recipe bindings could not be verified.')
    for symbol in symbols:
        missing='No stored output for this recipe and instrument under the current preparation context.'
        member={'instrument_id':symbol,'state':'missing','reason':missing,'reason_code':'NO_STORED_OUTPUT',
            'materializations':[],'unavailable_materializations':[],'current_price_snapshot':None,
            'preparation_bindings':[],'readiness':_not_ready(missing)}
        local_issues=[]; instrument=current.get(symbol);snapshot=None
        try:
            if instrument is None or instrument.get('price_snapshot') is None:
                raise IncompatibleCoverage('CURRENT_PRICE_UNAVAILABLE','This Scope member has no current registered price snapshot.')
            member['current_price_snapshot']=deepcopy(instrument['price_snapshot'])
            snapshot,_=_price_snapshot(store,instrument['price_snapshot'],batch,verify_rows=False)
            if snapshot['body']['instrument_id']!=symbol:
                raise IncompatibleCoverage('CURRENT_INSTRUMENT_MISMATCH','The current price snapshot belongs to another instrument.')
        except Exception as error:
            code=error.code if isinstance(error,IncompatibleCoverage) else 'CURRENT_PRICE_UNAVAILABLE'
            message=str(error) if isinstance(error,IncompatibleCoverage) else 'The current registered price snapshot could not be verified.'
            local_issues.append(_issue(code,message,symbol))
            snapshot=None
        if snapshot is not None:
            seen=set()
            for binding in by_symbol.get(symbol,[]):
                try:
                    feature=store.resolve(binding['feature'])
                    if reference(project_feature(feature))!=reference(recipe):
                        raise IncompatibleCoverage('INCOMPATIBLE_LEGACY_RECIPE','An existing source-bound Feature does not match the exact reusable input and output contract.')
                    # Validate the existing executable contract per member, then
                    # compare the selected reusable semantics. One damaged bound
                    # Feature must not conceal healthy members of the Scope.
                    if not _same_semantics(feature,recipe):
                        raise IncompatibleCoverage('INCOMPATIBLE_LEGACY_RECIPE','An existing source-bound definition has different ordered transformations, parameters or policies.')
                    if feature['body']['recipe']['selection']!={'measure':'close','entity_id':symbol,'dimensions':[]}:
                        raise IncompatibleCoverage('INCOMPATIBLE_INSTRUMENT_BINDING','An existing Feature definition belongs to another instrument.')
                    if binding['source_view']!=feature['body']['recipe']['sources'][0]['source_view']:
                        raise IncompatibleCoverage('INCOMPATIBLE_SOURCE_BINDING','An existing registration and Feature definition disagree on their SourceView.')
                    if binding['source_view']==snapshot['body']['definition']:
                        member['preparation_bindings'].append({'legacy_feature':binding['feature'],
                            'price_snapshot':reference(snapshot),'batch_policy':deepcopy(batch),'knowledge_cutoff':cutoff,
                            'requires_explicit_preparation_request':True,'period_required':True,'output_period':None})
                    refs,projection_issues=_linked_materializations(store,feature)
                    local_issues.extend(dict(issue,instrument_id=symbol) for issue in projection_issues)
                    if not refs and binding['source_view']!=snapshot['body']['definition']:
                        local_issues.append(_issue('STALE_SOURCE_VIEW','The existing bound recipe uses a different SourceView than the current price registry.',symbol))
                    for materialization in refs:
                        marker=(materialization['id'],materialization['content_sha256'])
                        if marker in seen:continue
                        seen.add(marker)
                        try:
                            # Research projections are independent from immutable output
                            # verification; adding a result must not hide stored coverage.
                            item=read_materialization(root,materialization['id'])
                            output=_usable_output(item,materialization,recipe,feature,symbol,snapshot,batch,cutoff)
                            member['materializations'].append(output)
                        except Exception as error:
                            code=error.code if isinstance(error,IncompatibleCoverage) else 'UNAVAILABLE_MATERIALIZATION'
                            message=str(error) if isinstance(error,IncompatibleCoverage) else 'A linked stored output could not be independently verified.'
                            unavailable={'reference':deepcopy(materialization),'code':code,'reason':message}
                            member['unavailable_materializations'].append(unavailable)
                            local_issues.append(_issue(code,message,symbol,materialization))
                except Exception as error:
                    code=error.code if isinstance(error,IncompatibleCoverage) else 'UNAVAILABLE_LEGACY_BINDING'
                    message=str(error) if isinstance(error,IncompatibleCoverage) else 'An existing source-bound Feature registration could not be verified.'
                    local_issues.append(_issue(code,message,symbol))
        if member['materializations']:
            member['state']='materialized';member['reason']='Verified stored output exists only for the listed periods.'
            member['reason_code']='STORED_BOUNDED_COVERAGE'
            member['readiness']=deepcopy(member['materializations'][0]['readiness_capabilities'])
        elif local_issues:
            member['state']='blocked';member['reason']=local_issues[0]['message'];member['reason_code']=local_issues[0]['code']
            member['readiness']=_not_ready(member['reason'])
        member['materializations'].sort(key=lambda item:item['reference']['id'])
        if len(member['preparation_bindings'])==1:
            member['preparation_binding']=deepcopy(member['preparation_bindings'][0])
            member['preparation_binding_reason']=None
        else:
            member['preparation_binding']=None
            member['preparation_binding_reason']=('No verified existing source-bound definition matches the current price SourceView.'
                if not member['preparation_bindings'] else 'Multiple existing preparation bindings require an explicit immutable selection.')
        response['members'].append(member);response['issues'].extend(local_issues)
    return _finish(response)
