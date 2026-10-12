# Research platform

This is the private **Gambit source repository**. Develop here; the original
Desktop workspace is a historical reference. Production data and research
execution remain on DigitalOcean and are not included in Git.

See [development and controlled releases](deploy/RELEASE_WORKFLOW.md) for branches,
automated checks, release preparation, deployment, and rollback. A Git push never
changes production. The existing foundation documentation follows below.

This platform turns registered source data into reproducible predictors and, through later
research stages, tested relationships, forecasts and portfolio decisions. Registered raw/PIT
history, the complete scoped transformation library, the first stored Feature and parent
Signal, reusable FX recipes and the return Target subsystem are implemented. The retained
P1/P2 kernels and durable Submit pathway use the approved, versioned FX Research Spec
`RSPEC_FX_SCOPE_ROUTED_SUBMIT` **2.0.0**. Installation does not run production research.
Downstream execution and live-use certification remain separate work.

## Current state

The [research UI](ui/README.md) has four required inputs: Feature, Target, Scope and
Expected Direction, followed by Submit. Feature selects a reusable recipe; Scope supplies
the instruments. The PIT Data Library is on the Experiment page; Signal Library groups
represented reusable FX recipes and preserves expanded historical outputs. Catalog and
selection APIs stay read-only; the [local API](src/api/README.md) adds explicit durable
Submit, cancellation, resume, progress and authoritative scoped-result routes.

[Specification 23](specs/23_p1_p2_submit_execution.md) owns the installed P1/P2 execution
contract and actual research storage paths. Individual instrument means TS; universe means
CS only, with five horizon-specific evaluations. `config/research_execution.json` binds the
exact ID, version and content hash of
`definitions/research_specs/RSPEC_FX_SCOPE_ROUTED_SUBMIT/2.0.0.json`.
The UI enables Submit when this registered profile verifies and readiness is satisfied;
only an explicit submission starts preparation and research. Installation and changing
selections do not prepare observations or run research. Software verification uses isolated
synthetic fixtures; historical foundation/specification reports remain unchanged.

The approved discovery period uses all eligible source history, with its start frozen to
the latest structural start among selected Scope members, through 31 December 2021.
The **Validation period** is 1 January 2022 through 31 August 2026. Research remains
retrospective date-label analysis: prior legacy use of this period is disclosed, exposure
for the specific recipe is unknown, and neither untouched holdout status nor historical
availability or live readiness is certified.

The [first stored Feature/Signal path](specs/17_stored_feature_trial.md) now connects verified
PIT data through an exact recipe to immutable Feature observations and independent Signal
retrieval. The [completion report](docs/first_signal_trial_report.md) records its actual output
and validation. The [return Target subsystem](specs/18_return_targets.md) implements certified
price, total and benchmark excess returns, exact scheduling, historical availability,
immutable persistence and explicit retrieval. The FX family now has approved provisional
retrospective policies for the requested 43 instruments and five scheduled-weekday horizons;
actual catalog contents and coverage are reported through the stored registry and execution
report. CES0500000003 remains economically ineligible as an investment return source.
Non-FX research binding is explicitly blocked by the current FX input adapter; existing
non-FX entries remain available. P3/P4/P5 engines and order execution remain unimplemented.
The [full-history store](docs/alfred_full_history_report.md) contains real raw data, provenance
and date-level PIT history for all 247 available reference months and 1,587 archived events.
The redundant 2018 raw/PIT sample and its separate database were [physically removed](docs/alfred_sample_removal.md)
at the user’s request; all 77 sample values remain in the full history. Its scientific
snapshot, values and lineage are unchanged. Exact intraday availability and trading readiness
remain uncertified.

Read the [specification index](specs/README.md), [decisions and open gates](docs/specification_decisions.md),
[legacy capability map](docs/legacy_capability_map.md) and [exact storage/pipeline specification](specs/12_data_pipeline_and_storage.md).
The original [foundation verification](docs/foundation_verification.md) is a historical report;
[specification verification](docs/specification_verification.md) records this revision.

## User-confirmed architecture

```text
raw → PIT → optional interactions → transformations → Feature/Target stores
                                                          ↓
                   Feature + Target + Scope + Expected Direction
                         + frozen backend Research Spec
                                                          ↓
                       P1 discovery/admission → P2 validation
                                                          ↓
                  compact Trial/Validation ledgers + detailed Artifact Store
                                                          ↓
                  Signal library: parent recipe → every tested relationship
                                                          ↓
            P3 individually validated relationships → instrument/horizon forecasts
                                                          ↓
                      P4 trading sleeves → P5 shared-capital allocation
                                                          ↓
                         separately authorized execution and reconciliation
```

