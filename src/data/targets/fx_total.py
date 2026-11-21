"""Modelled FX funding P&L, separate from spot and executable broker returns."""
from bisect import bisect_right
from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, localcontext
from hashlib import sha256
from pathlib import Path
import gzip
import json
import re

from data import fx_funding as funding
from data.transformations.identity import canonical_bytes, digest, reference
from data.transformations.contracts import decimal_text, normalize_reference
from data.alfred_onboarding import stable_read, strict_json

SCHEMA=funding.SCHEMA
FAMILY='modelled_total_return'

def policy():
    return funding.record('policy_definition',{
        'kind':'fx_benchmark_funding_model_v1','approval_state':'approved',
        'source_model':'BIS_policy_proxies_plus_MAS_SORA','unsupported_currencies':['CNH'],
        'accrual':'daily_calendar_compounding','day_count':'ACT_365_FIXED',
        'rate_unit':'percent_per_year','borrow_lend':'same_benchmark',
        'formula':'spot_ratio_times_base_growth_minus_quote_growth',
        'normalization':'initial_quote_notional','short':'negative_long_under_symmetric_benchmark_model',
        'missing':'retain_null_never_zero','bis_missing':'hold_previous_only_for_declared_no_observation_days_max_7_calendar_days',
        'sora_accrual':'value_date_until_next_fixing_max_7_calendar_days',
        'source_timing':'retrospective_date_labels_publication_not_certified',
        'broker_markup':False,'execution_costs':False,'historical_pit_certified':False,
    },'Modelled FX total return · benchmark funding, before execution costs')

def _definition(spot, model):
    body=spot['body'];pair=body.get('instrument_id')
    # Compact spot definitions expose their pair via their economic identity.
    if pair is None:
        pair=body['sources'][0]['selection']['entity_id']
    if len(pair)!=6 or pair[:3] not in funding.SUPPORTED or pair[3:] not in funding.SUPPORTED or pair[:3]==pair[3:]:
        raise ValueError('Modelled financing excludes CNH and unsupported currency pairs')
    value={'schema_version':SCHEMA,'record_type':'target_definition','version':'1.0.0',
        'body':{'kind':'fx_modelled_total_return_v1','instrument_id':pair,
            'spot_target':reference(spot),'funding_model':model,
            'horizon':deepcopy(body['horizon']),'unit':'dimensionless_fraction','currency':pair[3:],
            'economic_coverage':'modelled_funding_before_execution_costs',
            'construction':{'basis':'total_return','representation':'simple','comparison':'none',
                            'instrument_basis':'total_return','benchmark_basis':None},
            'availability_mode':'retrospective_date_label','historical_pit_certified':False}}
    value['id']='TARGET_'+digest(value)
    value['display_name']=pair+' modelled total return '+str(body['horizon']['amount'])+' scheduled weekdays'
    return value

def validate_record(value):
    if value.get('record_type')=='target_materialization_manifest':return validate_manifest(value)
    if set(value)!={'schema_version','record_type','version','body','id','display_name'} or value['schema_version']!=SCHEMA:
        raise ValueError('Invalid modelled Target envelope')
    if value['record_type']!='target_definition' or value['version']!='1.0.0':raise ValueError('Unsupported modelled Target')
    body=value['body']
    if set(body)!={'kind','instrument_id','spot_target','funding_model','horizon','unit','currency','economic_coverage','construction','availability_mode','historical_pit_certified'}:
        raise ValueError('Invalid modelled Target definition fields')
    pair=body['instrument_id'];horizon=body['horizon']
    if len(pair)!=6 or pair[:3] not in funding.SUPPORTED or pair[3:] not in funding.SUPPORTED or pair[:3]==pair[3:]:
        raise ValueError('Unsupported modelled Target pair')
    normalize_reference(body['spot_target']);normalize_reference(body['funding_model'])
    if body['funding_model']!=reference(policy()):raise ValueError('Modelled Target policy differs')
    if body['kind']!='fx_modelled_total_return_v1' or body['unit']!='dimensionless_fraction' or body['currency']!=pair[3:] or body['historical_pit_certified'] is not False:
        raise ValueError('Modelled Target semantics differ')
    if horizon.get('amount') not in (1,7,21,63,252):raise ValueError('Unsupported financing horizon')
    fixed={'construction':{'basis':'total_return','representation':'simple','comparison':'none',
                          'instrument_basis':'total_return','benchmark_basis':None},
           'availability_mode':'retrospective_date_label','economic_coverage':'modelled_funding_before_execution_costs'}
    if any(body[k]!=v for k,v in fixed.items()) or horizon.get('unit')!='scheduled_bars':
        raise ValueError('Modelled Target construction or time grid differs')
    bare={k:v for k,v in value.items() if k not in ('id','display_name')}
    if value['id']!='TARGET_'+digest(bare):raise ValueError('Modelled Target identity differs')
    return value

