"""Read-only reusable recipe presentation over the existing stored library.

No definitions, observations or scientific records are written. Only Features
with verified research outcomes are included. List reads verify catalog metadata only;
observation verification occurs when an output is opened. Research links retain their
original relationship and result references; they never certify a whole recipe.
"""
from copy import deepcopy
from pathlib import Path
from jsonschema.exceptions import ValidationError
from data.catalog_reads import catalog_glob

from api.signal_library import (ENTRIES, SIGNAL_ID, MATERIALIZATION_ID,
    SignalNotFound, _summary, _coverage, _detail)
from data.alfred_onboarding import stable_read, strict_json
from data.feature_store import FeatureStore, PublicationError, read_materialization
from data.feature_store_contracts import normalize_library_entry
from data.reusable_features import reusable_recipe_mapping_context
from data.transformations.identity import canonical_bytes, digest, reference
from api.research_labels import recipe_label

OUTPUT_PREFIX='/api/signal-library-outputs/'


def _load_outputs(root, identifier, materialization_id=None):
    """Verify observation bindings without interpreting linked research results.

    The scientific Signal reader intentionally rejects research-linked entries
    until a research reader exists. This presentation adapter independently uses
    the existing strict materialization reader and preserves research references
    as references, never as verified metrics or an inferred validation decision.
    """
    if not isinstance(identifier,str) or not SIGNAL_ID.fullmatch(identifier):
        raise SignalNotFound('Unknown Signal')
    store=FeatureStore(root);folder=store.path(ENTRIES+'/'+identifier)
    if not folder.is_dir():raise SignalNotFound('Unknown Signal')
    entries=[];bindings={};feature=None
    for candidate in sorted(folder.glob('*.json')):
        path=store.path(str(candidate.relative_to(store.root)))
        entry=normalize_library_entry(strict_json(stable_read(path)))
        if entry['signal_id']!=identifier or path.name!=digest(entry)+'.json':
            raise PublicationError('Signal projection identity mismatch')
        if feature is not None and entry['feature']!=feature:
            raise PublicationError('Conflicting exact Feature references')
        feature=entry['feature'];entries.append(entry)
        for binding in entry['feature_materializations']:
            if bindings.setdefault(binding['id'],binding)!=binding:
                raise PublicationError('Conflicting exact materialization references')
    if not entries:raise SignalNotFound('Unknown Signal')
    if not bindings:raise PublicationError('Signal has no completed stored output')
    state='results_linked' if any(e['relationship_results'] for e in entries) else 'untested'
    loaded=[]
    if materialization_id is not None and materialization_id not in bindings:raise SignalNotFound("Materialization is not linked to this Signal")
    for identifier_mid,binding in sorted(bindings.items()):
        if materialization_id is not None and identifier_mid != materialization_id:continue
        item=read_materialization(store.root,identifier_mid)
        if (reference(item['manifest'])!=binding or reference(item['feature'])!=feature
                or item['feature']['body']['signal_id']!=identifier):
            raise PublicationError('Signal/Feature/materialization reference mismatch')
        loaded.append(dict(item,signal_id=identifier,materialization_state='materialized',
            scientific_state=state,library_entries=entries))
    loaded.sort(key=lambda item:(_coverage(item['observations'])['cutoff_end'] or '',item['manifest']['id']),reverse=True)
    return store,loaded


def _research(entries):
    """Keep authoritative links and their historical context, without averaging."""
    links=[];seen=set();relationships=set()
    for entry in entries:
        projection=reference(entry)
        for group in entry['relationship_results']:
            key=(entry['signal_id'],canonical_bytes(projection),canonical_bytes(group))
            if key in seen:continue
            seen.add(key)
            relationships.add((entry['signal_id'],canonical_bytes(group['relationship'])))
            links.append(dict(deepcopy(group),signal_id=entry['signal_id'],projection=projection))
    links.sort(key=lambda row:(row['signal_id'],row['relationship']['id'],row['projection']['id']))
    return {'state':'results_linked' if links else 'untested',
        'label':'Research results linked' if links else 'Untested',
        'relationship_count':len(relationships),'relationships':links,'metrics':[],
        'description':('Research links are preserved under each original relationship. Scope, Target, horizon, direction, '
            'Research Spec and evaluation period belong to the authoritative relationship/trial records. '
            'Linked outcomes are not aggregated or interpreted as recipe-wide validation. '
            'An authoritative research reader is required to verify and display their metrics.' if links else
            'No target/horizon relationship has been tested. Preparing observations is not research.')}


