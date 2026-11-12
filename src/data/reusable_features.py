"""Instrument-independent FX recipe identities over unchanged legacy bindings.

Registration writes definitions and an immutable mapping completion only. It
never computes observations, creates source-specific Features, or changes a
historical Feature, Signal, materialization, or experiment identity.
"""
from collections import Counter
from data.catalog_reads import catalog_glob, memo
from copy import deepcopy
import re

from data.alfred_onboarding import stable_read, strict_json
from data.feature_store import FeatureStore, PublicationError, record_path
from data.fx_feature_recipes import (_catalog_bindings, configurations, get_fx_policy,
    LOG_FIRST, LOG_BASIS, CATALOG_KIND, FULL_CONFIGURATION_PROFILE,
    MOMENTUM_CONFIGURATION_PROFILE, MOMENTUM_CATALOG_PROFILE, VOLATILITY_CONFIGURATION_PROFILE,
    VOLATILITY_CATALOG_PROFILE, PAIR_CATALOG_PROFILES, CONFIGURATION_COUNTS, configuration_profile,
    build_fx_feature)
from data.fx_pipeline import _universe
from data.targets.fx import _price_snapshot
from data.transformations.registry import Registry
from data.transformations.engine import _metadata, _parameters
from data.transformations.contracts import normalize_reference
from data.transformations.identity import reference, make_feature_definition, normalize_recipe
from data.reusable_feature_contracts import (INPUT_CONTRACT, RECIPE_KIND, REGISTRATION_KIND,
    make_record, validate_record)

RECIPE_ID=re.compile(r'FEATURE_RECIPE_[0-9a-f]{64}\Z',re.ASCII)
REGISTRATION_ROOT='storage/catalog/feature_recipes'
REGISTRATION_BY_PROFILE = {
    FULL_CONFIGURATION_PROFILE: 'reusable_fx_feature_recipes.1.0.0',
    MOMENTUM_CONFIGURATION_PROFILE: 'reusable_fx_momentum_recipes.1.0.0',
    VOLATILITY_CONFIGURATION_PROFILE: 'reusable_fx_volatility_recipes.1.0.0',
}
PROFILE_BY_REGISTRATION = {name: profile for profile, name in REGISTRATION_BY_PROFILE.items()}


class ReusableRecipeNotFound(PublicationError):
    pass


def _context(root, profile=FULL_CONFIGURATION_PROFILE):
    registry=Registry(root);policy=get_fx_policy(root)
    variants=configurations(registry,profile)
    if len(variants)!=CONFIGURATION_COUNTS[profile]:raise PublicationError('Fixed FX configuration profile is incomplete')
    return registry,policy,{item['id']:item for item in variants}


def _definition(registry,policy,configuration):
    entry=registry.resolve(configuration['operator']);identifier=entry['id']
    if identifier not in LOG_FIRST+LOG_BASIS:raise PublicationError('Unsupported reusable FX operator')
    previous='source';unit=INPUT_CONTRACT['unit_binding'];semantics='price';steps=[]
    if identifier in LOG_FIRST:
        log=registry.operator('TR_BASE_level_log');contract=log['body']['execution_contract']
        steps.append({'node':'log_price','phase':'transformation','operator':reference(log),'inputs':['source'],
                      'parameters':[],'grid_policy':contract['grid_profile']})
        previous='log_price';unit,semantics=_metadata(unit,semantics,contract,{})
    step={'node':'fx_value','phase':'transformation','operator':reference(entry),'inputs':[previous],
          'parameters':deepcopy(configuration['parameters']),'grid_policy':configuration['grid_policy']}
    params=registry.validate_parameters(entry,_parameters(step,entry),'daily',step['grid_policy'])
    if identifier in LOG_BASIS and params.get('basis')!='log':raise PublicationError('Internal logarithmic basis required')
    unit,semantics=_metadata(unit,semantics,entry['body']['execution_contract'],params);steps.append(step)
    body={'kind':'reusable_fx_feature_recipe','input_contract':deepcopy(INPUT_CONTRACT),'steps':steps,
          'output_node':'fx_value','output_contract':{'unit_template':unit,'value_semantics':semantics},
          'history_mode':'resolved_state','history_policy':reference(registry.get_policy('POL_TRANSFORM_HISTORY')),
          'execution_policy':reference(registry.get_policy('POL_TRANSFORM_EXECUTION')),
          'evaluation_policy':reference(policy),'calculation_geometry':'independent_per_instrument'}
    label=', '.join(p['name']+'='+str(p['value']['value']) for p in step['parameters'])
    display=('Log -> ' if identifier in LOG_FIRST else '')+entry['display_name']+' ('+label+')'
    record=make_record(RECIPE_KIND,body,display);validate_record(record)
    return record


