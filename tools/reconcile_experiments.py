#!/usr/bin/env python3
"""Inspect immutable experiment history; optionally rebuild its lookup projection.

Never launches research or selects between conflicting historical trials.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from runtime.research_jobs import ResearchJobs
from runtime.experiment_identity import IdentityIndex
from research.store import lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--rebuild-index', action='store_true')
    args = parser.parse_args()
    if not (args.root / 'config/research_execution.json').is_file():
        parser.error('An existing research workspace is required')
    jobs = ResearchJobs(args.root)
    with lock(args.root, 'research-writer'):
        state = IdentityIndex(jobs).rebuild(persist=args.rebuild_index)
    groups = defaultdict(list)
    unresolved = []
    for rid, entry in state['entries'].items():
        if entry['scientific_identity'] is None:
            unresolved.append(rid)
        else:
            groups[entry['scientific_identity']].append(rid)
    print(json.dumps({'schema': 'experiment_reconciliation_v1',
        'verified_submissions': len(state['entries']), 'unresolved_inputs': unresolved,
        'same_science_groups': [v for v in groups.values() if len(v) > 1],
        'publication_recovery_pending': state['pending'], 'integrity_issues': state['issues'],
        'index_rebuilt': args.rebuild_index, 'research_launched': False}, indent=2))
    return 1 if state['issues'] or unresolved else 0


if __name__ == '__main__':
    raise SystemExit(main())
