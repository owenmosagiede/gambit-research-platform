"""Shared application routes; transports enforce authentication and HTTP boundaries."""
import json
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from data.alfred_onboarding import stable_read
from data.alfred_pit import inside
from api.pit_library import ASSETS as PIT_ASSETS, list_pit_library
from api.signal_library import (SIGNAL_ID, MATERIALIZATION_ID, SignalNotFound,
                                list_signal_library, get_signal_detail)

from api.target_library import (TARGET_ID, TargetNotFound, InvalidTargetQuery,
                                list_target_library, get_target_detail)
from api.scope_library import (SCOPE_ID, ScopeNotFound, InvalidScopeQuery,
                               list_scope_library, get_scope_resolution)

from api.feature_recipes import InvalidFeatureRecipeQuery, list_feature_recipes
from api.feature_library import InvalidFeatureQuery, FeatureNotFound, list_feature_library, get_feature_resolution
from api.signal_summaries import list_signal_summaries, get_signal_output_detail
from api.experiment_labels import with_experiment_labels
from research.contracts import readiness, request_id, ResearchError, ResearchConflict, ResearchBlocked
from research.store import ResearchStore
from services.research_worker import WebResearchJobs
from api.catalog_cache import CatalogCache
from api.feature_research import feature_research, trial_evidence, RECIPE, TRIAL, TABLE_ROLES

ASSETS = dict(PIT_ASSETS, **{'/signals.js': ('signals.js', 'text/javascript; charset=utf-8'),
                           '/signal-research.js': ('signal-research.js', 'text/javascript; charset=utf-8'),
                           '/signal-research.css': ('signal-research.css', 'text/css; charset=utf-8'),
                           '/targets.js': ('targets.js', 'text/javascript; charset=utf-8'),
                           '/scopes.js': ('scopes.js', 'text/javascript; charset=utf-8'),
                           '/features.js': ('features.js', 'text/javascript; charset=utf-8'),
                           '/queue.js': ('queue.js', 'text/javascript; charset=utf-8'),
                           '/batches.js': ('batches.js', 'text/javascript; charset=utf-8'),
                           '/submission.js': ('submission.js', 'text/javascript; charset=utf-8')})


# Local brand files only; no external font/CDN dependency or general directory serving.
ASSETS.update({
    '/brand/fonts/IBMPlexMono-Medium.ttf': ('brand/fonts/IBMPlexMono-Medium.ttf', 'font/ttf'),
    '/brand/fonts/IBMPlexMono-OFL.txt': ('brand/fonts/IBMPlexMono-OFL.txt', 'text/plain; charset=utf-8'),
    '/brand/fonts/IBMPlexMono-Regular.ttf': ('brand/fonts/IBMPlexMono-Regular.ttf', 'font/ttf'),
    '/brand/fonts/Inter-OFL.txt': ('brand/fonts/Inter-OFL.txt', 'text/plain; charset=utf-8'),
    '/brand/fonts/Inter-Variable.ttf': ('brand/fonts/Inter-Variable.ttf', 'font/ttf'),
    '/brand/gambit-app-mark.svg': ('brand/gambit-app-mark.svg', 'image/svg+xml'),
    '/brand/gambit-wordmark-reverse.svg': ('brand/gambit-wordmark-reverse.svg', 'image/svg+xml'),
    '/brand/gambit.css': ('brand/gambit.css', 'text/css; charset=utf-8'),
    '/gambit-theme.css': ('gambit-theme.css', 'text/css; charset=utf-8'),
})


