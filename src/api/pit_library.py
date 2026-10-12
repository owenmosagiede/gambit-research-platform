"""Local, read-only PIT library metadata API and explicitly allowed UI assets."""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from data.alfred_onboarding import ref, stable_read, strict_json
from data.alfred_pit import inside, read_pit as read_pilot
from data.alfred_full_history import read_pit as read_full

SNAPSHOT_ID = re.compile(r'SNAPSHOT_[0-9a-f]{64}\Z')
TOKEN = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,127}\Z')
VERSION = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z')
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/index.html': ('index.html', 'text/html; charset=utf-8'),
          '/library.css': ('library.css', 'text/css; charset=utf-8'),
          '/library.js': ('library.js', 'text/javascript; charset=utf-8')}
PROFILES = {
    'storage/catalog/pit_store/completions': ('COMPLETE', 'bounded_sample', read_pilot),
    'storage/catalog/pit_store/full_history/completions': ('COMPLETE_FULL_HISTORY_RAW_AND_PIT', 'full_history', read_full),
}


class UnsupportedCompletion(ValueError):
    pass

def definition(root, folder, binding, kind):
    """Resolve only an exact pinned definition from an allowlisted directory."""
    if not TOKEN.fullmatch(binding['id']) or not VERSION.fullmatch(binding['version']):
        raise ValueError('Invalid definition reference')
    path=inside(root,f"definitions/{folder}/{binding['id']}/{binding['version']}.json")
    record=strict_json(stable_read(path))
    if record['record_type']!=kind or ref(record)!=binding:
        raise ValueError('Definition does not match its immutable reference')
    return record


def verified_item(root, path):
    relative=str(path.parent.relative_to(root))
    if relative not in PROFILES:
        raise UnsupportedCompletion('Unsupported completion location')
    status,scope,reader=PROFILES[relative]
    marker=strict_json(stable_read(inside(root,str(path.relative_to(root)))))
    if marker.get('status')!=status:
        raise UnsupportedCompletion('Unsupported completion status')
    snapshot_id=marker['pit_snapshot']['id']
    if not SNAPSHOT_ID.fullmatch(snapshot_id) or path.stem!=snapshot_id:
        raise ValueError('Completion name does not match its snapshot')
    verified=reader(root,snapshot_id)
    snapshot,rows=verified[:2]
    if marker['pit_snapshot']!=ref(snapshot) or marker['raw_snapshot']!=snapshot['upstream_snapshots'][0]:
        raise ValueError('Completion points to different verified data')
    periods=sorted({row['observation_date'] for row in rows})
    vintages=sorted({row['vintage_date'] for row in rows})
    if scope=='full_history':
        run=verified[2]
        if marker['counts']!=run['counts'] or marker['coverage']!=run['coverage']:
            raise ValueError('Completion coverage is inconsistent')
        if marker['counts']['vintage_events']!=len(rows) or marker['counts']['reference_months']!=len(periods):
            raise ValueError('Completion counts are inconsistent')
        # The full reader verifies the package; also pin the completion's package locator.
        from data.alfred_onboarding import canonical, sha
        run_bytes=strict_json(stable_read(inside(root,marker['run_path'])))
        if run_bytes!=run or marker['run_sha256']!=sha(canonical(run)):
            raise ValueError('Completion package locator mismatch')
    elif marker['record_count']!=len(rows) or marker['reference_months']!=len(periods):
        raise ValueError('Completion counts are inconsistent')
    view=definition(root,'source_views',snapshot['definition'],'source_view_definition')
    dataset=definition(root,'datasets',view['body']['dataset'],'dataset_definition')
    provider=definition(root,'providers',dataset['body']['source_contract'],'provider_contract')
    body=provider['body']
    if any(row['series_id']!=body['native_series_id'] for row in rows):
        raise ValueError('Series metadata differs from observations')
    label='Full history' if scope=='full_history' else (periods[0][:4]+' sample' if periods[0][:4]==periods[-1][:4] else 'Bounded sample')
    return {'id':dataset['id'],'series_id':body['native_series_id'],'name':dataset['display_name'],
            'provider':body['provider'],'frequency':body['frequency'],'units':body['units'],
            'snapshot':{'id':snapshot_id,'label':label,'scope':scope,'source_view_version':view['version'],
                        'observation_start':periods[0],'observation_end':periods[-1],'observation_count':len(periods),
                        'event_count':len(rows),'vintage_start':vintages[0],'vintage_end':vintages[-1],
                        'vintage_count':len(vintages),'missing_event_count':sum(row['status']=='missing' for row in rows),
                        'timing_precision':'date','captured_at':snapshot['information_cutoff']}}