def _recipe_presentation(store, recipe):
    contract=recipe['body']['input_contract']
    if contract.get('measure')!='close' or contract.get('value_semantics')!='price':
        raise PublicationError('Unsupported reusable input display contract')
    transformations=[]
    for step in recipe['body']['steps']:
        operator=store.resolve(step['operator'])
        # A readable caption only: the canonical operator/version stays intact.
        label=('Skip Recent Difference' if operator['id']=='TR_BASE_momentum_skip_diff'
               else operator['display_name'])
        transformations.append({'node':step['node'],'operator':deepcopy(step['operator']),
            'label':label,'parameters':deepcopy(step['parameters'])})
    return {'kind':'reusable_fx_recipe','id':recipe['id'],'recipe':reference(recipe),'name':recipe_label(recipe),
        'source':{'label':'Closing prices','input_contract':deepcopy(contract)},
        'transformations':transformations,'observation_count':None,'outputs':[]}


def _output_summary(store,loaded):
    output=_metadata_summary(store,loaded) if loaded[0].get('metadata_only') else _summary(store,loaded)
    output['detail_href']=OUTPUT_PREFIX+output['signal_id']
    output['research']=_research(loaded[0]['library_entries'])
    output['materializations']=[{
        'id':item['manifest']['id'],'reference':reference(item['manifest']),
        'row_count':item['manifest']['row_count'],'status_counts':deepcopy(item['manifest']['status_counts']),
        'coverage':item['catalog_coverage'] if item.get('metadata_only') else _coverage(item['observations']),
        'readiness_capabilities':deepcopy(item['manifest'].get('readiness_capabilities',{})),
        'href':output['detail_href']+'?materialization_id='+item['manifest']['id']}
        for item in loaded]
    return output


def _load_output_metadata(root, identifier, *, store=None):
    """Validate exact catalog references without opening observation payloads."""
    store=store or FeatureStore(root);entries=[];bindings={};feature_ref=None
    for path in sorted(catalog_glob(store.path(ENTRIES+'/'+identifier), '*.json')):
        entry=normalize_library_entry(strict_json(stable_read(path)))
        if entry['signal_id']!=identifier or path.name!=digest(entry)+'.json':
            raise PublicationError('Signal projection identity mismatch')
        if feature_ref is not None and feature_ref!=entry['feature']:
            raise PublicationError('Conflicting Feature references')
        feature_ref=entry['feature'];entries.append(entry)
        for binding in entry['feature_materializations']:
            if bindings.setdefault(binding['id'],binding)!=binding:raise PublicationError('Conflicting output references')
    if not bindings:raise SignalNotFound('No stored output metadata')
    feature=store.resolve(feature_ref)
    if feature['body']['signal_id']!=identifier:raise PublicationError('Signal identity mismatch')
    loaded=[]
    for binding in bindings.values():
        manifest=store.resolve(binding)
        if manifest['definition']!=feature_ref:raise PublicationError('Output belongs to another Feature')
        metadata={key:store.resolve(manifest['metadata'][key]) for key in ('dataset','source_view')}
        key=manifest['input_key'];index=key.get('output_index',[])
        refs=[r['reference_time'] for r in index if r.get('reference_time')]
        cutoffs=[r['evaluation_cutoff'] for r in index if r.get('evaluation_cutoff')]
        period=key.get('period',{});cutoff=key.get('knowledge_cutoff')
        coverage={'reference_start':min(refs) if refs else period.get('start_inclusive'),
            'reference_end':max(refs) if refs else period.get('end_inclusive'),
            'cutoff_start':min(cutoffs) if cutoffs else cutoff,'cutoff_end':max(cutoffs) if cutoffs else cutoff}
        loaded.append({'feature':feature,'manifest':manifest,'metadata':metadata,'signal_id':identifier,
            'library_entries':entries,'catalog_coverage':coverage,'metadata_only':True})
    loaded.sort(key=lambda x:(x['catalog_coverage']['cutoff_end'] or '',x['manifest']['id']),reverse=True)
    return store,loaded


