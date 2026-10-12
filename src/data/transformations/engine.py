"""Provider-independent, cutoff-scoped reference recipe executor.

This module returns transient canonical results. It never reads observations from
storage, downloads data, enumerates recipes, or publishes features/signals.
"""
from calendar import monthrange
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
from pathlib import Path

from data.pit_selection import select_asof
from . import numeric
from .contracts import (ContractError, EXECUTION_IDENTITY_PROFILE, decimal_text,
    normalize_input, normalize_result, normalize_cutoffs, normalize_reference)
from .identity import (canonical_bytes, digest, reference, normalize_recipe,
    make_feature_definition, execution_materialization_id)
from .registry import Registry


class InputError(ContractError):
    """The input cannot honestly satisfy its declared temporal contract."""


class RecipeError(ContractError):
    """The requested recipe is incompatible or outside the supported scope."""


ExecutionFailure = numeric.ExecutionFailure


def implementation_reference():
    """Pin the current implementation bytes without paths or runtime timestamps."""
    folder = Path(__file__).resolve().parent
    paths = {name:folder/name for name in ('engine.py','numeric.py','contracts.py','identity.py','registry.py')}
    paths['pit_selection.py'] = folder.parent/'pit_selection.py'
    evidence = {name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in paths.items()}
    return {'id':'IMPLEMENTATION_TRANSFORMATION_FOUNDATION','version':'2.0.0','content_sha256':digest(evidence)}


def _parameters(step, entry):
    specs = {p['name']:p for p in entry['body']['parameters']}
    result = {}
    for parameter in step['parameters']:
        spec = specs.get(parameter['name'])
        if spec is None or parameter['unit'] != spec['unit'] or parameter['value']['kind'] != spec['value_kind']:
            raise RecipeError('Parameter name, unit or typed value differs from the operator contract')
        value = parameter['value']['value']
        result[parameter['name']] = int(value) if spec['value_kind']=='integer' else float(value) if spec['value_kind']=='decimal' else value
    return result


def _metadata(unit, semantics, contract, parameters):
    if semantics not in contract['input_semantics']:
        raise RecipeError('INAPPLICABLE: input value semantics are not accepted by the operator')
    rule = contract['output_unit_rule']
    if rule == 'dimensionless': unit = 'dimensionless'
    elif rule == 'observation_count': unit = 'observations'
    elif rule == 'log_input': unit = 'log_'+unit
    elif rule == 'per_observation': unit = unit+'_per_observation'
    elif rule == 'change_basis':
        if parameters['basis'] != 'diff': unit = 'dimensionless'
    elif rule != 'preserve': raise ExecutionFailure('Unimplemented registered unit rule: '+rule)
    semantics = semantics if contract['output_semantics']=='preserve' else contract['output_semantics']
    return unit, semantics


def _preflight(series, recipe, registry):
    if series.get('execution') is not None:
        # A derived root needs a SourceView that binds its upstream definition;
        # silently reusing a raw SourceView would give the wrong logical identity.
        raise InputError('Derived roots require an explicitly defined SourceView; compose steps in one recipe instead')
    if recipe['sources'][0]['source_view'] != series['source_view'] or recipe['selection'] != series['selection']:
        raise RecipeError('Recipe SourceView or resolved selection differs from the input')
    if recipe['history_policy'] != series['history_policy']:
        raise RecipeError('UNDECLARED_HISTORY_MODE: input and recipe history policies differ')
    for name,identifier in [('execution_policy','POL_TRANSFORM_EXECUTION'),('history_policy','POL_TRANSFORM_HISTORY')]:
        record = registry.resolve_policy(recipe[name])
        if record['id'] != identifier: raise RecipeError('Unsupported policy role: '+name)
    if 'evaluation_policy' in recipe:
        policy=registry.resolve_policy(recipe['evaluation_policy'])
        if policy['body']['kind']!='selection':raise RecipeError('Evaluation policy must be an approved selection policy')
    if series['cadence']['frequency']=='intraday' and series['temporal_precision']!='utc_timestamp':
        raise InputError('Intraday cadence requires UTC timestamp precision')
    capabilities = set(series['capabilities'])
    if 'revision_history' not in capabilities:
        references = [r['reference_time'] for r in series['observations']]
        if len(references) != len(set(references)):
            raise InputError('Multiple vintages require the revision_history capability')
    if recipe['history_mode']=='emitted_history' and 'release_events' not in capabilities:
        raise RecipeError('Emitted history requires explicit event anchors; timestamps are never inferred')
    unit, semantics, compiled = series['unit'], series['value_semantics'], []
    for index,step in enumerate(recipe['steps']):
        entry = registry.resolve(step['operator'])
        c = entry['body']['execution_contract']
        if c['certification']['status'] != 'approved':
            raise RecipeError('Operator has not passed certification')
        if not set(c['capabilities']) <= capabilities:
            raise RecipeError('INAPPLICABLE: input lacks required temporal capabilities')
        if c['temporal_mode'] != 'reference_state' and index != 0:
            raise RecipeError('Release-state operators require native source context as the first step')
        if c['temporal_mode']=='release_event_history' and recipe['history_mode']!='emitted_history':
            raise RecipeError('UNDECLARED_HISTORY_MODE: this operator requires emitted history')
        frequency = series['cadence']['frequency'] if index == 0 or recipe['history_mode']=='resolved_state' else 'event'
        parameters = registry.validate_parameters(entry, _parameters(step, entry), frequency, step.get('grid_policy'))
        unit,semantics = _metadata(unit,semantics,c,parameters)
        compiled.append((entry,parameters,unit,semantics,frequency))
    if unit != recipe['output_unit']:
        raise RecipeError('Declared recipe output unit differs from composed operator units')
    events = series.get('release_events',[])
    if any(e['reference_time']>e['available_at'] for e in events):
        raise InputError('Release reference anchors cannot be later than their availability')
    if len({e['available_at'] for e in events}) != len(events):
        raise InputError('Ambiguous event ordering: one selected release anchor per availability time is required')
    return compiled


