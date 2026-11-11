"""Frozen, phase-separated FX inputs for explicitly approved research profiles.

Planning reads metadata only. P1 never parses P2 Target observations: partition
checksums concern bytes, then anchor AND endpoint date windows select rows before
JSON decoding. This is retrospective date-label research, never historical PIT or
live eligibility. No profile in this module grants scientific approval.
"""
from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
import gzip
import re

from data.alfred_onboarding import stable_read, strict_json
from data.feature_store import FeatureStore, PublicationError, materialization_path, read_materialization
from data.fx_feature_contracts import validate_record as validate_feature_manifest
from data.fx_feature_store import prepare_fx_feature
from data.reusable_features import load_reusable_recipe, legacy_bindings_for_recipe, legacy_recipe_projector
from data.scopes import resolve_scope
from data.fx_pipeline import list_instruments
from data.targets.store import TargetStore
from data.targets.fx import (_approved_policy, _price_snapshot, _definition, _schedule,
    validate_manifest as validate_target_manifest, validate_row as validate_target_row, construct_rows)
from data.transformations.contracts import normalize_time
from data.transformations.identity import canonical_bytes, digest, reference
from research.contracts import KERNEL_POLICIES
from research.performance import measure, counter
from research.schedule import period_for, resolved_periods

HORIZONS = (1, 7, 21, 63, 252)
APPROVALS = ('clock_compatibility', 'retrospective_alignment', 'validation_exposure', 'missing_evidence')


class InputsBlocked(ValueError):
    def __init__(self, message, *, reasons=None):
        self.reasons = reasons or [{'code': 'INPUTS_BLOCKED', 'message': str(message)}]
        self.blockers = self.reasons
        super().__init__(message)


class InputsCancelled(RuntimeError):
    cancelled = True


def _check_cancel(cancelled):
    if cancelled and cancelled():
        raise InputsCancelled('Research input preparation was cancelled')


def _profile(profile):
    if not isinstance(profile, dict) or profile.get('approval_state') != 'approved':
        raise InputsBlocked('Research profile has unresolved scientific decisions')
    if profile.get('availability_mode') != 'retrospective_date_label':
        raise InputsBlocked('Only explicitly approved retrospective date-label inputs are supported')
    if not profile.get('id') or not profile.get('version'):
        raise InputsBlocked('Research profile needs an exact identity and version')
    if any(profile.get('approvals', {}).get(name) is not True for name in APPROVALS):
        raise InputsBlocked('All research compatibility and exposure decisions must be explicit')
    kernel = profile.get('kernel', {})
    if (kernel.get('clock_compatibility') != 'approved' or kernel.get('horizon_unit') != 'scheduled_weekdays'
            or kernel.get('kernel_policy') not in KERNEL_POLICIES
            or kernel.get('missing_evidence') != KERNEL_POLICIES.get(kernel.get('kernel_policy'))
            or type(kernel.get('spacing')) is not int or kernel.get('spacing') != 1):
        raise InputsBlocked('Research clock is not approved for these scheduled-weekday Targets')
    periods = profile.get('periods', {})
    for phase in ('P1', 'P2'):
        period = periods.get(phase)
        if not isinstance(period, dict) or set(period) != {'start_inclusive', 'end_exclusive'}:
            raise InputsBlocked('Both research periods must be fixed before submission')
        normalize_time(period['end_exclusive'], 'date')
        automatic = phase == 'P1' and profile.get('discovery_start_rule') == 'scope_structural_start_v1' and period['start_inclusive'] is None
        if automatic and kernel['kernel_policy'] != 'scheduled_weekday_hac_v2':
            raise InputsBlocked('Automatic discovery start requires the versioned scheduled-weekday policy')
        if not automatic:normalize_time(period['start_inclusive'], 'date')
        if not automatic and period['start_inclusive'] >= period['end_exclusive']:
            raise InputsBlocked('Research period must increase')
    if periods['P1']['end_exclusive'] > periods['P2']['start_inclusive']:
        raise InputsBlocked('Discovery and validation periods must be ordered and disjoint')
    cutoff = profile.get('target_selection', {}).get('knowledge_cutoff')
    normalize_time(cutoff, 'date')
    if any(period['end_exclusive'] > cutoff for period in periods.values()):
        raise InputsBlocked('Research periods exceed the explicitly pinned knowledge cutoff')
    return deepcopy(profile)


def _period_days(period):
    when, stop = date.fromisoformat(period['start_inclusive']), date.fromisoformat(period['end_exclusive'])
    while when < stop:
        if when.weekday() < 5:
            yield when.isoformat()
        when += timedelta(days=1)


