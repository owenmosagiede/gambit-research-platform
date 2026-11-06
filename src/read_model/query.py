"""Bounded SELECT-only website queries. No research imports or source reads."""
import base64
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import time

from read_model.storage import (SCHEMA, CursorExpired, Unavailable, confined, connect,
                                current, encoded, freshness, read_document)


class InvalidQuery(ValueError):
    pass


def cursor_encode(value):
    return base64.urlsafe_b64encode(encoded(value).encode()).decode().rstrip('=')


def cursor_decode(value):
    try:
        if not isinstance(value, str) or len(value) > 2048: raise ValueError()
        result = json.loads(base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True))
        if not isinstance(result, dict) or set(result) != {'generation', 'query', 'key'}: raise ValueError()
        return result
    except (ValueError, TypeError, UnicodeError) as exc: raise InvalidQuery('Invalid page cursor') from exc


@contextmanager
def snapshot(directory, generation=None):
    path, manifest = current(directory, generation)
    db = connect(path)
    deadline = time.monotonic() + 2
    db.set_progress_handler(lambda: time.monotonic() > deadline, 1000)
    try:
        schema = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
        if schema is None or json.loads(schema[0]) != SCHEMA: raise Unavailable('Incompatible database')
        yield db, manifest
        # An integrity revocation published during this request invalidates it.
        if read_document(confined(directory, 'status.json')).get('unavailable'):
            raise Unavailable('Projection verification was revoked')
    finally: db.close()


