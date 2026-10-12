"""Read-only discovery and exact-version resolution of registered scopes."""
import re

from data.scopes import ScopeNotFound, list_scopes, resolve_scope

SCOPE_ID = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,127}\Z', re.ASCII)
SCOPE_VERSION = re.compile(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z', re.ASCII)


class InvalidScopeQuery(ValueError):
    pass


def list_scope_library(root):
    return list_scopes(root)


def get_scope_resolution(root, identifier, version):
    if not isinstance(identifier, str) or not SCOPE_ID.fullmatch(identifier):
        raise ScopeNotFound('Unknown Scope')
    if not isinstance(version, str) or not SCOPE_VERSION.fullmatch(version):
        raise InvalidScopeQuery('An exact registered version is required')
    return resolve_scope(root, identifier, version)