def _plan_id(plan):
    return 'RESEARCH_PLAN_' + digest({k: v for k, v in plan.items() if k != 'plan_id'})


def _validate_plan(plan):
    if not isinstance(plan, dict) or plan.get('plan_id') != _plan_id(plan):
        raise InputsBlocked('Frozen research plan identity differs')
    _profile(plan['profile'])
    if 'feature_application' in plan:
        from research.feature_applications import validate_frozen
        validate_frozen(plan['feature_application'], plan['recipe'], plan['scope'], plan['mode'])
    if plan.get('application_class') == 'external_stored_feature_to_individual_ts':
        from research.external_features import validate_policy
        source = plan['external_source']
        validate_policy(source['policy'])
        from research.contracts import ref as policy_ref
        if (plan['mode'] != 'TS' or plan['scope']['kind'] != 'instrument' or len(plan['members']) != 1
                or source['feature'] != plan['recipe'] or plan['members'][0]['feature'] != source['feature']
                or source['alignment_policy'] != plan['profile'].get('external_alignment_policy')
                or policy_ref(source['policy']) != source['alignment_policy']):
            raise InputsBlocked('Frozen external application contract differs')
    if not plan['members'] or plan['structural_common_start']!=max(member['structural_source_start'] for member in plan['members']):
        raise InputsBlocked('Frozen research structural start differs from member source coverage')
    expected = resolved_periods(plan['profile'], plan['structural_common_start'])
    fields = ('periods', 'horizons', 'horizon_periods', 'excluded_horizons')
    if any(plan.get(field) != expected.get(field) for field in fields):
        raise InputsBlocked('Frozen research plan periods or horizons differ')
    if plan['knowledge_cutoff'] != plan['profile']['target_selection']['knowledge_cutoff']:
        raise InputsBlocked('Frozen research cutoff differs')
    symbols = [m['instrument_id'] for m in plan['members']]
    if symbols != plan['scope']['members'] or len(symbols) != len(set(symbols)):
        raise InputsBlocked('Frozen research Scope membership differs')


def _phase(plan, phase, admission=None, horizon=None):
    _validate_plan(plan)
    if phase not in ('P1', 'P2'):
        raise InputsBlocked('Unknown research phase')
    if horizon is not None and (type(horizon) is not int or horizon not in plan['horizons']):
        raise InputsBlocked('Research must use one of the frozen plan horizons')
    if phase == 'P2':
        if (not isinstance(admission, dict) or admission.get('plan_id') != plan['plan_id']
                or admission.get('direction') != plan['intent']['expected_direction']):
            raise InputsBlocked('P2 requires admission bound to this plan and its frozen direction')
        admitted = admission.get('admitted_horizons')
        if (not isinstance(admitted, list) or not admitted or len(admitted) != len(set(admitted))
                or any(type(h) is not int or h not in plan['horizons'] for h in admitted)
                or (horizon is not None and horizon not in admitted)):
            raise InputsBlocked('P2 horizon has not been admitted by P1')
    return period_for(plan, phase, horizon)


def _feature_metadata(store, feature, snapshot, batch, cutoff):
    result = []
    for path in sorted(store.path('storage/catalog/feature_store').glob('*/manifest.json')):
        value = strict_json(stable_read(path))
        if value.get('definition') != reference(feature):
            continue
        if value.get('schema_version') != '0.6.0':
            continue
        validate_feature_manifest(value)
        key = value['input_key']
        if value['id'] != path.parent.name:
            raise InputsBlocked('Feature materialization path identity differs')
        if (key['source_snapshots'] != [reference(snapshot)] or key['batch_policy'] != batch
                or key['knowledge_cutoff'] != cutoff):
            continue
        store.verify_closure([value])  # Checksums only: no observation decoding.
        result.append({'reference': reference(value), 'period': deepcopy(key['period'])})
    return sorted(result, key=lambda item: item['reference']['id'])


