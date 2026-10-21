"""Bounded FX price-snapshot adapter for the existing return Target service.

Targets remain 0.4 semantic definitions. 0.5 is an additive compact observation
and partition manifest representation for honestly unknown source availability.
The schedule resolver and return arithmetic are the existing Target kernels.
"""
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal, DecimalException, localcontext
import math
import re
from jsonschema.exceptions import ValidationError

from data.alfred_onboarding import strict_json, stable_read
from data.fx_records import make_record, read_rows, write_rows, schema_validator, validate_member
from data.transformations.identity import canonical_bytes, digest, reference
from data.transformations.contracts import normalize_time, normalize_reference, decimal_text, canonical_decimal, object_fields
from .contracts import create_definition, create_policy, validate_definition, REASONS
from .engine import _ratio
from .scheduling import resolve_intervals
from .store import TargetStore, TargetStoreError, materialization_path, InterruptedTargetPublication

PROFILE='target_fx_snapshot.1.0.0'
POLICY_FIELDS={'approval_state','approval_evidence','representation','horizons','calendar_id','calendar_version',
    'clock','entry','endpoint','retrospective_policy'}
RESEARCH_ALIGNMENT={'mode':'retrospective_date_label','max_date_gap':0,'max_valuation_gap_seconds':None}


def _coverage(rows, field='reference_time'):
    values=[row[field] for row in rows]
    return {'start':min(values) if values else None,'end':max(values) if values else None}


def _schema(record):
    error=next(schema_validator().iter_errors(record),None)
    if error is not None:raise TargetStoreError('Invalid FX structural schema: '+error.message)


def approved_choices(policy):
    """Exact machine-readable approval scope, also bound to immutable evidence."""
    return {**{key:deepcopy(policy[key]) for key in POLICY_FIELDS-{'approval_state','approval_evidence','retrospective_policy'}},
        'retrospective_alignment':deepcopy(RESEARCH_ALIGNMENT),
        'scope':'fx_gross_spot_price_returns',
        'schedule_semantics':{'weekdays':['Monday','Tuesday','Wednesday','Thursday','Friday'],
            'holiday_exclusions':False,'date_labels':'native_provider_dates','horizon_display_unit':'scheduled_weekdays',
            'entry_interpretation':'return_anchoring_only','anchor_counted_as_forward_increment':False},
        'alignment_semantics':{'unknown_timing':'allow_provisional_retrospective','known_incompatibility':'block',
            'historical_pit_certification':False,'live_execution_certification':False}}


def readiness(approved=False, valid_count=0, policy=None):
    return {'retrospective_research':{'decision':'ready' if approved and valid_count else 'blocked',
        'policy':policy,'reason':None if approved and valid_count else 'Approved retrospective policy and valid stored observations are required.'},
        'historical_replay':{'decision':'blocked','reason':'Historical publication times and complete source vintages are unavailable.'},
        'live_use':{'decision':'unresolved','reason':'Daily valuation timing, source price basis and live eligibility are unverified.'}}


def validate_batch_policy(policy):
    """A supported explicit scientific choice, never a new hidden default."""
    object_fields(policy,POLICY_FIELDS,path='FX return batch policy')
    if policy.get('approval_state')!='approved':raise TargetStoreError('FX return policy needs explicit approval')
    normalize_reference(policy['approval_evidence'])
    if policy['representation'] not in {'simple','log'}:raise TargetStoreError('Unsupported return representation')
    if type(policy['horizons']) is not list or not policy['horizons'] or any(type(h) is not int or h<=0 for h in policy['horizons']) or len(set(policy['horizons']))!=len(policy['horizons']):raise TargetStoreError('Explicit unique positive horizons required')
    if policy['calendar_id']!='RESEARCH_WEEKDAYS' or policy['calendar_version']!='1.0.0' or policy['clock']!='scheduled_bars':
        raise TargetStoreError('This bounded generator supports only the declared weekday research grid')
    if policy['entry']!={'rule':'anchor_mark','delay':{'amount':0,'unit':'calendar_days'}} or policy['endpoint']!={'rule':'exact','tolerance':{'amount':0,'unit':'calendar_days'}}:
        raise TargetStoreError('This bounded generator requires the approved zero-delay exact endpoints')
    normalize_reference(policy['retrospective_policy'])
    return deepcopy(policy)