def _project_legacy(store,feature,registry,policy,expected):
    """Verify the old identity/source binding and project exact common semantics."""
    store._validate(feature);recipe=normalize_recipe(feature['body']['recipe'])
    if reference(make_feature_definition(recipe,feature['display_name']))!=reference(feature):raise PublicationError('Legacy Feature identity differs')
    view=store.resolve(recipe['sources'][0]['source_view']);dataset=store.resolve(view['body']['dataset'])
    if view['body'].get('kind')!='fx_constructed_view' or dataset['body'].get('kind')!='fx_constructed_dataset':
        raise PublicationError('Only canonical FX price bindings have reusable FX projections')
    meta=dataset['body']['source_metadata'];symbol=dataset['body']['instrument_id']
    from data.transformations.fx import instrument_spec
    specification=instrument_spec(symbol)
    if (view['body'].get('profile')!='fx_price.1.0.0' or dataset['body'].get('profile')!='fx_price.1.0.0'
            or any(meta.get(k)!=specification[k] for k in ('base_currency','quote_currency','unit'))
            or meta.get('price_field')!='close'):
        raise PublicationError('Legacy source does not satisfy the reusable FX price input contract')
    if view['body']['source_metadata']!=meta or recipe['selection']!={'measure':'close','entity_id':symbol,'dimensions':[]}:
        raise PublicationError('Legacy Feature source selection differs')
    if recipe['sources'][0]['alias']!='source' or recipe['calculation_scope_requirement']!='none' or recipe['scope_policy'] is not None:
        raise PublicationError('Legacy Feature has a different input or calculation scope')
    unit=INPUT_CONTRACT['unit_binding'];actual_unit=meta['unit'];semantics='price'
    for step in recipe['steps']:
        operator=registry.resolve(step['operator']);contract=operator['body']['execution_contract']
        params=registry.validate_parameters(operator,_parameters(step,operator),'daily',step.get('grid_policy'))
        actual_unit,_=_metadata(actual_unit,semantics,contract,params)
        unit,semantics=_metadata(unit,semantics,contract,params)
    if recipe['output_unit']!=actual_unit:raise PublicationError('Legacy output unit differs from its source and operators')
    body={'kind':'reusable_fx_feature_recipe','input_contract':deepcopy(INPUT_CONTRACT),'steps':recipe['steps'],
          'output_node':recipe['output_node'],'output_contract':{'unit_template':unit,'value_semantics':semantics},
          'history_mode':recipe['history_mode'],'history_policy':recipe['history_policy'],
          'execution_policy':recipe['execution_policy'],'evaluation_policy':recipe.get('evaluation_policy'),
          'calculation_geometry':'independent_per_instrument'}
    candidate=make_record(RECIPE_KIND,body)
    match=expected.get(candidate['id'])
    if match is None or reference(candidate)!=reference(match):raise PublicationError('Legacy recipe is outside the exact approved reusable FX configurations')
    return deepcopy(match)


def recipe_for_legacy_feature(root,feature):
    registry,policy,variants=_context(root)
    expected={record['id']:record for record in (_definition(registry,policy,v) for v in variants.values())}
    return _project_legacy(FeatureStore(root),feature,registry,policy,expected)


