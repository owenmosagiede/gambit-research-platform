#!/usr/bin/env python3
"""Operator-triggered release transfer. Default action only previews changes."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from release_bundle import verify


def ssh_args(key, known_hosts):
    for path in (key, known_hosts):
        if not Path(path).is_file(): raise ValueError('An existing deployment key and pinned known_hosts file are required')
    control = Path('/tmp/gambit-cloud-608233107')
    if control.is_symlink(): raise ValueError('Unsafe SSH control directory')
    control.mkdir(mode=0o700, exist_ok=True)
    if control.stat().st_uid != os.getuid() or control.stat().st_mode & 0o077:
        raise ValueError('SSH control directory must be private to this user')
    return ['ssh', '-i', str(key), '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'UserKnownHostsFile='+str(known_hosts), '-o', 'IPQoS=none', '-o', 'ConnectTimeout=15',
            '-o', 'ConnectionAttempts=2', '-o', 'ControlMaster=auto', '-o', 'ControlPersist=900',
            '-o', 'ControlPath='+str(control/'ssh'),
            'root@64.23.188.70']


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['plan', 'apply', 'rollback'], nargs='?', default='plan')
    p.add_argument('--ssh-key', type=Path, required=True); p.add_argument('--known-hosts', type=Path, required=True)
    p.add_argument('--archive', type=Path); p.add_argument('--sha256'); p.add_argument('--checks', type=Path)
    p.add_argument('--plan-sha256'); p.add_argument('--release-id')
    a = p.parse_args(); transport = ssh_args(a.ssh_key, a.known_hosts)
    control = ['/opt/gambit/venv/bin/python', '-B', '/opt/gambit/release-control/release_server.py', a.action]
    if a.action == 'rollback':
        if not a.release_id or not re.fullmatch('[0-9a-f]{40}-[0-9a-f]{12}', a.release_id): p.error('Valid release-id required')
        control += ['--release-id', a.release_id]
    else:
        if not a.archive or not a.sha256 or not a.checks: p.error('archive, sha256 and passing checks receipt are required')
        manifest, _ = verify(a.archive, a.sha256)
        checks = json.loads(a.checks.read_text())
        if checks.get('success') is not True or checks.get('commit') != manifest['commit']:
            p.error('Checks must pass for this exact release commit')
        remote = '/var/lib/gambit-releases/incoming/'+a.sha256+'.tar.gz'
        upload = """import hashlib,os,pathlib,sys,tempfile
p=pathlib.Path(sys.argv[1]);data=sys.stdin.buffer.read()
assert hashlib.sha256(data).hexdigest()==sys.argv[2], 'Checksum mismatch'
p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
if p.exists():
 assert hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[2], 'Existing archive differs'
else:
 fd,tmp=tempfile.mkstemp(dir=p.parent)
 with os.fdopen(fd,'wb') as f: f.write(data);f.flush();os.fsync(f.fileno())
 os.chmod(tmp,0o600);os.replace(tmp,p)
"""
        cmd = shlex.join(['/opt/gambit/venv/bin/python','-c',upload,remote,a.sha256])
        subprocess.run(transport+[cmd], input=a.archive.read_bytes(), check=True)
        control += ['--archive', remote, '--sha256', a.sha256]
        if a.action == 'apply':
            if not a.plan_sha256 or not re.fullmatch('[0-9a-f]{64}', a.plan_sha256): p.error('Reviewed plan-sha256 required')
            control += ['--plan-sha256', a.plan_sha256]
    result = subprocess.run(transport+[shlex.join(control)])
    raise SystemExit(result.returncode)


if __name__ == '__main__': main()