def _approved_policy(store, policy):
    policy=validate_batch_policy(policy)
    evidence=store.resolve(policy['approval_evidence'])
    body=evidence.get('body',{})
    object_fields(body,{'kind','authority','decision_text','decision_time','approved_policy'},path='FX research approval')
    if evidence['record_type']!='onboarding_evidence' or body['kind']!='fx_research_approval' or body['authority']!='user_explicit_decision':
        raise TargetStoreError('A matching explicit research decision is required')
    if not isinstance(body['decision_text'],str) or not body['decision_text'].strip():raise TargetStoreError('Approval decision text is required')
    normalize_time(body['decision_time'],'utc_timestamp')
    if body['approved_policy']!=approved_choices(policy):raise TargetStoreError('Return policy exceeds or differs from the recorded approval')
    retrospective=store.resolve(policy['retrospective_policy'])
    expected={'kind':'fx_retrospective_policy','approval':policy['approval_evidence'],
        'mode':'retrospective_date_label','historical_replay':False,'live_use':False,
        'unknown_availability':'preserve_null','source_selection':'pinned_original_capture'}
    if retrospective['record_type']!='policy_definition' or retrospective.get('body')!=expected:
        raise TargetStoreError('An explicit pinned retrospective policy preserving unknown availability is required')
    return policy


def validate_alignment_evidence(store, alignment_policy):
    """Validate the recorded cross approval without authorizing any return rule."""
    from data.transformations.fx import normalize_alignment_policy
    alignment=normalize_alignment_policy(alignment_policy)
    if alignment['mode']!='retrospective_date_label':raise TargetStoreError('The bounded FX snapshot workflow requires approved retrospective date alignment')
    evidence=store.resolve(alignment['approval_evidence']);body=evidence.get('body',{})
    object_fields(body,{'kind','authority','decision_text','decision_time','approved_policy'},path='FX research approval')
    if evidence['record_type']!='onboarding_evidence' or body['kind']!='fx_research_approval' or body['authority']!='user_explicit_decision':raise TargetStoreError('Cross alignment requires an explicit research decision')
    normalize_time(body['decision_time'],'utc_timestamp')
    if not isinstance(body['decision_text'],str) or not body['decision_text'].strip() or body['approved_policy'].get('retrospective_alignment')!=RESEARCH_ALIGNMENT:
        raise TargetStoreError('Research approval does not authorize this retrospective alignment')
    return alignment


def _schedule(store, policy, first, last, *, install=True):
    """Expected grid generated from policy, never by dropping missing prices."""
    normalize_time(first,'date');normalize_time(last,'date')
    if first>last:raise TargetStoreError('Invalid source coverage')
    start=date.fromisoformat(first)
    try:end=date.fromisoformat(last)+timedelta(days=max(policy['horizons'])*2+14)
    except OverflowError as exc:raise TargetStoreError('Horizon exceeds supported calendar bounds') from exc
    marks=[];day=start
    while day<=end:
        if day.weekday()<5:
            text=day.isoformat();marks.append({'mark_id':'DATE_'+text,'time':text,'session_id':'DATE_'+text})
        day+=timedelta(days=1)
    schedule_policy=create_policy({'kind':'target_schedule','calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0',
        'timezone':'UTC','observation_convention':'retrospective_date_label','temporal_precision':'date','anchor_convention':'declared_marks'},
        'Declared weekday research grid; not a verified FX session calendar')
    if install:store.install_record(schedule_policy)
    config={'policy_id':schedule_policy['id'],'version':'1.0.0','temporal_precision':'date',
        'calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0','timezone':'UTC','observation_convention':'retrospective_date_label',
        'coverage_start':start.isoformat(),'coverage_end':end.isoformat(),'marks':marks}
    evidence=make_record('onboarding_evidence',{'kind':'declared_research_schedule','schedule':config,
        'approval':policy['approval_evidence'],'market_calendar_certified':False,'timezone_meaning':'date arithmetic only; does not establish source timezone'})
    if install:store.install_record(evidence)
    config['evidence']=reference(evidence)
    anchors={'mode':'market_schedule','mark_ids':[m['mark_id'] for m in marks if m['time']<=last]}
    return config,anchors,schedule_policy


