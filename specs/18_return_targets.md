# 18 — Executable return Targets

Status: executable Target contract **0.4.0**, calculation/identity/scheduling interpretation
**1.0.0**. This specification governs continuous forward investment-return Targets.
It supersedes only the draft Target construction, observation, materialization and
retrieval clauses of specifications 01, 03 and 12. Their 0.2 schema examples and
historical evidence remain unchanged; existing Feature/Signal identity and stored
artifacts remain unchanged. Other research and downstream contracts retain their
existing authority. [Library explanations](../docs/target_library.md) supply formulas,
domains, examples and source requirements; [implementation evidence](../docs/target_implementation_report.md)
records actual tests and proof artifacts.

## Canonical contract and preflight

`src/data/targets/contracts.py` owns exact closed semantic validation and uses the
existing canonical reference, selection, decimal and time validators. `target_store.schema.json`
and `target_materialization.schema.json` in `specs/schemas/` document the new record family. `TargetStore` dispatches by
`schema_version` and `record_type`; it does not reinterpret old 0.2 Target documents
as executable 0.4 definitions.

A concrete Target definition stores:

- `sources`: one `instrument` and, for excess, one `benchmark`, each with exact
  SourceView reference, selected measure/entity/dimensions and economic policy reference.
- `construction`: `basis` (`price`, `total_return`, `benchmark_excess`), `representation`
  (`simple`, `log`), `comparison` (`none`, `arithmetic_difference`, `log_difference`),
  `instrument_basis` and nullable `benchmark_basis`. Initial excess requires matching
  price/total-return bases, currency, coverage, observation convention and actual interval.
- `unit`: `dimensionless_fraction` or `natural_log_return`; exact currency and economic coverage.
- Exact `schedule_policy`, `outcome_policy`, `validity_policy`, `calculation` and other
  `dependencies` references; explicit anchor mode/set identity; entry, horizon and endpoint.

An economic source policy binds instrument/investment-series identity, selected measure,
source input kind (`price`, `wealth_index`, `period_returns`), units, currency, base/quote
currencies and quotation direction, calendar ID/version, IANA timezone, observation convention,
income/corporate-action treatment,
adjustment convention, period-return representation, zero-terminal permission, availability
basis, vintage capability and documentary evidence. Provider is retained in provenance.
It cannot authorize unsupported economics merely by labeling an arbitrary numeric series
as a price. The adapter verifies Dataset/SourceView/selection/unit/dependency closure.

Five versioned policy kinds are executable: `economic_source`, `target_schedule`,
`outcome_selection`, `mathematical_validity`, and `return_calculation`. Their canonical
IDs bind their contents; unresolved policy names, vague horizons or unregistered formulas
cannot pass preflight. The reusable calculation policy pins `decimal_50_then_binary64_guard`; concrete source,
horizon and timing bindings remain in each Target definition.
The current validity policy retains null rows for expected failures, rejects nonfinite
sources, forbids stale substitution, and requires exact complete period-return coverage.

## Schedule evidence and interpretation

Logical policy and finite execution coverage are separate. `target_schedule` defines
calendar ID/version, IANA timezone, observation convention, temporal precision and the
`declared_marks` anchor convention. The submitted finite canonical schedule supplies:

```text
policy_id, version, temporal_precision, calendar_id, calendar_version, timezone,
observation_convention, coverage_start, coverage_end, marks, evidence
```

Each expected mark has a stable `mark_id`, `time` and `session_id`; timestamp marks also
have `local_time` with explicit offset evidence, checked against the IANA timezone.
Coverage bounds are inclusive and must cover every requested interval. This is a
certified expected calendar, never a calendar inferred from surviving price rows.
Its exact `evidence` reference resolves an existing `onboarding_evidence` record with
kind `canonical_market_schedule`; the checksum-verified JSON payload must equal
`{kind: canonical_market_schedule, schedule: <submitted schedule without evidence>}`.
A generic evidence label without those exact marks and semantics cannot pass preflight.
Holidays and shortened sessions appear in that exact evidence. The subsystem consumes
and validates canonical calendars; it does not invent exchange holiday schedules.