class Rates:
    def __init__(self, rows):
        self.rows=rows
        self.days={c:[r['date'] for r in v] for c,v in rows.items()}
        self.exact={c:{r['date']:r for r in v} for c,v in rows.items()}
        self.accrual={}
        for currency,values in rows.items():
            previous=None;last_date=None;days={}
            for row in values:
                when=date.fromisoformat(row['date'])
                if last_date is not None and (when-last_date).days!=1:previous=None
                if row['rate_pct'] is not None:previous=row
                elif not row['observation_status'].startswith('M: Missing value; data cannot exist'):
                    previous=None
                days[row['date']]=(previous if previous is not None and
                    (when-date.fromisoformat(previous['date'])).days<=7 else None)
                last_date=when
            self.accrual[currency]=days

    def factor(self,currency,start,end):
        start=date.fromisoformat(start);end=date.fromisoformat(end)
        if end<=start or (end-start).days>4000:raise ValueError('Invalid financing interval')
        operands=[];growth=Decimal(1)
        with localcontext() as context:
            context.prec=50
            for offset in range((end-start).days):
                day=(start+timedelta(days=offset)).isoformat()
                if currency=='SGD':
                    index=bisect_right(self.days[currency],day)-1
                    if index<0 or index+1>=len(self.days[currency]):return None,None
                    row=self.rows[currency][index]
                    if (date.fromisoformat(self.days[currency][index+1])-date.fromisoformat(row['date'])).days>7:
                        return None,None
                else:row=self.accrual[currency].get(day)
                if row is None or row['rate_pct'] is None:return None,None
                rate=Decimal(row['rate_pct'])/Decimal(100)
                multiplier=1+rate/Decimal(365)
                if multiplier<=0:raise ValueError('Nonpositive daily financing multiplier')
                growth*=multiplier
                operands.append({'accrual_date':day,'source_date':row['date'],
                                 'source_row_sha256':row['source_row_sha256'],'rate_pct':row['rate_pct']})
        return growth,digest(operands)

def construct(definition, spot_rows, rows, snapshot):
    validate_record(definition);pair=definition['body']['instrument_id'];rates=Rates(rows);output=[]
    for spot in spot_rows:
        status=spot['status'];reason=spot.get('reason_code');value=base=quote=None;proof=None
        if status=='valid':
            base,bproof=rates.factor(pair[:3],spot['entry_time'],spot['exit_time'])
            quote,qproof=rates.factor(pair[3:],spot['entry_time'],spot['exit_time'])
            if base is None or quote is None:
                status='unavailable';reason='FUNDING_NOT_AVAILABLE'
            else:
                with localcontext() as context:
                    context.prec=50
                    value=decimal_text((1+Decimal(spot['value']))*base-quote)
                proof=digest({'base':bproof,'quote':qproof})
        row={'schema_version':SCHEMA,'record_type':'target_observation','target':reference(definition),
            'instrument_id':pair,'prediction_anchor':spot['prediction_anchor'],
            'entry_time':spot['entry_time'],'exit_time':spot['exit_time'],
            'intended_end':spot.get('intended_end',spot['exit_time']),
            'status':status,'reason_code':reason,'value':value,
            'unit':'dimensionless_fraction','currency':pair[3:],
            'temporal_precision':'date','label_available_at':None,'historical_eligibility_certified':False,
            'spot_target_row_id':spot['id'],'spot_return':spot['value'],
            'base_growth':decimal_text(base) if base is not None else None,
            'quote_growth':decimal_text(quote) if quote is not None else None,
            'funding_snapshot':snapshot,'funding_inputs_sha256':proof,'operands':deepcopy(spot['operands'])}
        row['id']='TARGET_ROW_'+digest(row);output.append(row)
    return output

def _implementation():
    return {p.name:sha256(stable_read(p)).hexdigest() for p in (Path(__file__),Path(funding.__file__))}