def _definition(store, construction, policy, horizon, schedule_policy, *, install=True):
    body=construction['body']; meta=body['source_metadata'];view=body['definition']
    selection={'measure':'close','entity_id':body['instrument_id'],'dimensions':[]}
    econ=create_policy({'kind':'economic_source','source_view':view,'selection':selection,
        'instrument_id':body['instrument_id'],'investment_series_id':body['economic_id'],
        'instrument_class':'spot_fx','input_kind':'price','unit':meta['unit'],'value_semantics':'price',
        'temporal_precision':'date','cadence':{'frequency':'daily','ordering':'reference_time','gap_policy':'explicit_missing','calendar':'gregorian'},
        'history_policy':policy['retrospective_policy'],'currency':meta['quote_currency'],
        'base_currency':meta['base_currency'],'quote_currency':meta['quote_currency'],'quotation_direction':'quote_per_base',
        'calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0','timezone':'UTC','observation_convention':'retrospective_date_label',
        'economic_coverage':'gross_spot_price','adjustment_convention':'unadjusted_price','includes_income':False,
        'includes_corporate_actions':False,'period_representation':None,'availability_basis':'unknown',
        'vintage_capability':'pinned_state','availability_evidence_complete':False,'zero_terminal_allowed':False,
        'evidence':[body['recipe'],policy['approval_evidence']]},body['instrument_id']+' retrospective price semantics')
    outcome=create_policy({'kind':'outcome_selection','selection':'pinned_later','availability_basis':'unknown',
        'finalization_wait':{'amount':0,'unit':'calendar_days'},'label_precision_policy':'conservative_date_boundary',
        'unknown_availability':'allow_uncertified'})
    validity=create_policy({'kind':'mathematical_validity','missing':'retain_null','stale':'reject',
        'nonpositive_start':'retain_null','nonfinite':'reject_source','negative_end':'retain_null','zero_terminal':'source_contract','period_coverage':'exact_complete'})
    calc=create_policy({'kind':'return_calculation','calculation_version':'1.0.0','arithmetic':'decimal_50_then_binary64_guard'})
    if install:
        for item in (econ,outcome,validity,calc):store.install_record(item)
    definition=create_definition({'sources':[{'role':'instrument','source_view':view,'selection':selection,'economic_policy':reference(econ)}],
        'construction':{'basis':'price','representation':policy['representation'],'comparison':'none','instrument_basis':'price','benchmark_basis':None},
        'unit':'dimensionless_fraction' if policy['representation']=='simple' else 'natural_log_return','currency':meta['quote_currency'],
        'economic_coverage':'gross_spot_price','schedule_policy':reference(schedule_policy),'anchor_policy':{'mode':'market_schedule','anchor_set_id':None},
        'entry':policy['entry'],'horizon':{'amount':horizon,'unit':policy['clock'],'counting':'exclusive_entry'},'endpoint':policy['endpoint'],
        'outcome_policy':reference(outcome),'validity_policy':reference(validity),'calculation':reference(calc),
        'dependencies':[body['recipe'],policy['retrospective_policy'],policy['approval_evidence']]},
        f"{body['instrument_id']} - {horizon} scheduled weekdays - {policy['representation']} gross spot return")
    if install:store.install_record(definition)
    return definition


