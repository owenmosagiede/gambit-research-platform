"""Bounded legacy FX execution through existing registries and shared snapshots."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
from data.alfred_onboarding import strict_json, stable_read
from data.feature_store import FeatureStore
from data.fx_records import make_record, read_rows, write_rows
from data.transformations.identity import canonical_bytes, digest, reference
from data.targets.fx import readiness


def _install(store,kind,body,name=None):
    record=make_record(kind,body,name);store.install_record(record);return record


def _universe():
    from data.transformations.fx import INSTRUMENTS
    return INSTRUMENTS


def register_and_construct(root,onboarding,*,alignment_policy=None,preserve_completion=None):
    from data.transformations.fx import recipe, construct_prices, iter_construct_universe, normalize_legs
    from data.fx_onboarding import read_source
    store=FeatureStore(root)
    if alignment_policy is not None:
        from data.targets.fx import validate_alignment_evidence
        validate_alignment_evidence(store,alignment_policy)
    arithmetic=_install(store,'policy_definition',{'kind':'fx_price_determinism','version':'1.0.0',
        'arithmetic':'decimal_50_then_binary64_guard','missing':'retain_null','fallback':'none'})
    project=Path(__file__).resolve().parents[2]
    implementation={'schema_version':'0.2.0','record_type':'implementation_manifest','version':'1.0.0',
        'code_artifacts':[store.io.blob(stable_read(project/path),'txt',path.replace('/','_'),None) for path in
            ('src/data/transformations/fx.py','src/data/fx_pipeline.py','src/data/fx_records.py')],
        'environment_artifacts':[store.io.blob(canonical_bytes({'python':sys.version,'decimal_precision':50}),'json','fx_runtime',1)], 'entrypoint_id':'fx_pipeline_register_and_construct','determinism_policy':reference(arithmetic)}
    implementation['id']='IMPLEMENTATION_'+digest(implementation)
    store.install_record(implementation);implementation_ref=reference(implementation)
    sources={};metadata={};snapshots={}
    for source in onboarding['sources']:
        result=read_source(root,source['pit_snapshot'])
        sources[source['symbol']]=[{k:r[k] for k in ('reference_time','value','status','reason_code','lineage','available_at','original_ingested_at','vintage_id')} for r in result['observations']]
        for row in sources[source['symbol']]:
            row['original_ingested_at']=datetime.fromisoformat(row['original_ingested_at'].replace('Z','+00:00')).isoformat(timespec='microseconds').replace('+00:00','Z')
        metadata[source['symbol']]={k:source['metadata'][k] for k in ('base_currency','quote_currency','unit','price_field','price_basis','timing')}
        metadata[source['symbol']]['source_view']=source['source_view']
        snapshots[source['symbol']]=source['pit_snapshot']
    preserved={};leg_snapshots={}
    if preserve_completion is not None:
        prior=store.resolve(preserve_completion)
        prior_body=prior.get('body',{})
        if prior_body.get('kind')!='fx_universe_completion' or prior_body.get('source_snapshots')!=snapshots:
            raise ValueError('Preserved construction must pin these exact source snapshots')
        for binding in prior_body['instruments']:
            record=store.resolve(binding);item=record['body'];symbol=item['instrument_id']
            if item.get('kind')!='fx_instrument_registration' or symbol in preserved:
                raise ValueError('Invalid preserved instrument registration')
            if item['source_inputs']!=[snapshots[d] for d in item['dependencies']]:
                raise ValueError('Preserved instrument source inputs differ')
            if item['price_snapshot'] is not None and item['construction']['method']!='usd_triangulation':
                snapshot=store.resolve(item['price_snapshot']);store.verify_closure([snapshot])
                if snapshot['body']['instrument_id']!=symbol:raise ValueError('Preserved price instrument mismatch')
                preserved[symbol]={'instrument_id':symbol,'registration':binding,**item}
                for ref in snapshot['body']['normalized_legs']:
                    currency=store.resolve(ref)['body']['currency']
                    if currency in leg_snapshots and leg_snapshots[currency]!=ref:raise ValueError('Inconsistent preserved normalized leg')
                    leg_snapshots[currency]=ref
        from data.transformations.fx import DIRECT,INVERSE
        if set(preserved)!=set(DIRECT+INVERSE) or len(prior_body['instruments'])!=43:
            raise ValueError('Preservation requires the completed 18-price / 43-instrument universe')
    # Single-operand direct/inverse math is explicitly specified by this task.
    evidence=_install(store,'onboarding_evidence',{'kind':'fx_requested_single_source_construction',
        'authority':'user_request_2026_10_09','scope':'Five direct, thirteen inverse instruments; preserve unknown timing and price basis.',
        'retrospective_cross_approval':False})
    single={'id':'FX_SINGLE_SOURCE','version':'1.0.0','mode':'single_source_observation',
        'approval_state':'approved','approval_evidence':reference(evidence),'max_date_gap':0,'max_valuation_gap_seconds':None}
    # The numerical kernel normalizes each source once for the whole universe.
    # When cross approval is absent, only single-source constructions execute.
    prices=iter(iter_construct_universe(sources,alignment_policy=alignment_policy,source_metadata=metadata,single_source_policy=single)) if alignment_policy and not preserved else None
    normalized=normalize_legs(sources,source_metadata=metadata) if not preserved else {}
    for currency,leg_rows in normalized.items():
        symbol=next(symbol for symbol,meta in metadata.items() if currency in (meta['base_currency'],meta['quote_currency']) and currency!='USD')
        leg_snapshot=_install(store,'snapshot_manifest',{'kind':'fx_normalized_leg','profile':'fx_price.1.0.0',
            'currency':currency,'implementation':implementation_ref,'upstream_snapshots':[snapshots[symbol]],'members':write_rows(store,leg_rows,'normalized_fx_leg'),
            'semantic_content_sha256':digest(leg_rows),'record_count':len(leg_rows)},'Reusable normalized '+currency+' USD leg')
        leg_snapshots[currency]=reference(leg_snapshot)
    del normalized
    outputs=[]
    for instrument_id in _universe():
        if instrument_id in preserved:
            outputs.append(preserved[instrument_id]);continue
        specification=recipe(instrument_id,metadata)['body']
        method=specification['method']
        allowed=method!='usd_triangulation' or alignment_policy is not None
        active_policy=alignment_policy if method=='usd_triangulation' else single
        if allowed:specification=recipe(instrument_id,metadata,alignment_policy=active_policy)['body']
        recipe_record=_install(store,'transformation_definition',{'kind':'fx_price_recipe','profile':'fx_price.1.0.0',**specification},instrument_id+' canonical FX price recipe')
        deps=specification['source_symbols']
        base,quote=instrument_id[:3],instrument_id[3:]
        meta={'base_currency':base,'quote_currency':quote,'unit':f'{quote}_per_{base}','price_field':'close','price_basis':'unknown',
            'timing':{'timezone':None,'bar_boundary':None,'session_convention':None,'synchronization':'unverified'}}
        construction={'method':method,'version':'1.0.0','price_basis':'unknown','alignment':active_policy['mode'] if allowed else 'unresolved',
            'policy':reference(recipe_record)}
        dataset=_install(store,'dataset_definition',{'kind':'fx_constructed_dataset','profile':'fx_price.1.0.0','instrument_id':instrument_id,
            'economic_id':specification['economic_id'],'recipe':reference(recipe_record),'source_metadata':meta},instrument_id+' reusable price dataset')
        view=_install(store,'source_view_definition',{'kind':'fx_constructed_view','profile':'fx_price.1.0.0',
            'dataset':reference(dataset),'recipe':reference(recipe_record),'source_metadata':meta},instrument_id+' reusable close proxy')
        registration={'kind':'fx_instrument_registration','profile':'fx_price.1.0.0','instrument_id':instrument_id,
            'economic_id':specification['economic_id'],'recipe':reference(recipe_record),'definition':reference(view),'construction':construction,
            'dependencies':deps,'source_inputs':[snapshots[d] for d in deps],'account_eligibility':'unverified',
            'source_metadata':meta,'price_snapshot':None,'price_coverage':{'start':None,'end':None},'price_row_count':0,
            'readiness_capabilities':readiness(),'blockers':['RETROSPECTIVE_ALIGNMENT_APPROVAL_REQUIRED'] if not allowed else ([] if alignment_policy else ['RETURN_POLICY_APPROVAL_REQUIRED'])}
        if allowed:
            if prices is not None:
                generated_id,rows=next(prices)
                if generated_id!=instrument_id:raise ValueError('Universe construction order differs')
            else:rows=construct_prices(instrument_id,sources,alignment_policy=active_policy,source_metadata=metadata)
            dates=[r['reference_time'] for r in rows];valid=[r['reference_time'] for r in rows if r['status']=='valid']
            members=write_rows(store,rows,'canonical_fx_price')
            snapshot=_install(store,'snapshot_manifest',{'kind':'fx_constructed_prices','profile':'fx_price.1.0.0',
                'instrument_id':instrument_id,'economic_id':specification['economic_id'],'definition':reference(view),
                'recipe':reference(recipe_record),'implementation':implementation_ref,'construction':construction,'source_metadata':meta,
                'upstream_snapshots':[snapshots[d] for d in deps],'normalized_legs':[leg_snapshots[c] for c in (base,quote) if c!='USD'],'members':members,'record_count':len(rows),
                'semantic_content_sha256':digest(rows),'coverage':{'start':min(dates),'end':max(dates)},
                'valid_coverage':{'start':min(valid) if valid else None,'end':max(valid) if valid else None},
                'status_counts':dict(Counter(r['status'] for r in rows)),
                'reason_counts':dict(Counter(r['reason_code'] for r in rows if r['reason_code'])),
                'readiness_capabilities':readiness(alignment_policy is not None,len(valid),alignment_policy['approval_evidence'] if alignment_policy else None)},instrument_id+' reusable price observations')
            registration.update(price_snapshot=reference(snapshot),price_coverage=snapshot['body']['valid_coverage'],price_row_count=len(rows),
                readiness_capabilities=snapshot['body']['readiness_capabilities'])
        record=_install(store,'onboarding_evidence',registration,instrument_id+' construction and data readiness')
        outputs.append({'instrument_id':instrument_id,'registration':reference(record),**registration})
    # Immutable execution projection; each input+policy set identifies a separate
    # completed catalog run. There is no mutable list of claimed-ready symbols.
    run={'kind':'fx_universe_completion','profile':'fx_price.1.0.0','source_snapshots':snapshots,
        'alignment_policy':alignment_policy,'instruments':[o['registration'] for o in outputs]}
    if preserve_completion is not None:run['preserved_completion']=preserve_completion
    completion=_install(store,'onboarding_evidence',run,'Requested 43-instrument construction completion')
    return {'completion':reference(completion),'instruments':outputs}


def list_instruments(root, targets=()):
    store=FeatureStore(root);registrations={}
    # Registrations are projections of real definitions/snapshots, never readiness
    # inferred merely from presence in the requested universe.
    for path in store.path('storage/catalog/onboarding/evidence').glob('EVIDENCE_*.json'):
        value=strict_json(stable_read(path))
        if value.get('schema_version')!='0.5.0' or value.get('body',{}).get('kind')!='fx_instrument_registration':continue
        store._validate(value);body=value['body'];symbol=body['instrument_id']
        previous=registrations.get(symbol)
        # This selection is a display projection only, with exact refs exposed.
        # Prefer real populated prices over an earlier blocked registration.
        def rank(record):
            details=record['body'];snapshot=details['price_snapshot']
            pinned=bool(snapshot and store.resolve(snapshot)['body'].get('implementation'))
            return (pinned,details['price_row_count'],record['id'])
        if previous is None or rank(value)>rank(previous):registrations[symbol]=value
    result=[]
    for symbol,value in sorted(registrations.items()):
        body=value['body']; linked=[t for t in targets if t.get('instrument_id')==symbol]
        capabilities=linked[0]['readiness_capabilities'] if linked else body['readiness_capabilities']
        result.append({'instrument_id':symbol,'display_name':symbol,'economic_id':body['economic_id'],
            'construction':body['construction'],'dependencies':body['dependencies'],'source_inputs':body['source_inputs'],
            'price_coverage':body['price_coverage'],'price_row_count':body['price_row_count'],'price_snapshot':body['price_snapshot'],
            'target_ids':[t['target_id'] for t in linked],'readiness_capabilities':dict(capabilities,
                pit_inputs={'decision':'ready','reason':'Captured source snapshots; historical PIT uncertified.'},
                constructed_prices={'decision':'ready' if body['price_row_count'] else 'blocked','reason':None if body['price_row_count'] else 'Alignment approval required.'},
                return_targets={'decision':'ready' if linked else 'blocked','reason':None if linked else 'Return policy approval required.'}),
            'blockers':[] if linked else body['blockers'],'registration':reference(value)})
    return result