class ApplicationRoutes:
    """One request, one response. Does not open sockets or execute workers."""
    def __init__(self, root, jobs, catalogs, method, path):
        self.root,self.jobs,self.catalogs=Path(root).resolve(),jobs,catalogs
        self.command,self.path=method,path
        self.response=None

    def send_bytes(self,status,content,content_type,head=False,allow=False):
        self.response=(status,content,content_type,allow)

    def send_json(self,status,value,head=False,allow=False):
        self.send_bytes(status,json.dumps(value,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()+b'\n','application/json; charset=utf-8',head,allow)

    def error(self,status,code,message,head=False,allow=False):
        self.send_json(status,{'error':{'code':code,'message':message}},head,allow)

    def read(self,head=False):
        root,jobs,catalogs=self.root,self.jobs,self.catalogs
        target=urlsplit(self.path)
        if target.scheme or target.netloc:
            self.error(404,'NOT_FOUND','This address is not available.',head);return
        if target.path=='/api/research-readiness':
            if target.query:self.error(400,'UNSUPPORTED_QUERY','This endpoint accepts no query.',head);return
            try:
                value=readiness(root);operational=jobs.operational_status();value.update(operational)
                if not operational['worker']['healthy']:
                    value['execution_enabled']=False
                    value['blockers'].append({'code':'WORKER_UNAVAILABLE','message':
                        'Research worker: '+operational['worker']['state']+'. Accepted requests remain stored. '+
                        ('Automatic recovery attempts are exhausted; the application service requires attention.' if operational['worker']['state']=='failed' else 'Execution readiness will update automatically.')})
                self.send_json(200,value,head)
            except Exception:self.error(503,'RESEARCH_SPEC_UNAVAILABLE','The backend Research Spec could not be verified.',head)
            return
        if target.path == '/api/batches' or target.path.startswith('/api/batches/'):
            from runtime.research_batches import ResearchBatches, checked
            batches = ResearchBatches(jobs)
            if target.query:
                self.error(400, 'UNSUPPORTED_QUERY', 'Use an exact batch ID.', head); return
            try:
                if target.path == '/api/batches':
                    value = {'batches': [{'batch_id': p.parent.name, 'name': checked(p)['request']['name'],
                        'state': checked(p.parent/'state.json') if (p.parent/'state.json').exists() else {'state':'previewing'}}
                        for p in sorted(batches.base.glob('*/manifest.json'))]}
                else:
                    value = batches.status(request_id(target.path[len('/api/batches/'):]))
                self.send_json(200, value, head)
            except FileNotFoundError: self.error(404, 'NOT_FOUND', 'Batch not found.', head)
            except ResearchError: self.error(409, 'BATCH_UNVERIFIED', 'Batch records could not be verified.', head)
            except Exception: self.error(503, 'BATCH_UNAVAILABLE', 'Batch status is temporarily unavailable.', head)
            return
        if target.path=='/api/experiments':
            if target.query:self.error(400,'UNSUPPORTED_QUERY','Use the queue endpoint without query parameters.',head);return
            try:value=with_experiment_labels(root,jobs,jobs.list_jobs())
            except Exception:self.error(503,'QUEUE_UNAVAILABLE','The experiment queue could not be verified.',head);return
            self.send_json(200,value,head);return
        if target.path.startswith('/api/experiments/'):

            if target.query:self.error(400,'UNSUPPORTED_QUERY','Use the exact request ID.',head);return
            try:value=jobs.get(request_id(target.path[len('/api/experiments/'):]))
            except (ResearchError,FileNotFoundError):self.error(404,'NOT_FOUND','This research request is unavailable.',head);return
            except Exception:self.error(503,'JOB_UNAVAILABLE','The research request could not be verified.',head);return
            self.send_json(200,{'job':value},head);return
        if target.path.startswith('/api/feature-research/'):
            identifier=target.path[len('/api/feature-research/'):]
            if target.query or not RECIPE.fullmatch(identifier):
                self.error(400,'INVALID_RECIPE','Use an exact recipe ID.',head);return
            try:value=catalogs.get(('feature-research',identifier),lambda:feature_research(root,identifier))
            except Exception:self.error(503,'RESEARCH_RESULTS_UNAVAILABLE','Authoritative research records could not be verified.',head);return
            self.send_json(200,value,head);return
        if target.path.startswith('/api/trial-evidence/'):
            identifier=target.path[len('/api/trial-evidence/'):]
            try:
                query=parse_qs(target.query,keep_blank_values=True,strict_parsing=True)
                if not TRIAL.fullmatch(identifier) or set(query)-{'role','offset'} or any(len(v)!=1 for v in query.values()):raise ValueError()
                role=query.get('role',[None])[0];offset=int(query.get('offset',['0'])[0])
                if role is not None and role not in TABLE_ROLES or offset<0 or offset>10000000 or role is None and offset:raise ValueError()
            except ValueError:self.error(400,'INVALID_EVIDENCE_QUERY','Use an exact trial and supported evidence page.',head);return
            try:value=catalogs.get(('trial-evidence',identifier,role,offset),lambda:trial_evidence(root,identifier,role,offset))
            except FileNotFoundError:self.error(404,'NOT_FOUND','This trial evidence is unavailable.',head);return
            except Exception:self.error(503,'EVIDENCE_UNAVAILABLE','Stored trial evidence could not be verified.',head);return
            self.send_json(200,value,head);return
        if target.path.startswith('/api/research-results/'):
            identifier=target.path[len('/api/research-results/'):]
            import re
            if target.query or not re.fullmatch(r'FEATURE_(?:RECIPE_)?[0-9a-f]{64}',identifier):
                self.error(400,'INVALID_RECIPE','Use an exact recipe ID.',head);return
            try:results=ResearchStore(root).results_for_recipe(identifier)
            except Exception:self.error(503,'RESEARCH_RESULTS_UNAVAILABLE','Authoritative research records could not be verified.',head);return
            self.send_json(200,{'recipe_id':identifier,'relationships':results},head);return
        scope_prefix = '/api/scope-library/'
        if target.path.startswith(scope_prefix):
            identifier = target.path[len(scope_prefix):]
            if not SCOPE_ID.fullmatch(identifier):
                self.error(404,'NOT_FOUND','This Scope is not available.',head);return
            try:
                query = parse_qs(target.query,keep_blank_values=True,strict_parsing=True)
                if set(query) != {'version'} or len(query['version']) != 1 or not query['version'][0]:
                    raise InvalidScopeQuery('An exact version is required')
            except ValueError:
                self.error(400,'UNSUPPORTED_QUERY','Use one exact registered Scope version.',head);return
            try:value=get_scope_resolution(root,identifier,query['version'][0])
            except InvalidScopeQuery:
                self.error(400,'UNSUPPORTED_QUERY','Use one exact registered Scope version.',head);return
            except ScopeNotFound:
                self.error(404,'NOT_FOUND','This registered Scope version is not available.',head);return
            except Exception:
                self.error(503,'SCOPE_UNAVAILABLE','This stored Scope could not be verified.',head);return
            self.send_json(200,value,head);return
        target_prefix = '/api/target-library/'
        if target.path.startswith(target_prefix):
            identifier = target.path[len(target_prefix):]
            if not TARGET_ID.fullmatch(identifier):
                self.error(404,'NOT_FOUND','This Target is not available.',head);return
            try:
                query = parse_qs(target.query,keep_blank_values=True,strict_parsing=True)
            except ValueError:
                self.error(400,'UNSUPPORTED_QUERY','Use an exact materialization and an optional paired training cutoff and precision.',head);return
            if set(query)-{'materialization_id','training_cutoff','cutoff_precision','start_inclusive','end_exclusive','range_precision'} or any(len(values)!=1 or not values[0] for values in query.values()):
                self.error(400,'UNSUPPORTED_QUERY','Use an exact materialization and an optional paired training cutoff and precision.',head);return
            materialization_id = query.get('materialization_id',[None])[0]
            training_cutoff = query.get('training_cutoff',[None])[0]
            cutoff_precision = query.get('cutoff_precision',[None])[0]
            try:value=get_target_detail(root,identifier,materialization_id,training_cutoff,cutoff_precision,
                query.get('start_inclusive',[None])[0],query.get('end_exclusive',[None])[0],
                query.get('range_precision',[None])[0])
            except InvalidTargetQuery:
                self.error(400,'UNSUPPORTED_QUERY','Use an exact materialization and a valid paired training cutoff and precision.',head);return
            except TargetNotFound:
                self.error(404,'NOT_FOUND','This stored Target or materialization is not available.',head);return
            except Exception:
                self.error(503,'TARGET_UNAVAILABLE','This stored Target could not be verified.',head);return
            self.send_json(200,value,head);return
        signal_prefix = ('/api/signal-library-outputs/' if target.path.startswith('/api/signal-library-outputs/')
                         else '/api/signal-library/')
        if target.path.startswith(signal_prefix):
            identifier = target.path[len(signal_prefix):]
            if not SIGNAL_ID.fullmatch(identifier):
                self.error(404,'NOT_FOUND','This Signal is not available.',head);return
            try:
                query = parse_qs(target.query,keep_blank_values=True,strict_parsing=True)
            except ValueError:
                self.error(400,'UNSUPPORTED_QUERY','Use only one valid materialization_id.',head);return
            if set(query)-{'materialization_id'} or any(len(values)!=1 for values in query.values()):
                self.error(400,'UNSUPPORTED_QUERY','Use only one valid materialization_id.',head);return
            materialization_id = query.get('materialization_id',[None])[0]
            if materialization_id is not None and not MATERIALIZATION_ID.fullmatch(materialization_id):
                self.error(400,'UNSUPPORTED_QUERY','Use only one valid materialization_id.',head);return
            try:
                reader=get_signal_output_detail if signal_prefix=='/api/signal-library-outputs/' else get_signal_detail
                value=reader(root,identifier,materialization_id)
            except SignalNotFound:
                self.error(404,'NOT_FOUND','This stored Signal or materialization is not available.',head);return
            except Exception:
                self.error(503,'SIGNAL_UNAVAILABLE','This stored Signal could not be verified.',head);return
            self.send_json(200,value,head);return
        if target.path=='/api/feature-resolution':
            try:
                query=parse_qs(target.query,keep_blank_values=True,strict_parsing=True)
                if set(query)!={'feature_id','feature_version','scope_id','scope_version'} or any(len(values)!=1 or not values[0] for values in query.values()):
                    raise InvalidFeatureQuery('Exact Feature and Scope identities required')
            except ValueError:
                self.error(400,'UNSUPPORTED_QUERY','Use exact registered Feature and Scope IDs and versions.',head);return
            try:
                value=get_feature_resolution(root,query['feature_id'][0],query['feature_version'][0],query['scope_id'][0],query['scope_version'][0])
            except (FeatureNotFound,ScopeNotFound):
                self.error(404,'NOT_FOUND','This Feature or Scope version is not available.',head);return
            except InvalidFeatureQuery:
                self.error(400,'UNSUPPORTED_QUERY','Use exact registered Feature and Scope IDs and versions.',head);return
            except Exception:
                self.error(503,'FEATURE_RESOLUTION_UNAVAILABLE','Stored Feature coverage could not be verified.',head);return
            self.send_json(200,value,head);return
        if target.path=='/api/feature-recipes':
            try:
                query=parse_qs(target.query,keep_blank_values=True,strict_parsing=True)
                if set(query)-{'instrument_id','limit','offset'} or any(len(values)!=1 or not values[0] for values in query.values()):
                    raise InvalidFeatureRecipeQuery('Unsupported query')
            except ValueError:
                self.error(400,'UNSUPPORTED_QUERY','Use an FX instrument identity, a limit from 1 to 500, and a nonnegative offset.',head);return
            try:
                value=list_feature_recipes(root,query.get('instrument_id',[None])[0],
                    query.get('limit',[None])[0],query.get('offset',[None])[0])
            except InvalidFeatureRecipeQuery:
                self.error(400,'UNSUPPORTED_QUERY','Use an FX instrument identity, a limit from 1 to 500, and a nonnegative offset.',head);return
            except Exception:
                self.error(503,'LIBRARY_UNAVAILABLE','The registered Feature recipes could not be loaded.',head);return
            self.send_json(200,value,head);return
        if target.path=='/api/target-library':
            try:
                query=parse_qs(target.query,keep_blank_values=True,strict_parsing=True)
            except ValueError:
                self.error(400,'UNSUPPORTED_QUERY','Use an instrument identity or a paired horizon amount and unit.',head);return
            if set(query)-{'instrument_id','horizon_amount','horizon_unit'} or any(len(values)!=1 or not values[0] for values in query.values()):
                self.error(400,'UNSUPPORTED_QUERY','Use an instrument identity or a paired horizon amount and unit.',head);return
            try:
                value=catalogs.get(('targets',tuple(sorted((k,tuple(v)) for k,v in query.items()))),
                    lambda:list_target_library(root,query.get('instrument_id',[None])[0],
                        query.get('horizon_amount',[None])[0],query.get('horizon_unit',[None])[0],metadata_only=True))
            except InvalidTargetQuery:
                self.error(400,'UNSUPPORTED_QUERY','Use an instrument identity or a paired horizon amount and unit.',head);return
            except Exception:
                self.error(503,'LIBRARY_UNAVAILABLE','The Target Library could not be loaded.',head);return
            self.send_json(200,value,head);return
        if target.query:
            self.error(400,'UNSUPPORTED_QUERY','This endpoint does not accept query parameters.',head);return
        if target.path=='/api/signal-library-summaries':
            try:value=catalogs.get_verified("list_signal_summaries",root,lambda:list_signal_summaries(root))
            except Exception:
                self.error(503,'LIBRARY_UNAVAILABLE','Signal recipe summaries could not be loaded.',head);return
            self.send_json(200,value,head);return
        if target.path=='/api/feature-library':
            try:value=catalogs.get_verified("list_feature_library",root,lambda:list_feature_library(root))
            except Exception:
                self.error(503,'LIBRARY_UNAVAILABLE','Registered Feature definitions could not be loaded.',head);return
            self.send_json(200,value,head);return
        if target.path=='/api/scope-library':
            try:value=catalogs.get("list_scope_library",lambda:list_scope_library(root))
            except Exception:
                self.error(503,'LIBRARY_UNAVAILABLE','The Scope Library could not be loaded.',head);return
            self.send_json(200,value,head);return
        if target.path=='/api/signal-library':
            try:value=catalogs.get("list_signal_library",lambda:list_signal_library(root))
            except Exception:
                self.error(503,'LIBRARY_UNAVAILABLE','The Signal Library could not be loaded.',head);return
            self.send_json(200,value,head);return
        if target.path=='/api/pit-library':
            try:value=catalogs.get("pit",lambda:list_pit_library(root,metadata_only=True))
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


    def write(self,data):
        jobs=self.jobs
        target=urlsplit(self.path)
        if target.path == '/api/batches' or target.path.startswith('/api/batches/'):
            from runtime.research_batches import ResearchBatches
            from data.alfred_onboarding import strict_json
            try:
                if target.scheme or target.netloc or target.query: raise ResearchError('Use exact batch endpoints')
                value = strict_json(data); batches = ResearchBatches(jobs)
                if target.path == '/api/batches':
                    result = batches.create(value)
                else:
                    parts = target.path[len('/api/batches/'):].split('/')
                    if len(parts) != 2: raise ResearchError('Use approve, pause or resume')
                    bid, action = parts; request_id(bid)
                    if action == 'approve': result = batches.approve(bid, value)
                    elif action in ('pause', 'resume') and value == {}: result = batches.control(bid, action)
                    else: raise ResearchError('Unsupported batch action')
                self.send_json(202, result)
            except ResearchConflict as exc: self.error(409, 'BATCH_CONFLICT', str(exc))
            except FileNotFoundError: self.error(404, 'NOT_FOUND', 'Batch not found.')
            except (ResearchError, ValueError, TypeError, UnicodeError) as exc: self.error(400, 'INVALID_BATCH', str(exc))
            except Exception: self.error(503, 'BATCH_UNAVAILABLE', 'Receipt uncertain. Check the same batch ID before retrying.')
            return
        submit=target.path=='/api/experiments'
        action=None;rid=None
        if target.path.startswith('/api/experiments/'):
            parts=target.path[len('/api/experiments/'):].split('/')
            if len(parts)==2 and parts[1] in ('cancel','resume'):
                rid,action=parts
        if not submit and action is None:
            self.error(405,'METHOD_NOT_ALLOWED','This endpoint provides read-only access.',allow=True);return
        if target.scheme or target.netloc or target.query:
            self.error(400,'INVALID_REQUEST','Use the exact submission endpoint.');return
        try:
            from data.alfred_onboarding import strict_json
            value=strict_json(data)
            if submit:
                job,created=jobs.submit(value)
                self.send_json(202 if created else 200,{'job':job});return
            request_id(rid)
            if value!={}:raise ResearchError('Action body must be empty')
            job=jobs.cancel(rid) if action=='cancel' else jobs.resume(rid)
            self.send_json(200,{'job':job})
        except ResearchConflict as exc:self.error(409,'REQUEST_CONFLICT',str(exc))
        except ResearchBlocked as exc:self.send_json(422,{'error':{'code':'EXTERNAL_ALIGNMENT_BLOCKED','message':str(exc)},'blockers':exc.blockers,'recorded':False})
        except FileNotFoundError:self.error(404,'NOT_FOUND','The research request is unavailable.')
        except (ResearchError,ValueError,TypeError,UnicodeError):self.error(400,'INVALID_SUBMISSION','Use exact registered selections and a unique request ID.')
        except Exception:self.error(503,'SUBMISSION_UNAVAILABLE','The request could not be verified or durably recorded. Retry with the same request ID.')