Anchor requests are either `{mode: market_schedule, mark_ids: [...]}` or
`{mode: explicit, anchor_set_id: <registered token>, times: [...]}`. Explicit mode has a reusable `anchor_set_id` in the
Target definition. Actual anchor values belong to materialization evidence. Ordered
anchors have stable `ANCHOR_` identities over the schedule semantics, anchor mode/set identity and canonical time.

Entry is `{rule, delay: {amount, unit}}`:

| Entry rule | Exact meaning |
| --- | --- |
| `anchor_mark` | Select the expected mark exactly at anchor plus declared delay; descriptive research convention, no simultaneous observe-and-trade claim |
| `next_scheduled` | Select the first expected mark strictly after anchor plus declared delay |

Delay is a nonnegative integer in `calendar_days` or `elapsed_seconds`. A date schedule
requires calendar-day precision even for zero delay. Horizon amount is a positive integer;
`counting` is always `exclusive_entry`: count from the resolved entry, excluding entry.

| Horizon unit | Exact interval and requirements | Example |
| --- | --- | --- |
| `trading_sessions` | Advance that many expected sessions; exactly one declared observation mark per session | Friday close plus one session is Monday close if Monday is an expected session; a holiday moves it to the next declared session |
| `scheduled_bars` | Advance that many expected marks; multiple marks per session permitted | A 10:00 entry plus two scheduled half-hour bars ends at 11:00 even if the 10:30 price is missing |
| `calendar_days` | Add local calendar days, retaining local wall clock for timestamps | Friday plus one day intends Saturday; an exact Saturday endpoint must be present or preflight rejects |
| `elapsed_seconds` | Add a fixed UTC duration; timestamp precision required | 86,400 seconds is exactly 24 hours, even across a daylight-saving transition |

Endpoint is `{rule, tolerance: {amount, unit}}`. `exact` requires zero tolerance and
an expected mark exactly at the intended endpoint. `next_scheduled` requires positive
bounded tolerance and selects the first expected mark at or after that intended end.
This rule matches calendar marks only: a missing price at the chosen endpoint remains
missing and never advances the endpoint. Session/bar horizons never count surviving rows.

A local calendar interval reaching an ambiguous or nonexistent daylight-saving clock
rejects preflight. Missing timezone/offset evidence and elapsed rules on date precision
also reject; no approximation to UTC midnight, 24 hours or a different local date occurs.
Preflight resolves every anchor/entry/intended-end/exit before reading returns. Insufficient
schedule coverage is definition/request incompatibility, distinct from a resolved future
endpoint whose outcome is not yet mature.

## Outcome selection and availability

`outcome_selection.selection` is `first_defensible` or `pinned_later`. Both operate on
canonical revisions under the explicit request knowledge cutoff. First-defensible
selection requires complete historical observation evidence; source `availability_basis`
is separately `first_published`, `first_archived`, `first_ingested` or `unknown`.
Those words are never interchangeable. Pinned-later selects the version available under
its pinned later cutoff; no moving “final vintage” interpretation exists.

The policy declares finalization wait, label precision (`conservative_date_boundary` or
`exact_timestamp`) and whether unknown availability is rejected or allowed uncertified.
Label availability is the maximum required economic endpoint, all selected instrument
and benchmark evidence availability, and the declared waiting/finalization condition.
Execution time is operational evidence, not historical availability.

Canonical rows retain Target/instrument/investment-series IDs, anchor identity and
precision, entry/intended-end/exit, horizon, source selection and exact lineage,
outcome-selection cutoff, source and label availability, economic coverage, value/unit,
validity/reason and historical certification. Valid values are finite canonical decimals;
unsuccessful scheduled rows remain null. `valid`, `invalid`, `missing` and `pending` are
separate states. A future endpoint is pending; a past absent endpoint is missing.

Historical retrieval requires a pinned materialization. An optional training cutoff and
its precision filter eligibility using that stored label version. Date precision requires
availability on an earlier date; equal dates cannot establish within-day ordering.
Timestamp evidence permits exact `<=` comparisons. Earlier materializations survive
newly matured or corrected labels; one update never overwrites a pinned earlier result.

## Identity, storage and publication

`create_definition` returns `TARGET_<full sha256>` over the `target_return.1.0.0`
identity profile and normalized semantic body. Source references/selection, economics,
return basis/representation/comparison, horizon and semantic timing policies all bind
identity. Descriptive names, execution timestamps, local paths, actual finite anchors,
appended values, Feature/Signal, direction and Research Spec do not.

