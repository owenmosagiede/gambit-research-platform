# 23 — P1/P2 Submit execution

This is the current additive implementation contract for the four-input Experiment
form, retained P1/P2 kernels, local worker and research records. It supersedes earlier
statements that Submit is inert or that P1/P2 are placeholders. It does not change
historical experiment 0.1 identities, stored observations, transformation definitions,
or the Feature/Scope separation in [21](21_reusable_features_and_scope.md).

## Installed behavior and current execution gate

The approved Research Spec is **RSPEC_FX_SCOPE_ROUTED_SUBMIT 2.0.0**, an immutable
`research_execution_profile/2.0.0` definition in
`definitions/research_specs/RSPEC_FX_SCOPE_ROUTED_SUBMIT/2.0.0.json`.
`config/research_execution.json` contains only its exact ID, version and content SHA-256.
The loader verifies canonical bytes and the reference before readiness enables Submit.
This execution-profile contract is separate from the older proposed platform 0.2
Research Spec schema; historical experiment/profile identities remain readable.

The installed policy fixes:

- Discovery through **2021-12-31**, exclusive end `2022-01-01`. No fixed start was
  supplied. `scope_structural_start_v1` freezes the selected instrument's structural
  source start, or the latest member structural start for fixed CS, in the submitted
  plan. Source coverage is not a claim of usable statistical coverage.
- **Validation period: 2022-01-01 through 2026-08-31**, exclusive end `2026-09-01`.
  Anchor and Target endpoint must both fit their phase. Long-horizon anchor coverage
  therefore ends earlier than the phase end; endpoints are never shortened or moved.
- `scheduled_weekday_hac_v2`, spacing one, and the retained **1, 7, 21, 63, 252**
  Monday–Friday horizons without holiday exclusions. Missing dates retain their
  actual weekday distance in HAC; they are never consecutive just because they are
  consecutive usable rows. No subsequent-valid-observation Targets are introduced.
- `unresolved_required_v1`: unavailable required P2 evidence is **Unresolved**;
  available evidence failing a criterion is **Failed**. Diagnostic-only statistics
  do not become required. Legacy threshold values remain unchanged.
- Retrospective date-matched FX research only. Historical timing certification and
  live readiness remain false; date labels do not imply tradable release times.
- Knowledge cutoff `2026-10-09`, **43 exact source pins** and **215 exact Target
  materialization pins** from the completed construction evidence. Registry-wide
  pins project to selected Scope members; every supplied member has all five
  horizon references. Ambiguous or incompatible references block before preparation.

The source pins resolve ten catalog display-snapshot differences and two AUDUSD
Target ambiguities. They select consistent existing artifacts; they do not replace
source records, rebind historical Features, or copy observations.

The interface may call the period **Validation period**. Backend metadata records
known legacy use of this interval and that prior use for the selected relationship
is not established. It makes neither an untouched-holdout claim nor an assumption
that every new recipe has already been evaluated.

Installation, imports, library browsing and changing Feature or Scope do not launch
materialization or research. Starting the server starts a local worker that can
recover previously submitted active requests; it does not create an experiment.
Verification uses synthetic stores; no production experiment is executed during
policy installation. An invalid, missing or unresolved profile keeps Submit blocked.

## Submission and Scope routing

`POST /api/experiments` accepts exactly `request_id`, `feature`, `target_family`,
`scope`, and `expected_direction`. Feature and Scope selections carry exact `id`
and `version`; request ID is a canonical UUID. The implemented family is
`price_return`; direction is `POSITIVE` or `NEGATIVE`. Research Spec is frozen in
the backend, not selected in another UI dropdown.

| Scope | Preparation | Research expansion |
| --- | --- | --- |
| Individual instrument | Selected recipe for that instrument | Five P1 TS evaluations |
| Universe | Selected recipe separately for every frozen member | Five P1 CS evaluations |

The horizons are always 1, 7, 21, 63 and 252 scheduled weekdays. Member preparation
does not create TS trials inside a universe experiment. CS computes one rank IC
per usable date across all required members, then evaluates the series across
dates. It never treats all member/date rows as independent time observations.

The worker resolves the reusable recipe against exact historical Feature bindings,
source snapshots, policies, Scope membership and each member/horizon Target. It
freezes an immutable plan before preparing outputs. A missing member, missing
horizon or ambiguous Target materialization is reported; no member or horizon is
silently removed. The current production input adapter supports reusable FX
recipes only. CES and other non-FX entries stay selectable/visible but their
unsupported research binding produces an explicit blocker.

## Preparation and phase boundaries

`research.inputs` exposes `resolve_plan`, `prepare_phase` and `load_phase`.
Preparation reuses only exact compatible Feature outputs wholly contained in the
requested phase. Missing weekday coverage is prepared for the selected recipe and
Scope in bounded chunks under the existing 366-calendar-day limit. Warm-up and
operator causality remain governed by the existing Feature preparation pathway;
this is not an exhaustive recipe or parameter search.

