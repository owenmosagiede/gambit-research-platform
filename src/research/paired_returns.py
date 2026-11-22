"""One frozen FX request, two prespecified Target branches, shared preparation.

Concurrent means paired in one execution, not additional competing workers.
Every P1 branch finishes before any P2 branch; admission/direction never cross
between spot and modelled total return.
"""
from copy import deepcopy

from research.contracts import DISCOVERY_DIRECTION, ResearchError, canonical, digest, ref
from research.store import inside, read_json
from research.schedule import period_for
from data.targets.store import TargetStore, materialization_path
from data.targets import fx_total
from data.transformations.identity import reference

FAMILIES=('price_return','total_return')
CONFIG='config/fx_total_return.json'

def resolve_plan(root,intent,profile,*,feature_manifest_index=None):
    from research import inputs
    if intent['expected_direction']!=DISCOVERY_DIRECTION:
        raise inputs.InputsBlocked('Paired total-return tests require P1 to discover each Target direction independently')
    original=dict(intent,target_family='price_return')
    plan=inputs.resolve_plan(root,original,profile,feature_manifest_index=feature_manifest_index)
    cs=plan['mode']=='CS'
    if cs:
        from data.fx_funded_scopes import validate_basis
        from data.fx_total_return_cs import load_release
        try:
            validate_basis(plan['scope'])
            config=load_release(root)
        except (ValueError, KeyError, OSError, TypeError) as exc:
            raise inputs.InputsBlocked('Choose an activated matched seventeen-member currency universe for Spot + Total Return: '+str(exc)) from exc
        if (config['scopes'].get(plan['scope']['id'])!=plan['scope']['reference']
                or config['price_catalog']!=plan['scope']['price_catalog']):
            raise inputs.InputsBlocked('The financed currency universe and frozen spot price catalog differ')
    else:
        if plan['mode']!='TS' or len(plan['members'])!=1:
            raise inputs.InputsBlocked('Paired return tests require an individual pair or a financed currency-reference CS universe')
        config=read_json(inside(root,CONFIG))
        if set(config)!={'schema','funding_model','funding_snapshot','materializations'} or config['schema']!='fx_total_return_release_v1':
            raise inputs.InputsBlocked('Modelled total-return release is not configured')
    if config['funding_model']!=reference(fx_total.policy()):raise inputs.InputsBlocked('Approved benchmark funding model differs')
    store=TargetStore(root)
    # Metadata-only acceptance. Observation values stay behind phase loading.
    snapshot=store.resolve(config['funding_snapshot'])
    from data.fx_funding import validate_record
    validate_record(snapshot)
    selected={}
    for member in plan['members']:
        pair=member['instrument_id']
        if 'CNH' in (pair[:3],pair[3:]):
            raise inputs.InputsBlocked('CNH is excluded from modelled financing; spot-only testing remains available')
        bindings=config['materializations'].get(pair,{})
        selected[pair]={str(h):bindings.get(str(h)) for h in plan['horizons']}
        for h,binding in selected[pair].items():
            if not isinstance(binding,dict) or set(binding)!={'definition','materialization'}:
                raise inputs.InputsBlocked('A frozen modelled total-return Target is required for every member and active horizon')
            manifest=fx_total.validate_manifest(read_json(store.path(materialization_path(binding['materialization']['id']))))
            if (reference(manifest)!=binding['materialization'] or manifest['definition']!=binding['definition']
                    or manifest['funding_model']!=config['funding_model'] or manifest['funding_snapshot']!=config['funding_snapshot']
                    or manifest['spot_materialization']!=member['targets'][h]['materialization']):
                raise inputs.InputsBlocked('Paired Targets do not share the exact frozen spot inputs and funding release')
            definition=store.resolve(binding['definition']);fx_total.validate_record(definition)
            if (definition['body']['spot_target']!=member['targets'][h]['definition']
                    or definition['body']['instrument_id']!=pair or definition['body']['horizon']['amount']!=int(h)):
                raise inputs.InputsBlocked('Paired Target member, horizon or underlying spot definition differs')
    plan['intent']=deepcopy(intent)
    plan['paired_returns']={'families':list(FAMILIES),'funding_model':config['funding_model'],
        'funding_snapshot':config['funding_snapshot'],
        'total_targets':selected if cs else selected[plan['members'][0]['instrument_id']],
        'selection_rule':'report_both_no_best_target_selection_v1'}
    if cs:
        plan['paired_returns']['comparison_membership']=plan['scope']['membership_snapshot']
    plan['plan_id']=inputs._plan_id(plan)
    return plan