def verified_fx_items(root, *, metadata_only=False):
    """Read sealed FX source snapshots without claiming historical vintage evidence.

    Publication validated row semantics; this metadata projection verifies exact
    immutable manifest references and every referenced payload before displaying
    its sealed coverage/counts. It does not use the ALFRED row adapters.
    """
    from data.feature_store import FeatureStore
    from data.transformations.identity import reference
    store=FeatureStore(root);items=[];issues=[]
    for path in sorted(store.path('storage/catalog/snapshots').glob('*/manifest.json')):
        try:
            record=strict_json(stable_read(path))
            if not isinstance(record,dict) or record.get('schema_version')!='0.5.0' or record.get('body',{}).get('kind')!='fx_source_snapshot':
                continue
            body=record['body']
            if body.get('completion_state')!='complete':continue
            snapshot=store.resolve(reference(record))
            if path.parent.name!=snapshot['id']:raise ValueError('FX snapshot path mismatch')
            if not metadata_only:store.verify_closure([snapshot])
            view=store.resolve(body['definition']);dataset=store.resolve(view['body']['dataset'])
            provider=store.resolve(dataset['body']['source_contract']);metadata=body['source_metadata']
            if any(provider['body'].get(key)!=value for key,value in metadata.items()):
                raise ValueError('FX provider source mismatch')
            if metadata['provenance_classification']!='retrospective_snapshot' or metadata['historical_availability'] is not None or metadata['historical_vintages_verified']:
                raise ValueError('Unsupported FX snapshot historical certification')
            times=body['original_ingestion_times']
            if not times:raise ValueError('Original ingestion evidence is required')
            items.append({'id':dataset['id'],'series_id':metadata['provider_symbol'],
                'name':dataset.get('display_name',metadata['provider_symbol']+' daily source closes'),
                'provider':metadata['provider'],'frequency':metadata['frequency'],'units':metadata['unit'],
                'snapshot':{'id':snapshot['id'],'label':'Retrospective source snapshot','scope':'retrospective_snapshot',
                    'source_view_version':view['version'],'source_view':body['definition'],'source_snapshot':reference(snapshot),
                    'observation_start':body['coverage']['start'],'observation_end':body['coverage']['end'],
                    'observation_count':body['record_count'],'event_count':body['record_count'],
                    'vintage_start':None,'vintage_end':None,'vintage_count':0,'missing_event_count':0,
                    'timing_precision':'date','captured_at':max(times),'original_ingestion_times':times,
                    'verification_state':'catalog_metadata_only' if metadata_only else 'payloads_verified',
                    'provenance_classification':'retrospective_snapshot','readiness':body['readiness'],
                    'limitation_codes':body['limitation_codes'],'price_basis':metadata['price_basis'],
                    'timing':metadata['timing'],'base_currency':metadata['base_currency'],'quote_currency':metadata['quote_currency']}})
        except Exception:
            issues.append({'code':'UNAVAILABLE_SNAPSHOT','snapshot_id':path.parent.name if SNAPSHOT_ID.fullmatch(path.parent.name) else None,
                           'message':'A stored source snapshot could not be verified.'})
    return items,issues