The fixed CS common start comes from member source structure. Recipe warm-up uses
the existing preparation path. Complete membership is required at each retained date; incomplete
dates are excluded with member coverage preserved. Observations remain date
precision, and historical availability remains null/uncertified. No midnight
availability or executable-close timing is invented.

Verified warm-up interpretation: the legacy registry calls its rule
`applied_after_structural_common_start`, but executable fixed-FX research passes
each member's full history into Feature calculation, then filters sample anchors
at the common start. The imported path retains that executable behavior; it does
not reset rolling calculations or change existing recipes at the common start.
Evidence in legacy `Data/src/`: `research_orchestrator/execution.py` lines 534–601,
`point_in_time_data/derived_feature_store.py` lines 873–889 and 1006–1024, and
`empirical_signal_research/engine.py` lines 487–551. The registry phrase alone must
not be interpreted as an approved alternative calculation reset.

Both the observation date and actual Target endpoint must lie in the permitted
phase. Target partitions are checksum-verified; rows outside the phase are excluded
before their value JSON is decoded. Only phase-safe labels are independently
recalculated against the pinned source and exact scheduled endpoints. A P1 caller
is never handed validation labels. Artifact hashing may inspect immutable bytes;
it does not constitute evaluation of their values.

P2 preparation and loading require the frozen plan, expected direction and admitted
horizons. Discovery effects conflicting with expected direction fail precheck
before validation preparation or reads. An admitted result lacking its discovery
effect produces an authoritative unresolved precheck. User direction is never
inferred from observations or reversed to obtain a pass.

## Versioned numerical implementation

`src/research/legacy/` contains only locally copied pure numerical/admission helpers.
`provenance.json` records complete source and function SHA-256 fingerprints and
policy/gate source fingerprints. No runtime path points back to legacy code and no
legacy runner, writer or scientific dataset is imported.

P1 TS retains intercept OLS, signed beta, Spearman IC and uncorrected
Newey–West/Bartlett covariance. P1 CS retains date-level Spearman IC and HAC
inference on mean IC. Spacing is explicitly one under the retained kernel policy,
so maxlags is horizon minus one. The new version uses actual scheduled weekday
positions for lag products, with usable observations as the sample denominator.
Missing observations contribute no score cross-products, never imputed zero values. Minimum usable samples are `max(3, maxlags+3)` for
TS and `max(3, maxlags+2)` IC dates for CS. Three chronological equal-count blocks
allocate remainders to earlier blocks.

P1 admission retains absolute HAC t >= 2; CS additionally requires absolute mean
IC >= 0.03. At least two of three computable blocks must agree with the full-sample
observed sign. Exact retained gate helpers preserve missing/zero-sign evidence
handling. Admission is distinct from the user's expected-direction P2 precheck.

P2 standard horizons retain correct direction, at least 25% discovery-effect
retention, directional HAC t >= 1.645, at least 15 effective observations, prescribed
block/leave-out stability and no significant opposing block. The 252 policy retains
its separate stability rules, at least four effective observations, diagnostic
inference and the low-sample-confidence flag. Effective N is the maximum set of
non-overlapping actual Target intervals; shared boundary prices are allowed. CS
blocks are date-atomic and do not split a date across blocks. Under v2, CS effective
N uses only dates with computable rank IC; constant cross sections cannot inflate
the minimum independent-observation count. Historical v1 counting remains intact.

P1 performs no multiple-testing correction. P2 Benjamini–Hochberg remains a
singleton diagnostic per relationship/horizon, not a batch-wide admission control.
Under v2, each required criterion explicitly distinguishes available pass/fail from
unavailable evidence. Missing required evidence takes precedence over other observed
failures, except the discovery-direction precheck still fails before validation access.
A measured effective N below its threshold is a failed criterion. Standard stability
requires all three block effects and directional t statistics, and all leave-out effects.
The 252 policy instead requires block, leave-out and chronological-half effects; its
t/p statistics remain diagnostic. A zero effect is available, not missing.

Historical profiles dispatch to the frozen estimators and `legacy_failed_v1` handling.
No previously stored result is recomputed or relabeled by installing v2.

Stored canonical decimal strings convert to finite binary64 values only at the
numerical boundary. Malformed/nonfinite inputs remain exclusions; operand lineage
and source values are preserved. Preparation does not count as scientific testing.

## Durable execution, identity and recovery

The local server hosts one background execution service with OS file locks for
writer serialization and exclusive worker claims. A request is recorded before
work begins. The request UUID, immutable scientific trial identity and attempt UUID
have different purposes; retries never turn into new scientific observations.

Reposting the same request ID and identical choices returns the existing job;
different choices under that ID conflict. Scientific reuse also works across
different request IDs when exact recipe/Scope/Target/profile/period/prepared-input,
implementation and data identities match. P2 trial identity includes its exact
discovery trial and discovery effect. Matching stored artifacts are verified before
a calculation is reused.

Each submission freezes the full profile and implementation fingerprint. Resume
retains those inputs and the frozen plan. A changed installed implementation blocks
an old request rather than silently replaying it with new code. A changed config
does not rewrite a prior request's frozen profile.