def _check_gaps(rows, cadence):
    frequency = cadence['frequency']
    if frequency in ('irregular','event','tick'): return
    for previous,current in zip(rows,rows[1:]):
        a,b = previous['reference_time'],current['reference_time']
        # Preserve clock precision and time of day, including Gregorian EOM.
        ad,bd = date.fromisoformat(a[:10]),date.fromisoformat(b[:10])
        if frequency in ('daily','weekly'):
            good = bd-ad == timedelta(days=1 if frequency=='daily' else 7) and a[10:]==b[10:]
        elif frequency=='intraday':
            if 'T' not in a: raise InputError('Intraday cadence requires UTC timestamp precision')
            good = datetime.fromisoformat(b.replace('Z','+00:00'))-datetime.fromisoformat(a.replace('Z','+00:00')) == timedelta(seconds=int(cadence['interval_seconds']))
        else:
            count = {'monthly':1,'quarterly':3,'semiannual':6,'annual':12}[frequency]
            total = ad.year*12+ad.month-1+count
            year,month = total//12,total%12+1
            same_anchor = ad.day==bd.day or (ad.day==monthrange(ad.year,ad.month)[1] and bd.day==monthrange(bd.year,bd.month)[1])
            good = (bd.year,bd.month)==(year,month) and same_anchor and a[10:]==b[10:]
        if not good:
            raise InputError('MISSING_PERIOD: regular cadence has an absent period; explicit_missing requires explicit null rows, never implicit insertion')


def _state(series, cutoff, anchor=None):
    rows = select_asof(series['observations'], cutoff, reference_cutoff=min(anchor,cutoff) if anchor else cutoff)
    _check_gaps(rows, series['cadence'])
    return rows


def _calculation(entry, parameters, rows, frequency, ordering=None):
    c = entry['body']['execution_contract']
    values,reasons = [],[]
    for row in rows:
        value = float(row['value']) if row['status']=='valid' else None
        reason = row['reason_code']
        if value is not None and 'positive_input' in c['input_requirements'] and value<=0:
            value,reason = None,'NONPOSITIVE_INPUT'
        values.append(value); reasons.append(reason)
    return numeric.calculate(c['kernel'],values,parameters,reference_times=ordering or [r['reference_time'] for r in rows],frequency=frequency,input_reasons=reasons)


def _policies(recipe):
    result = [{'role':'execution','artifact':recipe['execution_policy']},{'role':'history','artifact':recipe['history_policy']}]
    if 'evaluation_policy' in recipe:result.append({'role':'evaluation','artifact':recipe['evaluation_policy']})
    result.extend({'role':'grid_'+str(i),'artifact':step['grid_policy']} for i,step in enumerate(recipe['steps']) if 'grid_policy' in step)
    return result


