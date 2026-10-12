"""Operational observation of the existing preparation callback.

This adapter does not change preparation inputs, outputs, order or calculations.
Progress is a replaceable sidecar, not research evidence. It intentionally lives
outside the scientific implementation fingerprint, like the rest of the UI API.
"""
from copy import deepcopy
import logging
from threading import local
from runtime.research_jobs import ResearchJobs, now
from research.store import inside, install_bytes, read_json
from research.contracts import canonical


class _ObservedAdapter:
    def __init__(self, delegate, jobs, request_id):
        self.delegate, self.jobs, self.request_id = delegate, jobs, request_id

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def prepare_phase(self, root, plan, phase, progress=None, **kwargs):
        members = [m['instrument_id'] for m in plan['members']]
        state = {'phase': phase, 'plan_id': plan['plan_id'], 'state': 'starting',
                 'members_total': len(members), 'members_completed': 0,
                 'batches_completed': 0, 'instrument': None, 'start': None, 'end': None}
        self.jobs._preparation(self.request_id, state)
        def observe(event):
            # Preserve cancellation/checkpoint behavior before operational writes.
            if progress:
                progress(event)
            if state['state'] == 'preparing_batch':
                state['batches_completed'] += 1
            instrument = event.get('instrument')
            state.update(state='preparing_batch', instrument=instrument,
                         start=event.get('start'), end=event.get('end'),
                         members_completed=members.index(instrument) if instrument in members else 0)
            self.jobs._preparation(self.request_id, state)
        try:
            result = self.delegate.prepare_phase(root, plan, phase, progress=observe, **kwargs)
        except BaseException:
            state['state'] = 'interrupted'
            self.jobs._preparation(self.request_id, state)
            raise
        if state['state'] == 'preparing_batch':
            state['batches_completed'] += 1
        state.update(state='complete', members_completed=len(members), instrument=None, start=None, end=None)
        self.jobs._preparation(self.request_id, state)
        return result


class ObservedResearchJobs(ResearchJobs):
    """Thread-local adapter instrumentation; Submit still sees the native adapter.

    In particular, adapter=None on the HTTP thread retains all native submission
    validation and external-feature routing. Other threads never see the wrapper.
    """
    def __init__(self, *args, **kwargs):
        self._progress_context = local()
        super().__init__(*args, **kwargs)

    @property
    def adapter(self):
        rid = getattr(self._progress_context, 'request_id', None)
        if rid is None:
            return self._base_adapter
        delegate = self._base_adapter
        if delegate is None:
            from research import inputs
            delegate = inputs
        return _ObservedAdapter(delegate, self, rid)

    @adapter.setter
    def adapter(self, value):
        self._base_adapter = value

    def _run(self, rid):
        self._progress_context.request_id = rid
        try:
            return super()._run(rid)
        finally:
            del self._progress_context.request_id

    def _preparation(self, rid, progress):
        try:
            # The sole executor owns preparation. Reading its small projection
            # avoids rescanning the event chain for every displayed batch.
            job = read_json(self._job_path(rid))
            value = dict(progress, request_id=rid, attempt_id=job['attempt_id'], plan=job.get('plan'), updated_at=now())
            install_bytes(inside(self.root, 'storage/catalog/operations/preparation/'+rid+'.json'),
                          canonical(value)+b'\n', mutable=True)
        except Exception:
            logging.getLogger(__name__).exception('Preparation progress could not be saved')

    def public(self, job):
        value = super().public(job)
        value.pop("preparation_progress", None)
        value.pop("preparation_progress_unavailable", None)
        try:
            progress = read_json(inside(self.root, 'storage/catalog/operations/preparation/'+job['request_id']+'.json'))
            if (progress['request_id'] == job['request_id'] and progress['attempt_id'] == job['attempt_id']
                    and job.get('plan') and progress.get('plan') == job['plan']):
                value['preparation_progress'] = deepcopy(progress)
        except FileNotFoundError:
            pass
        except (KeyError, ValueError, TypeError, OSError):
            value['preparation_progress_unavailable'] = True
        return value