This content-addressed profile fixes definition/policy registry versions at `1.0.0`.
A changed scientific meaning creates a distinct content ID; it does not rewrite an
existing version or add redundant aliases. Exact upstream definition versions remain
identity-bearing dependencies.

Definitions are immutable versioned records at
`definitions/targets/<TARGET_ID>/1.0.0.json`; policies remain in the existing policy
registry. Target manifests are at
`storage/catalog/target_store/<MATERIALIZATION_ID>/manifest.json`. The materialization
input key binds exact definition, source evidence, resolved schedule/anchor hashes,
knowledge cutoff/precision, implementation dependencies and output integrity digest.
The implementation manifest also pins the selected IANA timezone’s actual TZif database
bytes, code/schema bytes and runtime evidence. A host unable to pin its timezone bytes
rejects publication rather than supplying an untracked calendar dependency.
The output digest in the new Target identity profile is explicit, unlike the older
0.2 draft request-only materialization proposal; it does not change old identities.

Observations, exact interval/schedule evidence and contributing-record lineage live
in the existing `storage/payloads/sha256/<prefix>/<hash>.<format>` namespace. A Target
Store extends the existing FeatureStore immutable installer/reference resolver rather
than creating a second payload store. Source snapshots/records remain upstream; exact
payload-row coordinates and row hashes bind operand lineage. Canonical source metadata
and documentary policies remain resolvable by immutable reference.

Publication writes and verifies complete payloads and dependencies before installing
the immutable ready manifest. An interrupted write can leave unpublished reusable blobs
but no apparently ready missing-payload Target. Repeated identical input reuses logical
and materialization identity. Refresh is per Target/request; new source corrections or
maturity change bound evidence/materialization while preserving prior artifacts.

## Service, API and alignment

`data.targets.service` exposes creation/preflight/materialization, listing, exact
definition/materialization lookup and retrieval. `retrieve_target(root, target_id,
materialization_id, training_cutoff=None, cutoff_precision=None)` never chooses a default
materialization. The command interface and executed examples are recorded in the report.

The read-only API serves `GET /api/target-library` and
`GET /api/target-library/<TARGET_ID>?materialization_id=<MATERIALIZATION_ID>` with optional
paired `training_cutoff`/`cutoff_precision`. Unknown IDs return 404, malformed/missing
selection or cutoff queries 400, and integrity failures generic 503. API reads verify
persisted records; there is no persistent response cache or write route. Existing
loopback/Host/Origin/static-asset protections remain in force.

The Target selector replaces mock options using this list. One Target option displays
investment series, return basis, representation, horizon and readiness. Unmaterialized,
unverified or historically uncertified definitions are disabled. The display chooses
the lexicographically greatest certified materialization ID where needed and visibly
pins that exact ID; this is a presentation preference, not implicit historical retrieval
or a latest-vintage promise. Label eligibility remains cutoff-specific. Empty production
storage is empty; isolated proof fixtures do not become selectable production Targets.

`align_feature` and `select_feature_at_anchor` implement the minimal alignment boundary.
Feature availability, evaluation time and reference time must pass prediction-cutoff
ordering; a future source version cannot alter an earlier chosen Feature. Target label
availability is independently checked at training time. Strict matching requires equal
precision, using earlier date or exact timestamp ordering. The explicitly declared
`conservative_next_day` policy permits mixed precision only with IANA timezone evidence
and conservative whole local date ordering. These functions do not perform empirical
research, cross validation, portfolio construction or live execution.

## Acceptance evidence and source readiness

The implementation report contains the executed coverage matrix linking construction,
scheduling, eligibility, revisions/leakage, identity, publication, retrieval and API/selector
cases to tests. Synthetic proof data uses the production canonical adapter/store/service,
not a separate fixture-only calculation. Historical reports and their old test counts are
preserved and are not reused as Target certification evidence.

Current production dataset CES0500000003 is an ineligible earnings series. Legacy FX
archives are read-only source candidates; they need verified canonical economic,
availability and calendar evidence before admission. No production Target is fabricated
and no new provider is downloaded to disguise this data prerequisite. Supported return
and timing behavior is executable; universal instrument/provider support is not claimed.