def _price_snapshot(store, binding, policy, *, verify_rows=True):
    """Bind the snapshot, dataset, view, recipe and source economic identities.

    Detailed reads replay the pure price construction from pinned canonical PIT
    inputs. Self-consistent hashes alone do not prove the price arithmetic.
    """
    from data.transformations.fx import instrument_spec, recipe, construct_prices, normalize_legs
    record=store.resolve(binding);body=record.get('body',{})
    profile=body.get('profile')
    if profile=='fx_currency_price.1.0.0':
        from data.transformations.fx_currency import instrument_spec, recipe, construct_prices
    if record['record_type']!='snapshot_manifest' or body.get('kind')!='fx_constructed_prices' or profile not in ('fx_price.1.0.0','fx_currency_price.1.0.0'):
        raise TargetStoreError('Target requires a canonical constructed FX price snapshot')
    spec=instrument_spec(body['instrument_id'])
    if body['economic_id']!=spec['economic_id']:raise TargetStoreError('FX economic identity mismatch')
    view=store.resolve(body['definition'])
    if not isinstance(view.get('body',{}).get('dataset'),dict):
        raise TargetStoreError('Price SourceView must bind an exact dataset')
    dataset=store.resolve(view['body']['dataset'])
    transformation=store.resolve(body['recipe']);recipe_body=transformation.get('body',{})
    if transformation['record_type']!='transformation_definition' or recipe_body.get('profile')!=profile:
        raise TargetStoreError('Not a canonical FX transformation recipe')
    expected_recipe=recipe(body['instrument_id'],recipe_body['sources'],recipe_body['alignment_policy'])
    if recipe_body!={'profile':profile,**expected_recipe['body']} or recipe_body['alignment_policy'] is None:
        raise TargetStoreError('FX recipe differs from the supported versioned construction')
    alignment=recipe_body['alignment_policy']
    if alignment['mode']=='retrospective_date_label' and alignment['approval_evidence']!=policy['approval_evidence']:
        raise TargetStoreError('Cross construction is not covered by the same explicit research decision')
    if alignment['mode']=='retrospective_date_label':validate_alignment_evidence(store,alignment)
    if alignment['mode'] not in {'single_source_observation','retrospective_date_label'}:
        raise TargetStoreError('This retrospective Target profile cannot claim exact valuation synchronization')
    meta={'base_currency':spec['base_currency'],'quote_currency':spec['quote_currency'],'unit':spec['unit'],
        'price_field':'close','price_basis':'unknown','timing':{'timezone':None,'bar_boundary':None,'session_convention':None,'synchronization':'unverified'}}
    if body['source_metadata']!=meta:raise TargetStoreError('Target source semantics differ from the bounded unknown-timing FX profile')
    expected_dataset={'kind':'fx_constructed_dataset','profile':profile,'instrument_id':spec['instrument_id'],
        'economic_id':spec['economic_id'],'recipe':body['recipe'],'source_metadata':meta}
    expected_view={'kind':'fx_constructed_view','profile':profile,'dataset':reference(dataset),'recipe':body['recipe'],'source_metadata':meta}
    if dataset['record_type']!='dataset_definition' or dataset['body']!=expected_dataset or view['record_type']!='source_view_definition' or view['body']!=expected_view:
        raise TargetStoreError('Price snapshot does not belong to its declared dataset and source view')
    expected_construction={'method':spec['method'],'version':'1.0.0','price_basis':'unknown','alignment':alignment['mode'],'policy':body['recipe']}
    if body['construction']!=expected_construction:raise TargetStoreError('Price construction metadata differs from its recipe')
    if not verify_rows:return record,None
    from data.fx_onboarding import read_source
    sources={};metadata={};upstreams={}
    for source_ref in body['upstream_snapshots']:
        source=read_source(store.root,source_ref);source_body=source['manifest']['body'];source_meta=source['metadata']
        symbol=source_meta['provider_symbol']
        if symbol in sources or symbol not in spec['source_symbols']:raise TargetStoreError('Duplicated or unrelated price source dependency')
        source_view=store.resolve(source_body['definition']);source_dataset=store.resolve(source_view['body']['dataset'])
        if source_view['body'].get('kind')!='fx_source_view' or source_dataset['body'].get('kind')!='fx_source_dataset' or source_view['body']['source_metadata']!=source_meta or source_dataset['body']['source_metadata']!=source_meta:
            raise TargetStoreError('Canonical PIT snapshot metadata disagrees with its source view/dataset')
        metadata[symbol]={key:source_meta[key] for key in ('base_currency','quote_currency','unit','price_field','price_basis','timing')}
        metadata[symbol]['source_view']=source_body['definition']
        sources[symbol]=[{key:row[key] for key in ('reference_time','value','status','reason_code','lineage','available_at','original_ingested_at','vintage_id')} for row in source['observations']]
        for row in sources[symbol]:
            if row['original_ingested_at'] is not None:
                row['original_ingested_at']=datetime.fromisoformat(row['original_ingested_at'].replace('Z','+00:00')).isoformat(timespec='microseconds').replace('+00:00','Z')
        upstreams[symbol]=source_ref
    if set(sources)!=set(spec['source_symbols']) or metadata!=recipe_body['sources']:
        raise TargetStoreError('Recipe source definitions differ from the pinned upstream snapshots')
    expected_legs=normalize_legs(sources,source_metadata=metadata);seen=set()
    for leg_ref in body['normalized_legs']:
        leg=store.resolve(leg_ref);leg_body=leg['body'];currency=leg_body['currency']
        if leg_body.get('kind')!='fx_normalized_leg' or leg_body.get('profile')!=profile or currency in seen or currency not in expected_legs:
            raise TargetStoreError('Invalid or duplicated normalized FX leg')
        values=read_rows(store,leg_body['members']);symbol=next(symbol for symbol in sources if currency in symbol.split('/'))
        if values!=expected_legs[currency] or leg_body['record_count']!=len(values) or leg_body['semantic_content_sha256']!=digest(values) or leg_body['upstream_snapshots']!=[upstreams[symbol]]:
            raise TargetStoreError('Normalized leg does not reproduce the pinned source input')
        seen.add(currency)
    if seen!=set(expected_legs):raise TargetStoreError('Incomplete normalized leg references')
    prices=read_rows(store,body['members'])
    expected=construct_prices(body['instrument_id'],sources,alignment_policy=alignment,source_metadata=metadata)
    if prices!=expected or digest(prices)!=body['semantic_content_sha256'] or len(prices)!=body['record_count'] or not prices:
        raise TargetStoreError('Price snapshot does not reproduce its pinned canonical operands')
    if (body['coverage']!=_coverage(prices) or body['valid_coverage']!=_coverage([p for p in prices if p['status']=='valid'])
            or body['status_counts']!=dict(Counter(p['status'] for p in prices)) or body['reason_counts']!=dict(Counter(p['reason_code'] for p in prices if p['reason_code']))):
        raise TargetStoreError('Price snapshot coverage or summary mismatch')
    return record,prices


