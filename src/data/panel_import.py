"""Versioned, read-only projections of frozen panel packages (record profile .11).

The package databases are the operands, not an invented ratio or new estimate of
publication time. One immutable database is shared by all its field projections.
Readers hash bytes before opening SQLite, query explicit selectors, retain null
updates, and never extend a frozen package into the future.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import zipfile

from data.alfred_onboarding import stable_read, strict_json
from data.transformations.identity import (canonical_bytes, digest, feature_id,
    signal_id, normalize_recipe, reference)
from data.transformations.contracts import normalize_reference, token

SCHEMA = '0.11.0'
VERSION = '1.0.0'
KINDS = {'macro', 'common', 'etf', 'expansion'}
LAYERS = {'archive', 'capture', 'retrospective'}
FILES = {'macro': ('gambit-macro-panels', 'panels.sqlite'),
         'common': ('gambit-common-panels', 'common.sqlite'),
         'etf': ('gambit-cross-asset-etf-panels', 'panels.sqlite'),
         'expansion': ('gambit-market-expansion', 'market.sqlite')}
PREFIXES = {'provider_contract': 'PROVIDER', 'dataset_definition': 'DATASET',
    'source_view_definition': 'SOURCE_VIEW', 'transformation_definition': 'TRANSFORM',
    'policy_definition': 'POL', 'snapshot_manifest': 'SNAPSHOT'}


def fail(message):
    raise ValueError('Frozen panel: ' + message)


def scientific(value):
    if isinstance(value, float):
        if not math.isfinite(value): fail('nonfinite source value')
        return str(value)
    if isinstance(value, dict): return {k: scientific(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [scientific(v) for v in value]
    return value


def utc(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None: fail('explicit timezone required')
    return parsed.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def file_hash(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file(): fail('ordinary file required')
    before = path.stat()
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b''): h.update(block)
    after = path.stat()
    if witness(before) != witness(after): fail('file changed while hashing')
    return {'sha256': h.hexdigest(), 'byte_count': after.st_size}


def witness(stat):
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def payload_path(root, member, suffix):
    sha = member['sha256']
    if not re.fullmatch('[0-9a-f]{64}', sha): fail('invalid payload hash')
    from data.feature_store import FeatureStore
    return FeatureStore(root).path(f'storage/payloads/sha256/{sha[:2]}/{sha}.{suffix}')


def install_payload(root, source, expected, suffix):
    """Stream a new immutable blob; do not share a writable staging inode."""
    if file_hash(source) != expected: fail('source fingerprint drift')
    target = payload_path(root, expected, suffix)
    if target.exists():
        if file_hash(target) != expected: fail('existing payload differs')
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.panel-', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as out, Path(source).open('rb') as inp:
            shutil.copyfileobj(inp, out, 4 * 1024 * 1024)
            out.flush(); os.fsync(out.fileno())
        if file_hash(tmp) != expected: fail('payload copy differs')
        os.chmod(tmp, 0o440)
        try: os.link(tmp, target)
        except FileExistsError:
            if file_hash(target) != expected: fail('publication collision')
    finally:
        Path(tmp).unlink(missing_ok=True)


def verify_archive(archive, folder, expected):
    with zipfile.ZipFile(archive) as bundle:
        names=bundle.namelist()
        if len(names) != len(set(names)): fail('duplicate archive member')
        for name,member in expected.items():
            native=folder.name+'/'+name
            info=bundle.getinfo(native)
            if info.file_size != member['byte_count']: fail('archive member size differs')
            h=hashlib.sha256()
            with bundle.open(info) as inp:
                for block in iter(lambda:inp.read(4*1024*1024),b''):h.update(block)
            if h.hexdigest() != member['sha256']: fail('database/evidence differs from original archive')


@contextmanager
def connect(path):
    path = Path(path).resolve()
    db = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
    db.row_factory = sqlite3.Row
    try: yield db
    finally: db.close()


def record(kind, body, name):
    body = scientific(body)
    return {'schema_version': SCHEMA, 'record_type': kind,
        'id': PREFIXES[kind] + '_' + digest({'kind': kind, 'body': body}),
        'version': VERSION, 'display_name': name, 'body': body}


def policy_record():
    return record('policy_definition', {'kind': 'frozen_panel_projection_v1',
        'approval_state': 'approved', 'parameters': [],
        'rules': ['preserve original model masks and source field units',
            'no candidate promotion, interpolation, fitting or price-to-flow substitution',
            'archive, capture and retrospective are different Features',
            'strict UTC availability before target anchor at 00 UTC',
            'original validity intervals, staleness and frozen ceiling apply',
            'capture snapshots do not create historical training observations',
            'pair projections only match their exact canonical pair',
            'common series have no automatic currency exposure or CS broadcast',
            'source-date archives are not certified intraday or live feeds']},
        'Frozen panel eligibility and projection')


def operator_record():
    return record('transformation_definition', {'kind': 'frozen_panel_field_v1',
        'operation': 'select an already engineered eligible source field unchanged'},
        'Stored panel field')


def validate_record(value):
    required = {'schema_version', 'record_type', 'id', 'version', 'display_name', 'body'}
    if set(value) != required or value['schema_version'] != SCHEMA or value['version'] != VERSION:
        fail('invalid record envelope')
    token(value['id'])
    if not isinstance(value['display_name'], str) or not value['display_name']: fail('missing name')
    body = value['body']; kind = value['record_type']
    if kind == 'feature_definition':
        if set(body) != {'signal_id', 'recipe', 'snapshot', 'projection'}: fail('invalid Feature body')
        normalize_recipe(body['recipe'], execution=False)
        if value['id'] != feature_id(body['recipe']) or body['signal_id'] != signal_id(body['recipe']):
            fail('Feature identity differs')
        normalize_reference(body['snapshot']); validate_projection(body['projection'])
        if body['recipe']['selection']['entity_id'] != body['projection']['entity_id']:
            fail('Feature selection differs')
    elif kind == 'materialization_manifest':
        if set(body) != {'feature', 'snapshot', 'projection'}: fail('invalid materialization')
        normalize_reference(body['feature']); normalize_reference(body['snapshot'])
        validate_projection(body['projection'])
        if value['id'] != 'MATERIALIZATION_' + digest(body): fail('materialization identity differs')
    elif kind in PREFIXES:
        if record(kind, body, value['display_name']) != value: fail('record identity differs')
        if kind == 'snapshot_manifest':
            if set(body) != {'kind', 'package', 'database', 'archive', 'attachments', 'frozen_max_asof'}:
                fail('invalid snapshot')
            if body['kind'] != 'frozen_panel_snapshot_v1' or body['package'] not in KINDS: fail('unknown snapshot kind')
            utc(body['frozen_max_asof'])
            for member in [body['database'], body['archive'], *body['attachments'].values()]:
                if set(member) != {'sha256', 'byte_count'} or not re.fullmatch('[0-9a-f]{64}', member['sha256']) or type(member['byte_count']) is not int or member['byte_count'] <= 0:
                    fail('invalid frozen operand fingerprint')
        elif kind == 'policy_definition' and value != policy_record(): fail('unknown projection policy')
        elif kind == 'transformation_definition' and value != operator_record(): fail('unknown projection operation')
    else: fail('unsupported record type')
    canonical_bytes(value)
    return value


def validate_projection(p):
    fields = {'package', 'layer', 'panel_ids', 'selector', 'field', 'entity_id', 'name',
              'frequency', 'unit', 'unit_label', 'pair', 'summary'}
    if set(p) != fields or p['package'] not in KINDS or p['layer'] not in LAYERS:
        fail('invalid projection contract')
    token(p['field']); token(p['entity_id']); token(p['unit'])
    if not p['panel_ids'] or not isinstance(p['selector'], dict): fail('missing selector')
    s = p['summary']
    if set(s) != {'row_count', 'valid_count', 'cutoff_start', 'cutoff_end', 'first_valid', 'latest'}:
        fail('invalid projection summary')
    if not 0 < s['valid_count'] <= s['row_count']: fail('all-held projections cannot be registered')
    utc(s['cutoff_start']); utc(s['cutoff_end']); utc(s['first_valid'])
    if not isinstance(s['latest'],dict) or set(s['latest']) != {'evaluation_cutoff','available_at','reference_time','status','reason_code'}:
        fail('projection metadata must contain headers only, never observation values')


def capture(db, package, folder):
    if package == 'macro': return db.execute('SELECT MAX(asof_utc) FROM asofs').fetchone()[0]
    if package == 'common': return json.loads((folder/'engineering.json').read_text())['capture_at']
    if package == 'etf': return json.loads((folder/'input-freeze.json').read_text())['capture_at']
    return json.loads(db.execute("SELECT value_json FROM metadata WHERE key='input_freeze'").fetchone()[0])['capture_at']


def field_unit(package, field, source_unit, kind=None):
    if package == 'etf':
        if field == 'daily_volume': return 'shares', 'shares traded'
        if field == 'close_usd': return 'USD', 'USD per share'
        if field.startswith(('adjusted_return', 'realized_vol', 'flow_pct')): return 'percent', 'percent / percentage-point H-minus-U difference'
        return 'USD', 'USD estimated or filed fund flow; original basis retained'
    if package == 'macro': return ('percent', 'percent') if source_unit == 'percent' else ('percentage_points', 'percentage points')
    if field.startswith(('return_', 'return_gap', 'price_pct', 'vol_')): return 'percent', 'percent / percentage-point return gap'
    if field in ('close_usd', 'adjusted_close_usd'): return 'USD', 'USD per share'
    if field == 'daily_volume': return 'shares', 'shares traded'
    if package == 'expansion' and source_unit == 'percent per annum' and field != 'level':
        return 'percentage_points', 'percentage points per annum'
    # Human source units remain explicit even when no platform enum exists.
    return 'native_' + digest(source_unit)[:16], source_unit


def _projection(package, layer, selector, field, name, entity, panels, frequency, unit, stats, latest, pair=None):
    u, label = field_unit(package, field, unit)
    return {'package': package, 'layer': layer, 'selector': selector, 'field': field,
        'name': name, 'entity_id': entity, 'panel_ids': sorted(panels), 'frequency': frequency,
        'unit': u, 'unit_label': label, 'pair': pair,
        'summary': {'row_count': stats['n'], 'valid_count': stats['valid'],
            'cutoff_start': stats['lo'], 'cutoff_end': stats['hi'], 'first_valid': stats['first'],
            'latest': scientific(latest)}}


def _latest_header(row):
    return {k:row[k] for k in ('evaluation_cutoff','available_at','reference_time','status','reason_code')}


def macro_groups(db,table,dims):
    """Sequential bounded-memory inventory; avoid millions of random row reads.

    Existing selector indexes are ideal for a selected history but are not
    covering aggregate indexes. Grouping the entire as-of-major table through
    them thrashes a small server's page cache. There are only a few thousand
    selector groups, so accumulate their metadata in one ordinary table scan.
    """
    ordered=list(db.execute('SELECT asof_id,asof_utc FROM asofs ORDER BY asof_id'))
    if [r[1] for r in ordered] != sorted({r[1] for r in ordered}):
        fail('macro integer cutoff index is not in unique chronological order')
    keys=['mode_id','feature_id']+dims
    query='SELECT '+','.join(keys+['asof_id','model_value','blocker_mask'])+' FROM '+table+' NOT INDEXED'
    cursor=db.cursor();cursor.row_factory=None
    states={}
    for row in cursor.execute(query):
        key=row[:-3];when,value,block=row[-3:]
        if key not in states:states[key]={'n':0,'valid':0,'lo':when,'hi':when,'first':None}
        s=states[key];s['n']+=1;s['lo']=min(s['lo'],when);s['hi']=max(s['hi'],when)
        if value is not None and not block:
            s['valid']+=1;s['first']=when if s['first'] is None else min(s['first'],when)
    asofs=dict(ordered)
    for key,s in sorted(states.items()):
        if not s['valid']:continue
        yield dict(zip(keys,key)),dict(s,**{k:asofs[s[k]] for k in ('lo','hi','first')})


def projections(db, package, cap):
    """Inventory each source once in grouped SQL; no per-feature full-table scans."""
    if package == 'macro':
        features = {r['feature_id']: dict(r) for r in db.execute('SELECT * FROM features')}
        currencies = dict(db.execute('SELECT currency_id,currency FROM currencies'))
        modes = dict(db.execute('SELECT mode_id,name FROM modes'))
        for table, dims in [('country_features', ['currency_id']), ('pair_features_data', ['base_id','quote_id'])]:
            for key,stats in macro_groups(db,table,dims):
                r=dict(key,**stats)
                f = features[r['feature_id']]; pair = None
                selector = {'table': table, 'mode_id': r['mode_id'], 'feature_id': r['feature_id']}
                if table == 'country_features':
                    selector['currency_id'] = r['currency_id']; name = currencies[r['currency_id']]
                    source_unit = 'percent' if f['metric'] in ('yoy','period_growth','rate') else 'percentage points'
                else:
                    selector.update(base_id=r['base_id'], quote_id=r['quote_id'])
                    pair = currencies[r['base_id']] + currencies[r['quote_id']]; name = pair
                    source_unit = 'percentage points'
                entity = 'PANEL_ENTITY_' + digest({'package': package, 'selector': selector})[:24]
                p = _projection(package, modes[r['mode_id']], selector, f['name'],
                    name + ' ' + f['description'], entity, [f['panel_id']], 'native', source_unit, r, None, pair)
                # Last state is obtained with the same indexed selector used by readers.
                last = list(source_rows(db, p, cap, cap))[-1:]
                p['summary']['latest'] = _latest_header(last[0]) if last else None
                yield p
        return
    if package in ('common', 'expansion'):
        series = {r['series_id']: dict(r) for r in db.execute('SELECT * FROM series')}
        bindings = {}
        if package == 'common':
            for r in db.execute('SELECT series_id,panel_id FROM bindings'): bindings.setdefault(r[0], []).append(r[1])
        query = '''SELECT f.series_id,f.layer,j.key field,COUNT(*) n,
            SUM(j.value IS NOT NULL AND f.block_mask=0) valid,MIN(available_from) lo,
            MAX(available_from) hi,MIN(CASE WHEN j.value IS NOT NULL AND f.block_mask=0 THEN available_from END) first
            FROM feature_states f,json_each(f.values_json) j WHERE f.series_id=? AND f.layer=?
            GROUP BY j.key'''
        if package == 'common':
            query=query.replace('j.key field,COUNT(*) n','j.key field,f.unit native_unit,f.frequency native_frequency,COUNT(*) n')
            query=query.replace('GROUP BY j.key','GROUP BY f.unit,f.frequency,j.key')
        # Bound SQLite's temporary aggregation to one native series/layer.
        # Global JSON expansion would sort millions of cells on a small disk.
        def groups():
            for group in db.execute("SELECT DISTINCT series_id,layer FROM feature_states WHERE layer IN ('archive','capture','retrospective')"):
                yield from db.execute(query,tuple(group))
        for r in groups():
            if not r['valid']: continue
            s = series[r['series_id']]; selector = {'series_id': r['series_id']}
            stats=dict(r); source_unit=s['unit']; frequency=s['frequency']; name=s.get('name',s['series_key'])+' '+r['field']
            if package == 'common':
                # ALFRED unit/cadence labels can change across vintages. Keep
                # separate, explicitly named regimes; other-regime updates
                # invalidate the old Feature rather than carrying it forward.
                selector.update(native_unit=r['native_unit'],native_frequency=r['native_frequency'])
                source_unit=r['native_unit'];frequency=r['native_frequency']
                total=db.execute('SELECT COUNT(*) n,MIN(available_from) lo,MAX(available_from) hi FROM feature_states WHERE series_id=? AND layer=?',
                    (s['series_id'],r['layer'])).fetchone()
                stats.update(dict(total));name+=' ('+frequency+'; '+source_unit+')'
            entity = 'PANEL_ENTITY_' + digest({'package': package, 'selector': selector})[:24]
            panels = bindings[s['series_id']] if package == 'common' else [s['block']]
            p = _projection(package, r['layer'], selector, r['field'], name,
                entity, panels, frequency, source_unit, stats, None)
            p['summary']['latest'] = _latest_header(list(source_rows(db, p, stats['hi'], cap))[-1])
            yield p
        return
    # ETF capture is a single latest state per panel/entity/cadence, not a
    # retrospective history with every past date assigned the same capture time.
    for layer in ('capture', 'retrospective'):
        where = "f.vector_id IN (SELECT vector_id FROM (SELECT vector_id,ROW_NUMBER() OVER (PARTITION BY panel_id,entity,frequency ORDER BY date DESC) rank FROM feature_vectors) WHERE rank=1)" if layer == 'capture' else 'f.retro_eligible=1'
        effective = 'observed_from' if layer == 'capture' else 'assumed_available_from'
        eligible = "j.value IS NOT NULL"
        if layer == 'capture':
            eligible += " AND julianday(substr(observed_from,1,10))-julianday(date)<=CASE frequency WHEN 'D' THEN 14 ELSE 150 END"
        query = f'''SELECT f.panel_id,f.entity,f.frequency,j.key field,COUNT(*) n,
            SUM({eligible}) valid,MIN({effective}) lo,MAX({effective}) hi,
            MIN(CASE WHEN {eligible} THEN {effective} END) first
            FROM feature_vectors f,json_each(f.values_json) j WHERE {where}
            AND f.panel_id=? AND f.entity=? AND f.frequency=? GROUP BY j.key'''
        def groups():
            for group in db.execute('SELECT DISTINCT panel_id,entity,frequency FROM feature_vectors'):
                yield from db.execute(query,tuple(group))
        for r in groups():
            if not r['valid']: continue
            selector = {k:r[k] for k in ('panel_id','entity','frequency')}
            entity = 'PANEL_ENTITY_' + digest({'package': package, 'selector': selector})[:24]
            p = _projection(package, layer, selector, r['field'], r['entity']+' '+r['field'], entity,
                [r['panel_id']], r['frequency'], '', r, None)
            p['summary']['latest'] = _latest_header(list(source_rows(db, p, r['hi'], cap))[-1])
            yield p


def _number(value):
    if value is None: return None
    out = Decimal(str(value))
    if not out.is_finite(): fail('nonfinite feature value')
    return str(value)


def source_rows(db, p, start=None, end=None):
    """Decode only requested interval plus one prevailing preperiod state.

    Bounds are UTC and the right edge is inclusive for inspection; research
    additionally uses strict-before-anchor eligibility. SQL parameters bind all
    selectors. Table names come only from this implemented profile.
    """
    package, layer, sel, field = p['package'], p['layer'], p['selector'], p['field']
    params = []; where = []; time = 'available_from'; table = 'feature_states'
    lower,upper=start,end
    if package == 'macro':
        table = sel['table']
        if table not in ('country_features','pair_features_data'): fail('unknown macro selector')
        view = 'country_feature_values' if table == 'country_features' else 'pair_feature_values'
        keys = ['mode_id','feature_id'] + (['currency_id'] if table == 'country_features' else ['base_id','quote_id'])
        where = ['p.'+k+'=?' for k in keys]; params = [sel[k] for k in keys]
        time = 'p.asof_id'
        if start:
            found=db.execute('SELECT asof_id FROM asofs WHERE asof_utc>=? ORDER BY asof_utc LIMIT 1',(start,)).fetchone()
            lower=found[0] if found else db.execute('SELECT MAX(asof_id)+1 FROM asofs').fetchone()[0]
        if end:
            found=db.execute('SELECT asof_id FROM asofs WHERE asof_utc<=? ORDER BY asof_utc DESC LIMIT 1',(end,)).fetchone()
            upper=found[0] if found else -1
        # Use integer lookup indices before joining the descriptive view.
        query = 'SELECT p.*,a.asof_utc FROM '+table+' p JOIN asofs a USING(asof_id)'
    elif package in ('common','expansion'):
        query = 'SELECT * FROM feature_states'; where = ['series_id=?','layer=?']; params = [sel['series_id'],layer]
    else:
        query = 'SELECT * FROM feature_vectors'; where = [k+'=?' for k in ('panel_id','entity','frequency')]
        params = [sel[k] for k in ('panel_id','entity','frequency')]
        if layer == 'retrospective': where.append('retro_eligible=1'); time = 'assumed_available_from'
        else: time = 'observed_from'
    base = query+' WHERE '+' AND '.join(where)
    if package == 'etf' and layer == 'capture':
        raw = list(db.execute(base+' ORDER BY date DESC LIMIT 1',params))
        if end and raw and raw[0]['observed_from'] > end: raw = []
    else:
        raw = []
        if start:
            raw.extend(db.execute(base+' AND '+time+'<? ORDER BY '+time+' DESC LIMIT 1',params+[lower]))
        bounded = base; args = list(params)
        if start: bounded += ' AND '+time+'>=?'; args.append(lower)
        if end: bounded += ' AND '+time+'<=?'; args.append(upper)
        raw.extend(db.execute(bounded+' ORDER BY '+time,args))
    for item in raw:
        r = dict(item); evidence = {}; until = None; block = 0
        if package == 'macro':
            available = r['asof_utc']; value = r['model_value']; block = r['blocker_mask']
            next_row = db.execute('SELECT asof_utc FROM asofs WHERE asof_utc>? ORDER BY asof_utc LIMIT 1',(available,)).fetchone()
            until = next_row[0] if next_row else None
            keys = ['mode_id','asof_id','feature_id'] + (['currency_id'] if table == 'country_features' else ['base_id','quote_id'])
            locator = {k:r[k] for k in keys}
            # Preserve the exact country operand lineage and reference periods.
            ids = [r['currency_id']] if table == 'country_features' else [r['base_id'],r['quote_id']]
            operands = []
            for cid in ids:
                x = db.execute('''SELECT c.lineage_id,c.frequency,d.iso_date reference_time,c.missing_mask,c.blocker_mask
                    FROM country_features c LEFT JOIN dates d ON d.ordinal=c.period_ordinal
                    WHERE mode_id=? AND asof_id=? AND feature_id=? AND currency_id=?''',
                    (r['mode_id'],r['asof_id'],r['feature_id'],cid)).fetchone()
                operands.append(dict(x))
            refs = [x['reference_time'] for x in operands if x['reference_time']]
            reference_time = max(refs) if refs else None
            evidence = {'country_operands': operands, 'source_missing_mask': r['missing_mask'],
                'source_block_mask': block, 'source_warning_mask': r['warning_mask']}
            reason = None if value is not None and not block else 'SOURCE_MISSING_OR_HELD'
            frequency = 'native'; reference_end = reference_time
        else:
            values = json.loads(r['values_json']); value = values.get(field)
            block = r.get('block_mask', 0); missing = json.loads(r['missing_json'])
            if package == 'etf':
                available = r['observed_from'] if layer == 'capture' else r['assumed_available_from']
                reference_time = reference_end = r['date']; locator = {'vector_id':r['vector_id']}
                evidence = {'source_class':r['source_class'],'retro_eligible':r['retro_eligible'],
                    'source_lineage':json.loads(r['lineage_json'])}
                if layer == 'capture':
                    age = (date.fromisoformat(available[:10])-date.fromisoformat(reference_end)).days
                    if age > (14 if r['frequency']=='D' else 150): block |= 1
            else:
                available = r['available_from']; until = r['available_until']
                reference_time = r.get('reference_date',r.get('period_start')); reference_end = r['reference_end'] if package == 'expansion' else r['period_end']
                locator = {'state_id': r['state_id']}
                evidence = {'source_lineage': json.loads(r['lineage_json'] if package == 'expansion' else r['input_ids_json']),
                    'source_block_mask':block,'source_warning_mask':r['warning_mask']}
            frequency = r['frequency']
            reason = ('SOURCE_HELD' if block else missing.get(field,'SOURCE_MISSING') if value is None else None)
            if package == 'common':
                evidence.update(source_unit=r['unit'],source_frequency=frequency)
                if r['unit'] != sel['native_unit'] or frequency != sel['native_frequency']:
                    block |= 8;reason='NATIVE_UNIT_OR_CADENCE_REGIME_CHANGED'
        if block: value = None
        evidence.update(source_table=table if package != 'etf' else 'feature_vectors', row_locator=locator, field=field)
        yield scientific({'entity_id':p['entity_id'],'measure':field,'dimensions':[],
            'reference_time':reference_time,'reference_end':reference_end,'frequency':frequency,
            'available_at':available,'evaluation_cutoff':available,'available_until':until,
            'vintage_id':layer,'value':_number(value),'status':'valid' if value is not None else 'missing',
            'reason_code':reason,'lineage':evidence})


def make_feature(snapshot, view, p):
    policy = reference(policy_record()); operator = reference(operator_record())
    recipe = normalize_recipe({'sources':[{'alias':'panel','source_view':reference(view)}],
        'steps':[{'node':'stored_field','phase':'transformation','operator':operator,'inputs':['panel'],
                  'parameters':[{'name':'projection','unit':'identity','value':{'kind':'token','value':'P_'+digest(p)}}]}],
        'output_node':'stored_field','output_unit':p['unit'],'calculation_scope_requirement':'none','scope_policy':None,
        'selection':{'entity_id':p['entity_id'],'measure':p['field'],
                     'dimensions':[{'name':'layer','value':p['layer']}]},
        'history_mode':'emitted_history','history_policy':policy,'execution_policy':policy,
        'evaluation_policy':policy},execution=False)
    name=p['name']
    if p['selector'].get('table') == 'country_features':
        # The package's shared feature table describes the downstream pair gap;
        # this projection is its domestic operand, before any pair subtraction.
        name=name.replace(' differential','')
    return {'schema_version':SCHEMA,'record_type':'feature_definition','id':feature_id(recipe),'version':VERSION,
        'display_name':name+' ['+p['layer']+']','body':{'recipe':recipe,'signal_id':signal_id(recipe),
        'snapshot':reference(snapshot),'projection':p}}


def manifest_for(feature):
    body = {'feature':reference(feature),'snapshot':feature['body']['snapshot'],
            'projection':feature['body']['projection']}
    return {'schema_version':SCHEMA,'record_type':'materialization_manifest',
        'id':'MATERIALIZATION_'+digest(body),'version':VERSION,
        'display_name':feature['display_name'],'body':body}


def snapshot_db(store, snapshot):
    from data.verified_inputs import memo, probe
    body = snapshot['body']; member = body['database']; path = payload_path(store.root, member, 'sqlite')
    def verify():
        for label,operand,expected in snapshot_operands(store.root,snapshot):
            probe(operand)
            if file_hash(operand) != expected: fail('native '+label+' hash differs')
        return str(path)
    # The verifier is execution/request-scoped; stat witnesses invalidate hits.
    return Path(memo(store.root,'frozen_panel_database',{'snapshot':reference(snapshot)},verify))


def snapshot_operands(root,snapshot):
    body=snapshot['body']
    result=[('database',payload_path(root,body['database'],'sqlite'),body['database']),
            ('archive',payload_path(root,body['archive'],'zip'),body['archive'])]
    result.extend(('evidence '+name,payload_path(root,member,'panel_evidence'),member)
                  for name,member in body['attachments'].items())
    return result


def resolved(root, feature, *, verify_database=True, store=None):
    from data.feature_store import FeatureStore
    store = store or FeatureStore(root)
    if store.root != Path(root).resolve(): fail('reader store belongs to another root')
    validate_record(feature)
    snapshot = store.resolve(feature['body']['snapshot']); validate_record(snapshot)
    p = feature['body']['projection']
    if snapshot['body']['package'] != p['package']: fail('package selection differs')
    view = store.resolve(feature['body']['recipe']['sources'][0]['source_view'])
    dataset = store.resolve(view['body']['dataset'])
    if dataset['body']['snapshot'] != reference(snapshot): fail('source view snapshot differs')
    expected = make_feature(snapshot, view, p)
    if reference(expected) != reference(feature): fail('stored projection differs from implemented recipe')
    store.verify_closure([feature])
    manifest = manifest_for(feature)
    actual = store.resolve(reference(manifest))
    if actual != manifest: fail('stored materialization differs')
    if verify_database: snapshot_db(store,snapshot)
    return store, snapshot, manifest, view, dataset


def read(root, feature, *, start=None, end=None):
    store, snapshot, manifest, view, dataset = resolved(root, feature,verify_database=False)
    cap = snapshot['body']['frozen_max_asof']; p = feature['body']['projection']
    if end and utc(end) > cap: fail('requested cutoff exceeds frozen capture; refresh first')
    if start and utc(start) > (utc(end) if end else cap): fail('requested interval starts after its frozen end')
    before={str(path):witness(path.stat()) for _,path,_ in snapshot_operands(root,snapshot)}
    path=snapshot_db(store,snapshot)
    with connect(path) as db:
        rows = list(source_rows(db,p,utc(start) if start else None,utc(end) if end else cap))
    if any(witness(Path(path).stat()) != signature for path,signature in before.items()):
        fail('operand changed during read')
    for row in rows:
        row.update(materialization_id=manifest['id'],frozen_max_asof=cap)
        row['lineage']['snapshot'] = reference(snapshot)
    return {'feature':feature,'manifest':manifest,'observations':rows,
        'metadata':{'dataset':dataset,'source_view':view},'operands':{}}


def read_materialization(root, identifier):
    from data.feature_store import FeatureStore, materialization_path
    store = FeatureStore(root)
    manifest = strict_json(stable_read(store.path(materialization_path(identifier)))); validate_record(manifest)
    if manifest['id'] != identifier: fail('materialization path differs')
    return read(root,store.resolve(manifest['body']['feature']))


def package_plan(folder, package, archive):
    folder = Path(folder); database = folder/FILES[package][1]
    with connect(database) as db:
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok': fail('SQLite integrity check failed')
        cap = capture(db,package,folder)
        fields = list(projections(db,package,cap))
    # Preserve all supplied timing, source, unit and quality contracts by hash.
    attachments = {p.name:file_hash(p) for p in sorted(folder.iterdir())
        if p.is_file() and p.suffix in ('.json','.md','.sql','.py')}
    database_hash=file_hash(database)
    verify_archive(archive,folder,{FILES[package][1]:database_hash,**attachments})
    return {'package':package,'directory':str(folder.resolve()),'database':database_hash,
        'archive_path':str(Path(archive).resolve()),'archive':file_hash(archive),
        'attachments':attachments,'frozen_max_asof':cap,'projections':fields}


def make_plan(packages):
    if not packages or len({p['package'] for p in packages}) != len(packages): fail('duplicate/empty package plan')
    for p in packages:
        for field in p['projections']: validate_projection(field)
    plan = {'schema':'gambit_native_panel_import_plan_v1','packages':packages,
        'research_jobs_authorized':False,'admissions_must_stay_closed':True,
        'policy':policy_record(),'operator':operator_record()}
    return dict(plan,plan_sha256=digest(plan))


def install(root, plan, expected_hash, *, isolated=False):
    """Explicit, resumable data migration. Publication links are installed last."""
    from data.feature_store import FeatureStore
    from research.store import lock, install_bytes
    if plan.get('plan_sha256') != expected_hash or digest({k:v for k,v in plan.items() if k!='plan_sha256'}) != expected_hash:
        fail('exact reviewed plan hash required')
    if plan != make_plan(plan['packages']): fail('plan semantics differ from this importer')
    if not isolated and not Path('/etc/gambit/research-admissions-closed').exists(): fail('research admissions must be closed')
    if isolated and os.environ.get('GAMBIT_ISOLATED_TEST') != '1': fail('isolated fixture flag required')
    store = FeatureStore(root); result = []
    # Complete the no-write fingerprint preflight before publishing any package.
    for package in plan['packages']:
        kind=package['package']; folder=Path(package['directory'])
        expected=[(folder/FILES[kind][1],package['database']),
                  (Path(package['archive_path']),package['archive'])]
        expected += [(folder/name,member) for name,member in package['attachments'].items()]
        for path,member in expected:
            if file_hash(path) != member: fail('source fingerprint drift')
    with lock(root,'research-writer',nonblocking=True) as acquired:
        if not acquired: fail('research writer is busy')
        if not isolated:
            if not Path('/etc/gambit/research-admissions-closed').exists(): fail('admissions reopened')
            if any(store.path('storage/catalog/operations/jobs').glob('*.json')):
                fail('job records exist; review idle state before this reset-era import')
        with store.writer():
            store.install_record(policy_record()); store.install_record(operator_record())
            for package in plan['packages']:
                kind = package['package']; folder = Path(package['directory'])
                with connect(folder/FILES[kind][1]) as db:
                    # Re-inventory exact selectors, values/masks and summary after plan.
                    fields = list(projections(db,kind,package['frozen_max_asof']))
                if fields != package['projections']: fail('projection inventory drift')
                install_payload(root,folder/FILES[kind][1],package['database'],'sqlite')
                install_payload(root,package['archive_path'],package['archive'],'zip')
                for name, member in package['attachments'].items():
                    if Path(name).name != name: fail('invalid attachment path')
                    install_payload(root,folder/name,member,'panel_evidence')
                snapshot = record('snapshot_manifest',{'kind':'frozen_panel_snapshot_v1','package':kind,
                    **{k:package[k] for k in ('database','archive','attachments','frozen_max_asof')}},kind+' frozen panel operands')
                store.install_record(snapshot)
                provider = record('provider_contract',{'provider':'Frozen catalog-sourced '+kind+' panels',
                    'native_series_id':kind,'frequency':'Mixed native cadences','units':'Per-field native units',
                    'package_snapshot':reference(snapshot)},kind+' panel sources')
                store.install_record(provider)
                dataset = record('dataset_definition',{'kind':'frozen_panel_dataset_v1','snapshot':reference(snapshot),
                    'source_contract':reference(provider)},kind+' panel dataset')
                store.install_record(dataset)
                view = record('source_view_definition',{'kind':'frozen_panel_source_view_v1','dataset':reference(dataset)},kind+' frozen eligible fields')
                store.install_record(view)
                counts = {}; values = 0
                for p in fields:
                    feature = make_feature(snapshot,view,p); store.install_record(feature)
                    manifest = manifest_for(feature); store.install_record(manifest)
                    from research.feature_applications import install_binding, PANEL_SERIES
                    install_binding(root,feature,PANEL_SERIES)
                    # Standard link-only Signal projection; no research outcomes.
                    entry = {'schema_version':'0.3.0','record_type':'signal_library_entry','version':'1.0.0',
                        'signal_id':feature['body']['signal_id'],'feature':reference(feature),
                        'feature_materializations':[reference(manifest)],'relationship_results':[], 'supersedes':None}
                    entry['id']='LIBRARYENTRY_'+digest(entry); store.install_record(entry)
                    counts[p['layer']] = counts.get(p['layer'],0)+1; values += p['summary']['valid_count']
                result.append({'package':kind,'snapshot':reference(snapshot),'registered_fields':len(fields),
                    'fields_by_layer':counts,'valid_stored_field_states':values,
                    'frozen_max_asof':package['frozen_max_asof']})
            receipt = {'schema':'gambit_native_panel_import_receipt_v1','plan_sha256':expected_hash,
                'packages':result,'research_jobs_launched':0,'admissions_closed':not isolated}
            path = store.path('storage/catalog/ingestions/native_panels/'+expected_hash+'.json')
            install_bytes(path,canonical_bytes(receipt)+b'\n')
            return receipt