def _targets(plan,member):
    targets=plan['paired_returns']['total_targets']
    return targets[member['instrument_id']] if plan['mode']=='CS' else targets


def branch_plan(plan,family):
    from research.inputs import _plan_id
    result=deepcopy(plan);result['intent']['target_family']=family
    result['paired_execution']={'parent_plan_id':plan['plan_id'],'family':family,
        'selection_rule':plan['paired_returns']['selection_rule']}
    if family=='total_return':
        for member in result['members']:
            member['targets']=deepcopy(_targets(plan,member))
    result['plan_id']=_plan_id(result)
    return result

def branch_data(root,plan,data,family,phase,horizon):
    result=deepcopy(data)
    if family=='price_return':return result
    from research.inputs import _load_target
    from data.verified_inputs import phase_inputs
    period=period_for(plan,phase,horizon);lookup={}
    bindings={m['instrument_id']:_targets(plan,m)[str(horizon)] for m in plan['members']}
    with phase_inputs(root,plan,phase,period=period):
        for member in plan['members']:
            spot,_=_load_target(root,member,plan,period,horizon)
            binding=bindings[member['instrument_id']]
            materialized=fx_total.read(root,binding['materialization']['id'],period=period,spot_rows=spot)
            if reference(materialized['manifest'])!=binding['materialization']:
                raise ResearchError('Frozen financing Target changed')
            rows=materialized['observations']
            matched={r['spot_target_row_id']:r for r in rows}
            if len(matched)!=len(rows) or set(matched)!={r['id'] for r in spot}:
                raise ResearchError('Financing Target must preserve every exact paired spot operand once')
            lookup.update({(member['instrument_id'],identifier):row for identifier,row in matched.items()})
    for row in result['rows']:
        target=lookup[(row['instrument'],row['lineage']['target_row_id'])]
        binding=bindings[row['instrument']]
        row['target']=target['value'] if target['status']=='valid' else None
        row['valid']=row['valid'] and target['status']=='valid'
        row['status']='valid' if row['valid'] else 'unavailable'
        if target['status']!='valid':row['reason_codes'].append(target['reason_code'])
        row['lineage'].update(target_materialization=binding['materialization'],target_row_id=target['id'],
            funding_snapshot=target['funding_snapshot'],funding_inputs_sha256=target['funding_inputs_sha256'],
            paired_spot_target_row_id=target['spot_target_row_id'])
    for coverage in result['coverage']:
        valid=sum(r['valid'] for r in result['rows'] if r['instrument']==coverage['instrument_id'])
        coverage.update(valid_rows=valid,unavailable_rows=coverage['scheduled_rows']-valid)
        if 'valid_distinct_source_update_count' in coverage:
            coverage['valid_distinct_source_update_count']=len({digest(r['lineage']['original_observation'])
                for r in result['rows'] if r['instrument']==coverage['instrument_id'] and r['valid']})
    result['lineage']['funding_model']=plan['paired_returns']['funding_model']
    result['lineage']['paired_spot_plan_id']=plan['plan_id']
    return result