def _where(filters, kind):
    clauses = []; params = []
    if kind == 'ledger': clauses.append("status IN ('succeeded','cancelled','blocked','failed')")
    if kind == 'queue': clauses.append("status NOT IN ('succeeded','cancelled')")
    for field in ('status', 'recipe', 'scope', 'direction'):
        if field in filters:
            if kind not in ('ledger','queue'): raise InvalidQuery('Unsupported filter')
            clauses.append(field + '=?'); params.append(filters[field])
    for name, operator in (('from', '>='), ('to', '<=')):
        if name in filters:
            if kind not in ('ledger','queue'): raise InvalidQuery('Unsupported date filter')
            from datetime import date
            try: date.fromisoformat(filters[name])
            except ValueError as exc: raise InvalidQuery('Invalid date') from exc
            clauses.append('substr(updated,1,10)' + operator + '?'); params.append(filters[name])
    if 'search' in filters:
        clauses.append("search LIKE ? ESCAPE '\\'")
        params.append('%' + filters['search'].casefold().replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%')
    return clauses, params


def page(directory, kind, query=None, *, recipe=None):
    query = dict(query or {})
    if set(query) - {'limit','cursor','search','status','recipe','scope','direction','from','to','generation'}:
        raise InvalidQuery('Unsupported query parameter')
    try: limit = int(query.pop('limit', '50'))
    except (TypeError, ValueError) as exc: raise InvalidQuery('Invalid page size') from exc
    if not 1 <= limit <= 100: raise InvalidQuery('Page size must be between 1 and 100')
    raw_cursor = query.pop('cursor', None)
    generation = query.pop('generation', None)
    if generation is not None:
        from read_model.storage import GENERATION
        if not GENERATION.fullmatch(generation): raise InvalidQuery('Invalid generation')
    if any(not isinstance(v, str) or len(v) > 256 for v in query.values()): raise InvalidQuery('Invalid filter')
    fingerprint = hashlib.sha256(encoded([kind, recipe, query, limit]).encode()).hexdigest()
    cursor = cursor_decode(raw_cursor) if raw_cursor else None
    if cursor and generation and cursor['generation'] != generation: raise InvalidQuery('Generation differs from cursor')
    if cursor and cursor['query'] != fingerprint: raise InvalidQuery('Cursor belongs to another query')
    if kind in ('ledger','queue'):
        table = 'experiments'; clauses, params = _where(query, kind)
        keys = ['updated', 'id'] if kind == 'ledger' else ["CASE WHEN status IN ('resolving','preparing','p1','p2') THEN 0 WHEN status='queued' THEN 1 ELSE 2 END", 'queue_key', 'id']
        directions = ['DESC', 'ASC'] if kind == 'ledger' else ['ASC'] * 3
    elif kind == 'recipes':
        table = 'recipes'; clauses, params = _where(query, kind); keys=['name','id']; directions=['ASC','ASC']
    elif kind == 'branches':
        if query: raise InvalidQuery('Use the exact recipe and page cursor')
        table = 'branches'; clauses=['recipe=?']; params=[recipe]; keys=['id']; directions=['ASC']
    else: raise InvalidQuery('Unknown collection')
    where = ' AND '.join(clauses) or '1'
    with snapshot(directory, cursor['generation'] if cursor else generation) as (db, manifest):
        total = db.execute('SELECT COUNT(*) FROM ' + table + ' WHERE ' + where, params).fetchone()[0]
        page_clauses = list(clauses); page_params = list(params)
        if cursor:
            key = cursor['key']
            if not isinstance(key,list) or len(key) != len(keys) or any(not isinstance(v,(str,int)) for v in key):
                raise InvalidQuery('Invalid page position')
            alternatives=[]
            for i,column in enumerate(keys):
                alternatives.append('(' + ' AND '.join([keys[j]+'=?' for j in range(i)] + [column+(' <?' if directions[i]=='DESC' else ' >?')]) + ')')
                page_params.extend(key[:i+1])
            page_clauses.append('(' + ' OR '.join(alternatives) + ')')
        columns = ','.join(k + ' AS key' + str(i) for i,k in enumerate(keys))
        sql = 'SELECT value,' + columns + ' FROM ' + table + ' WHERE ' + (' AND '.join(page_clauses) or '1')
        sql += ' ORDER BY ' + ','.join(k+' '+d for k,d in zip(keys,directions)) + ' LIMIT ?'
        records = db.execute(sql, [*page_params, limit+1]).fetchall()
        if sum(len(r['value'].encode()) for r in records[:limit]) > 4 * 1024 * 1024:
            raise Unavailable('Page exceeds the serving response bound')
        next_cursor = None
        if len(records) > limit:
            last = records[limit-1]
            next_cursor = cursor_encode({'generation':manifest['generation'],'query':fingerprint,
                                         'key':[last['key'+str(i)] for i in range(len(keys))]})
        items = [json.loads(r['value']) for r in records[:limit]]
        if kind in ('queue','ledger'):
            for item in items:
                job = item['job']; item['queue_position'] = None
                if job['status'] == 'queued':
                    key = job.get('queued_at',job.get('created_at',''))
                    item['queue_position'] = 1 + db.execute("SELECT COUNT(*) FROM experiments WHERE status='queued' AND (queue_key<? OR (queue_key=? AND id<?))", (key,key,job['request_id'])).fetchone()[0]
        value = {'schema_version':'read_model_v1','items':items,'total':total,'next_cursor':next_cursor,
                 'freshness':freshness(manifest),'issue_count':manifest['issue_count'],
                 'issues':[json.loads(r[0]) for r in db.execute('SELECT value FROM issues ORDER BY id LIMIT 20')]}
        if kind in ('ledger','queue'):
            value['status_counts'] = dict(db.execute('SELECT status,COUNT(*) FROM experiments GROUP BY status'))
            value['worker'] = {'state':'not_live_checked', 'message':'This snapshot shows recorded work, not a live worker-health check.'}
    return value


def detail(directory, kind, identity, generation=None):
    tables = {'trial':'trials','relationship':'relationships','decision':'decisions','experiment':'experiments'}
    if kind not in tables or not isinstance(identity,str) or len(identity)>128: raise InvalidQuery('Invalid record')
    with snapshot(directory, generation) as (db, manifest):
        if kind == 'experiment':
            alias = db.execute('SELECT canonical_id FROM aliases WHERE id=?',(identity,)).fetchone()
            if alias: identity=alias[0]
        size = db.execute('SELECT length(CAST(value AS BLOB)) FROM '+tables[kind]+' WHERE id=?',(identity,)).fetchone()
        if size and size[0] > 4 * 1024 * 1024: raise Unavailable('Metadata detail exceeds the serving response bound')
        record = db.execute('SELECT value FROM '+tables[kind]+' WHERE id=?',(identity,)).fetchone()
        if record is None: raise LookupError('No verified projected record')
        value = {'schema_version':'read_model_v1', 'record':json.loads(record[0]), 'freshness':freshness(manifest),
                 'numerical_evidence':'not_loaded; this endpoint returns stored metadata only'}
    return value