def legacy_recipe_projector(root,recipe):
    """Build one verified, per-request projector for independently read members."""
    validate_record(recipe)
    if recipe['body']['input_contract']['source_profile']=='fx_currency_price.1.0.0':
        from data.fx_currency_features import projector
        return projector(root,recipe)
    registry,policy,variants=_context(root)
    expected={record['id']:record for record in (_definition(registry,policy,v) for v in variants.values())}
    candidate=expected.get(recipe['id'])
    if candidate is None or reference(candidate)!=reference(recipe):raise PublicationError('Unapproved reusable Feature projection')
    store=FeatureStore(root)
    return lambda feature:_project_legacy(store,feature,registry,policy,{candidate['id']:candidate})


def _legacy_context(root):
    store,variants,bindings,catalogs=_catalog_bindings(root)
    registry,policy,approved=_context(root)
    if variants!=approved or len(bindings)!=7740 or len({b['instrument_id'] for b in bindings.values()})!=43:
        raise PublicationError('Existing FX registrations must contain180configurations and7740exactbindings')
    definitions={key:_definition(registry,policy,item) for key,item in approved.items()}
    return store,registry,policy,definitions,bindings,catalogs


def _registration(definitions,bindings,catalogs,profile=FULL_CONFIGURATION_PROFILE):
    counts=Counter(item['configuration_id'] for item in bindings.values())
    if set(counts)!=set(definitions) or set(counts.values())!={43}:raise PublicationError('Every reusable recipe requires43legacy source bindings')
    if profile not in REGISTRATION_BY_PROFILE:raise PublicationError('Unknown fixed FX configuration profile')
    body={'kind':'reusable_fx_feature_recipe_registration','profile':REGISTRATION_BY_PROFILE[profile],
          'legacy_catalogs':sorted(catalogs,key=lambda ref:ref['id']),
          'recipes':[{'configuration_id':key,'feature_recipe':reference(definitions[key]),'legacy_binding_count':counts[key]} for key in sorted(definitions)],
          'recipe_count':len(definitions),'legacy_binding_count':len(bindings),'instrument_count':43,'observation_action':'none'}
    result=make_record(REGISTRATION_KIND,body,'Reusable FX Feature recipes and preserved historical source bindings')
    validate_record(result);return result


def register_reusable_fx_recipes(root):
    store,registry,policy,definitions,bindings,catalogs=_legacy_context(root)
    expected={record['id']:record for record in definitions.values()}
    # Validate every historical binding before writing a completion. Use one
    # Registry/store for all7740 references; never rewrite their identities.
    for binding in bindings.values():
        feature=store.resolve(binding['feature'])
        if _project_legacy(store,feature,registry,policy,expected)!=definitions[binding['configuration_id']]:
            raise PublicationError('Legacy binding maps to a different reusable recipe')
        recipe=feature['body']['recipe']
        if recipe['selection']['entity_id']!=binding['instrument_id'] or recipe['sources'][0]['source_view']!=binding['source_view']:
            raise PublicationError('Legacy mapping source differs from its Feature')
    completion=_registration(definitions,bindings,catalogs);pending=[];reused=0
    for record in [*definitions.values(),completion]:
        path=store.path(record_path(record))
        if path.exists():
            old=strict_json(stable_read(path));store._validate(old)
            if reference(old)!=reference(record):raise PublicationError('Conflicting reusable recipe identity')
            if record['record_type']==RECIPE_KIND:reused+=1
        else:pending.append(record)
    with store.writer():
        for record in pending:store.install_record(record)
    return {'registration':reference(completion),'recipe_count':180,'added_recipes':180-reused,'reused_recipes':reused,
            'legacy_binding_count':7740,'instrument_count':43,'new_observations':0,'historical_records_rewritten':0}