def validate_manifest(value):
    fields={'schema_version','record_type','id','version','definition','state','input_key','partitions',
            'row_count','status_counts','semantic_content_sha256','research_readiness','funding_snapshot',
            'spot_materialization','funding_model','coverage','valid_coverage','reason_counts'}
    if set(value)!=fields or value['schema_version']!=SCHEMA or value['record_type']!='target_materialization_manifest' or value['state']!='ready':
        raise ValueError('Invalid modelled Target manifest')
    for key in ('definition','funding_snapshot','spot_materialization','funding_model'):normalize_reference(value[key])
    if value['funding_model']!=reference(policy()):raise ValueError('Target funding model differs')
    if value['id']!='MATERIALIZATION_'+digest(value['input_key']):raise ValueError('Modelled materialization identity differs')
    key=value['input_key']
    if set(key)!={'definition','funding_snapshot','spot_materialization','funding_model','implementation','output_sha256','temporal_precision'}:
        raise ValueError('Invalid modelled Target input key')
    if any(key[k]!=value[k] for k in ('definition','funding_snapshot','spot_materialization','funding_model')) or key['output_sha256']!=value['semantic_content_sha256']:
        raise ValueError('Modelled Target input/output binding differs')
    if sum(value['status_counts'].values())!=value['row_count'] or value['research_readiness'] not in ('uncertified','no_valid_labels'):
        raise ValueError('Modelled Target counts or certification differ')
    return value

def _coverage(rows):
    days=[r['prediction_anchor'] for r in rows]
    return {'start':min(days) if days else None,'end':max(days) if days else None}

def materialize(root,spot_materialization,funding_snapshot):
    from .service import read_materialization as read_spot
    from .store import TargetStore
    store=TargetStore(root);source=read_spot(root,spot_materialization['id'])
    if reference(source['manifest'])!=spot_materialization or source['manifest']['schema_version']!='0.5.0':
        raise ValueError('Modelled FX return requires an exact compact spot Target')
    snapshot,rates=funding.load(root,funding_snapshot)
    model=policy();definition=_definition(source['definition'],reference(model))
    rows=construct(definition,source['observations'],rates,funding_snapshot)
    key={'definition':reference(definition),'funding_snapshot':funding_snapshot,
         'spot_materialization':spot_materialization,'funding_model':reference(model),
         'implementation':_implementation(),'output_sha256':digest(rows),'temporal_precision':'date'}
    with store.writer():
        store.install_record(model);store.install_record(definition)
        groups={}
        for row in rows:groups.setdefault(row['prediction_anchor'][:4],[]).append(row)
        partitions=[]
        for year,values in sorted(groups.items()):
            data=gzip.compress(b'\n'.join(canonical_bytes(r) for r in values)+b'\n',mtime=0)
            partitions.append({'year':year,'payload':store.io.blob(data,'bin','modelled_fx_target_'+year,len(values)),
                               'row_count':len(values),'semantic_sha256':digest(values)})
        manifest={'schema_version':SCHEMA,'record_type':'target_materialization_manifest',
            'id':'MATERIALIZATION_'+digest(key),'version':'1.0.0','definition':reference(definition),
            'state':'ready','input_key':key,'partitions':partitions,'row_count':len(rows),
            'status_counts':dict(Counter(r['status'] for r in rows)),
            'reason_counts':dict(Counter(r['reason_code'] for r in rows if r['reason_code'])),
            'coverage':_coverage(rows),'valid_coverage':_coverage([r for r in rows if r['status']=='valid']),
            'semantic_content_sha256':digest(rows),'research_readiness':'uncertified' if any(r['status']=='valid' for r in rows) else 'no_valid_labels',
            'funding_snapshot':funding_snapshot,'spot_materialization':spot_materialization,'funding_model':reference(model)}
        store.verify_closure([manifest]);store.install_record(manifest)
    return {'definition':reference(definition),'materialization':reference(manifest)}

