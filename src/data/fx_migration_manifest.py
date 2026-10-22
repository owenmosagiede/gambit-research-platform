"""Byte-identical research canonical JSON without whole-manifest copies."""
import hashlib
import os
import tempfile
from research.contracts import canonical,ResearchError


def chunks(value):
    if type(value) is dict:
        if any(type(k) is not str for k in value):raise ResearchError('Non-string key')
        yield b'{'
        for n,k in enumerate(sorted(value)):
            if n:yield b','
            yield canonical(k);yield b':'
            yield from chunks(value[k])
        yield b'}'
    elif type(value) in (list,tuple):
        yield b'['
        for n,v in enumerate(value):
            if n:yield b','
            yield from chunks(v)
        yield b']'
    else:yield canonical(value)


def manifest_digest(value):
    sha=hashlib.sha256()
    for part in chunks(value):sha.update(part)
    return sha.hexdigest()


def install_manifest(path,value,*,replace=False):
    """Atomic durable output; immutable existing files must have identical bytes."""
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.migration-manifest-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:
            for part in chunks(value):out.write(part)
            out.write(b'\n');out.flush();os.fsync(out.fileno())
        if replace:os.replace(name,path)
        else:
            try:os.link(name,path)
            except FileExistsError:
                if path.is_symlink():raise ValueError('Symlink manifest')
                with open(name,'rb') as a,path.open('rb') as b:
                    while True:
                        x=a.read(1024*1024);y=b.read(1024*1024)
                        if x!=y:raise ValueError('Immutable manifest conflict')
                        if not x:break
        fd=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:
        if os.path.exists(name):os.unlink(name)