def construct_rows(definition, prices, schedule, anchors, knowledge_cutoff):
    """Endpoint dependency only: an interior price is never selected or hashed."""
    normalize_time(knowledge_cutoff,'date');validate_definition(definition)
    body=definition['body']; intervals=resolve_intervals(schedule,anchors,body['entry'],body['horizon'],body['endpoint'])
    by_time={row['reference_time']:row for row in prices}
    if len(by_time)!=len(prices):raise TargetStoreError('Duplicate canonical price dates')
    rows=[]
    for interval in intervals:
        operands=[];value=None;reason=None;status='valid'
        if interval['exit_time']>=knowledge_cutoff:
            status='pending';reason='FUTURE_ENDPOINT'
        for role in ('entry','exit'):
            when=interval[role+'_time'];price=by_time.get(when)
            operands.append({'role':role,'reference_time':when,'price_observation_id':price['id'] if price else None})
        selected=[by_time.get(interval[key]) for key in ('entry_time','exit_time')]
        capture=[p.get('original_ingested_at') for p in selected if p and p.get('original_ingested_at')]
        for when in capture:normalize_time(when,'utc_timestamp')
        if status=='valid':
            if any(p is None for p in selected):status='missing';reason='MISSING_ENDPOINT'
            elif any(p['status']!='valid' for p in selected):
                # A known missing/invalid source endpoint is not immature merely
                # because its full operand capture cannot be established.
                status='invalid' if any(p['status']=='invalid' for p in selected) else 'missing';reason='SOURCE_INVALID' if status=='invalid' else 'SOURCE_MISSING'
            elif len(capture)!=2 or any(when[:10]>=knowledge_cutoff for when in capture):
                # A date cutoff proves only knowledge strictly before that day.
                # Capture proves current archived knowledge, never release time.
                status='pending';reason='ENDPOINT_NOT_AVAILABLE'
            else:
                try:
                    for price in selected:canonical_decimal(price['value'])
                    with localcontext() as ctx:
                        ctx.prec=50
                        result,reason=_ratio(Decimal(selected[0]['value']),Decimal(selected[1]['value']),body['construction']['representation'],False)
                        if reason:status='invalid'
                        elif not math.isfinite(float(result)):status='invalid';reason='NONFINITE_OUTPUT'
                        else:value=decimal_text(result)
                except (DecimalException,OverflowError):status='invalid';reason='NONFINITE_OUTPUT'
        # Historical publication remains unknown; actual archived capture is a
        # distinct dimension and never substitutes for historical label time.
        row={'schema_version':'0.5.0','record_type':'target_observation','target':reference(definition),
            'prediction_anchor':interval['prediction_anchor'],'entry_time':interval['entry_time'],'exit_time':interval['exit_time'],
            'intended_end':interval['intended_end'],'temporal_precision':'date','value':value,'status':status,'reason_code':reason,
            'operands':operands,'source_availability':None,'label_available_at':None,
            'original_capture_complete_at':max(capture) if len(capture)==2 else None,
            'historical_eligibility_certified':False,'maturity':'future_endpoint' if reason=='FUTURE_ENDPOINT' else 'elapsed_endpoint'}
        # Cutoff is manifest evidence. Once economically mature, extending the
        # cutoff cannot change this observation or unrelated partition identity.
        row['id']='TARGETOBS_'+digest(row);rows.append(row)
    return rows


def validate_row(row):
    required={'schema_version','record_type','target','prediction_anchor','entry_time','exit_time','intended_end','temporal_precision','value','status','reason_code','operands','source_availability','label_available_at','original_capture_complete_at','historical_eligibility_certified','maturity','id'}
    object_fields(row,required,path='Compact Target row');_schema(row)
    if row['schema_version']!='0.5.0' or row['record_type']!='target_observation' or row['temporal_precision']!='date':raise TargetStoreError('Invalid compact Target row')
    if row['id']!='TARGETOBS_'+digest({k:v for k,v in row.items() if k!='id'}):raise TargetStoreError('Target row digest mismatch')
    normalize_reference(row['target'])
    for name in ('prediction_anchor','entry_time','exit_time','intended_end'):normalize_time(row[name],'date')
    if not row['prediction_anchor']<=row['entry_time']<row['exit_time'] or row['exit_time']!=row['intended_end']:raise TargetStoreError('Target interval mismatch')
    if row['status']=='valid':
        canonical_decimal(row['value'])
        if row['reason_code'] is not None or not math.isfinite(float(Decimal(row['value']))):raise TargetStoreError('Invalid numeric Target')
    elif row['status'] not in {'pending','missing','invalid'} or row['value'] is not None or row['reason_code'] not in REASONS:raise TargetStoreError('Invalid null Target')
    if row['historical_eligibility_certified'] is not False or row['source_availability'] is not None or row['label_available_at'] is not None:raise TargetStoreError('Retrospective profile cannot certify historical availability')
    if row['original_capture_complete_at'] is not None:normalize_time(row['original_capture_complete_at'],'utc_timestamp')
    if row['status']=='valid' and row['original_capture_complete_at'] is None:raise TargetStoreError('Valid retrospective label requires known original captures')
    if row['status']=='pending' and row['reason_code'] not in {'FUTURE_ENDPOINT','ENDPOINT_NOT_AVAILABLE'}:raise TargetStoreError('Invalid pending FX label reason')
    if row['maturity']!=('future_endpoint' if row['reason_code']=='FUTURE_ENDPOINT' else 'elapsed_endpoint'):raise TargetStoreError('Label maturity differs from endpoint reason')
    if type(row['operands']) is not list or len(row['operands'])!=2:raise TargetStoreError('Exactly two endpoint operands required')
    for role,operand in zip(('entry','exit'),row['operands']):
        object_fields(operand,{'role','reference_time','price_observation_id'},path='Target endpoint')
        if operand['role']!=role or operand['reference_time']!=row[role+'_time']:raise TargetStoreError('Target endpoint role or date mismatch')
        identifier=operand['price_observation_id']
        if identifier is not None and (not isinstance(identifier,str) or not re.fullmatch('FXPRICE_[a-f0-9]{64}',identifier)):raise TargetStoreError('Invalid price operand identity')
        if row['status']=='valid' and identifier is None:raise TargetStoreError('Valid Target requires both endpoint prices')
    return row


