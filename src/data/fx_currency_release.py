"""Explicit staging of a complete currency release; activation belongs to migration."""
import logging
from copy import deepcopy
from pathlib import Path
from data.feature_store import FeatureStore
from data.fx_currency_catalog import publish_prices, resolve_prices, add, active_release
from data.fx_currency_features import register as register_features
from data.fx_currency_scopes import register as register_scopes
from data.targets.fx import materialize, read_materialization
from data.transformations.identity import reference
from research.contracts import load_profile as legacy_profile, profile_blockers, ref, canonical, digest
from research.store import read_json, inside, install_bytes


def load_profile(root):
    release=active_release(root)
    if release is None:raise ValueError('Currency release is not active')
    return profile_for(root,release)


def profile_for(root,release):
    binding=release['body']['research_spec']
    from research.contracts import exact_selection
    exact_selection({k:binding[k] for k in ('id','version')})
    path=inside(root,f"definitions/research_specs/{binding['id']}/{binding['version']}.json")
    profile=read_json(path)
    if ref(profile)!=binding or path.read_bytes()!=canonical(profile)+b'\n' or profile_blockers(profile):
        raise ValueError('Currency Research Spec differs or is not approved')
    return profile


def stage(root, sources, return_policy, request_text):
    original=legacy_profile(root)
    if profile_blockers(original):raise ValueError('An approved existing Research Spec is required')
    cutoff=original['target_selection']['knowledge_cutoff']
    config=read_json(Path(root)/'config/fx_retrospective_completion.json')
    if config['knowledge_cutoff']!=cutoff or config['return_policy']!=return_policy:
        raise ValueError('Return policy and cutoff must match the approved completion configuration')
    if return_policy['horizons']!=[1,7,21,63,252] or return_policy['representation']!='simple':
        raise ValueError('The five scheduled-weekday simple-return horizons are required')
    prices=publish_prices(root,sources,return_policy,request_text)
    _,instruments=resolve_prices(root,reference(prices),verify_rows=True)
    scopes=register_scopes(root,reference(prices))
    features=register_features(root,reference(prices))
    targets={}
    for symbol,item in sorted(instruments.items()):
        outputs=materialize(root,item['price_snapshot'],return_policy,knowledge_cutoff=cutoff)
        targets[symbol]={str(h):o['materialization'] for h,o in zip(return_policy['horizons'],outputs)}
    profile=deepcopy(original)
    profile.update(id='RESEARCH_SPEC_FX_CURRENCY_QUOTES',version='1.0.0')
    profile['target_selection']={'knowledge_cutoff':cutoff,'selection_scope':'currency_price_catalog',
        'price_catalog':reference(prices),'source_snapshots':{s:r['price_snapshot'] for s,r in sorted(instruments.items())},
        'materializations':targets}
    install_bytes(inside(root,f"definitions/research_specs/{profile['id']}/{profile['version']}.json"),canonical(profile)+b'\n')
    release=add(FeatureStore(root),'onboarding_evidence',{'kind':'fx_currency_release','version':'1.0.0',
        'price_catalog':reference(prices),'feature_catalog':reference(features),'scopes':scopes,
        'research_spec':ref(profile),'approval':prices['body']['approval']})
    validate_release(root,release)
    return release