Payloads are published before manifests, and artifacts before trial ledger records.
Immutable publication rejects conflicting bytes. An append-only, checksummed event
chain is operational authority; the mutable job JSON is a projection. A worker can
reconcile interrupted active requests, reuse already committed trials, and rebuild
progress from events even when a job projection is absent. Cancellation takes effect
at checkpoints and retains committed evidence. It is not a rollback of valid data.

Operational states distinguish queued/resolving/preparing/P1/P2 work from blocked,
failed, cancelled and succeeded requests. A succeeded job can contain rejected,
failed or unresolved scientific outcomes. Every horizon retains its own outcome.

## Actual storage locations

Paths are relative to `research_platform/`. The implemented record envelope is
additive schema **0.8.0**, record version **1.0.0**; old schemas and IDs are unchanged.
Scientific IDs contain a full SHA-256 of their scientific key. Records also carry
a checksum, and references bind exact ID, version and content hash.

| Record | Implemented location |
| --- | --- |
| Active exact policy reference | `config/research_execution.json` |
| Immutable approved execution profile | `definitions/research_specs/RSPEC_FX_SCOPE_ROUTED_SUBMIT/2.0.0.json` |
| Submission and frozen profile/implementation | `storage/catalog/submissions/<request_uuid>.json` |
| Frozen plans | `storage/catalog/research_plans/RESEARCHPLAN_<hash>.json` |
| Implementation evidence | `storage/catalog/research_implementations/RESEARCHIMPLEMENTATION_<hash>.json` |
| Attempt events | `storage/catalog/attempts/<attempt_uuid>/events/RESEVENT_<hash>.json` |
| Rebuildable job state and OS locks | `storage/catalog/operations/jobs/<request_uuid>.json` and `storage/catalog/operations/*.lock` |
| P1 and evaluated P2 trial ledgers | `storage/catalog/trial_ledger/records/TRIAL_<hash>.json` |
| P1 admission decisions | `storage/catalog/admission_ledger/records/ADMISSION_<hash>.json` |
| P2 decisions, including prechecks | `storage/catalog/validation_ledger/records/VALIDATION_<hash>.json` |
| Artifact manifests | `storage/catalog/trial_artifacts/ARTIFACT_<hash>/manifest.json` |
| Shared evidence bytes | `storage/payloads/sha256/<first_two>/<hash>.json` |
| Exposure records | `storage/catalog/research_exposure/records/EXPOSURE_<hash>.json` |
| Tested relationships | `storage/catalog/signal_library/relationships/RELATIONSHIP_<hash>.json` |
| Immutable research links | `storage/catalog/signal_library/research_links/RESEARCHLINK_<hash>.json` |

The earlier proposed operations SQLite index is not the current job-state authority.
The registered v2 backend profile is embedded in submissions with its exact
reference; editing the active config cannot rewrite a previously frozen request.

Compact trial records own metrics, sample summaries, evidence and artifact refs.
Detailed aligned rows, exclusions, IC histories, blocks, coverage and lineage live
in shared payloads referenced by artifact manifests. Signal Library reads those
authorities through exact links; metrics are not editable library copies. Earlier
partial links remain immutable while the reader shows maximal completed evidence
branches. Independent Research Spec/period branches remain separately inspectable.
The reader verifies relationship, discovery, evaluation and decision bindings.
There is no parent-recipe-wide validated flag.

## API and UI handoff

The read routes `GET /api/research-readiness`, `GET /api/experiments/<request_uuid>`
and `GET /api/research-results/<recipe_id>` expose readiness, progress and scoped
authority records. Explicit same-origin JSON POST routes create submissions and
request cancellation/resume. See [API instructions](../src/api/README.md).

The four existing inputs remain Feature, Target, Scope and Expected Direction.
Submit follows Expected Direction. The UI freezes their displayed choices with
the request, shows all five horizons, preserves a request ID after uncertain
responses, and provides bounded polling/retry, cancellation and resume controls.
Changing selectors only resolves stored coverage. Completed result notifications
refresh the read-only Signal Library without changing library inclusion policy.

## Verification scope and limits

Synthetic tests check independent dense-calendar score-matrix HAC oracles for TS/CS
at all five horizons, consecutive-date legacy parity, gaps and constant IC dates,
required/diagnostic evidence, effective N, and historical kernel fingerprints. Input
and full-pipeline fixtures check immutable profile references, exact source/Target
pins, discovery-start freezing, five separate horizon results, phase-safe labels,
scoped lineage and duplicate prevention. HTTP/UI tests check enabled and blocked
Submit behavior, no automatic execution, recovery and result reads.

Historical FX availability and live certification remain unresolved. The existing
non-FX research adapter limitation remains explicit. No new threshold, bulk
migration, parameter search, P3/P4/P5, broker connection or order execution is included.
A future submitted experiment must still satisfy per-member coverage and statistical
criteria; enabling the approved process is not a successful research outcome.