The Target branch constructs ex-post outcomes under exact registered definitions and remains
separate from causal Feature observations. P1/P2 retain verified legacy methodology under
explicit policies after compatibility checks. P3 preserves the supplied design: individual
calibration, decay, error-dependence-aware combination, uncertainty and attribution. P4 uses
market risk, forecast uncertainty, costs, mandate and venue context to construct sleeves.
P5 owns shared-capital allocation; the precise feedback/aggregate-feasibility protocol remains
open. RequiredTrade never itself authorizes order submission.

## Transformation library inventory

The [explanatory transformation catalogue](docs/transformation_library_catalogue.md) covers
90 legacy transformation registrations, one interaction and one parameter-grid extension.
The [active library](docs/transformation_library.md) implements 98 approved version 2
registrations with exact parameter, unit, temporal and failure contracts. The historical
catalogue remains source evidence; numerical acceptance and compatibility changes are
recorded separately.

## One Signal across many tests

Reusable FX recipe identity binds the input contract, ordered transformations, exact
parameters and semantic policy versions; it excludes instrument, universe and materialization
period. Historical bound Feature/Signal IDs and non-FX definitions remain intact. Target
assets/horizons, evaluated Scope, direction, Research Spec, periods and IC
belong to relationship/trial/result records beneath it. A new lookback changes the recipe;
a new target, a folder move or an execution retry does not.

Scope-dependent computation still binds Scope and membership before calculating values.
Those bindings participate in materialization and trial identity. No parent-wide validated flag
is permitted: only specific validated relationships become eligible for P3. Rejections, failures
and unresolved results stay visible; metrics are read through exact authoritative result links.

## Locations

Application root: `Multi-Asset Model/research_platform/`. Parent `Data/` and `FX/` remain legacy
stores. This task reads them without rewriting or moving them. Ignored local config references
observed raw/PIT locations; a configuration path is not a scientific identity or certificate.

- `definitions/`: authoritative versioned Dataset/View/operator/Feature/Target/Scope/Research
  Spec/policy locations, including the approved FX Submit Research Spec 2.0.0.
  Mandates and venues are separate downstream contexts.
- `src/`: reusable computation, data, runtime, API and execution code. Implemented paths cover
  experiment contracts, bounded ALFRED raw/PIT ingestion, transformations, canonical PIT
  adaptation, Feature/Target persistence and preparation, retained P1/P2 kernels,
  research authority and the durable local Submit worker. P3/P4/P5 remain placeholders.
- `ui/`: four API-backed inputs, Submit/readiness/progress, the Experiment PIT sidebar,
  and reusable Signal summaries with exact output and scoped research details.
- `storage/catalog/`: raw/PIT and Feature manifests, exact source-operand/lineage records,
  Target manifests, implementation evidence, Signal Library links, operational execution audits, and the
  rebuildable `pit_store/full_history/index.sqlite`. New research records include
  submissions, plans, append-only attempt events, trial/admission/validation ledgers,
  artifact manifests, exposure records and immutable research links. Current job
  projections use `operations/jobs/*.json`; they are not a new SQLite authority.
- `storage/payloads/`: immutable raw evidence, PIT/Feature/Target JSONL and execution evidence stored by
  checksum and referenced from manifests. Research evidence uses shared hash-addressed
  JSON payloads. Parquet representations remain future work.
- `storage/cache/`, `temporary/`, `logs/`: separate operational data under explicit retention rules.
- `specs/`: reviewable contracts and schemas; `docs/`: decisions, inventory, mapping and verification.
- `tests/fixtures/`: marked synthetic examples. `tests/` verifies software/specification contracts;
  P1/P2 scientific testing code belongs in reusable research modules, not here.
- `archive/legacy/`: reserved only; legacy files have not been moved or archived. Bounded imports preserve their original artifacts.

[Specification 12](specs/12_data_pipeline_and_storage.md) and its portable config give exact
path templates, record ownership, catalog-index behavior and payload reuse rules. There is no
second independently editable Signal definition or library copy of trial metrics.

## Verification