def _target_metadata(store, snapshot, batch, cutoff, selected):
    """Select exact compatible manifests; ambiguity blocks, never pick max hash."""
    candidates = {str(h): [] for h in HORIZONS}
    for path in sorted(store.path('storage/catalog/target_store').glob('*/manifest.json')):
        raw = strict_json(stable_read(path))
        if raw.get('schema_version') != '0.5.0' or raw.get('price_snapshot') != reference(snapshot):
            continue
        manifest = validate_target_manifest(raw)
        key = manifest['input_key']
        if key['batch_policy'] != batch or key['knowledge_cutoff'] != cutoff:
            continue
        if manifest['id'] != path.parent.name:
            raise InputsBlocked('Target materialization path identity differs')
        definition = store.resolve(manifest['definition'])
        horizon = definition['body']['horizon']['amount']
        if horizon not in HORIZONS:
            continue
        schedule_policy = store.resolve(definition['body']['schedule_policy'])
        expected = _definition(store, snapshot, batch, horizon, schedule_policy, install=False)
        if reference(expected) != manifest['definition']:
            raise InputsBlocked('Target does not follow the frozen source and approved return policy')
        store.verify_closure([manifest])
        candidates[str(horizon)].append({'definition': reference(definition), 'materialization': reference(manifest)})
    targets = {}
    for horizon, found in candidates.items():
        pinned = selected.get(horizon)
        if pinned is not None:
            found = [item for item in found if (item['materialization'] == pinned if isinstance(pinned, dict)
                                               else item['materialization']['id'] == pinned)]
        if len(found) != 1:
            raise InputsBlocked(f'Exactly one compatible Target materialization required for {snapshot["body"]["instrument_id"]} horizon {horizon}')
        targets[horizon] = found[0]
    return targets


def _structural_start(store, snapshot):
    body = snapshot['body']
    starts = [normalize_time(body['coverage']['start'], 'date')]
    upstream = body.get('upstream_snapshots')
    if not isinstance(upstream, list) or not upstream:
        raise InputsBlocked('Structural common start needs exact canonical source coverage')
    for binding in upstream:
        source = store.resolve(binding)
        if source['record_type'] != 'snapshot_manifest' or source['body'].get('kind') != 'fx_source_snapshot':
            raise InputsBlocked('Structural coverage requires canonical FX PIT source metadata')
        starts.append(normalize_time(source['body']['coverage']['start'], 'date'))
    return max(starts)