def _metadata_summary(store, loaded):
    from api.signal_library import _source
    item=loaded[0];feature=item['feature'];manifest=item['manifest']
    source,_=_source(store,item)
    transforms=[{'node':step['node'],'operator':step['operator'],
        'label':store.resolve(step['operator'])['display_name'],'parameters':step['parameters']}
        for step in feature['body']['recipe']['steps']]
    return {'signal_id':item['signal_id'],'name':feature['display_name'],'feature':reference(feature),
        'source':source,'transformations':transforms,'materialization_state':'materialized',
        'scientific_state':_research(item['library_entries'])['state'],'materialization_count':len(loaded),
        'default_materialization_id':manifest['id'],'row_count':manifest['row_count'],
        'status_counts':manifest['status_counts'],'coverage':item['catalog_coverage'],'latest_observation':None,
        'unit':manifest['metadata']['unit'],'value_semantics':manifest['metadata']['value_semantics'],
        'availability_semantics':manifest['metadata']['availability_semantics'],
        'readiness_capabilities':manifest.get('readiness_capabilities',{}),'verification_state':'catalog_metadata_only'}


def _registered_entry(store, feature):
    if feature['record_type']=='feature_recipe_definition':return _recipe_presentation(store,feature)
    recipe=feature['body']['recipe'];view=store.resolve(recipe['sources'][0]['source_view'])
    dataset=store.resolve(view['body']['dataset']);provider=store.resolve(dataset['body']['source_contract'])
    return {'kind':'registered_feature','id':feature['id'],'recipe':reference(feature),
        'signal_id':feature['body']['signal_id'],'name':feature['display_name'],
        'source':{'label':provider['body']['provider']+' · '+provider['body']['native_series_id'],
                  'input_contract':{'source_view':reference(view)}},
        'transformations':[{'node':step['node'],'operator':step['operator'],
            'label':store.resolve(step['operator'])['display_name'],'parameters':step['parameters']}
            for step in recipe['steps']], 'observation_count':None,'outputs':[]}


def _verified_branch(store, link):
    """Verify completed outcome metadata without opening numerical artifacts."""
    from research.contracts import ref, digest as research_digest
    from data.transformations.contracts import normalize_reference
    relation=store.resolve('relationship',link['body']['relationship']);body=relation['body']
    normalize_reference(body['recipe'])
    normalize_reference(body['scope'].get('reference',body['scope']))
    scope=body['scope'];scope_ref=scope.get('reference',scope)
    if any(scope.get(key,scope_ref[key])!=scope_ref[key] for key in ('id','version')):
        raise PublicationError('Frozen Scope identity differs from its reference')
    if 'membership_snapshot' in scope:normalize_reference(scope['membership_snapshot'])
    if body['mode'] not in ('TS','CS') or body['horizon'] not in (1,7,21,63,252):
        raise PublicationError('Unsupported research mode or horizon')
    trials=[store.resolve('trial',r) for r in link['body']['trial_results']]
    admissions=[store.resolve('admission',r) for r in link['body']['admission_results']]
    validations=[store.resolve('validation',r) for r in link['body']['validation_results']]
    by_ref={research_digest(ref(t)):t for t in trials}
    stages={t['body']['stage']:t for t in trials}
    if len(by_ref)!=len(trials) or set(stages) not in ({'P1'},{'P1','P2'}) or len(stages)!=len(trials):
        raise PublicationError('A completed research branch requires one discovery trial and at most one validation trial')
    for trial in trials:
        key=trial['scientific_key'];stage=trial['body']['stage']
        if key['relationship']!=ref(relation) or key['stage']!=stage:
            raise PublicationError('Trial relationship or stage differs')
        normalize_reference(key['research_spec'])
        if (key.get('horizon',body['horizon'])!=body['horizon']
                or trial['body'].get('horizon',body['horizon'])!=body['horizon']
                or trial['body'].get('mode',body['mode'])!=body['mode']):
            raise PublicationError('Trial mode or horizon differs')
        if trial['body'].get('execution_status','completed') not in ('completed','not_computable','discovery_direction_failed'):
            raise PublicationError('Trial execution has not completed')
    if len(admissions)!=1:
        raise PublicationError('Completed discovery requires one authoritative admission decision')
    admission=admissions[0]['body'];p1=stages['P1']
    if (admission['relationship']!=ref(relation) or admission['trial']!=ref(p1)
            or admission['decision'] not in ('admitted','rejected','unresolved')
            or p1['body'].get('admission',admission['decision'])!=admission['decision']):
        raise PublicationError('Admission does not match completed discovery')
    if len(validations)>1 or ('P2' in stages and not validations):
        raise PublicationError('Validation trial requires its authoritative decision')
    for validation in validations:
        value=validation['body'];evaluation=value['evaluation_trial']
        if (value['relationship']!=ref(relation) or value['discovery_trial']!=ref(p1)
                or admission['decision']!='admitted' or value['decision'] not in ('VALIDATED','FAILED','UNRESOLVED')):
            raise PublicationError('Validation does not match admitted discovery')
        if evaluation is None:
            if 'P2' in stages or value['decision']=='VALIDATED':
                raise PublicationError('Validation success requires a completed evaluation')
        else:
            p2=stages.get('P2')
            if (p2 is None or evaluation!=ref(p2) or p2['scientific_key']['discovery_trial']!=ref(p1)
                    or p2['scientific_key']['research_spec']!=p1['scientific_key']['research_spec']
                    or p2['body'].get('decision',value['decision'])!=value['decision']):
                raise PublicationError('Validation evaluation differs from its discovery branch')
    return relation,trials,admissions,validations


