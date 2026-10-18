"""Bounded, immutable retrospective FX Feature preparation and retrieval.

The ordinary PIT executor is deliberately not called with fabricated availability.
Registered causal numeric kernels operate on one verified captured price state,
with explicit missing weekday slots and an immutable actual knowledge cutoff.
"""
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
import sys

from data.alfred_onboarding import stable_read, strict_json
from data.feature_store import FeatureStore, PublicationError, materialization_path, _publish_entry
from data.fx_feature_contracts import (PROFILE, VERSION, lineage_record, materialization_id,
    validate_record, validate_materialization)
from data.transformations import numeric
from data.transformations.contracts import normalize_time, decimal_text
from data.transformations.identity import (reference, digest, canonical_bytes, normalize_bindings,
    feature_id, signal_id)
from data.transformations.engine import _metadata
from data.targets.fx import _approved_policy, _price_snapshot
from data.verified_inputs import memo, phase_end, verified_prices


def _dates(start, end):
    current=date.fromisoformat(start); last=date.fromisoformat(end)
    while current<=last:
        if current.weekday()<5: yield current.isoformat()
        current += timedelta(days=1)


def _compile(root, feature, snapshot, batch):
    from data.fx_feature_recipes import validate_fx_recipe
    result=validate_fx_recipe(root, feature)
    policy_values={item['name']:item['value']['value'] for item in result['evaluation_policy']['body']['parameters']}
    if policy_values.get('source_retrospective_policy')!=batch['retrospective_policy'] or policy_values.get('source_alignment_approval')!=batch['approval_evidence']:
        raise PublicationError('FX preparation batch differs from the recipe approval bindings')
    recipe=feature['body']['recipe']; body=snapshot['body']
    if feature['id']!=feature_id(recipe) or feature['body']['signal_id']!=signal_id(recipe):
        raise PublicationError('Feature identity differs from the exact recipe')
    if recipe['sources'][0]['source_view']!=body['definition']:
        raise PublicationError('Feature recipe belongs to another FX price SourceView')
    if recipe['selection']['entity_id']!=body['instrument_id'] or recipe['selection']['measure']!='close' or recipe['selection']['dimensions']:
        raise PublicationError('Feature selection must be this exact economic instrument close')
    unit=body['source_metadata']['unit']; semantics='price'
    for item in result['steps']:
        entry, parameters=item['entry'],item['parameters']
        contract=entry['body']['execution_contract']
        if contract['certification']['status']!='approved' or contract['temporal_mode']!='reference_state':
            raise PublicationError('FX preparation requires approved causal reference-state operators')
        unit,semantics=_metadata(unit,semantics,contract,parameters)
    if unit!=recipe['output_unit'] or unit!=result['unit'] or semantics!=result['value_semantics']:
        raise PublicationError('Compiled FX output metadata differs from the registered recipe')
    return result


def _scheduled_input(snapshot, prices, cutoff, end):
    body=snapshot['body']; by_date={row['reference_time']:row for row in prices}
    if len(by_date)!=len(prices) or not prices:
        raise PublicationError('FX prices require unique source date labels')
    first=min(by_date)
    if end<first: raise PublicationError('Requested sample precedes stored FX coverage')
    dates=list(_dates(first,end)); scheduled=[]
    for day in dates:
        row=by_date.get(day)
        if row is not None:
            for dependency in row['input_dependencies']:
                capture=dependency['original_ingested_at']
                if capture is None or capture[:10]>cutoff:
                    raise PublicationError('Selected captured state was not known at the declared cutoff')
            if row['available_at'] is not None:
                raise PublicationError('This bounded profile preserves unknown historical availability only')
        scheduled.append({'reference_time':day,'price_row_id':row['id'] if row else None,
                          'price_row_sha256':digest(row) if row else None})
    record=lineage_record('fx_feature_input_record',{'profile':PROFILE,'price_snapshot':reference(snapshot),
        'knowledge_cutoff':cutoff,'schedule_start':first,'schedule_end':end,
        'calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0',
        'scheduled_inputs':scheduled,'source_rows_sha256':digest(prices)})
    return record,dates,[by_date.get(day) for day in dates]