def resolve_plan(root, intent, profile):
    """Resolve metadata and immutable bindings, without any preparation or labels."""
    profile = _profile(profile)
    if set(intent) != {'feature', 'scope', 'target_family', 'expected_direction'}:
        raise InputsBlocked('Expected one recipe, Scope, return family and explicit direction')
    if intent['target_family'] != 'price_return' or intent['expected_direction'] not in ('POSITIVE', 'NEGATIVE'):
        raise InputsBlocked('Only Price Return and a frozen ex-ante direction are supported')
    from research import external_features as external
    external_source = None
    from research import feature_applications
    try:
        scope = resolve_scope(root, intent['scope']['id'], intent['scope']['version'])
        application = feature_applications.resolve(root, intent['feature'], scope)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise InputsBlocked(str(exc), reasons=getattr(exc, 'blockers', None)) from exc
    external_selection = application['contract']['kind'] == feature_applications.SINGLE_SERIES
    try:
        recipe = (external.definition(root, intent['feature']) if external_selection else
                  load_reusable_recipe(root, intent['feature']['id'], intent['feature']['version']))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise InputsBlocked('The selected registered recipe or Scope could not be verified: ' + str(exc)) from exc
    if scope.get('kind') not in ('instrument', 'universe'):
        raise InputsBlocked('Scope must explicitly distinguish an instrument from a fixed universe')
    if scope['kind'] == 'instrument' and len(scope['members']) != 1:
        raise InputsBlocked('Instrument Scope must contain exactly one member')
    if not scope['members'] or len(set(scope['members'])) != len(scope['members']):
        raise InputsBlocked('Scope members are empty or ambiguous')
    if external_selection:
        if scope['kind'] != 'instrument':
            raise InputsBlocked('External stored Features support individual instrument TS only; universe broadcasting is unsupported')
        external_source = external.resolve_source(root, recipe, profile)
    store = TargetStore(root)
    config = strict_json(stable_read(store.path('config/fx_retrospective_completion.json')))
    batch = _approved_policy(store, config['return_policy'])
    cutoff = profile['target_selection']['knowledge_cutoff']
    if config.get('knowledge_cutoff') != cutoff:
        raise InputsBlocked('Profile cutoff differs from the approved completion configuration')
    if batch['horizons'] != list(HORIZONS) or batch['representation'] != 'simple':
        raise InputsBlocked('Price Return must bind the approved five-horizon simple-return family')
    oriented=scope.get('research_basis')=='currency_against_quote_reference'
    if oriented:
        from data.fx_currency_catalog import resolve_prices
        catalog,currency_rows=resolve_prices(root,scope['price_catalog'])
        if (profile['target_selection'].get('selection_scope')!='currency_price_catalog'
                or profile['target_selection'].get('price_catalog')!=scope['price_catalog']
                or batch!=catalog['body']['return_policy']):
            raise InputsBlocked('Currency Research Spec must pin this exact currency price catalog')
        current_rows=list(currency_rows.values())
    else:current_rows = list_instruments(root)
    current = {item['instrument_id']: item for item in current_rows}
    if len(current) != len(current_rows):
        raise InputsBlocked('Current instrument registry contains conflicting identities')
    bindings = [] if external_selection else legacy_bindings_for_recipe(root, reference(recipe), verify_features=False)
    projector = None if external_selection else legacy_recipe_projector(root, recipe)
    selected = profile['target_selection'].get('materializations', {})
    source_pins = profile['target_selection'].get('source_snapshots', {})
    registry_pins = profile['target_selection'].get('selection_scope') in ('registered_fx_registry','currency_price_catalog')
    allowed_pins = set(current) if registry_pins else set(scope['members'])
    if (not isinstance(selected, dict) or set(selected) - allowed_pins
            or any(not isinstance(values, dict) or set(values) - {str(h) for h in HORIZONS}
                   for values in selected.values())):
        raise InputsBlocked('Target materialization pins must address exact selected members and horizons')
    if not isinstance(source_pins,dict) or set(source_pins)-allowed_pins:
        raise InputsBlocked('Source pins must address registered members of the declared selection scope')
    if registry_pins and (set(selected)!=set(source_pins) or not set(scope['members']).issubset(selected)):
        raise InputsBlocked('The registered research source/Target bindings do not cover the selected Scope')
    if registry_pins:
        def exact_pin(value):
            return (isinstance(value,dict) and set(value)=={'id','version','content_sha256'}
                    and isinstance(value['id'],str) and bool(value['id'])
                    and isinstance(value['version'],str) and re.fullmatch(r'\d+\.\d+\.\d+',value['version'])
                    and isinstance(value['content_sha256'],str) and re.fullmatch(r'[0-9a-f]{64}',value['content_sha256']))
        if (any(set(values)!={str(h) for h in HORIZONS} or not all(exact_pin(v) for v in values.values()) for values in selected.values())
                or not all(exact_pin(v) for v in source_pins.values())):
            raise InputsBlocked('Registered research bindings require exact source and all five Target references for every member')
    members, blockers, starts = [], [], []
    for symbol in scope['members']:
        try:
            if symbol not in current or (symbol not in source_pins and current[symbol].get('price_snapshot') is None):
                raise InputsBlocked('Current price snapshot is unavailable')
            snapshot, _ = _price_snapshot(store, source_pins.get(symbol,current[symbol].get('price_snapshot')), batch, verify_rows=False)
            if snapshot['body']['instrument_id'] != symbol:
                raise InputsBlocked('Current price snapshot belongs to another Scope member')
            start = _structural_start(store, snapshot)
            if external_source:
                start = max(start, external_source['first_eligible_anchor'])
            starts.append(start)
            if external_source:
                members.append({'instrument_id': symbol, 'feature': reference(recipe),
                    'signal_id': recipe['body']['signal_id'], 'price_snapshot': reference(snapshot),
                    'source_view': snapshot['body']['definition'], 'structural_source_start': start,
                    'feature_materializations': [],
                    'targets': _target_metadata(store, snapshot, batch, cutoff, selected.get(symbol, {}))})
                continue
            found = [b for b in bindings if b['instrument_id'] == symbol and b['source_view'] == snapshot['body']['definition']]
            if len(found) != 1:
                raise InputsBlocked('Exactly one existing instrument binding is required')
            feature = store.resolve(found[0]['feature'])
            if reference(projector(feature)) != reference(recipe):
                raise InputsBlocked('Instrument binding differs from the reusable calculation')
            members.append({'instrument_id': symbol, 'feature': reference(feature),
                'signal_id': feature['body']['signal_id'], 'price_snapshot': reference(snapshot),
                'source_view': snapshot['body']['definition'], 'structural_source_start': start,
                'feature_materializations': _feature_metadata(store, feature, snapshot, batch, cutoff),
                'targets': _target_metadata(store, snapshot, batch, cutoff, selected.get(symbol, {}))})
        except (ValueError, KeyError, OSError, TypeError) as exc:
            blockers.append({'code': 'MEMBER_INPUTS_UNRESOLVED', 'instrument_id': symbol, 'message': str(exc)})
    if blockers:
        raise InputsBlocked('Selected Scope has unresolved members; no member was silently dropped', reasons=blockers)
    frozen_scope = {key: deepcopy(scope[key]) for key in ('id', 'version', 'kind', 'reference', 'membership_snapshot', 'members')}
    if oriented:
        frozen_scope.update({k:deepcopy(scope[k]) for k in ('research_basis','reference_currency','price_catalog')})
    schedule = resolved_periods(profile, max(starts))
    discovery = schedule['periods']['P1']
    if discovery['start_inclusive'] >= discovery['end_exclusive']:
        raise InputsBlocked('The selected Scope has no structural history in the approved discovery period')
    plan = {'schema_version': '1.0.0', 'intent': deepcopy(intent), 'profile': profile,
        'recipe': reference(recipe), 'scope': frozen_scope, 'mode': application['mode'], 'feature_application': application,
        **schedule, 'knowledge_cutoff': cutoff,
        'batch_policy': batch, 'structural_common_start': max(starts), 'members': members,
        'availability_mode': 'retrospective_date_label', 'historical_replay_certified': False, 'live_certified': False}
    if external_source:
        plan['application_class'] = 'external_stored_feature_to_individual_ts'
        plan['external_source'] = external_source
    plan['plan_id'] = _plan_id(plan)
    return plan