def _pinned_read_context(root):
    """Resolve completed immutable mappings without consulting current run config.

    Current preparation config determines readiness, never whether an existing
    registered recipe exists. Completed catalog references remain authoritative
    even if a particular source file later becomes unavailable. Source metadata
    is checked by strict binding reads or independently by a Scope resolver.
    """
    store=FeatureStore(root)
    paths=sorted(catalog_glob(store.path(REGISTRATION_ROOT), '*/manifest.json'))
    if not paths:raise ReusableRecipeNotFound('Reusable FX recipes have not been registered')
    completions = []
    for candidate_path in paths:
        relative = candidate_path.relative_to(store.root).as_posix()
        completion = strict_json(stable_read(store.path(relative)))
        store._validate(completion)
        if completion['record_type'] != REGISTRATION_KIND or record_path(completion) != relative:
            raise PublicationError('Reusable registration path or kind differs')
        completions.append(completion)
    profiles = {PROFILE_BY_REGISTRATION[record['body']['profile']] for record in completions}
    if len(profiles) > 1 and profiles != {MOMENTUM_CONFIGURATION_PROFILE, VOLATILITY_CONFIGURATION_PROFILE}:
        raise PublicationError('Conflicting completed FX configuration profiles')
    registry, policy = Registry(root), get_fx_policy(root)
    variants_by_profile = {profile: {v['id']: v for v in configurations(registry, profile)}
                           for profile in sorted(profiles)}
    definitions_by_profile = {profile: {key: _definition(registry, policy, value) for key, value in variants.items()}
                              for profile, variants in variants_by_profile.items()}
    rules={item['name']:item['value']['value'] for item in policy['body']['parameters']}
    approval=rules.get('source_alignment_approval');retrospective=rules.get('source_retrospective_policy')
    if approval is None or retrospective is None:raise PublicationError('Stored recipe policy lacks pinned source approval references')
    store.resolve(approval)
    retro=store.resolve(retrospective)
    if retro.get('body')!={'kind':'fx_retrospective_policy','approval':approval,
            'mode':'retrospective_date_label','historical_replay':False,'live_use':False,
            'unknown_availability':'preserve_null','source_selection':'pinned_original_capture'}:
        raise PublicationError('Stored recipe retrospective source policy differs')
    bindings={};sources={}
    for completion in completions:
        profile = PROFILE_BY_REGISTRATION[completion['body']['profile']]
        variants, definitions = variants_by_profile[profile], definitions_by_profile[profile]
        count, binding_count = len(variants), len(variants) * 43
        local_bindings={};local_catalogs=completion['body']['legacy_catalogs']
        for catalog_ref in local_catalogs:
            catalog=store.resolve(catalog_ref);body=catalog['body']
            if (catalog['record_type']!='onboarding_evidence' or body.get('kind')!=CATALOG_KIND
                    or body.get('profile') not in PAIR_CATALOG_PROFILES or configuration_profile(body)!=profile or body.get('evaluation_policy')!=reference(policy)):
                raise PublicationError('Pinned legacy recipe catalog differs from the reusable policy')
            actual={item['id']:item for item in body['configurations']}
            if actual!=variants or len(actual)!=len(body['configurations']) or body['configuration_count']!=count:
                raise PublicationError('Pinned recipe configurations differ from the approved grid')
            keys=set();symbols=set()
            for binding in body['bindings']:
                if set(binding)!={'configuration_id','instrument_id','feature','price_snapshot','source_view'}:
                    raise PublicationError('Invalid pinned legacy binding fields')
                key=(binding['configuration_id'],binding['instrument_id'])
                if key in keys or binding['configuration_id'] not in definitions:
                    raise PublicationError('Duplicate or unknown pinned recipe binding')
                keys.add(key);symbols.add(binding['instrument_id'])
                for name,prefix in (('feature','FEATURE_'),('price_snapshot','SNAPSHOT_'),('source_view','SOURCE_VIEW_')):
                    ref=normalize_reference(binding[name])
                    if ref!=binding[name] or ref['version']!='1.0.0' or not re.fullmatch(prefix+r'[0-9a-f]{64}',ref['id']):
                        raise PublicationError('Invalid pinned legacy binding reference')
                source=(binding['price_snapshot'],binding['source_view'])
                if sources.setdefault(binding['instrument_id'],source)!=source:
                    raise PublicationError('Pinned instrument has conflicting source references')
                previous=local_bindings.setdefault(binding['feature']['id'],binding)
                if previous!=binding:raise PublicationError('Conflicting pinned legacy Feature binding')
            if (symbols!=set(_universe()) or body['instrument_count']!=43 or body['binding_count']!=binding_count
                    or keys!={(identifier,symbol) for identifier in definitions for symbol in symbols}):
                raise PublicationError('Pinned legacy catalog must cover its fixed grid across 43 instruments')
        expected=_registration(definitions,local_bindings,local_catalogs,profile)
        if reference(completion)!=reference(expected):raise PublicationError('Reusable mapping completion differs from its pinned legacy catalogs')
        for identifier,binding in local_bindings.items():
            if bindings.setdefault(identifier,binding)!=binding:raise PublicationError('Conflicting reusable completion bindings')
    definitions = {key: value for group in definitions_by_profile.values() for key, value in group.items()}
    if len(definitions) != sum(map(len, definitions_by_profile.values())) or len(bindings) != len(definitions) * 43:
        raise PublicationError('Reusable mapping has an unexpected historical binding count')
    return store,registry,policy,definitions,bindings


