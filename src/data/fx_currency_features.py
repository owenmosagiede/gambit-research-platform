"""Approved currency-price recipes, separate from canonical instrument TS recipes."""
from copy import deepcopy
import hashlib
from data.alfred_onboarding import identified
from data.feature_store import FeatureStore
from data.fx_currency_catalog import add, resolve_prices, active_release
from data.fx_feature_recipes import (RULES, configurations, build_fx_feature, configuration_profile,
    MOMENTUM_CONFIGURATION_PROFILE)
from data.reusable_feature_contracts import CURRENCY_INPUT_CONTRACT, make_record, RECIPE_KIND
from data.reusable_features import _definition
from data.transformations.identity import canonical_bytes, reference
from data.transformations.registry import Registry

POLICY_ID = 'POL_TRANSFORM_EVALUATION_FX_CURRENCY_SNAPSHOT'


def get_policy(root):
    registry=Registry(root); policy=registry.get_policy(POLICY_ID,'2.0.0')
    registry.resolve_policy(reference(policy))
    rules={p['name']:p['value']['value'] for p in policy['body']['parameters']}
    if any(rules.get(k)!=v for k,v in RULES.items()):
        raise ValueError('Currency Feature evaluation rules differ')
    return policy


def register(root, price_catalog):
    store=FeatureStore(root); catalog,instruments=resolve_prices(root,price_catalog)
    batch=catalog['body']['return_policy']
    payload=canonical_bytes({'authority':catalog['body']['approval'],'price_catalog':price_catalog,
        'registration_scope':'all_126_oriented_exposures_all_180_approved_configurations',
        'orientation':'construct_price_before_entire_feature_chain','rules':RULES})+b'\n'
    evidence=identified('onboarding_evidence',{'kind':'transform_execution_policy',
        'payload':{'sha256':hashlib.sha256(payload).hexdigest(),'byte_count':len(payload),'row_count':None},
        'media_type':'application/json','description':'Explicit currency-reference Feature evaluation approval.'},'EVIDENCE_')
    store.io.blob(payload,'json','currency_feature_approval',None);store.install_record(evidence)
    parameters=[{'name':k,'unit':'policy_setting','value':{'kind':'token','value':v}} for k,v in sorted(RULES.items())]
    for name,value in [('source_retrospective_policy',batch['retrospective_policy']),('source_alignment_approval',batch['approval_evidence'])]:
        parameters.append({'name':name,'unit':'policy_reference','value':{'kind':'reference','value':value}})
    policy={'schema_version':'0.2.0','record_type':'policy_definition','id':POLICY_ID,'version':'2.0.0',
        'display_name':'Currency-reference snapshot Feature evaluation',
        'body':{'kind':'selection','specification':reference(evidence),'parameters':parameters,'approval_state':'approved','compatibility_evidence':[]}}
    store.install_record(policy);registry=Registry(root);variants=configurations(registry)
    if len(variants)!=180:raise ValueError('Expected 180 approved FX configurations')
    recipes=[];bindings=[]
    from research.feature_applications import install_binding, CURRENCY_QUOTE
    for config in variants:
        record=_definition(registry,policy,config)
        body=deepcopy(record['body']);body['input_contract']=deepcopy(CURRENCY_INPUT_CONTRACT)
        recipe=make_record(RECIPE_KIND,body,'Currency / quote: '+record['display_name'])
        store.install_record(recipe);install_binding(root,recipe,CURRENCY_QUOTE)
        recipes.append({'configuration':config,'recipe':reference(recipe)})
        for symbol,instrument in sorted(instruments.items()):
            feature=build_fx_feature(root,instrument,config,registry=registry,evaluation_policy=policy,store=store)
            store.install_record(feature)
            bindings.append({'configuration_id':config['id'],'instrument_id':symbol,'feature':reference(feature),
                'price_snapshot':instrument['price_snapshot'],'source_view':feature['body']['recipe']['sources'][0]['source_view']})
    return add(store,'onboarding_evidence',{'kind':'fx_currency_feature_catalog','price_catalog':price_catalog,
        'evaluation_policy':reference(policy),'recipes':recipes,'bindings':bindings})


def context(root):
    release=active_release(root)
    if release is None:raise ValueError('Currency release has not been activated')
    store=FeatureStore(root);catalog=store.resolve(release['body']['feature_catalog'])
    body=catalog['body']
    if body.get('kind')!='fx_currency_feature_catalog' or body['price_catalog']!=release['body']['price_catalog']:
        raise ValueError('Currency Feature catalog differs from release')
    policy=get_policy(root)
    if body['evaluation_policy']!=reference(policy):raise ValueError('Currency Feature policy differs')
    return store,catalog,policy


def records(root):
    from data.catalog_reads import memo
    return memo(root,'currency_reusable_recipes',lambda:_records(root))