def execute(jobs,rid,plan,adapter,prepare,profile,implementation):
    from research.direction import discovery_binding
    branches={f:branch_plan(plan,f) for f in FAMILIES};states={};links=[];pending=[]
    def update(h,f,**changes):
        states.setdefault(str(h),{family:{'p1_status':'pending','p2_status':'pending'} for family in FAMILIES})[f].update(changes)
        horizons=[]
        for n in plan['horizons']:
            pair=states.get(str(n),{family:{'p1_status':'pending','p2_status':'pending'} for family in FAMILIES})
            row={'horizon':n,'paired_targets':deepcopy(pair)}
            for stage in ('p1_status','p2_status'):
                values=[p[stage] for p in pair.values()]
                row[stage]='complete' if all(v not in ('pending','running') for v in values) else 'running' if 'running' in values else 'pending'
            horizons.append(row)
        jobs._update(rid,horizons=horizons,progress={'total':len(horizons),'completed':sum(
            h['p1_status']=='complete' and h['p2_status']=='complete' for h in horizons)},results=links)
    for horizon in plan['horizons']:
        jobs._check(rid);prepared=prepare('P1',horizon)
        jobs._update(rid,status='p1',stage='P1',message=f'Paired spot and modelled total-return discovery: {horizon} weekdays.')
        common=None
        for family in FAMILIES:
            branch=branches[family];update(horizon,family,p1_status='running')
            relation={'recipe':branch['recipe'],'scope':branch['scope'],'mode':branch['mode'],
                'target_family':family,'horizon':horizon,'horizon_unit':'scheduled_weekdays',
                'members':[m['instrument_id'] for m in branch['members']],
                'targets':[m['targets'][str(horizon)]['definition'] for m in branch['members']],
                'expected_direction':DISCOVERY_DIRECTION}
            if 'feature_application' in branch:relation['feature_application']=branch['feature_application']
            relationship=jobs.store.put('relationship',relation,relation)
            jobs._record_access(rid,branch,'P1',horizon)
            if common is None:common=adapter.load_phase(jobs.root,plan,prepared,'P1',horizon)
            data=branch_data(jobs.root,plan,common,family,'P1',horizon)
            jobs._check(rid)
            trial=jobs._trial(branch,prepared,'P1',horizon,relationship,data,profile,implementation)
            decision=trial['body']['admission']
            admission=jobs.store.put('admission',{'trial':ref(trial)}, {'trial':ref(trial),'relationship':ref(relationship),
                'decision':decision,'evidence':trial['body'].get('evidence',{}),'reason_codes':trial['body'].get('reason_codes',[])})
            links.append(ref(jobs._link(relationship,trial,admission)))
            update(horizon,family,p1_status=decision,p2_status='pending' if decision=='admitted' else 'not_admitted')
            if decision=='admitted':
                binding=discovery_binding(trial,admission)
                if binding is None:
                    validation=jobs.store.put('validation',{'discovery':ref(trial),'precheck':'missing_effect','profile':digest(profile)},
                        {'relationship':ref(relationship),'decision':'UNRESOLVED',
                         'reason_codes':['DISCOVERY_EFFECT_UNAVAILABLE'],'discovery_trial':ref(trial),'evaluation_trial':None})
                    links[-1]=ref(jobs._link(relationship,trial,admission,validation=validation))
                    update(horizon,family,p2_status='UNRESOLVED')
                    continue
                update(horizon,family,discovery_direction=binding['direction'])
                pending.append((horizon,family,relationship,trial,admission,binding))
    # All P1 branches/horizons above are complete before validation access.
    common_cache={}
    for horizon,family,relationship,p1,admission,direction in pending:
        jobs._check(rid);branch=branches[family]
        token={'plan_id':plan['plan_id'],'admitted_horizons':[horizon],
               'directions_by_horizon':{str(horizon):direction['direction']}}
        prepared=prepare('P2',horizon,token)
        jobs._update(rid,status='p2',stage='P2',message=f'{family}: validating its own P1 direction at {horizon} weekdays.')
        update(horizon,family,p2_status='running')
        jobs._record_access(rid,branch,'P2',horizon,direction_binding=direction)
        if horizon not in common_cache:
            common_cache[horizon]=adapter.load_phase(jobs.root,plan,prepared,'P2',horizon,admission=token)
        data=branch_data(jobs.root,plan,common_cache[horizon],family,'P2',horizon)
        jobs._check(rid)
        p2=jobs._trial(branch,prepared,'P2',horizon,relationship,data,profile,implementation,
            discovery_effect=p1['body']['metrics']['primary_effect'],discovery_trial=ref(p1),direction_binding=direction)
        validation=jobs.store.put('validation',{'discovery':ref(p1),'evaluation':ref(p2)},
            {'relationship':ref(relationship),'decision':p2['body']['decision'],'discovery_trial':ref(p1),
             'evaluation_trial':ref(p2),'reason_codes':p2['body'].get('reason_codes',[]),
             'evidence':p2['body'].get('evidence',{}),'direction_binding':direction})
        links[:]=[r for r in links if jobs.store.resolve('link',r)['body']['relationship']!=ref(relationship)]
        links.append(ref(jobs._link(relationship,p1,admission,p2,validation)))
        update(horizon,family,p2_status=p2['body']['decision'])
    jobs._check(rid)
    jobs._update(rid,status='succeeded',stage='complete',results=links,
        message='Paired execution completed. Spot and modelled total return retain separate scientific decisions.')
