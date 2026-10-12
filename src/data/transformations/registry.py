"""Read authoritative versioned definitions; no observation storage or discovery jobs.

Mathematical parameter validation is independent of optional, explicitly bounded
parameter-grid enumeration. Aliases never overwrite another library's identity.
"""
from copy import deepcopy
from itertools import product
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from data.catalog_reads import reading, catalog_glob

VERSION = '2.0.0'
DEFAULT_ROOT = Path(__file__).resolve().parents[3]


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def immutable_reference(record):
    """Existing v0.2 definition projection; display labels are not semantic."""
    semantic = {key: value for key, value in record.items() if key != 'display_name'}
    return {'id': record['id'], 'version': record['version'],
            'content_sha256': hashlib.sha256(canonical_bytes(semantic)).hexdigest()}


reference = immutable_reference


def _read(path):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('Duplicate registry JSON key')
            value[key] = item
        return value
    with reading(path):
        data = path.read_text()
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite registry value')))


class Registry:
    def __init__(self, root=DEFAULT_ROOT):
        self.root = Path(root).resolve()
        self._schema = _read(self.root/'specs/schemas/platform.schema.json')
        self._validator = Draft202012Validator(self._schema)
        self._operators = self._load('transformations', 'transformation_definition')
        self._policies = self._load('policies', 'policy_definition', prefix='POL_TRANSFORM_')
        for record in self._operators.values():
            body = record['body']
            if 'execution_contract' not in body:
                raise ValueError('Executable transformation contract missing')
            for name in ['output_unit_policy', 'missing_data_policy']:
                self.resolve_policy(body[name])
            self.resolve_policy(body['execution_contract']['grid_profile'])
            self._verify_specification(body['specification'])
        for policy in self._policies.values():
            self._verify_specification(policy['body']['specification'])

    def _load(self, folder, kind, prefix=''):
        records = {}
        for path in sorted(catalog_glob(self.root/'definitions'/folder, '*/'+VERSION+'.json')):
            if prefix and not path.parent.name.startswith(prefix):
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(self.root):
                raise ValueError('Registry path leaves platform')
            value = _read(path)
            self._validator.validate(value)
            if value['record_type'] != kind or value['id'] != path.parent.name or value['version'] != VERSION:
                raise ValueError('Registry identity/path mismatch')
            key = (value['id'], value['version'])
            if key in records:
                raise ValueError('Duplicate registry identity')
            records[key] = value
        return records

    def _verify_specification(self, binding):
        path = self.root/'storage/catalog/onboarding/evidence'/(binding['id']+'.json')
        if not path.resolve().is_relative_to(self.root):
            raise ValueError('Policy evidence path leaves platform')
        value = _read(path)
        if immutable_reference(value) != binding:
            raise ValueError('Policy specification identity mismatch')
        body = value['body']
        if value['record_type'] != 'onboarding_evidence' or body['kind'] != 'transform_execution_policy':
            raise ValueError('Wrong transformation policy evidence')
        payload = body['payload']
        target = self.root/f"storage/payloads/sha256/{payload['sha256'][:2]}/{payload['sha256']}.json"
        if not target.resolve().is_relative_to(self.root):
            raise ValueError('Policy payload path leaves platform')
        with reading(target):
            data = target.read_bytes()
        if len(data) != payload['byte_count'] or hashlib.sha256(data).hexdigest() != payload['sha256']:
            raise ValueError('Policy evidence checksum mismatch')

    def all_operators(self):
        return [deepcopy(self._operators[key]) for key in sorted(self._operators)]

    def operator(self, identifier, version=VERSION):
        try:
            return deepcopy(self._operators[(identifier, version)])
        except KeyError:
            raise ValueError('Unknown transformation identity/version: '+str(identifier)) from None

    def resolve(self, binding):
        if not isinstance(binding, dict) or set(binding) != {'id', 'version', 'content_sha256'}:
            raise ValueError('Expected pinned operator reference')
        record = self.operator(binding['id'], binding['version'])
        if immutable_reference(record) != binding:
            raise ValueError('Transformation reference content mismatch')
        return record

    def get_policy(self, identifier, version=VERSION):
        try:
            return deepcopy(self._policies[(identifier, version)])
        except KeyError:
            raise ValueError('Unknown transformation policy: '+str(identifier)) from None

    def resolve_policy(self, binding):
        if not isinstance(binding, dict) or set(binding) != {'id', 'version', 'content_sha256'}:
            raise ValueError('Expected pinned policy reference')
        record = self.get_policy(binding['id'], binding['version'])
        if immutable_reference(record) != binding or record['body']['approval_state'] != 'approved':
            raise ValueError('Unapproved or mismatched policy reference')
        return record

    def validate_parameters(self, entry, parameters, frequency, grid_policy=None):
        from .numeric import validate_parameters
        self.resolve(immutable_reference(entry))
        c = entry['body']['execution_contract']
        if frequency not in c['supported_frequencies']:
            raise ValueError('Unsupported frequency for this registration')
        normalized = validate_parameters(c['kernel'], parameters, frequency)
        if grid_policy is not None:
            if not any(candidate == normalized for candidate in self._grid_candidates(entry, frequency, grid_policy)):
                raise ValueError('Parameters outside the explicitly selected grid policy')
        return normalized

    def _grid_candidates(self, entry, frequency, policy):
        from .numeric import validate_parameters, ParameterError
        c = entry['body']['execution_contract']
        self.resolve(immutable_reference(entry))
        selected = self.resolve_policy(policy)
        extension = selected['id'] == 'POL_TRANSFORM_GRID_WEEKLY_156'
        if extension:
            if entry['id'] != 'TR_BASE_standard_zscore' or frequency != 'weekly':
                raise ValueError('Weekly156 policy applies only to the base weekly z-score')
            params = {item['name']:item['value']['value'] for item in selected['body']['parameters']}
            if params['frequency'] != frequency or params['kernel'] != c['kernel']:
                raise ValueError('Extension policy binding mismatch')
            yield from self._grid_candidates(entry, frequency, params['base_policy'])
            yield validate_parameters(c['kernel'], {'w': int(params['w'])}, frequency)
            return
        if policy != c['grid_profile']:
            raise ValueError('Grid policy is incompatible with the registration')
        if frequency not in c['supported_frequencies']:
            raise ValueError('Unsupported frequency for this registration')
        parameters = {item['name']:item['value']['value'] for item in selected['body']['parameters']}
        horizons = tuple(int(parameters[f'{frequency}_H{i}']) for i in range(1,6)) if any(isinstance(v,str) for v in c['parameter_grid'].values()) else None
        def alias(name):
            a,b,d,e,f = horizons
            return {'K':tuple(dict.fromkeys((1,a,b,d,e,f))),'W':horizons,'W_STAT':(b,d,e,f),
                    'HALF_LIFE':(a,b,d,e),'K_SHORT':tuple(dict.fromkeys((1,a,b))),
                    'K_SKIP':(b,d,e,f),'S_SKIP':tuple(dict.fromkeys((1,a))),
                    'K_ACCEL':tuple(dict.fromkeys((1,a,b,d))),'SLOPE_W':(b,d,e),'VOL_W':(b,d,e),
                    'TREND_W':(a,b,d),'K_SLOPE_CHANGE':tuple(dict.fromkeys((1,a))),
                    'AUTOCORR_LAG':tuple(dict.fromkeys((1,a))),'VARIANCE_RATIO_K':(a,b),
                    'VARIANCE_RATIO_W':(d,e,f)}[name]
        axes = {name: alias(axis) if isinstance(axis,str) else axis for name,axis in sorted(c['parameter_grid'].items())}
        candidate_count = 1
        for values in axes.values():
            candidate_count *= len(values)
        if candidate_count > 100000:
            raise ValueError('Registered parameter grid exceeds enumeration safety limit')
        for values in product(*axes.values()):
            candidate = dict(zip(axes,values))
            for name in ['low','high','q']:
                if name in candidate: candidate[name]=float(candidate[name])
            kernel = c['kernel']
            if selected['id'] == 'POL_TRANSFORM_GRID_BASE':
                if kernel in ['trend.ma_crossover','trend.ema_crossover','vol.ratio']:
                    allowed = {(horizons[a],horizons[b]) for a,b in [(0,1),(1,2),(2,3),(3,4),(0,2),(1,3),(2,4)]}
                    if (candidate['fast'],candidate['slow']) not in allowed:continue
            if kernel in ['distribution.quantile_range','input_distribution.quantile_range'] and (candidate['low'],candidate['high']) not in [(0.1,0.9),(0.05,0.95)]:continue
            if selected['id'] == 'POL_TRANSFORM_GRID_PRICE' and kernel == 'price.vol_normalized_log_return' and candidate['k'] > candidate['w']:continue
            try:
                yield validate_parameters(kernel,candidate,frequency)
            except ParameterError:
                # Finite legacy axes may include mathematically insufficient values.
                # Such values are excluded, never repaired or silently executed.
                continue

    def enumerate_grid(self, entry, frequency, policy, max_combinations=None):
        if type(max_combinations) is not int or not 1 <= max_combinations <= 100000:
            raise ValueError('Explicit max_combinations bound between1 and100000 is required')
        result = []
        for candidate in self._grid_candidates(entry,frequency,policy):
            if candidate not in result:result.append(candidate)
            if len(result) > max_combinations:
                raise ValueError('Grid exceeds the explicitly requested combination bound')
        return result


def all_operators(root=DEFAULT_ROOT):return Registry(root).all_operators()
def operator(identifier,version=VERSION,root=DEFAULT_ROOT):return Registry(root).operator(identifier,version)
def resolve(binding,root=DEFAULT_ROOT):return Registry(root).resolve(binding)
def get_policy(identifier,version=VERSION,root=DEFAULT_ROOT):return Registry(root).get_policy(identifier,version)
def resolve_policy(binding,root=DEFAULT_ROOT):return Registry(root).resolve_policy(binding)
def validate_parameters(entry,parameters,frequency,grid_policy=None,root=DEFAULT_ROOT):return Registry(root).validate_parameters(entry,parameters,frequency,grid_policy)
def enumerate_grid(entry,frequency,policy,max_combinations=None,root=DEFAULT_ROOT):return Registry(root).enumerate_grid(entry,frequency,policy,max_combinations)
