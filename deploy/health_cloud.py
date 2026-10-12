#!/usr/bin/env python3
"""Project private operational checks into one public, non-sensitive health bit."""
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT = Path('/srv/gambit/research_platform')
OUTPUT = Path('/run/gambit-health/status.json')
BACKUP = Path('/var/lib/gambit-backup/status.json')
sys.path.insert(0, str(ROOT / 'src'))


def checks(root, backup, *, now, worker, mounted, disk):
    result = {'volume': mounted, 'worker': worker.get('healthy') is True}
    result['capacity'] = all(disk(path).free >= 5 * 1024 ** 3 for path in (root, Path('/')))
    try:
        status = json.loads(backup.read_text())
        result['backup'] = False
        if status['status'] == 'succeeded':
            stamp = datetime.fromisoformat(status['finished_at']).timestamp()
            result['backup'] = 0 <= now - stamp <= 36 * 3600
        # A scheduled backup can be uploading while the application has restarted.
        # Keep this grace bounded; it never conceals a failed or stuck backup.
        if status['status'] in {'staging', 'uploading'}:
            stamp = datetime.fromisoformat(status['started_at']).timestamp()
            result['backup'] = 0 <= now - stamp <= 6 * 3600
    except (OSError, ValueError, KeyError, TypeError):
        result['backup'] = False
    return result


def main():
    if os.geteuid() != 0: raise SystemExit('Run under the root-owned health service')
    from services.research_worker import external_health
    now = time.time()
    try:
        result = checks(ROOT, BACKUP, now=now, worker=external_health(ROOT),
                        mounted=ROOT.parent.is_mount(), disk=shutil.disk_usage)
    except Exception:
        result = {'monitor': False}
    value = {'checked_at': now, 'healthy': all(result.values()), 'checks': result}
    OUTPUT.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    shutil.chown(OUTPUT.parent, user='root', group='gambit')
    fd, temporary = tempfile.mkstemp(dir=OUTPUT.parent, prefix='.health-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        shutil.chown(temporary, user='root', group='gambit'); os.chmod(temporary, 0o640)
        os.replace(temporary, OUTPUT)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


if __name__ == '__main__': main()