def validate_release(root,release, *, numerical=True):
    if type(numerical) is not bool:raise ValueError('Numerical validation mode must be explicit')
    store=FeatureStore(root)
    if store.resolve(reference(release))!=release or release['body'].get('kind')!='fx_currency_release':
        raise ValueError('Invalid currency release')
    logging.getLogger(__name__).info('Currency validation: %s prices started','numerical' if numerical else 'metadata')
    catalog,instruments=resolve_prices(root,release['body']['price_catalog'],verify_rows=numerical)
    logging.getLogger(__name__).info('Currency validation: prices passed')
    profile=profile_for(root,release);selection=profile['target_selection']
    if (selection.get('selection_scope')!='currency_price_catalog' or selection['price_catalog']!=reference(catalog)
            or selection['source_snapshots']!={s:r['price_snapshot'] for s,r in instruments.items()}
            or set(selection['materializations'])!=set(instruments)):
        raise ValueError('Currency Research Spec must pin all 126 oriented sources and Targets')
    from data.scopes import resolve_scope
    from data.transformations.fx_currency import SCOPE_IDS
    if {r['id'] for r in release['body']['scopes']}!=set(SCOPE_IDS) or len(release['body']['scopes'])!=7:
        raise ValueError('Release requires exactly seven currency Scopes')
    for binding in release['body']['scopes']:
        scope=resolve_scope(root,binding['id'],binding['version'])
        if scope['reference']!=binding or scope['price_catalog']!=reference(catalog):raise ValueError('Release Scope differs')
    features=store.resolve(release['body']['feature_catalog'])['body']
    if features.get('kind')!='fx_currency_feature_catalog' or features['price_catalog']!=reference(catalog):
        raise ValueError('Release Feature catalog differs')
    from data.fx_currency_features import get_policy
    from data.fx_feature_recipes import configurations,build_fx_feature,configuration_profile
    from data.reusable_features import _definition
    from data.reusable_feature_contracts import make_record,RECIPE_KIND,CURRENCY_INPUT_CONTRACT
    from data.transformations.registry import Registry
    registry=Registry(root);policy=get_policy(root);variants={v['id']:v for v in configurations(registry,configuration_profile(features))}
    if features['evaluation_policy']!=reference(policy) or len(features['recipes'])!=len(variants):
        raise ValueError('Release Feature family is incomplete')
    seen=set()
    from research.feature_applications import binding_for,CURRENCY_QUOTE
    for item in features['recipes']:
        config=item['configuration']
        if config!=variants.get(config['id']) or config['id'] in seen:raise ValueError('Invalid Feature configuration')
        seen.add(config['id']);expected=_definition(registry,policy,config)
        body=deepcopy(expected['body']);body['input_contract']=deepcopy(CURRENCY_INPUT_CONTRACT)
        expected=make_record(RECIPE_KIND,body,'Currency / quote: '+expected['display_name'])
        if store.resolve(item['recipe'])!=expected:raise ValueError('Currency reusable recipe differs')
        _,application=binding_for(root,expected)
        if application['kind']!=CURRENCY_QUOTE:raise ValueError('Currency application differs')
    seen=set()
    for position,binding in enumerate(features['bindings'],1):
        if position%1000==0:logging.getLogger(__name__).info('Currency validation: Feature %s/%s',position,len(features['bindings']))
        key=(binding['configuration_id'],binding['instrument_id'])
        if key in seen:raise ValueError('Duplicate currency binding')
        seen.add(key)
        instrument=instruments[key[1]]
        expected=build_fx_feature(root,instrument,variants[key[0]],registry=registry,evaluation_policy=policy,store=store)
        if (store.resolve(binding['feature'])!=expected or binding['price_snapshot']!=instrument['price_snapshot']
                or binding['source_view']!=expected['body']['recipe']['sources'][0]['source_view']):
            raise ValueError('Currency source-bound Feature differs')
    if seen!={(v,s) for v in variants for s in instruments}:raise ValueError('Incomplete currency bindings')
    from data.targets.store import TargetStore
    target_store=TargetStore(root) if not numerical else None
    target_count=0
    target_log='Currency validation' if numerical else 'Currency metadata'
    for symbol,pins in selection['materializations'].items():
        if set(pins)!={'1','7','21','63','252'}:raise ValueError('Missing Target horizon')
        for horizon,binding in pins.items():
            target_count+=1
            logging.getLogger(__name__).info('%s: Target %s/630 started',target_log,target_count)
            if numerical:
                result=read_materialization(root,binding['id'])
            else:
                from data.targets.fx import _definition
                manifest=target_store.resolve(binding);definition=target_store.resolve(manifest['definition'])
                snapshot=target_store.resolve(instruments[symbol]['price_snapshot'])
                schedule_policy=target_store.resolve(definition['body']['schedule_policy'])
                expected=_definition(target_store,snapshot,catalog['body']['return_policy'],int(horizon),schedule_policy,install=False)
                if reference(expected)!=manifest['definition']:raise ValueError('Currency Target metadata semantics differ')
                result={'manifest':manifest,'definition':definition}
            manifest=result['manifest']
            if (reference(manifest)!=binding or manifest['price_snapshot']!=instruments[symbol]['price_snapshot']
                    or manifest['input_key']['batch_policy']!=catalog['body']['return_policy']
                    or manifest['input_key']['knowledge_cutoff']!=selection['knowledge_cutoff']
                    or result['definition']['body']['horizon']['amount']!=int(horizon)):
                raise ValueError('Currency Target semantics differ')
            logging.getLogger(__name__).info('%s: Target %s/630 passed',target_log,target_count)
    return release


def build_momentum_catalogs(root, release):
    """Build the fixed momentum reset records using existing inputs, read-only.

    No observations are recomputed, no records are installed, and no existing
    record changes identity. Callers must validate the installed metadata and
    separately switch active registration/release pointers during their reset.
    """
    from data.reusable_features import build_momentum_registration
    from data.fx_currency_features import build_momentum_catalog
    from data.fx_records import make_record
    store=FeatureStore(root)
    if set(release)=={'id','version','content_sha256'}:release=store.resolve(release)
    if store.resolve(reference(release))!=release or release['body'].get('kind')!='fx_currency_release':
        raise ValueError('Expected exact existing currency release')
    ts=build_momentum_registration(root)
    catalog=build_momentum_catalog(root,release['body']['feature_catalog'])
    body=deepcopy(release['body']);body['feature_catalog']=reference(catalog)
    new_release=make_record('onboarding_evidence',body)
    return {'records':[*ts['records'],catalog,new_release],'release':new_release,
        'registration':ts['registration'],'feature_catalog':reference(catalog),
        'ts_recipes':ts['recipes'],'cs_recipes':[r['recipe'] for r in catalog['body']['recipes']],
        'features':ts['features']+[b['feature'] for b in catalog['body']['bindings']]}