def _chunks(days):
    """Keep each publication under the existing 366-day verification boundary."""
    if not days:
        return
    start = previous = date.fromisoformat(days[0])
    for text in days[1:]:
        current = date.fromisoformat(text)
        expected = previous + timedelta(days=1)
        while expected.weekday() >= 5:
            expected += timedelta(days=1)
        if current != expected or (current - start).days >= 366:
            yield start.isoformat(), previous.isoformat()
            start = current
        previous = current
    yield start.isoformat(), previous.isoformat()


def _verified_feature(root, binding):
    from data.verified_inputs import memo, current
    def load():
        item = (read_materialization(root, binding['id'], research=True) if current(root)
                else read_materialization(root, binding['id']))
        if reference(item['manifest']) != binding:
            raise InputsBlocked('Feature reference differs from verified materialization')
        # Research uses observations and manifest, not the large source operand
        # copies returned for standalone inspection. Verification above is full.
        return {'manifest': item['manifest'], 'observations': item['observations']}
    with measure('feature.verify'):
        return load()  # FX research reader owns the bounded verification cache


def _check_output(item, member, plan, period):
    manifest = item['manifest']; key = manifest['input_key']
    if (manifest['definition'] != member['feature'] or key['source_snapshots'] != [member['price_snapshot']]
            or key['batch_policy'] != plan['batch_policy'] or key['knowledge_cutoff'] != plan['knowledge_cutoff']):
        raise InputsBlocked('Prepared Feature does not match frozen scientific inputs')
    if not period['start_inclusive'] <= key['period']['start_inclusive'] <= key['period']['end_inclusive'] < period['end_exclusive']:
        raise InputsBlocked('A Feature output crosses the frozen phase boundary')
    if any(row['entity_id'] != member['instrument_id'] for row in item['observations']):
        raise InputsBlocked('Feature contains another instrument')


def prepare_phase(root, plan, phase, progress=None, cancelled=None, admission=None, *, horizon=None):
    from data.verified_inputs import phase_inputs
    period = _phase(plan, phase, admission, horizon)
    with phase_inputs(root, plan, phase, period=period), measure('feature.preparation'):
        return _prepare_phase(root, plan, phase, progress, cancelled, period)