Run the existing dependency-free experiment checks from the platform root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_contracts.py' -v
```

New specification schemas/examples have a separate conformance check documented in
[the schema notes](specs/schemas/README.md) and the specification verification report. No
scientific research is executed by these checks. Successful shape validation is not data
readiness, methodological approval, compatibility, live certification or persistence.

## Completed FX Target build

The approved family is populated: 25 reusable cross histories and **215 logical Targets**
across all 43 instruments at 1/7/21/63/252 scheduled weekdays. The Target Store contains
**1,928,440 scheduled rows**, including **1,562,485 valid simple returns**; missing and pending
rows remain explicit. The original 18 source snapshots and direct/inverse price histories
were preserved. Every combination has numerical outcomes under the approved provisional
retrospective policy. Historical PIT and live readiness remain uncertified.

The calendar is Monday–Friday with no holiday exclusions and exact endpoints; zero delay
means return anchoring only. [Specification 19](specs/19_fx_sources_and_return_targets.md)
records the approval. The [execution report](docs/fx_execution_report.md) contains actual
counts, direct/inverse/cross retrieval examples, test evidence and a repeat with no immutable
file changes. The [complete coverage matrix](docs/fx_target_coverage.csv) lists all 215 combinations.

The Submit pathway pins 43 exact source snapshots and all 215 completed Target
materializations. These research bindings resolve ten catalog display-snapshot mismatches
and two AUDUSD Target selection ambiguities without migrating or replacing stored data.
Research Spec 2.0.0 selects `scheduled_weekday_hac_v2`: HAC uses actual Monday–Friday
distance, preserving missing-date gaps. Required unavailable P2 evidence is `UNRESOLVED`;
available evidence that fails a required criterion is `FAILED`, while the retained
252-day inference diagnostic exception remains. Earlier policies and results are unchanged.
Installed P1/P2 code and stored observations do not constitute a production research run
or live certification. See [specification 23](specs/23_p1_p2_submit_execution.md).

## Implemented transformation foundation

The [active library](docs/transformation_library.md) documents all 98 approved version 2
registrations and their exact legacy mappings, formulas, domains, examples and tests.
[Specification16](specs/16_transformation_execution.md) defines canonical envelopes,
Feature/Signal identities, transient materialization evidence, exact recipe composition,
and historical cutoff versus emitted-history semantics. The implementation is in
`src/data/transformations/`; its numerical acceptance uses synthetic inputs.
[Specification 17](specs/17_stored_feature_trial.md) adds the separately approved stored
Feature/Signal path. Its archive-date results are materialized and scientifically untested;
no empirical relationship metrics have been created. The
[historical catalogue](docs/transformation_library_catalogue.md) remains unchanged source evidence.

Run the complete current suite from the platform root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests/specifications -v
```

## Full-history ALFRED implementation

The [full-history completion report](docs/alfred_full_history_report.md) records all 247
reference months from March 2006 through September 2026, with 1,587 PIT events across 187
available archive vintages. Its separate database is `storage/catalog/pit_store/full_history/index.sqlite`.
The redundant separate 2018 pilot has been removed. [Specification 15](specs/15_alfred_full_history.md)
describes the initial archive-state source, revision preservation and date-level limitations.

## Open the local application

Run `.venv/bin/python tools/run_research_worker.py` and, in a separate terminal,
`.venv/bin/python tools/serve_research_platform.py` from this root, then open
`http://127.0.0.1:8765`. The sidebar reads verified stored PIT metadata through
`GET /api/pit-library`; no stored data is modified. See [UI instructions](ui/README.md)
and the [API contract](src/api/README.md).

## Signal Library UI

Open `http://127.0.0.1:8765/#signals` to browse represented reusable FX recipe summaries
and unchanged non-FX entries. Expanded output details retain exact historical Signal IDs,
instruments, counts and lineage. The Feature dropdown separately reads reusable recipe
definitions, including registered unmaterialized configurations. Scoped research results
resolve to authoritative records without a recipe-wide validation flag. See
[specification 22](specs/22_signal_library_recipe_summaries.md) and
[the current UI instructions](ui/README.md); the earlier
[UI completion report](docs/signal_library_ui_report.md) remains historical evidence.

## Return Target library

The [Target library](docs/target_library.md) explains every executable return construction,
domain and timing rule. [Specification 18](specs/18_return_targets.md) owns the current
0.4 contracts, identity and storage rules; the [implementation report](docs/target_implementation_report.md)
records actual acceptance tests and persisted fixture proof. The Target dropdown reads
`GET /api/target-library` and reflects actual persisted return builds and their readiness.
Provisional retrospective FX outputs remain distinguishable from strict historical PIT and
live eligibility. An unpopulated combination exposes its blocker; no macro earnings Target
is fabricated.


## Bounded legacy FX import (9 October 2026)

The new FX source adapter preserves all 18 requested Twelve Data histories in the existing
PIT snapshot/shared payload system: 145,236 completed closes. It retains unknown historical
availability and the original capture evidence. The 43 requested economic instruments are
registered; 18 direct/inverse price histories were stored before the subsequent approval.
The approved 25 date-matched cross histories and all 215 simple-return Target combinations
are now stored and independently verified. Unknown synchronization is a disclosed
provisional retrospective limitation; known incompatibilities and bad endpoints remain
blocked. Preserve the earlier audit history and already completed work. Registration or this
approval is not itself evidence of completed materialization, strict historical replay or
live readiness.

See [specification 19](specs/19_fx_sources_and_return_targets.md),
[FX data contracts](docs/fx_data_contracts.md), and [execution evidence](docs/fx_execution_report.md).
The existing UI reads the actual FX source catalog and construction readiness.
`tools/fx_batch.py` inspects the bounded sources, resumes from stored prices, and verifies reuse of an explicit completed run without provider downloads or unnecessary re-onboarding. `docs/fx_completed_run.json` pins this completed execution.
`tools/targets.py` supports instrument/horizon filtering and explicit persisted build/range/cutoff reads.
