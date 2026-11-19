"""Lossless, bounded storage for disposable verified-metadata cache values."""
import base64
import binascii
import hashlib
import json
import zlib

from read_model.storage import IntegrityFailure, encoded

PREFIX = 'zlib1:'
MAX_VALUE_BYTES = 64 * 1024 * 1024


def pack(value):
    raw = encoded(value).encode()
    if len(raw) > MAX_VALUE_BYTES:
        raise ValueError('Verified metadata cache value exceeds its bound')
    if len(raw) < 1024:
        return raw.decode()
    compressed = base64.b64encode(zlib.compress(raw, level=1)).decode('ascii')
    envelope = PREFIX + str(len(raw)) + ':' + hashlib.sha256(raw).hexdigest() + ':' + compressed
    return envelope if len(envelope) < len(raw) else raw.decode()


def unpack(value):
    # Closed older generations used plain JSON. Their verified source checksum
    # baselines remain usable; conversion does not discard or replace them.
    if not value.startswith(PREFIX):
        if len(value.encode()) > MAX_VALUE_BYTES:
            raise IntegrityFailure('Verified metadata cache value exceeds its bound')
        return json.loads(value)
    try:
        if len(value) > 2 * MAX_VALUE_BYTES:
            raise ValueError('Oversized compressed cache envelope')
        _, size, expected, payload = value.split(':', 3)
        count = int(size)
        if str(count) != size or not 0 < count <= MAX_VALUE_BYTES:
            raise ValueError('Invalid cache expansion size')
        if len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
            raise ValueError('Invalid cache digest')
        stream = zlib.decompressobj()
        raw = stream.decompress(base64.b64decode(payload, validate=True), count + 1)
        if (len(raw) != count or not stream.eof or stream.unused_data or stream.unconsumed_tail
                or hashlib.sha256(raw).hexdigest() != expected):
            raise ValueError('Compressed cache content differs')
        return json.loads(raw)
    except (ValueError, TypeError, UnicodeError, binascii.Error, zlib.error) as exc:
        raise IntegrityFailure('Verified metadata cache content is invalid') from exc