def _research_catalog(root, issues):
    """Read verified completed branches once, isolating unavailable records."""
    from research.store import ResearchStore, FOLDERS, inside
    from research.contracts import ref
    store=ResearchStore(root);result={};branches={}
    relative='storage/catalog/'+FOLDERS['link']
    inside(root,relative)  # Preserve confinement and watch the original path too.
    for path in sorted(catalog_glob(Path(root)/relative, 'RESEARCHLINK_*.json')):
        try:
            link=store.get('link',path.stem)
            relation,trials,admissions,validations=_verified_branch(store,link)
            body=relation['body'];recipe_id=body['recipe']['id']
            row={'signal_id':'SIGNAL_'+recipe_id.removeprefix('FEATURE_RECIPE_').removeprefix('FEATURE_'),
                'projection':ref(link),'relationship':ref(relation),'attempt_ids':[],
                'recipe':deepcopy(body['recipe']),
                **{key:deepcopy(link['body'][key]) for key in ('trial_results','admission_results','validation_results')},
                **{key:deepcopy(body[key]) for key in ('scope','mode','horizon','target_family','expected_direction')},
                'p1_status':admissions[0]['body']['decision'],
                'p2_status':validations[0]['body']['decision'] if validations else 'not_run'}
            branches.setdefault(canonical_bytes(ref(relation)),[]).append(row)
        except (ValueError,KeyError,TypeError,OSError):
            issues.append({'code':'UNAVAILABLE_RESEARCH_LINK','record_id':path.stem,
                'message':'A research result link or its trial/admission/validation references could not be verified.'})
    for rows in branches.values():
        def evidence(row):
            return {canonical_bytes(r) for key in ('trial_results','admission_results','validation_results') for r in row[key]}
        seen=set()
        for row in rows:
            key=frozenset(evidence(row))
            if key in seen or any(key<evidence(other) for other in rows):continue
            seen.add(key);result.setdefault(row['recipe']['id'],[]).append(row)
    return result


def _research_projection(rows):
    return {'state':'results_linked','label':'Research results recorded',
        'relationship_count':len({canonical_bytes(r['relationship']) for r in rows}),
        'trial_count':len({canonical_bytes(t) for r in rows for t in r['trial_results']}),
        'relationships':deepcopy(rows),'metrics':[],
        'description':'Recorded outcomes include rejected, failed and unresolved research. Each outcome belongs to its exact hypothesis and evaluation period.'}


def _recipe_projector(root):
    """Dispatch output mapping by its pinned currency or canonical input profile."""
    legacy=None;currency=None;projectors={}
    def project(feature):
        nonlocal legacy,currency
        policy=feature['body']['recipe'].get('evaluation_policy',{}).get('id')
        if policy!='POL_TRANSFORM_EVALUATION_FX_CURRENCY_SNAPSHOT':
            if legacy is None:_,legacy=reusable_recipe_mapping_context(root)
            return legacy(feature)
        from data.fx_currency_features import context, records, projector
        if currency is None:
            _,catalog,_=context(root);approved=records(root)
            by_config={r['configuration']['id']:approved[r['recipe']['id']] for r in catalog['body']['recipes']}
            currency={b['feature']['id']:(b,by_config[b['configuration_id']]) for b in catalog['body']['bindings']}
        match=currency.get(feature['id'])
        if match is None or match[0]['feature']!=reference(feature):
            raise PublicationError('Feature has no exact completed currency mapping')
        recipe=match[1]
        if recipe['id'] not in projectors:projectors[recipe['id']]=projector(root,recipe)
        return projectors[recipe['id']](feature)
    return project


