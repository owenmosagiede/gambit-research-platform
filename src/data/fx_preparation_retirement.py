"""Explicit retirement of one obsolete operator bundle, never published research.

The request is a separately reviewed, exact inventory, not a directory wildcard.
No production commitments are embedded in source or tests. Runtime and incoming
references are checked again by the offline planner before any deletion.
"""
from pathlib import Path, PurePosixPath
import re
import subprocess
from research.contracts import digest

NAME='momentum-preparation-2026-10-17'
PREFIX='storage/catalog/operations/'+NAME+'/'
SERVICE='gambit-momentum-preparation-20261017.service'
INPUTS=('preparation-manifest.json','instrument-preparation-matrix.json','scope-coverage-matrix.json')
SCHEMA='obsolete_momentum_preparation_retirement_v1'


def validate_request(request):
    if not isinstance(request,dict) or set(request)!={'schema','prefix','files','bundle_sha256'}:
        raise ValueError('Invalid preparation retirement request')
    if request['schema']!=SCHEMA or request['prefix']!=PREFIX or not isinstance(request['files'],dict) or not request['files']:
        raise ValueError('Only the reviewed obsolete preparation bundle can be retired')
    for path,binding in request['files'].items():
        if not isinstance(path,str) or not path.startswith(PREFIX) or PurePosixPath(path).as_posix()!=path or '..' in PurePosixPath(path).parts:
            raise ValueError('Unsafe preparation retirement path')
        tail=path[len(PREFIX):]
        top=tail in (*INPUTS,'target-preflight-receipt.json','cloud-verify-all.jsonl') or re.fullmatch(r'release-[0-9a-f]{40}\.sha256',tail)
        progress=re.fullmatch(r'progress/[0-9a-f]{64}/(?:program|status|partial)\.json',tail)
        binding_file=re.fullmatch(r'progress/[0-9a-f]{64}/bindings/[A-Z]{6}/FEATURE_RECIPE_[0-9a-f]{64}\.json',tail)
        if not (top or progress or binding_file):raise ValueError('Unreviewed preparation file type: '+path)
        if (not isinstance(binding,dict) or set(binding)!={'sha256','bytes'} or not isinstance(binding['sha256'],str)
                or not re.fullmatch('[0-9a-f]{64}',binding['sha256']) or type(binding['bytes']) is not int or binding['bytes']<0):
            raise ValueError('Invalid preparation file commitment: '+path)
    if any(PREFIX+n not in request['files'] for n in INPUTS):raise ValueError('Missing frozen preparation inputs')
    hashes={n:request['files'][PREFIX+n]['sha256'] for n in INPUTS}
    if digest(hashes)!=request['bundle_sha256']:raise ValueError('Preparation input bundle digest differs')
    return request


def watch_options(request):
    if request is None:return {}
    validate_request(request)
    values={b['sha256'] for b in request['files'].values()}|{request['bundle_sha256']}
    values.update(p[len(PREFIX):].split('/')[1] for p in request['files'] if p.startswith(PREFIX+'progress/'))
    return {'watched_values':values,'watched_name':NAME}


def runtime_blockers():
    """Read-only Linux probe. Unknown state blocks; never stop or disable a unit."""
    blockers=[]
    try:
        units={SERVICE}
        # Include timers, drop-ins, and alternative units that use the old tool.
        for base in ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system'):
            for p in Path(base).rglob('*'):
                if not p.is_file() or p.suffix not in ('.service','.timer','.conf'):continue
                text='\n'.join(line for line in p.read_text(errors='replace').splitlines()
                    if line.strip()!='ExecStartPre=/usr/bin/systemctl stop '+SERVICE and not line.lstrip().startswith('#'))
                if NAME in text or 'prepare_momentum_population.py' in text or SERVICE in text:
                    units.add(p.name if p.suffix!='.conf' else p.parent.name.removesuffix('.d'))
        for unit in sorted(units):
            output=subprocess.check_output(['systemctl','show',unit,'--property=LoadState,ActiveState,MainPID,UnitFileState,TriggeredBy'],text=True,timeout=15)
            state=dict(line.split('=',1) for line in output.splitlines() if '=' in line)
            if (state.get('LoadState') not in ('loaded','masked','not-found') or state.get('ActiveState') not in ('inactive','failed')
                    or state.get('MainPID','0')!='0' or state.get('UnitFileState','') not in ('','disabled','static','masked','masked-runtime')
                    or state.get('TriggeredBy')):
                blockers.append('Preparation unit may run or be scheduled: '+unit)
        proc=Path('/proc')
        if not proc.is_dir():raise OSError('Linux process inventory unavailable')
        for p in proc.glob('[0-9]*/cmdline'):
            try:args=p.read_bytes().decode(errors='replace')
            except FileNotFoundError:continue
            if NAME in args or 'prepare_momentum_population.py' in args:
                blockers.append('Preparation process is active: '+p.parent.name)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        blockers.append('Cannot verify preparation runtime is inactive: '+type(exc).__name__)
    return blockers


def retirement_selection(root,index,request):
    from data.fx_currency_migration import RETIRED,_scopes
    from data.scopes import PAIR_IDS
    validate_request(request)
    blockers=runtime_blockers()
    actual={p:v for p,v in index.files.items() if p.startswith(PREFIX)}
    if actual!=request['files']:blockers.append('Preparation inventory differs: missing, changed or extra files')
    # Incoming references to paths, input hashes, file hashes, or operation IDs
    # block retirement even if they belong to history selected elsewhere.
    for path,value in index.dependencies():
        if not path.startswith(PREFIX):blockers.append('External consumer of preparation bundle: '+path+' -> '+value)
    try:
        records=index.records
        manifest=records[PREFIX+INPUTS[0]];matrix=records[PREFIX+INPUTS[1]];scopes=records[PREFIX+INPUTS[2]]
        if (not isinstance(manifest,dict) or not isinstance(matrix,list) or not isinstance(scopes,list)
                or _scopes(scopes)!=RETIRED|set(PAIR_IDS)):
            raise ValueError('Obsolete mixed-scope preparation inputs differ')
        programs={p.rsplit('/',1)[0] for p in actual if p.endswith('/program.json')}
        if not programs:raise ValueError('Missing preparation program evidence')
        for base in programs:
            program=records[base+'/program.json'];status=records[base+'/status.json']
            if (program.get('kind')!='momentum_discovery_preparation_v1' or program.get('research_executed') is not False
                    or digest(program)!=base.rsplit('/',1)[1]
                    or program.get('inputs')!={n:request['files'][PREFIX+n]['sha256'] for n in INPUTS}
                    or status.get('research_executed') is not False or status.get('status') not in ('paused','completed')):
                raise ValueError('Preparation program/status cannot be retired')
        receipt=records.get(PREFIX+'target-preflight-receipt.json')
        if receipt is not None and (receipt.get('research_executed') is not False or receipt.get('bundle_sha256')!=request['bundle_sha256']):
            raise ValueError('Preparation preflight receipt differs')
    except (KeyError,TypeError,AttributeError,ValueError) as exc:
        blockers.append('Unverifiable preparation evidence: '+str(exc))
    # Never broaden deletion on a failed check. Outgoing data references do not
    # transfer ownership of published Features, Targets, prices, or results.
    return (set(request['files']) if not blockers else set()),blockers