def _prepare_phase(root, plan, phase, progress, cancelled, period):
    """Prepare only this phase's selected recipe; validation requires admission."""
    if plan.get('application_class') == 'external_stored_feature_to_individual_ts':
        from research.external_features import prepare
        return prepare(root, plan, phase, period, cancelled)
    from data.verified_inputs import current, retain_price_inputs
    requested = set(_period_days(period))
    prepared = {'plan_id': plan['plan_id'], 'phase': phase, 'period': deepcopy(period), 'members': []}
    published = False
    for member in plan['members']:
        _check_cancel(cancelled)
        with retain_price_inputs(root, member['price_snapshot'], plan['batch_policy']):
            output = {'instrument_id': member['instrument_id'], 'materializations': [], 'unavailable': []}
            covered = set()
            for candidate in member['feature_materializations']:
                p = candidate['period']
                # Do not read an observation payload extending into another phase.
                if not period['start_inclusive'] <= p['start_inclusive'] <= p['end_inclusive'] < period['end_exclusive']:
                    continue
                _check_cancel(cancelled)
                item = _verified_feature(root, candidate['reference'])
                if reference(item['manifest']) != candidate['reference']:
                    raise InputsBlocked('Frozen Feature materialization reference differs')
                _check_output(item, member, plan, period)
                covered.update(row['reference_time'] for row in item['observations'])
                output['materializations'].append(candidate['reference'])
            for start, end in _chunks(sorted(requested - covered)):
                _check_cancel(cancelled)
                if progress:
                    progress({'stage': phase, 'action': 'preparing_feature', 'instrument': member['instrument_id'], 'start': start, 'end': end})
                try:
                    saved = prepare_fx_feature(root, member['feature'], price_snapshot=member['price_snapshot'],
                        batch_policy=plan['batch_policy'], knowledge_cutoff=plan['knowledge_cutoff'], start=start, end=end)
                except PublicationError as exc:
                    # Null-only warm-up/member windows remain explicit missing input,
                    # not successful publications or silently omitted Scope members.
                    if str(exc) not in ('No valid FX Feature observations; recipe remains registered only',
                                        'Output interval has no scheduled weekdays'):
                        raise
                    output['unavailable'].append({'start_inclusive': start, 'end_inclusive': end,
                        'reason': 'NO_VALID_FEATURE_OBSERVATIONS'})
                    continue
                published = True
                item = _verified_feature(root, saved['materialization'])
                if reference(item['manifest']) != saved['materialization']:
                    raise InputsBlocked('Published Feature reference differs')
                _check_output(item, member, plan, period)
                output['materializations'].append(saved['materialization'])
            output['materializations'] = sorted({r['id']: r for r in output['materializations']}.values(), key=lambda r: r['id'])
            if current(root) is not None:
                if not published:
                    _feature_lookup(root, member, output, plan, period)
                _target_prices(root, member, plan, period)
            prepared['members'].append(output)
    # A later member's lineage publication changes the catalog generation.
    # Warm Feature lookups only after all publications, retaining the ordinary
    # catalog/index witnesses and their conflicting-identity detection.
    if published and current(root) is not None:
        for member, output in zip(plan['members'], prepared['members']):
            _check_cancel(cancelled)
            with retain_price_inputs(root, member['price_snapshot'], plan['batch_policy']):
                _feature_lookup(root, member, output, plan, period)
    prepared['prepared_id'] = 'PREPARED_' + digest(prepared)
    return prepared


_DATE_FIELD = {name: re.compile(rb'"' + name.encode() + rb'":"(\d{4}-\d{2}-\d{2})"')
               for name in ('prediction_anchor', 'entry_time', 'exit_time')}


def _phase_target_rows(store, manifest, period):
    """Hash-check bytes, then reject other-phase rows before value JSON parsing."""
    rows, rejected = [], Counter()
    for member in manifest['partitions']:
        coverage = member['coverage']
        if coverage['end'] < period['start_inclusive'] or coverage['start'] >= period['end_exclusive']:
            continue
        raw = gzip.decompress(store.payload(member))
        lines = raw.splitlines()
        if len(lines) != member['row_count']:
            raise InputsBlocked('Target partition row count differs')
        for line in lines:
            dates = {}
            for field, expression in _DATE_FIELD.items():
                matches = expression.findall(line)
                if len(matches) != 1:
                    raise InputsBlocked('Target phase boundary is malformed or ambiguous')
                dates[field] = matches[0].decode('ascii')
            if not period['start_inclusive'] <= dates['prediction_anchor'] < period['end_exclusive']:
                continue
            if not all(period['start_inclusive'] <= when < period['end_exclusive'] for when in dates.values()):
                rejected['ENDPOINT_OUTSIDE_PHASE'] += 1
                continue
            value = strict_json(line)
            if canonical_bytes(value) != line:
                raise InputsBlocked('Target observation bytes are not canonical')
            validate_target_row(value)
            rows.append(value)
    if len({row['prediction_anchor'] for row in rows}) != len(rows):
        raise InputsBlocked('Duplicate Target anchor in a phase')
    return sorted(rows, key=lambda row: row['prediction_anchor']), dict(rejected)


def _load_target(root, member, plan, period, horizon):
    with measure('target.verify'):
        return _load_target_verified(root, member, plan, period, horizon)


