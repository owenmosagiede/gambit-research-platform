"""Additive Submit contract. Historical experiment 0.1 identities are unchanged."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import hashlib, json, math, re, uuid

HORIZONS=(1,7,21,63,252)
KERNEL_POLICIES={'retained_legacy_v1':'legacy_failed_v1',
                 'scheduled_weekday_hac_v2':'unresolved_required_v1'}
class ResearchError(ValueError): pass
class ResearchConflict(ResearchError): pass
class ResearchBlocked(ResearchError):
    def __init__(self, blockers):
        self.blockers=blockers; super().__init__('; '.join(b['message'] for b in blockers))

def scientific(value):
    if type(value) is float:
        if not math.isfinite(value): raise ResearchError('Nonfinite research number')
        return format(value,'.17g')
    if type(value) is dict:
        if any(type(k) is not str for k in value):raise ResearchError('Non-string key')
        return {k:scientific(v) for k,v in value.items()}
    if type(value) in (list,tuple):return [scientific(v) for v in value]
    if type(value) not in (str,int,bool,type(None)):raise ResearchError('Unsupported research value')
    return value

def canonical(value):return json.dumps(scientific(value),sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def ref(value):return {'id':value['id'],'version':value.get('version','1.0.0'),'content_sha256':digest(value)}
def identifier(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,127}',value):raise ResearchError('Invalid identifier')
    return value

def request_id(value):
    try:
        if str(uuid.UUID(value))!=value:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise ResearchError('request_id must be a canonical UUID')
    return value

def exact_selection(value):
    if type(value) is not dict or set(value)!={'id','version'}:raise ResearchError('Exact id and version required')
    identifier(value['id'])
    if not re.fullmatch(r'\d+\.\d+\.\d+',str(value['version'])):raise ResearchError('Exact semantic version required')
    return deepcopy(value)

def normalize_submission(value):
    if type(value) is not dict or set(value)!={'request_id','feature','target_family','scope','expected_direction'}:
        raise ResearchError('Submit requires request_id, Feature, Target family, Scope and Expected Direction')
    request_id(value['request_id'])
    if value['target_family']!='price_return':raise ResearchError('Only the populated Price Return family is supported')
    if value['expected_direction'] not in ('POSITIVE','NEGATIVE'):raise ResearchError('Expected Direction must be frozen explicitly')
    return {'request_id':value['request_id'],'feature':exact_selection(value['feature']),
        'target_family':value['target_family'],'scope':exact_selection(value['scope']),
        'expected_direction':value['expected_direction']}

def profile_blockers(profile):
    blockers=[]
    def block(code,message):blockers.append({'code':code,'message':message})
    if not isinstance(profile,dict):return [{'code':'RESEARCH_PROFILE_MISSING','message':'A versioned backend Research Spec must be registered.'}]
    if profile.get('approval_state')!='approved':block('RESEARCH_PROFILE_PENDING','The installed Research Spec awaits explicit scientific compatibility decisions.')
    descriptions={
        'clock_compatibility':'Approve the statistical time-grid policy for scheduled-weekday Targets.',
        'retrospective_alignment':'Approve the retrospective date-label research alignment; historical availability remains unknown.',
        'validation_exposure':'Freeze evaluation periods and classify prior validation exposure.',
        'missing_evidence':'Choose the versioned treatment of unavailable P2 statistics.'}
    approvals=profile.get('approvals',{})
    if not isinstance(approvals,dict):approvals={}
    for name,message in descriptions.items():
        if approvals.get(name) is not True:block(name.upper()+'_PENDING',message)
    def iso_date(value):
        if type(value) is not str:raise ValueError()
        parsed=date.fromisoformat(value)
        if parsed.isoformat()!=value:raise ValueError()
        return parsed
    try:
        identifier(profile['id']);exact_selection({'id':profile['id'],'version':profile['version']})
        periods=profile['periods']
        for phase in ('P1','P2'):
            p=periods[phase]
            if set(p)!={'start_inclusive','end_exclusive'}:raise ValueError()
            end=iso_date(p['end_exclusive'])
            if phase=='P1' and p['start_inclusive'] is None and profile.get('discovery_start_rule')=='scope_structural_start_v1':
                if profile.get('kernel',{}).get('kernel_policy')!='scheduled_weekday_hac_v2':raise ValueError()
            elif not iso_date(p['start_inclusive'])<end:raise ValueError()
        if periods['P1']['end_exclusive']!='2022-01-01' or periods['P2']['start_inclusive']!='2022-01-01':raise ValueError()
        from research.schedule import validate_profile_schedule
        validate_profile_schedule(profile)
    except (KeyError,TypeError,ValueError,AttributeError):block('RESEARCH_PERIODS_UNRESOLVED','Freeze valid discovery and validation periods around the retained 2022-01-01 boundary.')
    if profile.get('availability_mode')!='retrospective_date_label':block('ALIGNMENT_UNSUPPORTED','This adapter requires an explicit retrospective date-label policy.')
    kernel=profile.get('kernel',{})
    if not isinstance(kernel,dict):kernel={}
    if (kernel.get('kernel_policy') not in KERNEL_POLICIES or kernel.get('clock_compatibility')!='approved'
        or kernel.get('horizon_unit')!='scheduled_weekdays' or type(kernel.get('spacing')) is not int or kernel.get('spacing')!=1
        or kernel.get('missing_evidence')!=KERNEL_POLICIES.get(kernel.get('kernel_policy'))):
        block('KERNEL_COMPATIBILITY_UNRESOLVED','Pin a supported versioned statistical clock and matching required-evidence policy.')
    try:iso_date(profile['target_selection']['knowledge_cutoff'])
    except (KeyError,TypeError,ValueError):block('SOURCE_CUTOFF_UNRESOLVED','Pin the source snapshot knowledge cutoff.')
    if not profile.get('exposure_classification'):block('EXPOSURE_CLASSIFICATION_MISSING','Research must identify historical exposure rather than assume an untouched holdout.')
    return blockers

def load_profile(root):
    p=Path(root)/'config/research_execution.json'
    if not p.is_file():return None
    from research.store import read_json
    configured=read_json(p)
    # Keep old flat snapshots readable for historical requests and isolated tests.
    # The installed policy uses an exact, verified immutable definition reference.
    if type(configured) is dict and set(configured)=={'research_spec'}:
        binding=configured['research_spec']
        if type(binding) is not dict or set(binding)!={'id','version','content_sha256'}:
            raise ResearchError('Research Spec requires an exact content reference')
        exact_selection({k:binding[k] for k in ('id','version')})
        from research.store import inside
        definition=inside(root,f"definitions/research_specs/{binding['id']}/{binding['version']}.json")
        value=read_json(definition)
        if ref(value)!=binding:raise ResearchError('Installed Research Spec identity/content differs')
        if definition.read_bytes()!=canonical(value)+b'\n':raise ResearchError('Noncanonical Research Spec definition')
        return value
    return configured

def readiness(root):
    profile=load_profile(root)
    from research.schedule import load_schedule, apply_schedule
    schedule=load_schedule(root)
    profile=apply_schedule(profile,schedule,price_time_series=True)
    blockers=profile_blockers(profile)
    horizons=list(schedule['horizons'] if schedule else HORIZONS)
    return {'implementation_installed':True,'execution_enabled':not blockers,'blockers':blockers,
        'method_summary':'Individual instrument: TS. Universe: CS only. Horizons: '+', '.join(map(str,horizons))+' scheduled weekdays.',
        'horizons':horizons,
        'research_spec':None if profile is None else {'id':profile.get('id'),'version':profile.get('version'),'content_sha256':digest(profile)},
        'production_research_launched_by_installation':False}