def catalog_item(root, path):
    """Exact completion/manifest metadata, without scanning observation payloads."""
    from data.feature_store import FeatureStore
    from data.alfred_onboarding import canonical, sha
    relative = str(path.parent.relative_to(root))
    if relative not in PROFILES:
        raise UnsupportedCompletion('Unsupported completion location')
    status, scope, _ = PROFILES[relative]
    # The retired bounded format has no complete coverage envelope. Keep its
    # existing strict reader rather than inventing missing metadata.
    if scope != 'full_history':
        return verified_item(root, path)
    marker = strict_json(stable_read(inside(root, str(path.relative_to(root)))))
    if marker.get('status') != status:
        raise UnsupportedCompletion('Unsupported completion status')
    store = FeatureStore(root)
    snapshot = store.resolve(marker['pit_snapshot'])
    raw = store.resolve(marker['raw_snapshot'])
    if path.stem != snapshot['id'] or snapshot['layer'] != 'pit' or snapshot['upstream_snapshots'] != [ref(raw)]:
        raise ValueError('Completion snapshot mismatch')
    run = strict_json(stable_read(inside(root, marker['run_path'])))
    if sha(canonical(run)) != marker['run_sha256'] or any(run[k] != marker[k] for k in ('counts','coverage','pit_snapshot','raw_snapshot')):
        raise ValueError('Completion package mismatch')
    view = definition(root, 'source_views', snapshot['definition'], 'source_view_definition')
    dataset = definition(root, 'datasets', view['body']['dataset'], 'dataset_definition')
    provider = definition(root, 'providers', dataset['body']['source_contract'], 'provider_contract')
    if run['source_view'] != ref(view) or run['dataset'] != ref(dataset) or run['provider_contract'] != ref(provider):
        raise ValueError('Completion definition mismatch')
    body, coverage, counts = provider['body'], run['coverage'], run['counts']
    if counts['vintage_events'] != snapshot['record_count'] or counts['reference_months'] != coverage['observation_periods']:
        raise ValueError('Completion count mismatch')
    return {'id':dataset['id'], 'series_id':body['native_series_id'], 'name':dataset['display_name'],
        'provider':body['provider'], 'frequency':body['frequency'], 'units':body['units'],
        'snapshot':{'id':snapshot['id'], 'label':'Full history', 'scope':scope,
            'source_view_version':view['version'], 'observation_start':coverage['observation_start'],
            'observation_end':coverage['observation_end'], 'observation_count':counts['reference_months'],
            'event_count':counts['vintage_events'], 'vintage_start':coverage['vintage_start'],
            'vintage_end':coverage['vintage_end'], 'vintage_count':coverage['vintage_date_count'],
            'missing_event_count':coverage['missing_change_events'], 'timing_precision':'date',
            'captured_at':snapshot['information_cutoff'], 'verification_state':'catalog_metadata_only'}}


def list_pit_library(root, *, metadata_only=False):
    """Discover completed stored PIT datasets, independently verifying each one.

    No index is required for this metadata endpoint. It does not claim query/live
    readiness and does not create, modify or repair any files.
    """
    root=Path(root).resolve();catalog=inside(root,'storage/catalog/pit_store')
    items=[];issues=[];seen=set()
    for path in sorted(catalog.glob('**/completions/*.json')):
        sid=path.stem if SNAPSHOT_ID.fullmatch(path.stem) else None
        try:
            item=catalog_item(root,path) if metadata_only else verified_item(root,path)
            sid=item['snapshot']['id']
            if sid in seen:
                issues.append({'code':'DUPLICATE_SNAPSHOT','snapshot_id':sid,'message':'A duplicate saved PIT snapshot was excluded.'})
                continue
            seen.add(sid);items.append(item)
        except UnsupportedCompletion:
            issues.append({'code':'UNSUPPORTED_COMPLETION','snapshot_id':sid,'message':'A saved PIT entry uses an unsupported completion format.'})
        except Exception:
            # No filesystem paths, raw exception details or source data in errors.
            issues.append({'code':'UNAVAILABLE_SNAPSHOT','snapshot_id':sid,'message':'A saved PIT snapshot could not be verified.'})
    fx_items,fx_issues=verified_fx_items(root,metadata_only=metadata_only)
    issues.extend(fx_issues)
    for item in fx_items:
        if item['snapshot']['id'] not in seen:
            seen.add(item['snapshot']['id']);items.append(item)
    # Prefer full coverage, then newest capture, using IDs as deterministic tie-breaks.
    items.sort(key=lambda item:item['snapshot']['id'])
    items.sort(key=lambda item:item['snapshot']['captured_at'],reverse=True)
    items.sort(key=lambda item:0 if item['snapshot']['scope']=='full_history' else 1)
    grouped={}
    for item in items:
        dataset=grouped.setdefault(item['id'],{key:value for key,value in item.items() if key!='snapshot'})
        dataset.setdefault('snapshots',[]).append(item['snapshot'])
    datasets=sorted(grouped.values(),key=lambda item:(item['name'].casefold(),item['id']))
    return {'schema_version':'1.0.0','dataset_count':len(datasets),'snapshot_count':len(items),'datasets':datasets,'issues':issues}


