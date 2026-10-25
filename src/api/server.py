"""Loopback development HTTP transport; shared application routes also serve WSGI."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit
from api.application import ApplicationRoutes, ASSETS, is_retired_batch_path
from api.catalog_cache import CatalogCache
from research.contracts import ResearchError, ResearchConflict, ResearchBlocked
from services.research_worker import WebResearchJobs


def make_server(root,host='127.0.0.1',port=0,research_jobs=None):
    """Serve this workspace only; research starts only from a durable submission."""
    if host!='127.0.0.1':
        raise ValueError('The research server binds to 127.0.0.1 only')
    root=Path(root).resolve()
    jobs=research_jobs if research_jobs is not None else WebResearchJobs(root)

    catalogs=CatalogCache()

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
            # Safari serializes a POST origin as null under no-referrer.
            # Keep exact-origin checks and suppress referrers to other sites.
            self.send_header('Referrer-Policy','same-origin')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            if allow:self.send_header('Allow','GET, HEAD')
            self.end_headers()
            if not head:
                try:self.wfile.write(content)
                except (BrokenPipeError,ConnectionResetError):pass

        def send_json(self,status,value,head=False,allow=False):
            self.send_bytes(status,json.dumps(value,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()+b'\n','application/json; charset=utf-8',head,allow)

        def error(self,status,code,message,head=False,allow=False):
            self.send_json(status,{'error':{'code':code,'message':message},
                **({'recorded':False} if self.command=='POST' and code in ('INVALID_ORIGIN','INVALID_HOST') else {})},head,allow)

        def allowed_request(self,head=False):
            port=self.server.server_address[1]
            allowed={f'127.0.0.1:{port}',f'localhost:{port}'}
            if self.headers.get('Host','') not in allowed:
                self.error(403,'INVALID_HOST','Use the local application address.',head);return False
            origin=self.headers.get('Origin')
            if origin is not None and origin not in {'http://'+value for value in allowed}:
                self.error(403,'INVALID_ORIGIN','This endpoint is available from the local application only.',head);return False
            return True

        def dispatch(self, data=None, head=False):
            route=ApplicationRoutes(root,jobs,catalogs,self.command,self.path)
            route.read(head) if data is None else route.write(data)
            status,content,kind,allow=route.response
            self.send_bytes(status,content,kind,head,allow)

        def serve(self,head=False):
            if self.allowed_request(head):self.dispatch(head=head)

        def do_GET(self):self.serve()
        def do_HEAD(self):self.serve(True)
        def do_POST(self):
            self.close_connection=True
            if not self.allowed_request():return
            target=urlsplit(self.path)
            if is_retired_batch_path(target.path):
                if self.headers.get('Origin')!='http://'+self.headers.get('Host',''):
                    self.error(403,'INVALID_ORIGIN','Submit is available from this local application only.');return
                # Compatibility response only: do not read or parse a batch body.
                self.dispatch(data=b'');return
            submit=target.path=='/api/experiments'
            action=None;rid=None
            if target.path.startswith('/api/experiments/'):
                parts=target.path[len('/api/experiments/'):].split('/')
                if len(parts)==2 and parts[1] in ('cancel','resume'):
                    rid,action=parts
            if not submit and action is None:
                self.error(405,'METHOD_NOT_ALLOWED','This endpoint provides read-only access.',allow=True);return
            if target.scheme or target.netloc or target.query:
                self.error(400,'INVALID_REQUEST','Use the exact local submission endpoint.');return
            if self.headers.get('Origin')!='http://'+self.headers.get('Host',''):
                self.error(403,'INVALID_ORIGIN','Submit is available from this local application only.');return
            if self.headers.get_content_type()!='application/json' or self.headers.get('Transfer-Encoding'):
                self.error(415,'INVALID_BODY','Use a bounded JSON request.');return
            try:
                lengths=self.headers.get_all('Content-Length',[])
                if len(lengths)!=1:raise ValueError()
                length=int(lengths[0])
                if not 1<=length<=16384:raise ValueError()
            except ValueError:
                self.error(413,'INVALID_LENGTH','Request body exceeds the endpoint limit.');return
            try:
                self.connection.settimeout(5)
                data=self.rfile.read(length)
                if len(data)!=length:raise ResearchError('Incomplete request')
                self.dispatch(data=data)
            except ResearchConflict as exc:self.error(409,'REQUEST_CONFLICT',str(exc))
            except ResearchBlocked as exc:self.send_json(422,{'error':{'code':'EXTERNAL_ALIGNMENT_BLOCKED','message':str(exc)},'blockers':exc.blockers,'recorded':False})
            except FileNotFoundError:self.error(404,'NOT_FOUND','The research request is unavailable.')
            except (ResearchError,ValueError,TypeError,UnicodeError):self.error(400,'INVALID_SUBMISSION','Use exact registered selections and a unique request ID.')
            except Exception:self.error(503,'SUBMISSION_UNAVAILABLE','The request could not be verified or durably recorded. Retry with the same request ID.')
        def reject_method(self):
            self.close_connection=True
            if self.allowed_request():self.error(405,'METHOD_NOT_ALLOWED','Only the explicit submission actions support writes.',allow=True)
        do_PUT=reject_method
        do_PATCH=reject_method
        do_DELETE=reject_method
        do_OPTIONS=reject_method
        do_TRACE=reject_method
        do_CONNECT=reject_method

    try:server=ThreadingHTTPServer((host,port),Handler)
    except OSError:
        jobs.close()
        raise
    server.daemon_threads=True
    original_close=server.server_close
    def close():
        jobs.close();original_close()
    server.server_close=close
    server.research_jobs=jobs
    return server
