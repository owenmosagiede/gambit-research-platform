"""Strict additive contracts for reusable recipes, without instrument bindings."""
from copy import deepcopy
import re

from data.transformations import contracts as c
from data.transformations.identity import canonical_bytes, digest, normalize_parameter, reference

SCHEMA_VERSION='0.7.0'
RECIPE_KIND='feature_recipe_definition'
REGISTRATION_KIND='feature_recipe_registration'
INPUT_CONTRACT={
    'asset_class':'fx','source_profile':'fx_price.1.0.0','source_kind':'fx_constructed_view',
    'measure':'close','value_semantics':'price','value_domain':'positive_or_controlled_null',
    'unit_binding':'quote_currency_per_base_currency','temporal_precision':'date',
    'observation_clock':'scheduled_weekdays','calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0',
    'historical_availability':'unknown_preserved_null'}
CURRENCY_INPUT_CONTRACT={**INPUT_CONTRACT,'source_profile':'fx_currency_price.1.0.0'}
PREFIXES={RECIPE_KIND:'FEATURE_RECIPE_',REGISTRATION_KIND:'FEATURE_RECIPE_REGISTRATION_'}


def make_record(kind,body,display_name=None):
    if kind not in PREFIXES:raise c.ContractError('Unsupported reusable Feature record')
    record={'schema_version':SCHEMA_VERSION,'record_type':kind,'version':'1.0.0','body':deepcopy(body)}
    record['id']=PREFIXES[kind]+digest(record)
    if display_name is not None:record['display_name']=display_name
    return record


def validate_record(record):
    c.object_fields(record,{'schema_version','record_type','version','id','body'},{'display_name'},'reusable Feature record')
    if record['schema_version']!=SCHEMA_VERSION or record['version']!='1.0.0' or record['record_type'] not in PREFIXES:
        raise c.ContractError('Unsupported reusable Feature profile')
    if 'display_name' in record:
        label=record['display_name']
        if type(label) is not str or not label or len(label)>500 or any(ord(ch)<32 or ord(ch)>126 for ch in label):
            raise c.ContractError('Invalid reusable Feature display name')
    kind=record['record_type'];body=record['body']
    if kind==RECIPE_KIND:
        fields={'kind','input_contract','steps','output_node','output_contract','history_mode','history_policy',
                'execution_policy','evaluation_policy','calculation_geometry'}
        c.object_fields(body,fields,path='reusable recipe body')
        if body['kind']!='reusable_fx_feature_recipe' or body['input_contract'] not in (INPUT_CONTRACT,CURRENCY_INPUT_CONTRACT):
            raise c.ContractError('Unsupported reusable FX input contract')
        if body['history_mode']!='resolved_state' or body['calculation_geometry']!='independent_per_instrument':
            raise c.ContractError('Unsupported reusable calculation profile')
        for name in ('history_policy','execution_policy','evaluation_policy'):c.normalize_reference(body[name])
        c.object_fields(body['output_contract'],{'unit_template','value_semantics'},path='reusable output contract')
        c.token(body['output_contract']['unit_template']);c.choice(body['output_contract']['value_semantics'],c.VALUE_SEMANTICS,'output semantics')
        if type(body['steps']) is not list or len(body['steps']) not in (1,2):raise c.ContractError('Unsupported reusable FX chain')
        previous='source';nodes=set()
        for step in body['steps']:
            c.object_fields(step,{'node','phase','operator','inputs','parameters','grid_policy'},path='reusable recipe step')
            c.token(step['node'])
            if step['node'] in nodes or step['node']=='source' or step['phase']!='transformation' or step['inputs']!=[previous]:
                raise c.ContractError('Reusable recipe wiring is not a single ordered chain')
            nodes.add(step['node']);previous=step['node']
            c.normalize_reference(step['operator']);c.normalize_reference(step['grid_policy'])
            if type(step['parameters']) is not list:raise c.ContractError('Parameters must be a list')
            params=[normalize_parameter(p) for p in step['parameters']]
            if params!=sorted(params,key=lambda p:p['name']) or len({p['name'] for p in params})!=len(params):
                raise c.ContractError('Parameters must be unique and canonical')
        if body['output_node']!=previous:raise c.ContractError('Reusable recipe output must be its terminal step')
    else:
        fields={'kind','profile','legacy_catalogs','recipes','recipe_count','legacy_binding_count','instrument_count','observation_action'}
        c.object_fields(body,fields,path='reusable registration body')
        if body['kind']!='reusable_fx_feature_recipe_registration' or body['profile']!='reusable_fx_feature_recipes.1.0.0' or body['observation_action']!='none':
            raise c.ContractError('Unsupported reusable registration profile')
        if type(body['legacy_catalogs']) is not list or not body['legacy_catalogs']:raise c.ContractError('Registration requires prior catalog references')
        for ref in body['legacy_catalogs']:c.normalize_reference(ref)
        if len({canonical_bytes(ref) for ref in body['legacy_catalogs']})!=len(body['legacy_catalogs']):raise c.ContractError('Duplicate prior catalog')
        if type(body['recipes']) is not list or not body['recipes']:raise c.ContractError('Registration requires recipes')
        for item in body['recipes']:
            c.object_fields(item,{'configuration_id','feature_recipe','legacy_binding_count'},path='reusable registration item')
            if not re.fullmatch(r'FXCONFIG_[0-9a-f]{64}',item['configuration_id']):raise c.ContractError('Invalid configuration ID')
            c.normalize_reference(item['feature_recipe'])
            if not item['feature_recipe']['id'].startswith('FEATURE_RECIPE_') or type(item['legacy_binding_count']) is not int or item['legacy_binding_count']<=0:
                raise c.ContractError('Invalid reusable mapping')
        if len({i['configuration_id'] for i in body['recipes']})!=len(body['recipes']) or len({i['feature_recipe']['id'] for i in body['recipes']})!=len(body['recipes']):
            raise c.ContractError('Duplicate reusable mapping')
        if any(type(body[k]) is not int or body[k]<=0 for k in ('recipe_count','legacy_binding_count','instrument_count')):
            raise c.ContractError('Invalid reusable registration counts')
        if body['recipe_count']!=len(body['recipes']) or body['legacy_binding_count']!=sum(i['legacy_binding_count'] for i in body['recipes']):
            raise c.ContractError('Reusable registration counts differ')
    if make_record(kind,body,record.get('display_name'))!=record:raise c.ContractError('Reusable record identity differs from content')
    return record