def validate_manifest(record):
    fields={'schema_version','record_type','id','version','definition','state','input_key','partitions','row_count','status_counts','reason_counts','coverage','valid_coverage','research_readiness','readiness_capabilities','semantic_content_sha256','price_snapshot','schedule','implementation'}
    object_fields(record,fields,path='Compact Target manifest');_schema(record)
    if record['schema_version']!='0.5.0' or record['record_type']!='target_materialization_manifest' or record['state']!='ready' or record['version']!='1.0.0':raise TargetStoreError('Invalid compact Target manifest')
    key=record['input_key']
    object_fields(key,{'identity_profile','definition','price_snapshot','schedule_sha256','anchors_sha256','knowledge_cutoff','implementation','output_sha256','approval','temporal_precision','batch_policy'},path='FX Target input key')
    if record['id']!='MATERIALIZATION_'+digest(key) or key['identity_profile']!=PROFILE:raise TargetStoreError('Target build identity mismatch')
    if key['temporal_precision']!='date':raise TargetStoreError('Wrong FX Target precision')
    normalize_time(key['knowledge_cutoff'],'date');validate_batch_policy(key['batch_policy'])
    for name in ('definition','price_snapshot','implementation'):
        normalize_reference(record[name])
        if record[name]!=key[name]:raise TargetStoreError('Target manifest/input binding mismatch')
    if key['approval']!=key['batch_policy']['approval_evidence']:raise TargetStoreError('Target approval binding mismatch')
    for name in ('output_sha256','schedule_sha256','anchors_sha256'):
        if not isinstance(key[name],str) or not re.fullmatch('[a-f0-9]{64}',key[name]):raise TargetStoreError('Invalid semantic content digest')
    if key['output_sha256']!=record['semantic_content_sha256']:raise TargetStoreError('Target output digest mismatch')
    if type(record['row_count']) is not int or record['row_count']<=0:raise TargetStoreError('Empty or invalid Target materialization')
    for field,allowed in (('status_counts',{'valid','missing','invalid','pending'}),('reason_counts',REASONS)):
        counts=record[field]
        if type(counts) is not dict or set(counts)-allowed or any(type(n) is not int or n<=0 for n in counts.values()):raise TargetStoreError('Invalid Target summary counts')
    if sum(record['status_counts'].values())!=record['row_count'] or sum(record['reason_counts'].values())!=record['row_count']-record['status_counts'].get('valid',0):raise TargetStoreError('Target summary count mismatch')
    for field in ('coverage','valid_coverage'):
        value=record[field];object_fields(value,{'start','end'},path=field)
        if value['start'] is None or value['end'] is None:
            if value!={'start':None,'end':None} or field!='valid_coverage' or record['status_counts'].get('valid',0):raise TargetStoreError('Invalid empty Target coverage')
        else:
            for when in value.values():normalize_time(when,'date')
            if value['start']>value['end']:raise TargetStoreError('Reversed Target coverage')
    if record['research_readiness']!='uncertified' or record['readiness_capabilities']!=readiness(True,record['status_counts'].get('valid',0),key['batch_policy']['retrospective_policy']):raise TargetStoreError('Unsupported Target readiness claim')
    validate_member(record['schedule'])
    if record['schedule']['role']!='target_schedule' or record['schedule']['format']!='json' or record['schedule']['row_count']!=record['row_count']:raise TargetStoreError('Invalid Target schedule payload')
    if type(record['partitions']) is not list or not record['partitions']:raise TargetStoreError('Missing Target observations')
    seen=set()
    for member in record['partitions']:
        validate_member(member)
        if member['role']!='target_observations' or member.get('codec')!='gzip_jsonl' or member.get('partition') in seen:raise TargetStoreError('Invalid or repeated Target partition')
        if type(member['row_count']) is not int or member['row_count']<=0:raise TargetStoreError('Invalid Target partition length')
        seen.add(member['partition'])
    if sum(m['row_count'] for m in record['partitions'])!=record['row_count']:raise TargetStoreError('Target partition count mismatch')
    return record