def _calculate(compiled, dates, prices):
    values=[]; reasons=[]
    for row in prices:
        if row is None: values.append(None); reasons.append('MISSING_PERIOD')
        elif row['status']!='valid':
            values.append(None); reasons.append(row['reason_code'] if row['reason_code'] in numeric.FAILURE_CODES else 'SOURCE_INVALID')
        else:
            values.append(float(row['value'])); reasons.append(None)
    for item in compiled['steps']:
        contract=item['entry']['body']['execution_contract']
        if 'positive_input' in contract['input_requirements']:
            for index,value in enumerate(values):
                if value is not None and value<=0:
                    values[index]=None; reasons[index]='NONPOSITIVE_INPUT'
        points=numeric.calculate(contract['kernel'], values, item['parameters'],
            reference_times=dates,frequency='daily',input_reasons=reasons)
        values=[point['value'] for point in points]; reasons=[point['reason'] for point in points]
    return [{'value':None if value is None else decimal_text(value),'reason':reason}
            for value,reason in zip(values,reasons)]


def _window_calculation(store, feature, snapshot, prices, batch, compiled, cutoff, end, *, verification=False):
    """One causal series per phase, retaining each window's original prefix lineage.

    Publication and independent verification use separate cache entries: the
    verifier never trusts the publisher's calculated points. Standalone reads,
    without an execution context, still replay the exact requested prefix.
    """
    last = phase_end(store.root, end)
    if end > last:
        raise PublicationError('Feature output extends beyond execution phase')
    key = {'feature': reference(feature), 'snapshot': reference(snapshot),
           'batch': batch, 'cutoff': cutoff, 'end': last}
    def schedule():
        record, dates, selected = _scheduled_input(snapshot, prices, cutoff, last)
        return record, dates, selected
    # Verification shares the already-verified source schedule, not calculated output.
    record, dates, selected = memo(store.root, 'feature_schedule', key, schedule)
    points = memo(store.root, 'verified_series' if verification else 'calculated_series', key,
                  lambda: _calculate(compiled, dates, selected))
    count = sum(day <= end for day in dates)
    if not count:
        raise PublicationError('Requested sample precedes stored FX coverage')
    body = dict(record['body'], schedule_end=end,
                scheduled_inputs=record['body']['scheduled_inputs'][:count])
    window = lineage_record('fx_feature_input_record', body)
    return window, dates[:count], points[:count]


def _bindings(recipe, batch):
    bindings=[{'role':role,'artifact':recipe[field]} for role,field in
        [('execution','execution_policy'),('history','history_policy'),('evaluation','evaluation_policy')]]
    bindings += [{'role':'grid_'+str(index),'artifact':step['grid_policy']}
                 for index,step in enumerate(recipe['steps']) if 'grid_policy' in step]
    bindings += [{'role':'retrospective','artifact':batch['retrospective_policy']},
                 {'role':'research_approval','artifact':batch['approval_evidence']}]
    return normalize_bindings(bindings)


def _implementation(store, recipe):
    project=Path(__file__).resolve().parents[2]
    names=('src/data/targets/store.py','src/data/verified_inputs.py','src/data/fx_feature_store.py','src/data/fx_feature_contracts.py','src/data/fx_feature_recipes.py',
        'src/data/feature_store.py','src/data/lineage_packs.py','src/data/transformations/engine.py','src/data/transformations/numeric.py',
        'src/data/transformations/registry.py','src/data/transformations/contracts.py','src/data/transformations/identity.py',
        'src/data/targets/fx.py','src/data/transformations/fx.py','src/data/fx_records.py',
        'src/data/fx_onboarding.py','src/data/alfred_onboarding.py','src/data/targets/contracts.py',
        'src/data/targets/scheduling.py','specs/schemas/platform.schema.json',
        'specs/schemas/fx.schema.json','specs/schemas/onboarding.schema.json')
    record={'schema_version':'0.2.0','record_type':'implementation_manifest','version':'1.0.0',
        'code_artifacts':[store.io.blob(stable_read(project/name),'txt',name.replace('/','_'),None) for name in names],
        'environment_artifacts':[store.io.blob(canonical_bytes({'python':sys.version,'numeric':'binary64',
            'profile':PROFILE}),'json','fx_feature_runtime',1)],
        'entrypoint_id':'prepare_fx_feature','determinism_policy':recipe['execution_policy']}
    record['id']='IMPLEMENTATION_'+digest(record)
    return record