def read(root,identifier,*,period=None,spot_rows=None):
    from .store import TargetStore,materialization_path
    from .service import read_materialization as read_spot
    store=TargetStore(root);manifest=validate_manifest(strict_json(stable_read(store.path(materialization_path(identifier)))))
    definition=store.resolve(manifest['definition']);validate_record(definition)
    if period is None:
        source=read_spot(root,manifest['spot_materialization']['id'])
        if reference(source['manifest'])!=manifest['spot_materialization']:raise ValueError('Underlying spot reference differs')
        spot_rows=source['observations']
        if _definition(source['definition'],manifest['funding_model'])!=definition:
            raise ValueError('Modelled Target definition differs from the frozen spot definition')
    elif spot_rows is None:raise ValueError('Phase reads require verified phase-only spot operands')
    snapshot,rates=funding.load(root,manifest['funding_snapshot'])
    if period:
        bounded={c:[r for r in values if r['date']<period['end_exclusive']] for c,values in rates.items()}
        # Only the next fixing DATE is needed as an interval/calendar witness;
        # no later rate value is passed into a stage's reconstruction.
        successor=next((r for r in rates['SGD'] if r['date']>=period['end_exclusive']),None)
        if successor:bounded['SGD'].append(dict(successor,rate_pct=None))
        rates=bounded
    saved=[]
    for partition in manifest['partitions']:
        if period and not period['start_inclusive'][:4]<=partition['year']<=period['end_exclusive'][:4]:continue
        lines=gzip.decompress(store.payload(partition['payload'])).splitlines()
        if len(lines)!=partition['row_count']:raise ValueError('Modelled Target partition count differs')
        values=[]
        for line in lines:
            if period:
                dates={}
                for field in ('prediction_anchor','entry_time','exit_time'):
                    matches=re.findall(rb'"'+field.encode()+rb'":"(\d{4}-\d{2}-\d{2})"',line)
                    if len(matches)!=1:raise ValueError('Ambiguous Target phase boundary')
                    dates[field]=matches[0].decode('ascii')
                if not all(period['start_inclusive']<=d<period['end_exclusive'] for d in dates.values()):continue
            value=strict_json(line)
            if canonical_bytes(value)!=line:raise ValueError('Noncanonical modelled Target observation')
            values.append(value)
        if not period and digest(values)!=partition['semantic_sha256']:raise ValueError('Modelled Target partition semantics differ')
        saved.extend(values)
    expected=construct(definition,spot_rows,rates,manifest['funding_snapshot'])
    if saved!=expected:raise ValueError('Modelled Target does not reproduce its exact funding and spot operands')
    if period is None and (len(saved)!=manifest['row_count'] or digest(saved)!=manifest['semantic_content_sha256']):raise ValueError('Modelled Target semantic content differs')
    if period is None and (dict(Counter(r['status'] for r in saved))!=manifest['status_counts'] or
            _coverage(saved)!=manifest['coverage'] or _coverage([r for r in saved if r['status']=='valid'])!=manifest['valid_coverage'] or
            dict(Counter(r['reason_code'] for r in saved if r['reason_code']))!=manifest['reason_counts']):
        raise ValueError('Modelled Target summary or coverage differs')
    return {'definition':definition,'manifest':manifest,'observations':saved,
            'source_metadata':{'funding_snapshot':reference(snapshot),'funding_model':manifest['funding_model']}}

def catalog_item(definition, manifests):
    body=definition['body'];valid=[m for m in manifests if m['definition']==reference(definition)]
    caps={'retrospective_research':{'decision':'ready','policy':body['funding_model']},
          'historical_replay':{'decision':'blocked','reason':'Benchmark vintages and spot times are uncertified.'},
          'live_use':{'decision':'blocked','reason':'Not an executable broker financing model.'}}
    return {'target_id':definition['id'],'name':definition['display_name'],
        'instrument_id':body['instrument_id'],'investment_series':body['instrument_id'],
        'return_basis':'total_return','return_model':FAMILY,'representation':'simple','comparison':'none',
        'horizon':body['horizon'],'definition_version':definition['version'],'definition_state':'valid',
        'source_eligibility':'eligible' if valid else 'unverified','readiness':'uncertified' if valid else 'unmaterialized',
        'funding_model':body['funding_model'],'reason':'Modelled benchmark funding; historical timing and executable costs are uncertified.',
        'schedule':{'calendar_id':'RESEARCH_WEEKDAYS','calendar_version':'1.0.0','holiday_exclusions':False},
        'readiness_capabilities':caps,
        'coverage':valid[0]['valid_coverage'] if valid else {'start':None,'end':None},
        'materializations':[{'id':m['id'],'state':m['state'],'research_readiness':m['research_readiness'],
            'valid_count':m['status_counts'].get('valid',0),'row_count':m['row_count'],
            'coverage':m['valid_coverage'],
            'readiness_capabilities':caps} for m in valid]}
