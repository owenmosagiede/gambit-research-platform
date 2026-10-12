# 16. Executable single-series transformation foundation

> Subsequent implementation: [Specification 17](17_stored_feature_trial.md) adds the approved real-source adapter, stored Feature/Signal path and optional semantic evaluation-policy reference. Statements below about synthetic-only execution describe this foundation revision.

Status: implemented for canonical synthetic input execution. Operator definitions
are version **2.0.0**; the transient series envelope is **1.0.0**. The existing
platform **0.2.0** definition and Feature/Signal identity conventions remain in use.
This specification extends 01, 03 and 12; it introduces no second observation store.

## Authority and verified coverage

The current user request authorizes the complete scoped library and its explicit
engineering policies. The historical [catalogue](../docs/transformation_library_catalogue.md)
remains unchanged source evidence. Its legacy identities, versions, file hashes
and mappings are retained in every applicable new registration.

The active library contains 98 approved registrations: 68 base registrations in
the original 15 families, 16 separately qualified price registrations, six generic
release registrations, and eight new primitives. There are 79 numerical kernels
(68 base, three additional price kernels, eight new primitives) plus one release
event-history calculation that orchestrates change and standardization kernels.
The five other release registrations share mathematics but add temporal eligibility
and anchoring. Counts of registrations, kernels and exact recipes are distinct.

The new primitives are causal lag, rolling sum, direct sample SD, and direct-input
skewness, excess kurtosis, IQR, quantile range and quantile skewness. The five legacy
distribution registrations still internally difference their input. No cross-series
interaction, target, research engine, production Feature or Signal is implemented.

## Authoritative locations and interfaces

| Concern | Location / callable |
| --- | --- |
| Approved operator definitions | `definitions/transformations/<id>/2.0.0.json` |
| Execution/history/units/missing/grid policies | `definitions/policies/POL_TRANSFORM_*/2.0.0.json` |
| Registry and bounded grid permission | `src/data/transformations/registry.py` — `Registry` |
| Numerical kernels and domain validation | `src/data/transformations/numeric.py` — `calculate`, `validate_parameters`, `required_history` |
| Uniform series validation | `src/data/transformations/contracts.py` — `normalize_input`, `normalize_result`, `normalize_series` |
| Executable schema | `specs/schemas/transformation_execution.schema.json` |
| Definition / recipe schema extensions | `specs/schemas/platform.schema.json` |
| Canonical identities | `src/data/transformations/identity.py` |
| Recipe execution | `src/data/transformations/engine.py` — `execute_recipe`, `execute_stages` |
| Shared PIT selection | `src/data/pit_selection.py` — `select_asof` |
| Generated operator documentation and coverage mapping | `docs/transformation_library.md` |

Metadata-only policy evidence uses the existing onboarding-evidence record and
content-addressed payload conventions. No calculated observations are stored there.
There is no dynamic formula evaluation, provider payload parser or legacy runtime
import in the transformation engine. Registry references resolve exact ID, version
and semantic content hashes, including approved policy evidence closure.

`alfred_pit.select_rows` delegates its existing selection behavior to the extracted
generic PIT selector; its public interface and interval semantics are unchanged.
Future adapter implementation evidence includes the extracted helper. Existing
stored implementation evidence, observations and snapshots are not rewritten.

## Canonical input and result envelopes

An input identifies an immutable SourceView, pinned source snapshots, one selected
measure/entity/dimension partition, units and explicit value semantics. It contains
reference time, historical availability, vintage identity, validity/reason and
lineage for every observation. Values use canonical finite decimal text or null;
typed parameters use canonical integer/decimal strings under platform conventions.
An input may carry revision history or a resolved state. Multiple vintages without
the revision-history capability reject. Source adapters own truthful conversion and
source-policy certification; labels such as provider name are provenance only.

Time precision is either a calendar date or a UTC microsecond timestamp. The engine
does not synthesize intraday precision from dates. Economic reference times may be
later than availability in a supplied native series, but cannot become operands
before the requested reference/evaluation cutoff. Release-event anchors additionally
require reference time at or before their own availability.