def materialize(root, price_snapshot, policy, *, knowledge_cutoff, fail_at=None):
    store=TargetStore(root);policy=_approved_policy(store,policy)
    normalize_time(knowledge_cutoff,'date')
    construction,prices=_price_snapshot(store,price_snapshot,policy);body=construction['body']
    store.verify_closure([construction,policy['approval_evidence'],policy['retrospective_policy']])
    config,anchors,schedule_policy=_schedule(store,policy,body['coverage']['start'],body['coverage']['end'])
    from .service import _implementation
    calc=create_policy({'kind':'return_calculation','calculation_version':'1.0.0','arithmetic':'decimal_50_then_binary64_guard'})
    implementation=_implementation(store,calc,config)
    results=[]
    for horizon in policy['horizons']:
        definition=_definition(store,construction,policy,horizon,schedule_policy)
        observations=construct_rows(definition,prices,config,anchors,knowledge_cutoff)
        if not observations:raise TargetStoreError('Source has no anchors on the approved research schedule')
        for row in observations:validate_row(row)
        schedule=store.io.blob(canonical_bytes({'schedule':config,'anchors':anchors}),'json','target_schedule',len(observations))
        output=digest(observations)
        key={'identity_profile':PROFILE,'definition':reference(definition),'price_snapshot':price_snapshot,
             'schedule_sha256':digest(config),'anchors_sha256':digest(anchors),'knowledge_cutoff':knowledge_cutoff,
             'implementation':implementation,'output_sha256':output,'approval':policy['approval_evidence'],'temporal_precision':'date','batch_policy':policy}
        identifier='MATERIALIZATION_'+digest(key);reused=store.path(materialization_path(identifier)).is_file()
        with store.writer():
            partitions=write_rows(store,observations,'target_observations')
            if fail_at=='payloads':raise InterruptedTargetPublication('Before Target manifest commit')
            good=[r['prediction_anchor'] for r in observations if r['status']=='valid']; dates=[r['prediction_anchor'] for r in observations]
            manifest={'schema_version':'0.5.0','record_type':'target_materialization_manifest','id':identifier,'version':'1.0.0',
                'definition':reference(definition),'state':'ready','input_key':key,'partitions':partitions,'row_count':len(observations),
                'status_counts':dict(Counter(r['status'] for r in observations)),
                'reason_counts':dict(Counter(r['reason_code'] for r in observations if r['reason_code'])),
                'coverage':{'start':min(dates),'end':max(dates)},'valid_coverage':{'start':min(good) if good else None,'end':max(good) if good else None},
                'research_readiness':'uncertified','readiness_capabilities':readiness(True,len(good),policy['retrospective_policy']),
                'semantic_content_sha256':output,'price_snapshot':price_snapshot,'schedule':schedule,'implementation':implementation}
            validate_manifest(manifest);store.verify_closure([manifest]);store.install_record(manifest)
        results.append({'target_id':definition['id'],'materialization':reference(manifest),'reused':reused,'row_count':len(observations),'status_counts':manifest['status_counts'],'reason_counts':manifest['reason_counts']})
    return results