def _registered(root):
    return memo(root, 'registered_reusable_recipes', lambda: _read_registered(root))


def _read_registered(root):
    store,registry,policy,definitions,bindings=_pinned_read_context(root)
    records={}
    for definition in definitions.values():
        stored=store.resolve(reference(definition))
        if stored['body']!=definition['body']:raise PublicationError('Reusable recipe contract differs from its approved operators')
        records[stored['id']]=stored
    return store,registry,policy,records,definitions,bindings


def list_reusable_fx_recipes(root):
    try:_,_,_,records,_,_=_registered(root)
    except ReusableRecipeNotFound:records={}
    from data.fx_currency_catalog import active_release
    if active_release(root):
        from data.fx_currency_features import records as currency_records
        records={**records,**currency_records(root)}
    return sorted(records.values(),key=lambda record:(record['display_name'],record['id']))


def load_reusable_recipe(root,identifier,version='1.0.0'):
    if not isinstance(identifier,str) or not RECIPE_ID.fullmatch(identifier) or version!='1.0.0':
        raise ReusableRecipeNotFound('Unknown reusable Feature recipe')
    from data.fx_currency_catalog import active_release
    if active_release(root):
        from data.fx_currency_features import records as currency_records
        record=currency_records(root).get(identifier)
        if record is not None:return deepcopy(record)
    _,_,_,records,_,_=_registered(root)
    if identifier not in records:raise ReusableRecipeNotFound('Unknown reusable Feature recipe')
    return deepcopy(records[identifier])


def legacy_bindings_for_recipe(root,recipe_ref,*,verify_features=True):
    """Return exact completed bindings; optionally defer per-member file checks.

    The default verifies each historical source snapshot and Feature projection.
    Resolvers may defer those file checks to report one unavailable member
    independently; catalog identities, exact reference structure and declared
    43-source coverage remain checked without opening individual source files.
    """
    from data.fx_currency_catalog import active_release
    if active_release(root):
        from data.fx_currency_features import records as currency_records, bindings as currency_bindings
        if recipe_ref.get('id') in currency_records(root):return currency_bindings(root,recipe_ref,verify_features)
    if type(verify_features) is not bool:raise PublicationError("verify_features must be boolean")
    store,registry,policy,records,definitions,bindings=_registered(root)
    record=records.get(recipe_ref.get('id')) if isinstance(recipe_ref,dict) else None
    if record is None or reference(record)!=recipe_ref:raise ReusableRecipeNotFound('Unknown exact reusable Feature recipe')
    configuration=next(key for key,value in definitions.items() if value['id']==record['id'])
    rules={item['name']:item['value']['value'] for item in policy['body']['parameters']}
    price_context={'approval_evidence':rules['source_alignment_approval']}
    result=[]
    for binding in bindings.values():
        if binding['configuration_id']!=configuration:continue
        if verify_features:
            snapshot,_=_price_snapshot(store,binding['price_snapshot'],price_context,verify_rows=False)
            if snapshot['body']['instrument_id']!=binding['instrument_id'] or snapshot['body']['definition']!=binding['source_view']:
                raise PublicationError('Pinned recipe source differs from its canonical price snapshot')
            feature=store.resolve(binding['feature'])
            if reference(_project_legacy(store,feature,registry,policy,records))!=recipe_ref:
                raise PublicationError('Historical Feature differs from its reusable recipe')
            if feature['body']['recipe']['selection']['entity_id']!=binding['instrument_id'] or feature['body']['recipe']['sources'][0]['source_view']!=binding['source_view']:
                raise PublicationError('Historical binding source differs')
        result.append(deepcopy(binding))
    if len(result)!=43:raise PublicationError('Reusable Feature must resolve43historical source bindings')
    return sorted(result,key=lambda item:item['instrument_id'])


