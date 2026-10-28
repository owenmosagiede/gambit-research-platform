"""Recognize one completed retirement during an explicitly approved cutover.

This module cannot install or delete definitions. The ordinary deployment planner
is unchanged. Protected historical evidence and both full source archives must
agree before its exact missing-definition blockers can be acknowledged.
"""
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile

import release_server as release
from release_bundle import canonical, safe_path, sha, SECRET

SOURCE_COMMIT = '9654b7de0b90d7f9a85718638effc271f6d6c6e1'
SOURCE_SHA256 = '225910f261192e6c2d92c3733d61da4a1ccd2b5ded9c7558b0dff3f04240b118'
PRIOR_RELEASE_ID = SOURCE_COMMIT + '-c5f149eefa65'
RESET_SHA256 = '4f3cfd3140376ee892d50bf6322752d77fc6fc7c84331c2ddc5501ee77da7ee0'
EVIDENCE_SHA256 = {
    'plan': '933990b62b28ca4d208eed9b296dd486f4b34c00127906e0cb439ca3666562b4',
    'status': '0cbda495d156fa7b68b92b4911eb82e683a57c5886465e67f32d64163137586c',
    # The server stores canonical JSON; the local pretty-printed export differs.
    'receipt': 'b8821b141a89b484ab6ec52089dbf52171c84d882803054cbc75b23060d6a580',
}
OMISSIONS_SHA256 = 'ce5c2904edea98fc97f7f4a865f8e0ffedb39fe2cd32a55dc5946f7c50686c5f'
OMISSIONS_COUNT = 5717
PREFIXES = ('definitions/features/', 'definitions/feature_recipes/',
            'definitions/feature_applications/bindings/')
REGISTRY_BLOCKER = 'Requires an explicit registry/configuration/runtime migration'
SAVED_NAMES = {'plan': 'plan.json', 'status': 'status.json', 'receipt': 'receipt.json'}


def _digest(value):
    # Historical reset/release identities include the terminal newline.
    return sha(canonical(value))


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeError('Duplicate retirement evidence key')
            result[key] = value
        return result
    def invalid(value):
        raise RuntimeError('Non-finite retirement evidence number: ' + value)
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


def _relative(name):
    if not isinstance(name, str):
        raise RuntimeError('Unsafe retirement path')
    p = PurePosixPath(name)
    if (not name or p.is_absolute() or '..' in p.parts or '\\' in name
            or not p.parts or str(p) != name):
        raise RuntimeError('Unsafe retirement path')
    return name