def _target_prices(root, member, plan, period):
    """Verified phase endpoints, without retaining the full provenance tree.

    The ordinary source verifier first checks all canonical operands. Only fields
    read by construct_rows are projected, and only dates its phase-safe intervals
    can select. Each horizon still independently reconstructs every Target row.
    """
    from data.verified_inputs import verified_prices, compact_memo
    def load():
        with measure('inputs.target_endpoints'):
            counter('inputs.target_endpoints.builds')
            snapshot, prices = verified_prices(TargetStore(root), member['price_snapshot'],
                                               plan['batch_policy'], _price_snapshot)
            if len({row['reference_time'] for row in prices}) != len(prices):
                raise InputsBlocked('Duplicate canonical price dates')
            fields = ('id', 'reference_time', 'value', 'status', 'original_ingested_at')
            return {'snapshot': canonical_bytes(snapshot), 'prices': [
                {key: row[key] for key in fields if key in row}
                for row in prices
                if period['start_inclusive'] <= row['reference_time'] < period['end_exclusive']]}
    return compact_memo(root, 'target_endpoints', {
        'snapshot': member['price_snapshot'], 'batch_policy': plan['batch_policy'],
        'period': period, 'knowledge_cutoff': plan['knowledge_cutoff']}, load)


def _load_target_verified(root, member, plan, period, horizon):
    store = TargetStore(root); binding = member['targets'][str(horizon)]
    manifest = validate_target_manifest(strict_json(stable_read(store.path(
        'storage/catalog/target_store/' + binding['materialization']['id'] + '/manifest.json'))))
    if (reference(manifest) != binding['materialization'] or manifest['definition'] != binding['definition']
            or manifest['price_snapshot'] != member['price_snapshot'] or manifest['input_key']['batch_policy'] != plan['batch_policy']
            or manifest['input_key']['knowledge_cutoff'] != plan['knowledge_cutoff']):
        raise InputsBlocked('Frozen Target dependencies differ')
    store.verify_closure([manifest])
    definition = store.resolve(binding['definition'])
    from data.verified_inputs import memo
    endpoints = _target_prices(root, member, plan, period)
    snapshot, prices = strict_json(endpoints['snapshot']), endpoints['prices']
    schedule_payload = strict_json(store.payload(manifest['schedule']))
    schedule, anchors, policy = memo(root, 'target_schedule',
        {'batch': plan['batch_policy'], 'snapshot': member['price_snapshot']},
        lambda: _schedule(store, plan['batch_policy'], snapshot['body']['coverage']['start'],
                          snapshot['body']['coverage']['end'], install=False))
    if (schedule_payload != {'schedule': schedule, 'anchors': anchors}
            or digest(schedule) != manifest['input_key']['schedule_sha256']
            or digest(anchors) != manifest['input_key']['anchors_sha256']
            or reference(_definition(store, snapshot, plan['batch_policy'], horizon, policy, install=False)) != binding['definition']):
        raise InputsBlocked('Target schedule or definition differs from approved exact inputs')
    rows, exclusions = _phase_target_rows(store, manifest, period)
    from data.targets.scheduling import resolve_intervals
    intervals = resolve_intervals(schedule, anchors, definition['body']['entry'], definition['body']['horizon'], definition['body']['endpoint'])
    safe_dates = [item['prediction_anchor'] for item in intervals if all(
        period['start_inclusive'] <= item[field] < period['end_exclusive'] for field in ('prediction_anchor', 'entry_time', 'exit_time'))]
    safe = {'mode': 'market_schedule', 'mark_ids': ['DATE_' + day for day in safe_dates]}
    # Recalculate only the phase's safe labels; future/validation labels are never
    # passed to construct_rows or returned to a P1 worker.
    with measure('target.reconstruct'):
        expected = construct_rows(definition, prices, schedule, safe, plan['knowledge_cutoff']) if safe_dates else []
    if expected != rows:
        raise InputsBlocked('Phase Target rows do not reproduce their frozen endpoints and arithmetic')
    return rows, exclusions


def load_phase(root, plan, prepared, phase, horizon, admission=None):
    from data.verified_inputs import phase_inputs
    period = _phase(plan, phase, admission, horizon)
    with phase_inputs(root, plan, phase, period=period), measure('inputs.loading'):
        return _load_phase(root, plan, prepared, phase, horizon, admission)