def reusable_recipe_mapping_context(root):
    """Return completed mappings and a strict projector sharing one read context.

    Mapping construction reads the completed catalogs and canonical reusable
    definitions once. It does not load the 7,740 historical Feature files, price
    snapshots, or observations. The returned callable validates only a supplied
    Feature, including its exact pinned reference, canonical recipe semantics,
    instrument and source view. Output/availability verification remains the
    caller's responsibility; a mapping is not evidence of materialization.

    The public mapping is detached from the callable's verification state.
    Reusable record values are shared across its 43 instrument bindings and
    should be treated as read-only by consumers.
    """
    store,registry,policy,records,definitions,bindings=_registered(root)
    canonical={key:records[definition['id']] for key,definition in definitions.items()}
    public_records={key:deepcopy(record) for key,record in canonical.items()}
    mapping={identifier:{'feature':deepcopy(binding['feature']),
                         'recipe':public_records[binding['configuration_id']],
                         'instrument_id':binding['instrument_id'],
                         'source_view':deepcopy(binding['source_view']),
                         'price_snapshot':deepcopy(binding['price_snapshot'])}
             for identifier,binding in bindings.items()}

    def project_feature(feature):
        identifier=feature.get('id') if isinstance(feature,dict) else None
        binding=bindings.get(identifier)
        if binding is None:raise ReusableRecipeNotFound('Feature has no completed reusable recipe mapping')
        if reference(feature)!=binding['feature']:
            raise PublicationError('Feature differs from its exact completed legacy reference')
        expected=canonical[binding['configuration_id']]
        projected=_project_legacy(store,feature,registry,policy,{expected['id']:expected})
        recipe=feature['body']['recipe']
        if (recipe['selection']['entity_id']!=binding['instrument_id']
                or recipe['sources'][0]['source_view']!=binding['source_view']):
            raise PublicationError('Feature instrument or source differs from its completed binding')
        if reference(projected)!=reference(expected):
            raise PublicationError('Feature differs from its completed reusable recipe')
        return deepcopy(expected)

    return mapping,project_feature


def reusable_recipe_mapping(root):
    """Return read-only catalog projections keyed by historical Feature ID.

    Use ``reusable_recipe_mapping_context`` when included Feature records also
    need verification, so mapping and projection share a single registry/store.
    """
    mapping,_=reusable_recipe_mapping_context(root)
    return mapping