def _rows(feature, mid, input_record, dates, points, start, cutoff, implementation, bindings):
    observations=[]; lineages=[]
    selection=feature['body']['recipe']['selection']
    # These immutable operands are identical for every row in this block.
    # Hash the large scheduled-input record once, preserving exact references.
    input_ref=reference(input_record); feature_ref=reference(feature)
    for index,(day,point) in enumerate(zip(dates,points)):
        if day<start: continue
        lineage=lineage_record('fx_feature_lineage_record',{'profile':PROFILE,
            'scheduled_input':dict(input_ref),'prefix_count':index+1,'reference_time':day,
            'evaluation_cutoff':cutoff,'operation':dict(feature_ref),'implementation':implementation,
            'policy_bindings':bindings,'dependency_semantics':'causal_prefix_audit_superset'})
        lineages.append(lineage)
        reason=point['reason']; value=point['value']
        observations.append({'materialization_id':mid,**selection,'reference_time':day,'evaluation_cutoff':cutoff,
            'available_at':None,'vintage_id':'CAPTURED_'+input_record['id'][8:],
            'value':value,'status':'valid' if value is not None else 'missing' if reason in
                ('MISSING_PERIOD','SOURCE_MISSING','MISSING_REQUIRED_OBSERVATION') else 'invalid',
            'reason_code':reason,'lineage':reference(lineage),'historical_eligibility_certified':False})
    return observations,lineages