def list_signal_summaries(root):
    store=FeatureStore(root);folder=store.path(ENTRIES);groups={};legacy=[];issues=[]
    research_catalog=_research_catalog(root,issues)
    for identifier,rows in research_catalog.items():
        try:
            refs={canonical_bytes(row['recipe']) for row in rows}
            if len(refs)!=1:raise PublicationError('Conflicting exact researched Feature references')
            feature=store.resolve(rows[0]['recipe']);entry=_registered_entry(store,feature)
            groups[identifier]=dict(entry,research=_research_projection(rows))
        except (ValueError,KeyError,TypeError,OSError,ValidationError):
            issues.append({'code':'UNAVAILABLE_RESEARCHED_FEATURE','record_id':identifier,
                'message':'The exact Feature definition referenced by research could not be verified.'})
    project_feature=_recipe_projector(root)
    for path in sorted(catalog_glob(folder, '*')):
        if path.name.startswith('.'):continue
        sid=path.name if SIGNAL_ID.fullmatch(path.name) else None
        try:
            if sid is None or not path.is_dir():raise SignalNotFound('Unknown Signal')
            loaded_store,loaded=_load_output_metadata(root,sid,store=store)
            if loaded[0]['metadata']['dataset']['body'].get('kind')!='fx_constructed_dataset':
                # Existing non-FX summary fields and presentation are unchanged.
                summary=_metadata_summary(loaded_store,loaded)
                feature_id=loaded[0]['feature']['id']
                group=groups.get(feature_id)
                if group is None:continue
                if group['recipe']!=summary['feature']:raise PublicationError('Research Feature differs from output')
                summary['scientific_state']='results_linked'
                groups.pop(feature_id)
                legacy.append({'kind':'stored_signal','id':sid,'signal':summary,'research':group['research']})
                continue
            recipe=project_feature(loaded[0]['feature'])
            if recipe['id'] not in groups:continue
            proposed=_recipe_presentation(loaded_store,recipe)
            output=_output_summary(loaded_store,loaded)
            group=groups[recipe['id']]
            if group['recipe']!=proposed['recipe']:raise PublicationError('Conflicting exact reusable recipe')
            group['outputs'].append(output)
        except Exception:
            issues.append({'code':'UNAVAILABLE_SIGNAL','signal_id':sid,
                'message':'A stored Signal or its reusable recipe mapping could not be verified and was excluded.'})
    entries=[]
    for group in groups.values():
        group['outputs'].sort(key=lambda output:(output['source']['series_id'],output['signal_id']))
        group['signal_id']=group.get('signal_id','SIGNAL_'+group['id'].removeprefix('FEATURE_RECIPE_'))
        group['details_deferred']=True
        entries.append(group)
    entries.extend(legacy)
    entries.sort(key=lambda entry:((entry['name'] if entry['kind']!='stored_signal' else entry['signal']['name']).casefold(),entry['id']))
    return {'schema_version':'1.0.0','entry_count':len(entries),'entries':entries,'issues':issues}


def get_signal_output_detail(root,identifier,materialization_id=None):
    if materialization_id is not None and (not isinstance(materialization_id,str) or not MATERIALIZATION_ID.fullmatch(materialization_id)):
        raise SignalNotFound('Unknown materialization')
    meta_store,metadata=_load_output_metadata(root,identifier)
    selected_id=materialization_id or metadata[0]['manifest']['id']
    store,loaded=_load_outputs(root,identifier,selected_id)
    from api.signal_library import _authoritative_research
    result=_detail(store,loaded,identifier,selected_id,
        research=_authoritative_research(root,loaded[0]['feature']['id']) or _research(loaded[0]['library_entries']),output_prefix=OUTPUT_PREFIX)
    result['materializations']=[{'id':x['manifest']['id'],'reference':reference(x['manifest']),
        'row_count':x['manifest']['row_count'],'status_counts':x['manifest']['status_counts'],
        'coverage':x['catalog_coverage'],'href':OUTPUT_PREFIX+identifier+'?materialization_id='+x['manifest']['id']} for x in metadata]
    result['signal']['materialization_count']=len(metadata)
    return result
