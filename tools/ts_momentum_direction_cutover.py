#!/usr/bin/env python3
"""Continue an existing TS momentum roster with P1-selected directions."""

import argparse
from collections import Counter
from hashlib import sha256
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from research.contracts import DISCOVERY_DIRECTION, ResearchError, canonical, ref
from research.direction import (SKIPPED_FOR_SIGN, continuation_id, exposure_key,
                                p2_exposures, verify_skipped)
from research.schedule import load_schedule, period_for
from research.store import install_bytes, lock, read_json
from runtime.research_jobs import ResearchJobs


def discovery_request(row, *, followup=False):
    return dict(row, expected_direction=DISCOVERY_DIRECTION,
                request_id=continuation_id(row['request_id'], followup=followup))


def plan_cutover(root, manifest_path, checkpoint_path, *, preview=False):
    """Capture exact parent jobs and eligible follow-ups without changing production."""
    raw = manifest_path.read_bytes()
    manifest, checkpoint = read_json(manifest_path), read_json(checkpoint_path)
    roster = manifest['entries']
    cursor = checkpoint['next_index']
    schedule = load_schedule(root)
    if (manifest['program'] != 'GAMBIT_TS_MOMENTUM_20261111'
            or manifest['schedule'] != ref(schedule)
            or checkpoint['manifest_sha256'] != sha256(raw).hexdigest()
            or not 0 <= cursor <= len(roster)
            or cursor != checkpoint['created'] or checkpoint['existing'] or checkpoint['blocked']
            or len(roster) != len({row['request_id'] for row in roster})
            or any(row['expected_direction'] != 'POSITIVE' for row in roster)):
        raise ResearchError('Original TS momentum roster and checkpoint differ')
    jobs = ResearchJobs(root)
    events = jobs._event_snapshot()
    from runtime.experiment_identity import IdentityIndex
    submissions = {path.stem for path in (root / 'storage/catalog/submissions').glob('*.json')}
    projections = {path.stem for path in (root / 'storage/catalog/operations/jobs').glob('*.json')}
    if (None in events or set(events) - submissions or projections - submissions):
        raise ResearchError('Resolve unexpected research event history before cutover')
    index = IdentityIndex(jobs)
    for path in (index.base / 'requests').glob('*.json'):
        journal = index.journal(path.stem)
        if journal['canonical_request_id'] not in submissions:
            raise ResearchError('Resolve incomplete intake before cutover')
    accepted = {row['request_id'] for row in roster[:cursor]}
    for rid in submissions - accepted:
        job = jobs._read_job(rid, events)
        if job is None or job['status'] not in ('succeeded', 'failed', 'blocked', 'cancelled'):
            raise ResearchError('An unrelated or unaccounted request blocks cutover')
    from data.legacy_batch_evidence import pending
    if pending(root):
        raise ResearchError('An active legacy batch blocks cutover')
    queued, staged, eligible = [], [], []
    states = Counter()
    for i, row in enumerate(roster):
        rid = row['request_id']
        if i >= cursor:
            staged.append(discovery_request(row))
            continue
        parent = jobs._submission(rid)
        job = jobs._read_job(rid, events)
        if parent['intent'] != {key: value for key, value in row.items() if key != 'request_id'}:
            raise ResearchError('Frozen momentum request differs from its roster')
        states[job['status']] += 1
        if job['status'] == 'queued' and not job['results'] and not job.get('plan'):
            if any(record['job']['status'] != 'queued' for record in jobs._events(rid, events)):
                raise ResearchError('An allegedly unstarted request already executed')
            queued.append({'parent': rid, 'child': discovery_request(row), 'parent_sha256': parent['record_sha256']})
        elif job['status'] == 'succeeded':
            plan = parent['frozen_plan']
            if plan['mode'] != 'TS':
                raise ResearchError('Momentum requests must retain their TS scope')
            for link_ref in job['results']:
                link = jobs.store.resolve('link', link_ref)['body']
                for validation_ref in link['validation_results']:
                    validation = jobs.store.resolve('validation', validation_ref)
                    if validation['body']['reason_codes'] != [SKIPPED_FOR_SIGN]:
                        continue
                    relationship = jobs.store.resolve('relationship', link['relationship'])
                    h = relationship['body']['horizon']
                    p1 = jobs.store.resolve('trial', validation['body']['discovery_trial'])
                    period = period_for(plan, 'P2', h)
                    verify_skipped(relationship, p1, validation, period)
                    eligible.append((rid, h, link_ref, exposure_key(relationship['body'], period)))
        elif not preview or job['status'] not in ('resolving', 'preparing', 'p1', 'p2'):
            raise ResearchError('Drain the active job and reconcile failed momentum requests before cutover')
    accessed, records, _ = p2_exposures(jobs.store, {row[3] for row in eligible})
    skipped = {}
    held = []
    for rid, h, link, identity in eligible:
        if (rid, h) in accessed or records.get(identity):
            held.append({'request_id': rid, 'horizon': h, 'reason': 'prior_p2_access'})
        else:
            skipped.setdefault(rid, {})[str(h)] = link
    followups = [{'parent': row['request_id'], 'child': discovery_request(row, followup=True),
                  'skipped': skipped[row['request_id']]}
                 for row in roster[:cursor] if row['request_id'] in skipped]
    return {'schema': 'ts_momentum_direction_cutover_v1', 'preview': preview,
            'roster_sha256': sha256(raw).hexdigest(),
            'checkpoint': checkpoint, 'original_states': dict(states),
            'queued': queued, 'staged': staged, 'followups': followups, 'held': held}