def _metadata_for(feature,snapshot,compiled,bindings):
    recipe=feature['body']['recipe'];body=snapshot['body']
    return {'source_view':body['definition'],'dataset':None,'selection':recipe['selection'],
        'unit':compiled['unit'],'value_semantics':compiled['value_semantics'],
        'cadence':{'frequency':'daily','ordering':'reference_time','gap_policy':'explicit_missing',
                   'calendar':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0'},
        'history_policy':recipe['history_policy'],'source_policy_bindings':bindings,
        'history_mode':'resolved_state','temporal_precision':'date','availability_semantics':'unknown_historical_availability'}


def prepare_fx_feature(root, feature_ref, *, price_snapshot, batch_policy, knowledge_cutoff, start, end,
                       fail_at=None):
    """Prepare one bounded output interval, warming up on all earlier stored weekdays.

    start/end are inclusive dates. Actual dates and coverage belong to this
    materialization, never to the logical recipe. An entirely null result fails
    without publishing a completed manifest or a selectable Signal.
    """
    store=FeatureStore(root); feature=store.resolve(feature_ref)
    if feature['record_type']!='feature_definition': raise PublicationError('Expected a registered Feature recipe')
    for value in (knowledge_cutoff,start,end): normalize_time(value,'date')
    if start>end or end>knowledge_cutoff: raise PublicationError('Invalid bounded Feature output interval')
    if (date.fromisoformat(end)-date.fromisoformat(start)).days >= 366:
        raise PublicationError('The verification profile permits at most 366 calendar days per materialization')
    batch=_approved_policy(store,batch_policy)
    snapshot,prices=verified_prices(store,price_snapshot,batch,_price_snapshot)
    compiled=_compile(root,feature,snapshot,batch)
    input_record,dates,points=_window_calculation(store,feature,snapshot,prices,batch,compiled,knowledge_cutoff,end)
    if not any(day>=start for day in dates): raise PublicationError('Output interval has no scheduled weekdays')
    if not any(point['value'] is not None for day,point in zip(dates,points) if day>=start):
        raise PublicationError('No valid FX Feature observations; recipe remains registered only')
    recipe=feature['body']['recipe']; bindings=_bindings(recipe,batch)
    store.verify_closure([feature,snapshot,batch['approval_evidence'],batch['retrospective_policy']])
    with store.writer():
        implementation=_implementation(store,recipe); implementation_ref=reference(implementation)
        key={'definition':feature_ref,'source_snapshots':[price_snapshot],'implementation':implementation_ref,
            'policy_bindings':bindings,'batch_policy':batch,'knowledge_cutoff':knowledge_cutoff,
            'period':{'start_inclusive':start,'end_inclusive':end},'scheduled_input':reference(input_record)}
        mid=materialization_id(key)
        rows,lineages=_rows(feature,mid,input_record,dates,points,start,knowledge_cutoff,implementation_ref,bindings)
        if store.path(materialization_path(mid)).exists():
            old=read_fx_materialization(root,mid,research=True)
            if old['observations']!=rows: raise PublicationError('Conflicting immutable FX Feature result')
            entry=_publish_entry(store,feature,old['manifest'])
            return {'reused':True,'feature':feature_ref,'signal_id':feature['body']['signal_id'],
                'materialization':reference(old['manifest']),'entry':reference(entry),
                'row_count':len(rows),'status_counts':old['manifest']['status_counts']}
        from data.lineage_packs import storage_mode, install_records
        mode = storage_mode()
        for record in (implementation,input_record): store.install_record(record)
        if mode == 'packed_v1':
            install_records(store,lineages,fail_at=fail_at)
        else:
            for record in lineages: store.install_record(record)
        member=store.io.blob(b''.join(canonical_bytes(row)+b'\n' for row in rows),'jsonl','fx_feature_observations',len(rows))
        meta=_metadata_for(feature,snapshot,compiled,bindings)
        meta['dataset']=store.resolve(meta['source_view'])['body']['dataset']
        manifest={'schema_version':VERSION,'record_type':'materialization_manifest','version':'1.0.0','id':mid,
            'identity_profile':PROFILE,'dataset_role':'feature','definition':feature_ref,'input_key':key,
            'metadata':meta,'scheduled_input':reference(input_record),'lineage':[reference(item) for item in lineages],
            'partitions':[member],'row_count':len(rows),'status_counts':{s:sum(row['status']==s for row in rows)
                for s in ('valid','missing','invalid')},'reason_counts':dict(Counter(row['reason_code'] for row in rows if row['reason_code'])),
            'semantic_content_sha256':digest(rows),'readiness_capabilities':{
                'retrospective_research':{'decision':'ready','policy':batch['retrospective_policy']},
                'historical_replay':{'decision':'blocked','reason':'Historical source availability and complete vintages are unknown.'},
                'live_use':{'decision':'unresolved','reason':'Valuation clock, price basis and live eligibility remain unverified.'}}}
        validate_materialization(manifest,rows);store.verify_closure([manifest])
        if fail_at=='payloads': raise PublicationError('Injected interruption before completed Feature manifest')
        store.install_record(manifest)
        verified=read_fx_materialization(root,mid,research=True)
        entry=_publish_entry(store,feature,verified['manifest'])
    return {'reused':False,'feature':feature_ref,'signal_id':feature['body']['signal_id'],
        'materialization':reference(manifest),'entry':reference(entry),
        'row_count':len(rows),'status_counts':manifest['status_counts']}


def read_fx_materialization(root, identifier, *, research=False):
    if not research:
        from data.verified_inputs import fresh_inputs
        with fresh_inputs():
            return _read_fx_materialization(root, identifier)
    def verify():
        item = _read_fx_materialization(root, identifier)
        # Source operand trees are available through fresh inspection, not copied
        # into every cached research window. Full verification has already run.
        return {key: value for key, value in item.items() if key != 'operands'}
    return memo(root, 'fx_materialization', {'id': identifier}, verify)


def _read_fx_materialization(root, identifier):
    """Independently verify payload, full price provenance, causal lineage and arithmetic."""
    store=FeatureStore(root)
    manifest=strict_json(stable_read(store.path(materialization_path(identifier))))
    validate_record(manifest)
    if manifest['id']!=identifier: raise PublicationError('FX Feature path identity mismatch')
    rows=[]
    for member in manifest['partitions']:
        data=store.payload(member);part=[strict_json(line) for line in data.splitlines()]
        if data!=b''.join(canonical_bytes(row)+b'\n' for row in part) or len(part)!=member['row_count']:
            raise PublicationError('Noncanonical FX Feature observations')
        rows.extend(part)
    validate_materialization(manifest,rows);store.verify_closure([manifest])
    key=manifest['input_key'];feature=store.resolve(manifest['definition'])
    batch=_approved_policy(store,key['batch_policy'])
    snapshot,prices=verified_prices(store,key['source_snapshots'][0],batch,_price_snapshot)
    compiled=_compile(root,feature,snapshot,batch)
    input_record,dates,points=_window_calculation(store,feature,snapshot,prices,batch,compiled,
        key['knowledge_cutoff'],key['period']['end_inclusive'],verification=True)
    if reference(input_record)!=manifest['scheduled_input'] or store.resolve(manifest['scheduled_input'])!=input_record:
        raise PublicationError('Scheduled source lineage does not reproduce pinned price rows')
    bindings=_bindings(feature['body']['recipe'],batch)
    if bindings!=key['policy_bindings']: raise PublicationError('FX Feature policy bindings differ')
    expected,lineages=_rows(feature,identifier,input_record,dates,points,
        key['period']['start_inclusive'],key['knowledge_cutoff'],key['implementation'],bindings)
    if rows!=expected or manifest['lineage']!=[reference(item) for item in lineages]:
        raise PublicationError('FX Feature observations or causal lineage do not reproduce')
    for item in lineages:
        if store.resolve(reference(item))!=item: raise PublicationError('Conflicting Feature lineage')
    meta=_metadata_for(feature,snapshot,compiled,bindings)
    view=store.resolve(meta['source_view']);meta['dataset']=view['body']['dataset']
    if manifest['metadata']!=meta: raise PublicationError('FX Feature output metadata differs from exact recipe')
    return {'feature':feature,'manifest':manifest,'observations':rows,
        'operands':{input_record['id']:{'record':input_record,'price_snapshot':snapshot}},
        'metadata':{'dataset':store.resolve(meta['dataset']),'source_view':view}}