def _protected_bytes(path, expected=None):
    """Read root-owned regular evidence without writable/redirected ancestors."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise RuntimeError('Retirement evidence needs an absolute protected path')
    for part in (path, *path.parents):
        info = part.lstat()
        if (stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022
                or (part == path and not stat.S_ISREG(info.st_mode))
                or (part != path and not stat.S_ISDIR(info.st_mode))):
            raise RuntimeError('Retirement evidence must be root-owned and protected: ' + str(part))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0
                or before.st_mode & 0o022 or before.st_size > 300 * 1024**2):
            raise RuntimeError('Unprotected or oversized retirement evidence')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read()
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size,
                                       after.st_mtime_ns, after.st_ctime_ns):
            raise RuntimeError('Retirement evidence changed while reading')
    finally:
        os.close(fd)
    if expected is not None and sha(data) != expected:
        raise RuntimeError('Retirement evidence checksum differs: ' + path.name)
    return data


def _protected_directory(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise RuntimeError('Retirement evidence destination needs an absolute protected directory')
    for part in (path, *path.parents):
        info = part.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022):
            raise RuntimeError('Retirement evidence destination must be root-owned and protected')


def trusted_bytes(path, expected=None):
    """Read protected release evidence for the cutover control caller."""
    return _protected_bytes(path, expected)


def _archive(raw, expected):
    """Verify the bytes just read, without reopening a potentially changed path."""
    if not re.fullmatch('[0-9a-f]{64}', expected) or sha(raw) != expected:
        raise RuntimeError('Retirement archive checksum differs')
    files = {}; total = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        for entry in archive:
            if (not entry.isfile() or entry.name in files
                    or (entry.name != 'release-manifest.json' and not safe_path(entry.name))):
                raise RuntimeError('Unsafe or duplicate retirement archive entry')
            total += entry.size
            if entry.size > 50 * 1024**2 or total > 250 * 1024**2:
                raise RuntimeError('Retirement source archive is too large')
            files[entry.name] = archive.extractfile(entry).read()
    manifest = _json(files.pop('release-manifest.json'))
    if (manifest.get('schema') != 'gambit_code_release_v1'
            or manifest.get('repository') != 'owenmosagiede/gambit-research-platform'
            or not re.fullmatch('[0-9a-f]{40}', manifest.get('commit', ''))):
        raise RuntimeError('Invalid retirement archive manifest')
    rows = manifest['files']
    if len({r['path'] for r in rows}) != len(rows) or {r['path'] for r in rows} != set(files):
        raise RuntimeError('Retirement archive inventory mismatch')
    for row in rows:
        data = files[_relative(row['path'])]
        if len(data) != row['bytes'] or sha(data) != row['sha256'] or SECRET.search(data):
            raise RuntimeError('Retirement archive payload mismatch')
    return manifest, files


def _derive(evidence, source_manifest, source_files, target_manifest, target_files):
    reset, status, receipt = (evidence[key] for key in ('plan', 'status', 'receipt'))
    if (reset.get('schema') != 'gambit_clean_momentum_reset_v1'
            or reset.get('sha256') != RESET_SHA256
            or _digest({k: v for k, v in reset.items() if k != 'sha256'}) != RESET_SHA256
            or status.get('phase') != 'complete' or status.get('plan_sha256') != RESET_SHA256
            or status.get('verification', {}).get('verified') is not True):
        raise RuntimeError('Exact verified completed retirement is required')
    if (source_manifest['commit'] != SOURCE_COMMIT
            or receipt.get('schema') != 'gambit_code_deployment_plan_v1'
            or receipt.get('status') != 'succeeded' or receipt.get('data_touched') is not False
            or receipt.get('commit') != SOURCE_COMMIT or receipt.get('release_id') != PRIOR_RELEASE_ID
            or receipt.get('blockers') != []):
        raise RuntimeError('Exact successful prior deployment receipt is required')
    review = receipt['post_reset_review']
    required = {'archive_sha256': SOURCE_SHA256, 'manifest_sha256': _digest(source_manifest),
        'reset_plan_sha256': RESET_SHA256, 'reset_plan_file_sha256': EVIDENCE_SHA256['plan'],
        'reset_status_file_sha256': EVIDENCE_SHA256['status'], 'omissions_sha256': OMISSIONS_SHA256,
        'action': 'acknowledged_absent_no_registry_writes'}
    if any(review.get(k) != v for k, v in required.items()):
        raise RuntimeError('Prior retirement acknowledgement differs')
    recognized = {}
    for directory, item in reset['moves'].items():
        _relative(directory)
        if not directory.startswith(PREFIXES):
            continue
        for relative, row in item.get('files', {}).items():
            name = _relative(directory + '/' + _relative(relative))
            if name in recognized:
                raise RuntimeError('Duplicate retirement inventory path')
            if name not in source_files:
                continue  # Prior reset also retired files absent from the source package.
            if (not name.startswith(PREFIXES) or sha(source_files[name]) != row['sha256']
                    or len(source_files[name]) != row['bytes']
                    or target_files.get(name) != source_files[name]):
                raise RuntimeError('Retired definition differs between reset and archives: ' + name)
            recognized[name] = row['sha256']
    if (len(recognized) != OMISSIONS_COUNT or _digest(recognized) != OMISSIONS_SHA256
            or review.get('acknowledged_omissions') != recognized):
        raise RuntimeError('Exact reviewed retirement inventory is required')
    return recognized


def _absent(root, omissions):
    root = Path(root)
    if not root.is_absolute() or any(part.is_symlink() for part in (root, *root.parents)):
        raise RuntimeError('Retirement application root is redirected')
    for name in omissions:
        path = root / _relative(name)
        if any(part.is_symlink() for part in (path, *path.parents) if part.is_relative_to(root)):
            raise RuntimeError('Retired definition path is redirected: ' + name)
        if path.exists() or not path.resolve().is_relative_to(root.resolve()):
            raise RuntimeError('Retired definition reappeared: ' + name)


@dataclass(frozen=True)
class RetirementContext:
    evidence_paths: dict
    source_archive: Path
    source_sha256: str
    target_archive: Path
    target_sha256: str
    source_manifest: dict
    source_files: dict
    target_manifest: dict
    target_files: dict
    _binding: dict
    retirement_archive: Path | None = None

    @property
    def binding(self):
        return _json(canonical(self._binding))

    def _fresh(self):
        fresh, raw = _load(self.evidence_paths, self.source_archive, self.source_sha256,
                           self.target_archive, self.target_sha256, self.retirement_archive)
        if fresh.binding != self.binding:
            raise RuntimeError('Retirement context changed')
        return fresh, raw

    def revalidate(self, root):
        fresh, _ = self._fresh()
        _absent(root, fresh._binding['acknowledged_omissions'])
        return fresh.binding

    def code_plan(self, root, manifest, files, archive_sha256):
        fresh, _ = self._fresh()
        _absent(root, fresh._binding['acknowledged_omissions'])
        pair = {fresh.source_sha256: (fresh.source_manifest, fresh.source_files),
                fresh.target_sha256: (fresh.target_manifest, fresh.target_files)}.get(archive_sha256)
        if pair is None or manifest != pair[0] or files != pair[1]:
            raise RuntimeError('Planner archive differs from retirement context')
        result = release.plan(root, manifest, files)
        recognized = fresh._binding['acknowledged_omissions']
        matched = [b['path'] for b in result['blockers']
                   if b['path'] in recognized and b['reason'] == REGISTRY_BLOCKER]
        if len(matched) != len(recognized) or set(matched) != set(recognized):
            raise RuntimeError('Planner did not identify every exact retirement blocker')
        result['blockers'] = [b for b in result['blockers']
            if not (b['path'] in recognized and b['reason'] == REGISTRY_BLOCKER)]
        if any(row['path'] in recognized for row in result['changes']):
            raise RuntimeError('Retired definitions cannot become deployment writes')
        result['retirement_acknowledgement'] = fresh.binding
        result.pop('plan_sha256', None)
        result['plan_sha256'] = _digest(result)
        return result

    def persist(self, folder):
        """Copy exact external evidence for recovery; never copy into application."""
        fresh, raw = self._fresh()
        folder = Path(folder)
        _protected_directory(folder.parent)
        folder.mkdir(mode=0o700, parents=False, exist_ok=False)
        payloads = {SAVED_NAMES[key]: raw[key] for key in SAVED_NAMES}
        payloads.update({'source.tar.gz': raw['source'], 'target.tar.gz': raw['target'],
                         'context.json': canonical(fresh.binding)})
        if fresh.retirement_archive is not None:
            payloads['retirement-source.tar.gz'] = raw['retirement_source']
        for name, data in payloads.items():
            fd = os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as out:
                out.write(data); out.flush(); os.fsync(out.fileno())
        fd = os.open(folder, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
        saved = load_saved(folder)
        if saved.binding != fresh.binding:
            raise RuntimeError('Saved retirement evidence differs')
        return saved


def _load(evidence_paths, source_archive, source_sha256, target_archive, target_sha256,
          retirement_archive=None):
    successor = source_sha256 != SOURCE_SHA256
    if set(evidence_paths) != set(SAVED_NAMES) or successor != (retirement_archive is not None):
        raise RuntimeError('Exact retirement inputs are required')
    if target_sha256 == source_sha256:
        raise RuntimeError('Retirement cutover requires distinct source and target archives')
    raw = {key: _protected_bytes(evidence_paths[key], EVIDENCE_SHA256[key]) for key in SAVED_NAMES}
    raw.update(source=_protected_bytes(source_archive, source_sha256),
               target=_protected_bytes(target_archive, target_sha256))
    source_manifest, source_files = _archive(raw['source'], source_sha256)
    target_manifest, target_files = _archive(raw['target'], target_sha256)
    evidence = {key: _json(raw[key]) for key in SAVED_NAMES}
    anchor_manifest, anchor_files = source_manifest, source_files
    if successor:
        raw['retirement_source'] = _protected_bytes(retirement_archive, SOURCE_SHA256)
        anchor_manifest, anchor_files = _archive(raw['retirement_source'], SOURCE_SHA256)
        # Both installed and proposed packages must retain the exact historically
        # retired definitions; this never broadens the acknowledged missing set.
        _derive(evidence, anchor_manifest, anchor_files, source_manifest, source_files)
    omissions = _derive(evidence, anchor_manifest, anchor_files, target_manifest, target_files)
    binding = {'schema': 'gambit_retired_definitions_v1', 'source_commit': SOURCE_COMMIT,
        'prior_release_id': PRIOR_RELEASE_ID, 'reset_plan_sha256': RESET_SHA256,
        'evidence_sha256': dict(EVIDENCE_SHA256), 'source_archive_sha256': source_sha256,
        'target_archive_sha256': target_sha256, 'source_manifest_sha256': _digest(source_manifest),
        'target_manifest_sha256': _digest(target_manifest), 'omissions_sha256': OMISSIONS_SHA256,
        'omissions_count': OMISSIONS_COUNT, 'acknowledged_omissions': omissions,
        'action': 'preserve_absence_no_registry_writes'}
    if successor:
        binding.update(schema='gambit_retired_definitions_v2', source_commit=source_manifest['commit'],
            retirement_source_commit=SOURCE_COMMIT, retirement_source_archive_sha256=SOURCE_SHA256,
            retirement_source_manifest_sha256=_digest(anchor_manifest))
    return RetirementContext(dict(evidence_paths), Path(source_archive), source_sha256,
        Path(target_archive), target_sha256, source_manifest, source_files, target_manifest,
        target_files, binding, Path(retirement_archive) if successor else None), raw


def load_context(evidence_paths, source_archive, source_sha256, target_archive, target_sha256,
                 *, retirement_archive=None):
    return _load(evidence_paths, source_archive, source_sha256, target_archive, target_sha256,
                 retirement_archive)[0]


def load_saved(folder):
    folder = Path(folder)
    binding = _json(_protected_bytes(folder / 'context.json'))
    context = load_context({key: folder / name for key, name in SAVED_NAMES.items()},
        folder / 'source.tar.gz', binding['source_archive_sha256'],
        folder / 'target.tar.gz', binding['target_archive_sha256'],
        retirement_archive=(folder / 'retirement-source.tar.gz'
                            if binding.get('schema') == 'gambit_retired_definitions_v2' else None))
    if context.binding != binding:
        raise RuntimeError('Saved retirement context differs')
    return context
