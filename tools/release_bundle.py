#!/usr/bin/env python3
"""Build and verify a commit-addressed, source-only deployment artifact."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile

FOLDERS = {'src', 'ui', 'tools', 'deploy', 'tests', 'specs', 'definitions', 'docs', 'config'}
ROOT_FILES = {'README.md', 'requirements-data.txt', 'requirements-cloud.lock'}
SECRET = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|dop_v1_[0-9a-f]{64}|AKIA[0-9A-Z]{16}')


def safe_path(name):
    p = PurePosixPath(name)
    if (not name or p.is_absolute() or '..' in p.parts or '\\' in name or str(p) != name
            or any(x in {'private', '__pycache__', '.git'} for x in p.parts)
            or any(x.startswith('.env') for x in p.parts)
            or '.local.' in p.name or p.suffix in {'.key', '.pem', '.pyc', '.log', '.sqlite', '.sqlite3', '.db'}
            or p.name == '.gitkeep' or p.name.startswith(('credentials', 'secrets'))):
        return False
    return name in ROOT_FILES or (len(p.parts) > 1 and p.parts[0] in FOLDERS)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()+b'\n'


def build(root, output):
    root = Path(root).resolve()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args])
    if Path(git('rev-parse', '--show-toplevel').decode().strip()) != root:
        raise ValueError('Build must use the dedicated project repository')
    if git('status', '--porcelain', '--untracked-files=all').strip():
        raise ValueError('Commit changes before building a release')
    commit = git('rev-parse', 'HEAD').decode().strip()
    files = {}
    for name in git('ls-files', '-z').decode().split('\0'):
        if not name or name.startswith('.github/') or name in {'.gitignore', 'AGENTS.md'} or PurePosixPath(name).name == '.gitkeep':
            continue
        if not safe_path(name):
            raise ValueError('File is outside the release allowlist: '+name)
        p = root/name
        if p.is_symlink():
            raise ValueError('Symlinks are not allowed: '+name)
        data = p.read_bytes()
        if SECRET.search(data):
            raise ValueError('Credential pattern found; inspect locally: '+name)
        files[name] = data
    manifest = {'schema': 'gambit_code_release_v1', 'commit': commit,
                'repository': 'owenmosagiede/gambit-research-platform',
                'files': [{'path': n, 'sha256': sha(d), 'bytes': len(d)} for n, d in sorted(files.items())]}
    files['release-manifest.json'] = canonical(manifest)
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as out, gzip.GzipFile(filename='', mode='wb', fileobj=out, mtime=0) as gz, tarfile.open(fileobj=gz, mode='w') as tar:
        for name, data in sorted(files.items()):
            entry = tarfile.TarInfo(name); entry.size = len(data); entry.mode = 0o644; entry.mtime = 0
            tar.addfile(entry, io.BytesIO(data))
    digest = sha(output.read_bytes())
    output.with_suffix(output.suffix+'.sha256').write_text(digest+'  '+output.name+'\n')
    return {'commit': commit, 'sha256': digest, 'files': len(manifest['files'])}


def verify(archive, expected):
    raw = Path(archive).read_bytes()
    if not re.fullmatch('[0-9a-f]{64}', expected) or sha(raw) != expected:
        raise ValueError('Archive checksum mismatch')
    payloads = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as tar:
        total = 0
        for entry in tar:
            if not entry.isfile() or entry.name in payloads or (entry.name != 'release-manifest.json' and not safe_path(entry.name)):
                raise ValueError('Unsafe or duplicate archive entry')
            total += entry.size
            if entry.size > 50*1024**2 or total > 250*1024**2:
                raise ValueError('Source archive is too large')
            payloads[entry.name] = tar.extractfile(entry).read()
    manifest = json.loads(payloads.pop('release-manifest.json'))
    if manifest.get('schema') != 'gambit_code_release_v1' or not re.fullmatch('[0-9a-f]{40}', manifest.get('commit', '')):
        raise ValueError('Invalid release manifest')
    if manifest.get('repository') != 'owenmosagiede/gambit-research-platform':
        raise ValueError('Unexpected repository')
    rows = manifest['files']
    if len({r['path'] for r in rows}) != len(rows) or {r['path'] for r in rows} != set(payloads):
        raise ValueError('Manifest inventory mismatch')
    for row in rows:
        data = payloads[row['path']]
        if len(data) != row['bytes'] or sha(data) != row['sha256'] or SECRET.search(data):
            raise ValueError('Release content verification failed: '+row['path'])
    return manifest, payloads


if __name__ == '__main__':
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build'); b.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1]); b.add_argument('--output', type=Path, required=True)
    v = sub.add_parser('verify'); v.add_argument('archive', type=Path); v.add_argument('--sha256', required=True)
    a = p.parse_args()
    if a.command == 'build': print(json.dumps(build(a.root, a.output)))
    else:
        m, _ = verify(a.archive, a.sha256); print(json.dumps({'verified': True, 'commit': m['commit'], 'files': len(m['files'])}))