def replace_queued(jobs, row):
    """Preserve the original envelope and publish its successor before retiring it."""
    rid, child_id = row['parent'], row['child']['request_id']
    original = jobs._submission(rid)
    if original['record_sha256'] != row['parent_sha256']:
        raise ResearchError('Original queued envelope changed after review')
    jobs.submit(row['child'], momentum_parent=rid)
    with lock(jobs.root, 'research-writer'):
        parent = jobs._read_job(rid)
        if parent['status'] == 'cancelled' and parent.get('superseded_by') == child_id:
            return
        if (parent['status'] != 'queued' or parent.get('plan') or parent['results']
                or jobs._read_job(child_id)['status'] != 'queued'):
            raise ResearchError('Retirement requires two unstarted, frozen requests')
        parent.update(status='cancelled', stage='superseded', superseded_by=child_id,
                      message='Replaced by a queued request that selects direction in P1.')
        parent['cancel_requested'] = True
        jobs._append(parent)


def apply_queued(root, plan):
    """Run while the independent worker is drained and held by release control."""
    if plan.get('schema') != 'ts_momentum_direction_cutover_v1' or plan.get('preview') is not False:
        raise ResearchError('Queue replacement needs a reviewed stopped-worker plan')
    jobs = ResearchJobs(root)
    with lock(root, 'research-worker-service', nonblocking=True) as stopped:
        if not stopped:
            raise ResearchError('The independent worker must finish and drain before changing queued work')
        with lock(root, 'research-executor', nonblocking=True) as idle:
            if not idle:
                raise ResearchError('Research is still executing')
            for row in plan['queued']:
                replace_queued(jobs, row)


def write_next_manifest(manifest_path, path, plan):
    """Give the existing paced intake a new, immutable roster with a fresh checkpoint."""
    original = read_json(manifest_path)
    if sha256(manifest_path.read_bytes()).hexdigest() != plan['roster_sha256']:
        raise ResearchError('Original roster changed after review')
    followups = plan['followups']
    source = dict(original, program='GAMBIT_TS_MOMENTUM_DISCOVERY_V1',
                  source_roster_sha256=plan['roster_sha256'],
                  entries=[row['child'] for row in followups] + plan['staged'],
                  p2_followups={row['child']['request_id']: {
                      'parent_request_id': row['parent'], 'skipped': row['skipped']}
                      for row in followups})
    install_bytes(path, canonical(source) + b'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('preview', 'review'):
        view = commands.add_parser(command)
        view.add_argument('--root', type=Path, required=True)
        view.add_argument('--manifest', type=Path, required=True)
        view.add_argument('--checkpoint', type=Path, required=True)
        if command == 'review':
            view.add_argument('--output', type=Path, required=True)
    apply = commands.add_parser('apply-queued')
    apply.add_argument('--root', type=Path, required=True)
    apply.add_argument('--plan', type=Path, required=True)
    apply.add_argument('--plan-sha256', required=True)
    args = parser.parse_args()
    if args.command == 'apply-queued':
        raw = args.plan.read_bytes()
        if sha256(raw).hexdigest() != args.plan_sha256:
            raise ResearchError('The reviewed queue plan has changed')
        plan = read_json(args.plan)
        apply_queued(args.root, plan)
        return
    plan = plan_cutover(args.root, args.manifest, args.checkpoint, preview=args.command == 'preview')
    if args.command == 'review':
        install_bytes(args.output, canonical(plan) + b'\n')
    print(canonical({**plan['original_states'], 'staged': len(plan['staged']),
                     'skipped_p2': sum(len(row['skipped']) for row in plan['followups']),
                     'held_p2': len(plan['held'])}).decode())


if __name__ == '__main__':
    main()