def _lineage(series, rows, recipe_ref, implementation, bindings, extra=()):
    refs = [series['source_view'],*series['source_snapshots'],*(r['lineage'] for r in rows),*extra]
    unique = {canonical_bytes(ref):ref for ref in refs}
    record = {'schema_version':'0.2.0','record_type':'lineage_manifest','version':'1.0.0',
              'inputs':[{'role':'input_'+str(i),'artifact':unique[key]} for i,key in enumerate(sorted(unique))],
              'operation':recipe_ref,'implementation':implementation,'policy_bindings':bindings}
    record['id'] = 'LINEAGE_'+digest(record)
    return record


def _envelope(original, recipe, rows, points, cutoffs, unit, semantics, implementation, executed_at, extra=(), event_order=False):
    if len(rows)!=len(points) or len(rows)!=len(cutoffs):
        raise ExecutionFailure('Operator result length differs from the requested output index')
    recipe_ref = reference(make_feature_definition(recipe))
    bindings = _policies(recipe)
    record = _lineage(original,rows,recipe_ref,implementation,bindings,extra)
    lineage_ref = reference(record)
    result = {k:deepcopy(v) for k,v in original.items() if k not in ('observations','release_events','execution')}
    result.update(unit=unit,value_semantics=semantics,capabilities=['resolved_state'])
    if event_order:
        result['cadence'] = {'frequency':'event','ordering':'evaluation_cutoff','gap_policy':'reject','calendar':'gregorian'}
    observations = []
    for index,(row,point,cutoff) in enumerate(zip(rows,points,cutoffs)):
        value = point['value']
        observations.append({**deepcopy(original['selection']), 'reference_time':row['reference_time'],
            'available_at':cutoff,'evaluation_cutoff':cutoff,'vintage_id':'DERIVED_'+str(index),
            'value':None if value is None else decimal_text(value),'status':'invalid' if value is None else 'valid',
            'reason_code':point['reason'],'lineage':lineage_ref})
    valid = sum(r['status']=='valid' for r in observations)
    unique_cutoffs = sorted(set(cutoffs))
    result['observations'] = observations
    result['execution'] = {'recipe':recipe_ref,
        'materialization_id':execution_materialization_id(recipe_ref,original,unique_cutoffs,implementation,bindings,output_index=[{'reference_time':r['reference_time'],'evaluation_cutoff':c} for r,c in zip(rows,cutoffs)]),
        'identity_profile':EXECUTION_IDENTITY_PROFILE,'implementation':implementation,'executed_at':executed_at,
        'cutoffs':unique_cutoffs,'status':'no_valid_output' if not valid else 'complete' if valid==len(observations) else 'partial',
        'availability_semantics':'derived_at_cutoff','history_mode':recipe['history_mode'],
        'lineage':[lineage_ref],'lineage_records':[record]}
    return normalize_result(result)


def _prefix(recipe, index, unit):
    result = deepcopy(recipe)
    result['steps'] = result['steps'][:index+1]
    result['output_node'] = result['steps'][-1]['node']
    result['output_unit'] = unit
    return result