def _records(root):
    store,catalog,policy=context(root);registry=Registry(root)
    variants={v['id']:v for v in configurations(registry,configuration_profile(catalog['body']))};result={}
    for item in catalog['body']['recipes']:
        config=item['configuration']
        if variants.pop(config['id'],None)!=config:raise ValueError('Unapproved or duplicate currency configuration')
        expected=_definition(registry,policy,config);body=deepcopy(expected['body'])
        body['input_contract']=deepcopy(CURRENCY_INPUT_CONTRACT)
        expected=make_record(RECIPE_KIND,body,'Currency / quote: '+expected['display_name'])
        actual=store.resolve(item['recipe'])
        if actual!=expected:raise ValueError('Currency recipe differs from approved configuration')
        result[actual['id']]=actual
    if variants:raise ValueError('Incomplete currency Feature family')
    return result


def bindings(root,recipe_ref,verify_features=True):
    store,catalog,policy=context(root)
    record=records(root).get(recipe_ref['id'])
    if record is None or reference(record)!=recipe_ref:raise ValueError('Unknown exact currency recipe')
    item=next(i for i in catalog['body']['recipes'] if i['recipe']==recipe_ref)
    _,instruments=resolve_prices(root,catalog['body']['price_catalog'])
    result=[b for b in catalog['body']['bindings'] if b['configuration_id']==item['configuration']['id']]
    if len(result)!=126 or {b['instrument_id'] for b in result}!=set(instruments):raise ValueError('Incomplete currency Feature bindings')
    registry=Registry(root)
    for b in result:
        instrument=instruments[b['instrument_id']]
        if b['price_snapshot']!=instrument['price_snapshot']:raise ValueError('Currency Feature price differs')
        snapshot=store.resolve(b['price_snapshot'])
        if b['source_view']!=snapshot['body']['definition']:raise ValueError('Currency Feature source differs')
        if verify_features:
            expected=build_fx_feature(root,instrument,item['configuration'],registry=registry,evaluation_policy=policy,store=store)
            if store.resolve(b['feature'])!=expected:raise ValueError('Currency Feature recipe differs')
    return sorted(deepcopy(result),key=lambda b:b['instrument_id'])


def projector(root,recipe):
    store,catalog,policy=context(root)
    item=next(i for i in catalog['body']['recipes'] if i['recipe']==reference(recipe))
    by_id={b['feature']['id']:b for b in bindings(root,reference(recipe),False)};registry=Registry(root)
    def project(feature):
        binding=by_id.get(feature['id'])
        if binding is None or binding['feature']!=reference(feature):raise ValueError('Unregistered currency Feature')
        expected=build_fx_feature(root,binding,item['configuration'],registry=registry,evaluation_policy=policy,store=store)
        if feature!=expected:raise ValueError('Currency Feature semantics differ')
        return deepcopy(recipe)
    return project


def build_momentum_catalog(root, catalog_ref):
    """Return a new metadata catalog for the exact momentum family, without writes."""
    from data.fx_records import make_record as catalog_record
    store=FeatureStore(root);original=store.resolve(catalog_ref);body=original['body']
    if body.get('kind')!='fx_currency_feature_catalog':raise ValueError('Expected currency Feature catalog')
    _,instruments=resolve_prices(root,body['price_catalog'])
    registry=Registry(root);policy=get_policy(root)
    if body['evaluation_policy']!=reference(policy):raise ValueError('Currency Feature policy differs')
    variants={v['id']:v for v in configurations(registry,MOMENTUM_CONFIGURATION_PROFILE)}
    recipes=[deepcopy(item) for item in body['recipes'] if item['configuration']['id'] in variants]
    if len(recipes)!=53 or {r['configuration']['id'] for r in recipes}!=set(variants):
        raise ValueError('Momentum catalog requires all 53 exact recipes')
    for item in recipes:
        config=item['configuration']
        if config!=variants[config['id']]:raise ValueError('Momentum configuration differs')
        expected=_definition(registry,policy,config);recipe_body=deepcopy(expected['body'])
        recipe_body['input_contract']=deepcopy(CURRENCY_INPUT_CONTRACT)
        expected=make_record(RECIPE_KIND,recipe_body,'Currency / quote: '+expected['display_name'])
        if store.resolve(item['recipe'])!=expected:raise ValueError('Momentum recipe differs')
    bindings=[deepcopy(b) for b in body['bindings'] if b['configuration_id'] in variants]
    keys={(b['configuration_id'],b['instrument_id']) for b in bindings}
    if len(bindings)!=53*126 or keys!={(v,s) for v in variants for s in instruments}:
        raise ValueError('Momentum currency bindings are incomplete or duplicated')
    for b in bindings:
        instrument=instruments[b['instrument_id']]
        expected=build_fx_feature(root,instrument,variants[b['configuration_id']],registry=registry,evaluation_policy=policy,store=store)
        if (store.resolve(b['feature'])!=expected or b['price_snapshot']!=instrument['price_snapshot']
                or b['source_view']!=expected['body']['recipe']['sources'][0]['source_view']):
            raise ValueError('Momentum currency Feature binding differs')
    return catalog_record('onboarding_evidence',{'kind':'fx_currency_feature_catalog',
        'configuration_profile':MOMENTUM_CONFIGURATION_PROFILE,'price_catalog':body['price_catalog'],
        'evaluation_policy':body['evaluation_policy'],'recipes':recipes,'bindings':bindings})