def _feature_lookup(root, member, outputs, plan, period):
    """Exact phase/member cache; all overlap comparisons precede compaction.

    Values contain only immutable scalars and reference tuples. A caller cannot
    mutate verified evidence through the lookup or a returned aligned row.
    """
    from data.verified_inputs import compact_memo
    key = {'member': {k: member[k] for k in ('instrument_id', 'feature', 'price_snapshot', 'source_view')},
           'materializations': outputs['materializations'], 'period': period,
           'batch_policy': plan['batch_policy'], 'knowledge_cutoff': plan['knowledge_cutoff']}
    def build():
        with measure('inputs.feature_lookup'):
            counter('inputs.feature_lookup.builds')
            features = {}
            for binding in outputs['materializations']:
                item = _verified_feature(root, binding)
                if reference(item['manifest']) != binding:
                    raise InputsBlocked('Prepared Feature materialization reference differs')
                _check_output(item, member, plan, period)
                for row in item['observations']:
                    when = row['reference_time']
                    old = features.get(when)
                    if old is not None and {k: v for k, v in old.items() if k not in ('materialization_id', 'lineage', 'vintage_id')} != {
                            k: v for k, v in row.items() if k not in ('materialization_id', 'lineage', 'vintage_id')}:
                        raise InputsBlocked('Overlapping prepared Feature observations disagree')
                    if old is None:
                        features[when] = row
            return {when: (row['value'], row['status'], row['reason_code'], row['materialization_id'],
                           tuple(row['lineage'][k] for k in ('id', 'version', 'content_sha256')))
                    for when, row in features.items()}
    return compact_memo(root, 'feature_lookup', key, build)


def _load_phase(root, plan, prepared, phase, horizon, admission=None):
    """Return complete-member aligned rows for one admitted stage/horizon only."""
    period = _phase(plan, phase, admission, horizon)
    if (prepared.get('plan_id') != plan['plan_id'] or prepared.get('phase') != phase or prepared.get('period') != period
            or prepared.get('prepared_id') != 'PREPARED_' + digest({k: v for k, v in prepared.items() if k != 'prepared_id'})):
        raise InputsBlocked('Prepared outputs are not bound to the frozen plan and phase')
    if [m['instrument_id'] for m in prepared['members']] != plan['scope']['members']:
        raise InputsBlocked('Prepared outputs silently changed Scope membership')
    if plan.get('application_class') == 'external_stored_feature_to_individual_ts':
        from research.external_features import load
        return load(root, plan, prepared, phase, horizon, period)
    rows, coverage = [], []
    for member, outputs in zip(plan['members'], prepared['members']):
        features = _feature_lookup(root, member, outputs, plan, period)
        targets, exclusions = _load_target(root, member, plan, period, horizon)
        valid_count = 0
        with measure('inputs.alignment'):
            for target in targets:
                feature = features.get(target['prediction_anchor'])
                valid = feature is not None and feature[1] == 'valid' and target['status'] == 'valid'
                valid_count += int(valid)
                reasons = ([] if feature and feature[1] == 'valid' else [feature[2] if feature else 'FEATURE_NOT_AVAILABLE'])
                if target['status'] != 'valid':
                    reasons.append(target['reason_code'])
                rows.append({'date': target['prediction_anchor'], 'instrument': member['instrument_id'],
                    'feature': feature[0] if feature and feature[1] == 'valid' else None,
                    'target': target['value'] if target['status'] == 'valid' else None,
                    'target_entry': target['entry_time'], 'target_end': target['exit_time'], 'valid': valid,
                    'status': 'valid' if valid else 'unavailable', 'reason_codes': reasons,
                    'available_at': None, 'target_available_at': None, 'historical_eligibility_certified': False,
                    'lineage': {'feature_materialization': feature[3] if feature else None,
                        'feature_lineage': dict(zip(('id', 'version', 'content_sha256'), feature[4])) if feature else None,
                        'target_materialization': member['targets'][str(horizon)]['materialization'],
                        'target_row_id': target['id'], 'target_operands': target['operands'],
                        'price_snapshot': member['price_snapshot']}})
        coverage.append({'instrument_id': member['instrument_id'], 'scheduled_rows': len(targets),
            'valid_rows': valid_count, 'unavailable_rows': len(targets) - valid_count, 'exclusions': exclusions,
            'feature_unavailable_windows': deepcopy(outputs['unavailable'])})
    rows.sort(key=lambda row: (row['date'], row['instrument']))
    return {'plan_id': plan['plan_id'], 'phase': phase, 'horizon': horizon, 'mode': plan['mode'],
        'members': deepcopy(plan['scope']['members']), 'rows': rows, 'coverage': coverage,
        'lineage': {'recipe': plan['recipe'], 'scope': plan['scope']['reference'],
                    'membership_snapshot': plan['scope']['membership_snapshot'], 'prepared_id': prepared['prepared_id']},
        'availability_mode': 'retrospective_date_label', 'historical_replay_certified': False, 'live_certified': False}