def _execute(series, recipe, cutoffs, registry, implementation, executed_at):
    source = normalize_input(series)
    recipe = normalize_recipe(recipe)
    cutoffs = normalize_cutoffs(cutoffs,source['temporal_precision'])
    implementation = normalize_reference(implementation or implementation_reference())
    executed_at = executed_at or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    compiled = _preflight(source,recipe,registry)
    events = source.get('release_events',[])
    final_rows,final_points,all_stages,all_refs = [],[],[],[]
    for cutoff in cutoffs:
        current_event = next((e for e in events if e['available_at']==cutoff),None)
        native_release = compiled[0][0]['body']['execution_contract']['temporal_mode']!='reference_state'
        if native_release and current_event is None:
            final_rows.append({'reference_time':None,'lineage':source['source_view']})
            final_points.append({'value':None,'reason':'INAPPLICABLE'})
            continue
        if recipe['history_mode']=='resolved_state':
            rows = _state(source,cutoff,current_event['reference_time'] if native_release else None)
            if native_release and (not rows or rows[-1]['reference_time']!=current_event['reference_time']):
                final_rows.append({'reference_time':current_event['reference_time'],'lineage':current_event['lineage']})
                final_points.append({'value':None,'reason':'MISSING_REQUIRED_OBSERVATION'})
                continue
            if not rows:
                final_rows.append({'reference_time':None,'lineage':source['source_view']})
                final_points.append({'value':None,'reason':'INSUFFICIENT_HISTORY'})
                continue
            for index,(entry,params,unit,semantics,frequency) in enumerate(compiled):
                points = _calculation(entry,params,rows,frequency)
                intermediate = _envelope(source,_prefix(recipe,index,unit),rows,points,[cutoff]*len(rows),unit,semantics,implementation,executed_at,extra=[current_event['lineage']] if native_release else ())
                all_stages.append(intermediate); all_refs.extend(intermediate['execution']['lineage'])
                rows = intermediate['observations']
            final_rows.append(rows[-1]); final_points.append(points[-1])
        else:
            selected_events = [e for e in events if e['available_at']<=cutoff and e['reference_time']<=e['available_at']]
            if not selected_events:
                final_rows.append({'reference_time':None,'lineage':source['source_view']})
                final_points.append({'value':None,'reason':'INSUFFICIENT_HISTORY'})
                continue
            entry,params,unit,semantics,frequency = compiled[0]
            shock = entry['body']['execution_contract']['temporal_mode']=='release_event_history'
            emitted,points,event_refs = [],[],[]
            for event in selected_events:
                state = _state(source,event['available_at'],event['reference_time'])
                # A declared event must resolve exactly its reference anchor.
                if not state or state[-1]['reference_time']!=event['reference_time']:
                    point = {'value':None,'reason':'MISSING_REQUIRED_OBSERVATION'}
                elif shock:
                    kernel = {'diff':'change.diff','pct':'change.pct','log':'change.log'}[params['basis']]
                    point = numeric.calculate(kernel,[float(r['value']) if r['status']=='valid' else None for r in state],{'k':params['k']},input_reasons=[r['reason_code'] for r in state])[-1]
                else:
                    point = _calculation(entry,params,state,frequency)[-1]
                emitted.append({'reference_time':event['reference_time'],'lineage':event['lineage']})
                event_refs.extend(r['lineage'] for r in state)
                points.append(point)
            if shock:
                points = numeric.calculate('standard.zscore',[p['value'] for p in points],{'w':params['w']},input_reasons=[p['reason'] for p in points])
            event_cutoffs = [e['available_at'] for e in selected_events]
            intermediate = _envelope(source,_prefix(recipe,0,unit),emitted,points,event_cutoffs,unit,semantics,implementation,executed_at,extra=event_refs,event_order=True)
            all_stages.append(intermediate); all_refs.extend(intermediate['execution']['lineage'])
            rows = intermediate['observations']
            for index,(entry,params,unit,semantics,frequency) in enumerate(compiled[1:],1):
                # Event order is availability order; economic reference periods
                # may repeat or move backwards at revisions.
                rows = sorted(rows,key=lambda r:r['evaluation_cutoff'])
                points = _calculation(entry,params,rows,frequency,ordering=event_cutoffs)
                intermediate = _envelope(source,_prefix(recipe,index,unit),rows,points,event_cutoffs,unit,semantics,implementation,executed_at,event_order=True)
                all_stages.append(intermediate); all_refs.extend(intermediate['execution']['lineage'])
                rows = intermediate['observations']
            final_rows.append(rows[-1]); final_points.append(points[-1])
    _,_,unit,semantics,_ = compiled[-1]
    result = _envelope(source,recipe,final_rows,final_points,cutoffs,unit,semantics,implementation,executed_at,extra=all_refs,event_order=recipe['history_mode']=='emitted_history')
    # Return closure for every transient intermediate lineage referenced by the
    # final manifest, not an opaque reference to a discarded temporary record.
    records = {r['id']:r for stage in all_stages for r in stage['execution']['lineage_records']}
    records.update({r['id']:r for r in result['execution']['lineage_records']})
    result['execution']['lineage_records'] = list(records.values())
    result['execution']['lineage'] = [reference(r) for r in records.values()]
    return normalize_result(result), all_stages


def execute_recipe(series, recipe, cutoffs, *, registry=None, implementation=None, executed_at=None):
    """Return one requested output per cutoff; no observation or definition writes."""
    return _execute(series,recipe,cutoffs,registry or Registry(),implementation,executed_at)[0]


def execute_stages(series, recipe, cutoffs, *, registry=None, implementation=None, executed_at=None):
    """Return validated intermediate envelopes for inspection of a declared chain."""
    return _execute(series,recipe,cutoffs,registry or Registry(),implementation,executed_at)[1]