def build_momentum_registration(root):
    """Build a new exact 53-recipe catalog; do not install or delete any files.

    The caller switches registration roots as one controlled reset. Existing
    Feature and recipe identities are retained; only their catalog changes.
    """
    from data.fx_records import make_record as catalog_record
    store,registry,policy,_,all_definitions,all_bindings=_registered(root)
    variants={v['id']:v for v in configurations(registry,MOMENTUM_CONFIGURATION_PROFILE)}
    definitions={key:all_definitions[key] for key in variants}
    bindings={key:b for key,b in all_bindings.items() if b['configuration_id'] in variants}
    if len(bindings)!=53*43:raise PublicationError('Momentum registration lacks exact source bindings')
    expected={record['id']:record for record in definitions.values()}
    for binding in bindings.values():
        feature=store.resolve(binding['feature'])
        if _project_legacy(store,feature,registry,policy,expected)!=definitions[binding['configuration_id']]:
            raise PublicationError('Momentum source binding differs')
        recipe=feature['body']['recipe']
        if recipe['selection']['entity_id']!=binding['instrument_id'] or recipe['sources'][0]['source_view']!=binding['source_view']:
            raise PublicationError('Momentum source mapping differs from its Feature')
    catalog=catalog_record('onboarding_evidence',{'kind':CATALOG_KIND,'profile':MOMENTUM_CATALOG_PROFILE,
        'evaluation_policy':reference(policy),'configurations':list(variants.values()),
        'bindings':sorted(bindings.values(),key=lambda b:(b['configuration_id'],b['instrument_id'])),
        'configuration_count':53,'instrument_count':43,'binding_count':53*43,
        'materialization_state':'registered_only','research_state':'not_executed'},
        'Fixed momentum FX Feature configurations')
    registration=_registration(definitions,bindings,[reference(catalog)],MOMENTUM_CONFIGURATION_PROFILE)
    return {'records':[catalog,registration],'registration':reference(registration),
        'recipes':[reference(r) for r in definitions.values()],
        'features':[b['feature'] for b in bindings.values()]}


def build_volatility_registration(root):
    """Build volatility metadata using the same pinned pair sources as momentum."""
    from data.fx_records import make_record as catalog_record
    from research.contracts import load_profile

    store, registry, policy, _, _, current = _registered(root)
    source_pins = load_profile(root)['target_selection']['source_snapshots']
    sources = {}
    for binding in current.values():
        symbol = binding['instrument_id']
        sources[symbol] = (binding['price_snapshot'], binding['source_view'])
    if set(sources) != set(_universe()):
        raise PublicationError('Volatility registration requires the exact registered pair universe')

    variants = configurations(registry, VOLATILITY_CONFIGURATION_PROFILE)
    definitions = {item['id']: _definition(registry, policy, item) for item in variants}
    expected = {definition['id']: definition for definition in definitions.values()}
    features, bindings = [], {}
    for symbol, (source, source_view) in sorted(sources.items()):
        snapshot = store.resolve(source_pins[symbol])['body']
        if snapshot['instrument_id'] != symbol or snapshot['definition'] != source_view:
            raise PublicationError('Volatility source view differs from the pinned pair research input')
        instrument = {'instrument_id': symbol, 'price_snapshot': source}
        for item in variants:
            feature = build_fx_feature(root, instrument, item, registry=registry, evaluation_policy=policy, store=store)
            if _project_legacy(store, feature, registry, policy, expected) != definitions[item['id']]:
                raise PublicationError('Volatility pair Feature differs from its reusable recipe')
            features.append(feature)
            bindings[feature['id']] = {'configuration_id': item['id'], 'instrument_id': symbol,
                                       'feature': reference(feature), 'price_snapshot': source,
                                       'source_view': source_view}
    catalog = catalog_record('onboarding_evidence', {'kind': CATALOG_KIND, 'profile': VOLATILITY_CATALOG_PROFILE,
        'evaluation_policy': reference(policy), 'configurations': variants,
        'bindings': sorted(bindings.values(), key=lambda row: (row['configuration_id'], row['instrument_id'])),
        'configuration_count': len(variants), 'instrument_count': len(sources), 'binding_count': len(bindings),
        'materialization_state': 'registered_only', 'research_state': 'not_executed'},
        'Fixed volatility FX Feature configurations')
    registration = _registration(definitions, bindings, [reference(catalog)], VOLATILITY_CONFIGURATION_PROFILE)
    return {'features': features, 'recipes': list(definitions.values()),
            'catalog': catalog, 'registration': registration}
