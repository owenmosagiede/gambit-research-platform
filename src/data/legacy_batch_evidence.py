"""Read-only compatibility for frozen batch history after scheduling retirement.

The preview representation must remain byte-for-byte compatible with historical
approval hashes. These readers never resolve inputs, submit jobs or repair state.
"""
from collections import Counter
from pathlib import Path

from research.contracts import ResearchError, digest, request_id
from research.store import read_json

BASE = 'storage/catalog/operations/research_batches'


def checked(path):
    value = read_json(path)
    if not isinstance(value, dict) or value.get('sha256') != digest({k: v for k, v in value.items() if k != 'sha256'}):
        raise ResearchError('Batch evidence checksum mismatch: ' + path.name)
    return value


def rows(directory):
    return sorted((checked(path) for path in (directory / 'rows').glob('*.json')), key=lambda row: row['index'])


def preview(directory, manifest):
    records = rows(directory); counts = dict(Counter(row['disposition'] for row in records))
    new = counts.get('new', 0); basis = manifest['request'].get('estimate_basis')
    estimates = {'new_submissions': new, 'p1_horizon_evaluations': new * 5,
        'p2_horizon_evaluations_upper_bound': new * 5,
        'scheduled_member_rows_upper_bound': {phase: sum(row.get('scheduled_member_rows', {}).get(phase, 0)
            for row in records if row['disposition'] == 'new') for phase in ('P1', 'P2')},
        'sequential_seconds_range': [new * n for n in basis['seconds_per_experiment']] if basis else None,
        'additional_bytes_range': [new * n for n in basis['bytes_per_experiment']] if basis else None,
        'basis': basis, 'execution': 'existing sequential worker',
        'limitations': ['Scheduled rows are workload bounds, not usable samples or independent observations.',
            'P2 depends on P1 admission. Reuse and coverage can reduce work.',
            'Time/storage are unknown unless an explicit calibration is supplied; estimates are not reservations.',
            'No extra workers or cloud capacity are provisioned.']}
    return {'batch_id': manifest['batch_id'], 'manifest_sha256': manifest['sha256'],
            'rows': [row['sha256'] for row in records], 'counts': counts, 'estimates': estimates}


def pending(root):
    """Keep unfinished legacy authority visible to the code-release idle gate."""
    base = Path(root) / BASE
    # Do not treat orphaned, redirected or unreadable evidence as an empty queue.
    if base.is_symlink() or (base.exists() and not base.is_dir()):
        raise ResearchError('Invalid legacy batch evidence directory')
    if not base.exists():
        return []
    active = []
    states = {'previewing', 'ready', 'approved', 'dispatching', 'paused', 'completed', 'needs_attention'}
    for directory in sorted(base.iterdir()):
        if directory.is_symlink() or not directory.is_dir():
            raise ResearchError('Unexpected legacy batch evidence: ' + directory.name)
        manifest_path = directory / 'manifest.json'; state_path = directory / 'state.json'
        if manifest_path.is_symlink() or not manifest_path.is_file() or state_path.is_symlink():
            raise ResearchError('Incomplete or redirected legacy batch evidence: ' + directory.name)
        manifest = checked(manifest_path)
        if (request_id(manifest.get('batch_id')) != directory.name
                or manifest.get('schema') not in ('research_batch_v1', 'research_batch_retained_ts_v1')):
            raise ResearchError('Legacy batch manifest identity or schema differs')
        if not state_path.exists():
            active.append('batch:' + directory.name)
            continue
        state = checked(state_path).get('state')
        if state not in states:
            raise ResearchError('Unknown legacy batch state: ' + directory.name)
        if state != 'completed':
            active.append('batch:' + directory.name)
    return active
