"""Replenish the existing TS queue without monopolizing the research writer."""

import argparse
import fcntl
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
import time


TERMINAL = {'succeeded', 'blocked', 'failed', 'cancelled'}
POLL_SECONDS = 45
MINIMUM_ADMISSION_INTERVAL = 8 * 60
BACKUP_UNIT = 'gambit-backup.service'


def may_admit(cursor, terminal_count, accepted, start_cursor, start_terminal):
    # Keep one slot for the initial admission and then replenish at the rate
    # that the worker finishes requests. An empty queue can always be refilled.
    budget = 1 + max(0, terminal_count - start_terminal)
    return cursor - start_cursor < budget or terminal_count >= accepted


def terminal_count(root, entries, cursor, read_json):
    directory = root / 'storage/catalog/operations/jobs'
    count = 0
    for row in entries[:cursor]:
        request_id = row['request_id']
        try:
            job = read_json(directory / (request_id + '.json'))
        except FileNotFoundError:
            continue  # The normal intake handles blocked requests and recovery.
        if job['request_id'] != request_id:
            raise ValueError('Job identity differs from the staged TS roster')
        count += job['status'] in TERMINAL
    return count


def backup_in_progress():
    state = subprocess.check_output(
        ['systemctl', 'show', BACKUP_UNIT, '--property=ActiveState', '--value'], text=True).strip()
    return state not in ('inactive', 'failed')


def run(args):
    root = args.root.resolve(strict=True)
    sys.path[:0] = [str(root / 'tools'), str(root / 'src')]
    from api.live_activity import observe
    from research.store import read_json
    from runtime.research_jobs import ACTIVE
    from ts_momentum_intake import launch, verify

    manifest_hash = sha256(args.manifest.read_bytes()).hexdigest()
    entries = verify(root, args.manifest)['entries']
    with args.checkpoint.with_suffix('.paced-intake.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            checkpoint = read_json(args.checkpoint)
            cursor = checkpoint['next_index']
            accepted = checkpoint['created'] + checkpoint['existing']
            if (checkpoint['manifest_sha256'] != manifest_hash
                    or not 0 <= args.start_terminal <= args.start_cursor <= cursor <= len(entries)
                    or cursor != accepted + len(checkpoint['blocked'])):
                raise ValueError('The paced intake checkpoint does not match its original roster and baseline')
            if cursor == len(entries):
                return
            # The existing durable checkpoint also preserves the admission
            # interval across a scheduler restart.
            checkpoint_age = time.time() - args.checkpoint.stat().st_mtime
            if checkpoint_age < MINIMUM_ADMISSION_INTERVAL or backup_in_progress():
                time.sleep(POLL_SECONDS)
                continue
            terminal = terminal_count(root, entries, cursor, read_json)
            if not may_admit(cursor, terminal, accepted, args.start_cursor, args.start_terminal):
                time.sleep(POLL_SECONDS)
                continue
            live = observe(root)
            active = live.get('active')
            if (live['worker']['state'] not in ('idle', 'running')
                    or live.get('activity_unavailable')
                    or (accepted > terminal and (not active or active['status'] not in ACTIVE))):
                time.sleep(POLL_SECONDS)
                continue
            started = time.monotonic()
            launch(root, args.manifest, args.checkpoint, count=1)
            updated = read_json(args.checkpoint)['next_index']
            if updated != cursor + 1:
                raise ValueError('Expected one request at the paced checkpoint')
            print(f'Paced intake advanced to {updated} after {terminal} terminal jobs '
                  f'({time.monotonic() - started:.1f}s).', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--start-cursor', type=int, required=True)
    parser.add_argument('--start-terminal', type=int, required=True)
    run(parser.parse_args())