def make_server(root,host='127.0.0.1',port=0):
    """Serve this local workspace only. No generic file server or write routes."""
    if host!='127.0.0.1':
        raise ValueError('The PIT library server binds to 127.0.0.1 only')
    root=Path(root).resolve()

    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        server_version='ResearchPlatform'
        sys_version=''

        def log_message(self,format,*args):
            # Keep arbitrary request paths and query text out of console logs.
            return

        def send_bytes(self,status,content,content_type,head=False,allow=False):
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(content)))
            self.send_header('Cache-Control','no-store' if content_type.startswith('application/json') else 'no-cache')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            if allow:self.send_header('Allow','GET, HEAD')
            self.end_headers()
            if not head:
                try:self.wfile.write(content)
                except (BrokenPipeError,ConnectionResetError):pass

        def send_json(self,status,value,head=False,allow=False):
            self.send_bytes(status,json.dumps(value,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()+b'\n','application/json; charset=utf-8',head,allow)

        def error(self,status,code,message,head=False,allow=False):
            self.send_json(status,{'error':{'code':code,'message':message}},head,allow)

        def allowed_request(self,head=False):
            port=self.server.server_address[1]
            allowed={f'127.0.0.1:{port}',f'localhost:{port}'}
            if self.headers.get('Host','') not in allowed:
                self.error(403,'INVALID_HOST','Use the local application address.',head);return False
            origin=self.headers.get('Origin')
            if origin is not None and origin not in {'http://'+value for value in allowed}:
                self.error(403,'INVALID_ORIGIN','This endpoint is available from the local application only.',head);return False
            return True

        def serve(self,head=False):
            if not self.allowed_request(head):return
            target=urlsplit(self.path)
            if target.scheme or target.netloc:
                self.error(404,'NOT_FOUND','This address is not available.',head);return
            if target.query:
                self.error(400,'UNSUPPORTED_QUERY','This endpoint does not accept query parameters.',head);return
            if target.path=='/api/pit-library':
                try:value=list_pit_library(root)
                except Exception:
                    self.error(503,'LIBRARY_UNAVAILABLE','The PIT Data Library could not be loaded.',head);return
                self.send_json(200,value,head);return
            asset=ASSETS.get(target.path)
            if asset is None:
                self.error(404,'NOT_FOUND','This address is not available.',head);return
            name,kind=asset
            try:content=stable_read(inside(root,'ui/'+name))
            except OSError:
                self.error(404,'NOT_FOUND','This page is not available.',head);return
            self.send_bytes(200,content,kind,head)

        def do_GET(self):self.serve()
        def do_HEAD(self):self.serve(True)
        def reject_method(self):
            self.close_connection=True
            if self.allowed_request():self.error(405,'METHOD_NOT_ALLOWED','This application provides read-only access.',allow=True)
        do_POST=reject_method
        do_PUT=reject_method
        do_PATCH=reject_method
        do_DELETE=reject_method
        do_OPTIONS=reject_method
        do_TRACE=reject_method
        do_CONNECT=reject_method

    server=ThreadingHTTPServer((host,port),Handler)
    server.daemon_threads=True
    return server