An explicit release event binds `reference_time`, `available_at` and `lineage`.
Two anchors with the same availability time reject as ambiguous in this one-series
contract. An adapter must resolve the selected release anchor without inventing one.

Intermediate and final results use the same validated envelope. Results add the
exact recipe, implementation reference, materialization ID, historical cutoffs,
actual execution timestamp, overall validity and reproducible lineage manifests.
Every row carries `evaluation_cutoff`; `available_at` equals that cutoff under
`availability_semantics: derived_at_cutoff`. This is the historical calculation's
eligibility bound, not an assertion of an actual market publication timestamp.
Actual execution time is metadata only. An output with no available source reference
has a null reference time and an invalid controlled reason.

`execute_stages` exposes the complete validated intermediate histories used in
composition. Next steps consume their canonical values, reasons, units and semantics.
A new standalone recipe cannot relabel a derived envelope as the original raw
SourceView: that root input is rejected. Reuse outside the same declared chain
requires a SourceView that explicitly binds the upstream definition. This preserves
the logical identity rather than silently dropping the preceding transformations.

## Exact recipe and historical semantics

A recipe uses the existing `predictor_recipe` inside a transient `feature_definition`.
It has one SourceView and one linear ordered chain, exact immutable operators,
exact typed parameters, selected partition, explicit history mode and approved
execution/history policies. No conversion, fill, difference or normalization is
inserted. Operators requiring native release state can only be the first step.
Semantic, parameter, capability, policy and output-unit compatibility is checked
before calculation. Interactions, multiple sources, forward references, branching
and scope-dependent calculations reject in this implementation.

In `resolved_state`, each requested cutoff independently selects the latest
available vintage for each reference time through that cutoff. The complete
declared chain runs on that state. A later revision can change a later result but
cannot change operands at an earlier cutoff. Running once on final revised history
and backdating values is never used.

In `emitted_history`, the first step is evaluated separately at each explicit event's
own availability cutoff and truncated to its reference anchor. Subsequent steps
consume the sequence of those emitted values in evaluation-cutoff order. Their
cadence is `event` and their windows count emitted observations. Economic reference
periods may repeat or move backwards during revisions; they do not reorder this
sequence. Seasonal processing after this switch rejects because event-frequency
seasonal buckets are unsupported. No undeclared temporal switch is inserted.

The six native release operators require both revision-history and release-event
capabilities and an exact event at each requested output cutoff. No matching event
returns `INAPPLICABLE`; an event whose reference anchor does not resolve returns
`MISSING_REQUIRED_OBSERVATION`. Neither carries the preceding release forward.
`release.shock_change_zscore` requires emitted history: each historical k-change is
computed from its own event's resolved state; the current change is compared with
the prior w emitted changes. It does not redifference that change sequence or revise
all prior changes using the latest state.

## Cadence, numerical and failure policies

Windows and lags count observations. Regular reference histories enforce the
declared Gregorian cadence: daily is one calendar day, weekly seven days, and
intraday requires an explicit positive integer `interval_seconds` and UTC timestamps.
Month-based cadences use strict strides of 1/3/6/12 months, preserving the day of
month or requiring both adjacent observations to be month ends. Arbitrary clipping
such as January 30 to February 28 is not silently inferred. No business calendar
or resampling is inferred. Tick, irregular and event series use their declared
observation ordering without calendar adjacency checks.

Both gap policies reject an absent regular period. `explicit_missing` means the
adapter has supplied an actual null observation for that slot, not permission for
the engine to insert or delete rows. Checks run inside each selected historical
state, so a future gap does not corrupt an earlier cutoff. Required operands must
be complete; seasonal filtering and capped streaks retain their explicit registered
exceptions. The current-inclusive or current-exclusive boundary is per operator.

Mathematical domains reject before execution: positive integer lags, appropriate
window minima, ordered fast/slow and quantile bounds, and all declared parameter
relationships. Grid permission is optional and separate. Enumerating a grid requires
an explicit policy and `max_combinations`; the weekly 156 extension is a policy
fingerprint bound to a recipe step, not a transformation or implicit candidate job.