def read_materialization(root, materialization_id):
    store=TargetStore(root);manifest=validate_manifest(strict_json(stable_read(store.path(materialization_path(materialization_id)))))
    if manifest['id']!=materialization_id:raise TargetStoreError('Target path mismatch')
    store.verify_closure([manifest]);definition=store.resolve(manifest['definition']);validate_definition(definition)
    observations=read_rows(store,manifest['partitions'])
    if digest(observations)!=manifest['semantic_content_sha256'] or len(observations)!=manifest['row_count']:raise TargetStoreError('Target persisted content mismatch')
    for row in observations:validate_row(row)
    policy=_approved_policy(store,manifest['input_key']['batch_policy'])
    construction,prices=_price_snapshot(store,manifest['price_snapshot'],policy);by_id={p['id']:p for p in prices}
    for row in observations:
        if row['target']!=manifest['definition']:raise TargetStoreError('Target definition mismatch')
        for operand in row['operands']:
            if operand['price_observation_id'] is not None:
                price=by_id.get(operand['price_observation_id'])
                if price is None or price['reference_time']!=operand['reference_time']:raise TargetStoreError('Target endpoint lineage mismatch')
    schedule=strict_json(store.payload(manifest['schedule']))
    object_fields(schedule,{'schedule','anchors'},path='Stored Target schedule')
    config,anchors,schedule_policy=_schedule(store,policy,construction['body']['coverage']['start'],construction['body']['coverage']['end'],install=False)
    if schedule!={'schedule':config,'anchors':anchors} or digest(config)!=manifest['input_key']['schedule_sha256'] or digest(anchors)!=manifest['input_key']['anchors_sha256']:
        raise TargetStoreError('Target schedule differs from the approved research grid and source coverage')
    horizon=definition['body']['horizon']['amount']
    if horizon not in policy['horizons'] or reference(_definition(store,construction,policy,horizon,schedule_policy,install=False))!=manifest['definition']:
        raise TargetStoreError('Target definition differs from its approved source and return policy')
    expected=construct_rows(definition,prices,schedule['schedule'],schedule['anchors'],manifest['input_key']['knowledge_cutoff'])
    if expected!=observations:raise TargetStoreError('Stored returns do not match pinned endpoints and schedule')
    if (dict(Counter(r['status'] for r in observations))!=manifest['status_counts']
            or dict(Counter(r['reason_code'] for r in observations if r['reason_code']))!=manifest['reason_counts']
            or _coverage(observations,'prediction_anchor')!=manifest['coverage']
            or _coverage([r for r in observations if r['status']=='valid'],'prediction_anchor')!=manifest['valid_coverage']):
        raise TargetStoreError('Target summary or coverage mismatch')
    for member in manifest['partitions']:
        values=read_rows(store,[member])
        if member['coverage']!=_coverage(values,'prediction_anchor') or any(row['prediction_anchor'][:4]!=member['partition'] for row in values):
            raise TargetStoreError('Target partition coverage mismatch')
    return {'definition':definition,'manifest':manifest,'observations':observations,'schedule':schedule,
        'operand_lineage':{'price_snapshot':manifest['price_snapshot'],'semantics':'Each observation references exactly its entry and exit price row; price operands resolve to source PIT rows.'},
        'source_metadata':construction['body']['source_metadata'],'readiness_capabilities':manifest['readiness_capabilities']}


def affected_labels(observations, changed_price_ids):
    """Exact endpoint reverse dependency projection; never holding-window overlap."""
    changed=set(changed_price_ids)
    return [row['id'] for row in observations if any(op['price_observation_id'] in changed for op in row['operands'])]


def catalog_targets(root):
    store=TargetStore(root);items=[]
    for path in sorted(store.path('storage/catalog/target_store').glob('*/manifest.json')):
        try:
            value=strict_json(stable_read(path))
            if not isinstance(value,dict) or value.get('schema_version')!='0.5.0':continue
            manifest=validate_manifest(value);definition=store.resolve(manifest['definition']);body=definition['body']
            policy=_approved_policy(store,manifest['input_key']['batch_policy'])
            snapshot,_=_price_snapshot(store,manifest['price_snapshot'],policy,verify_rows=False);price=snapshot['body']
            if path.parent.name!=manifest['id'] or body['sources'][0]['source_view']!=price['definition']:raise TargetStoreError('Target catalog ownership mismatch')
            schedule_policy=store.resolve(body['schedule_policy'])
            if body['horizon']['amount'] not in policy['horizons'] or reference(_definition(store,snapshot,policy,body['horizon']['amount'],schedule_policy,install=False))!=manifest['definition']:
                raise TargetStoreError('Catalog Target differs from its approved scientific definition')
            # Catalog reads verify compact manifests and checksum payloads without
            # decompressing/recalculating millions of observations. Detail does that.
            store.verify_closure([manifest])
            items.append({'target_id':definition['id'],'name':definition['display_name'],'instrument_id':price['instrument_id'],
                'investment_series':price['economic_id'],'return_basis':body['construction']['basis'],'representation':body['construction']['representation'],
                'comparison':body['construction']['comparison'],'horizon':body['horizon'],
                'schedule':{'calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0','holiday_exclusions':False},
                'schedule_policy':body['schedule_policy'],'definition_version':definition['version'],
                'source_eligibility':'eligible','definition_state':'valid','readiness':'uncertified','reason':'Provisional retrospective research only; historical timing uncertified.',
                'coverage':manifest['valid_coverage'],'construction':price['construction'],'readiness_capabilities':manifest['readiness_capabilities'],
                'materializations':[{'id':manifest['id'],'state':'ready','research_readiness':'uncertified','valid_count':manifest['status_counts'].get('valid',0),
                    'row_count':manifest['row_count'],'coverage':manifest['valid_coverage'],'readiness_capabilities':manifest['readiness_capabilities'],'reason':'Provisional retrospective research only'}]})
        except (ValueError,OSError,KeyError,TypeError,ValidationError):
            continue
    grouped={}
    for item in items:
        if item['target_id'] in grouped:grouped[item['target_id']]['materializations']+=item['materializations']
        else:grouped[item['target_id']]=item
    return list(grouped.values())