Arithmetic uses Python binary64 floats internally; serialized results are canonical
decimal strings, not a claim of arbitrary precision. Nonfinite arithmetic never
produces a valid output. Sample SD uses n-1; direct descriptive SD may equal zero.
Dividing by zero SD/variance/MAD/range remains undefined. Log/positive-price and
denominator restrictions are explicit. Quantiles use type 7; ranks preserve half-tie
conventions; skewness and excess kurtosis retain the documented sample adjustments.

Exponential calculations use half-life alpha, first-value seeding, declared warmup
and reset on missing/invalid arithmetic. Insufficient warmup remains distinct from
source missingness and domain failure. EW z-score uses pre-current moments with a
stable centered variance recurrence, a versioned numerical improvement over
subtracting large squared means. EW volatility remains RMS change, not centered SD.
The generated catalogue gives each operator's exact initialization and boundary.

Version 2 deliberately adds stricter domains/finite checks, accepts zero descriptive
volatility and mathematically defined zero numerators with nonzero denominators,
enforces declared positive-price semantics, and exposes precise failure reasons.
These changes use new IDs/versioned registrations; no legacy version is redefined.

Malformed or incompatible inputs/recipes raise validation errors (`InputError`,
`RecipeError`, `ContractError` or `ParameterError`). Expected pointwise mathematical
failures preserve requested rows with null values and controlled reason codes.
Unexpected implementation defects raise `ExecutionFailure` or remain visible
exceptions. Status is `complete`, `partial` or `no_valid_output`; an all-null output
is never reported as successful scientific output. No failed row is replaced by zero.

## Stable identities and transient execution evidence

Operator references bind ID/version/content. Feature and future parent Signal IDs
use the existing platform 0.2 predictor-recipe digest. SourceView, selected partition,
ordered steps, operator versions, typed parameters, history/execution policies and
optional grid-policy fingerprint affect logical identity. Display labels, execution
time, paths and newly appended observations do not. Target, target horizon, expected
direction and Research Spec are relationship context, not hidden feature identity
inputs. Distinct SourceViews can produce equal numbers while retaining distinct IDs.

The existing UTC production `materialization_id` utility preserves platform 0.2 test
vectors. Date-aware in-memory calculations use a separately tagged identity profile,
`transformation_execution.1.0.0`, never a fabricated production store manifest.
Its key binds recipe, exact input evidence/semantic series digest, precision, cutoff
coverage, implementation, policies and output reference/cutoff index. Thus a full
intermediate history and a single final value at the same cutoff have different
execution IDs. Provider labels and actual execution time are excluded.

Lineage uses existing platform 0.2 `lineage_manifest` records. Final results return
the transient intermediate lineage closure; source snapshot/view, selected operand
and release-event references remain traceable. No definitions, Feature observations,
Signal registrations, materialization manifests or lineage records are published by
the executor. Existing storage templates in specification 12 remain authoritative.

## Verification and remaining production gates

The suite covers every registration with a defined independent expected result,
all 79 kernels with constant/missing/extreme/future-append cases, all 7,234 approved
base grid combinations across ten frequencies plus the weekly 156 permission,
composition, direct-versus-differenced distributions, revision leakage, release
anchors, temporal precision, partition isolation, identity vectors and schema drift.
Finite acceptance coverage does not prove every arbitrary parameter/data value.

The implementation is ready for the separate task of preparing a first production
Feature recipe after source eligibility is established. Operator certification is
complete independently of any real dataset's release/live fitness. Before running
the existing CES0500000003 data, that next task must pin an adapter mapping its
SourceView/measure/entity, units, cadence, missingness, vintage lineage and snapshot
into this envelope; verify what its archive dates establish; and approve the
decision-clock/availability rule for timestamped Feature observations. Daily API
access and archive vintages alone do not establish exact historical release times.
Release operators additionally require defensible event anchors and history.

Only then may the separate bounded task publish one auditable Feature definition,
its corresponding parent Signal ID and a Feature materialization using the existing
store contracts. Target/trial/research execution and live scheduling remain outside
that task. No provider download or real-source transformation was performed here.
