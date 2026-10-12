# Return Target subsystem — implementation report

Completed in `/Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/research_platform`.
The executable scope is continuous forward investment returns. The production catalog is
truthfully empty because its only onboarded production dataset is economic earnings data.
An isolated persisted market fixture proves the complete production path.

## Implemented files and ownership

| Concern | Executable owner |
| --- | --- |
| Closed definitions, source economic policies, observations, stable identity | `src/data/targets/contracts.py`; `specs/schemas/target_store.schema.json` |
| Expected market schedules, entry/end rules, four horizons, temporal alignment | `src/data/targets/scheduling.py` |
| Source qualification, forward construction, vintage selection, availability | `src/data/targets/engine.py` |
| Existing canonical PIT snapshots to return inputs | `src/data/targets/adapter.py` |
| Existing registry/shared payload extension and immutable publication | `src/data/targets/store.py`; `specs/schemas/target_materialization.schema.json` |
| Creation, preflight, materialization, refresh, list, lookup, historical retrieval | `src/data/targets/service.py`; `tools/targets.py` |
| Read-only API and actual Target dropdown | `src/api/target_library.py`, `src/api/server.py`, `ui/targets.js`, `ui/index.html` |
| Reproducible isolated persisted proof | `tools/run_target_fixture_proof.py`; `tests/fixtures/target_return_proof/` |
| Authoritative semantics and explanatory library | `specs/18_return_targets.md`; `docs/target_library.md` |

Six reusable calculation/validity/outcome policy definitions are installed in the existing
`definitions/policies/` registry. Source-specific economics and market schedules require
admitted source evidence; the proof registers such records only in its isolated store.
No production Target definition is manufactured. Directory READMEs and documentation
indexes now describe the executable Target path.

## Fully executable capability boundary

Price/spot simple and natural-log returns use exact eligible endpoints. Total returns use
certified wealth indices or complete consecutive canonical period returns. Simple period
returns compound wealth factors; log period returns sum. Benchmark excess is the difference
of compatible simple returns or the difference of compatible log returns. Arithmetic excess
has no universal lower bound of minus one. Outputs remain dimensionless fractions or natural
logs, without percentage scaling or annualization.

Source qualification checks investment instrument/series, measure and dimensions, unit,
currency, FX base/quote orientation, calendar/version, timezone, observation convention,
income/corporate-action treatment, adjustment semantics and availability/vintage evidence.
Ambiguous adjusted prices, macro earnings changes, rates/yields/spreads and raw futures
ratios are rejected. Specialized instruments can enter through certified canonical wealth
or return sources. There are no pricing, roll, leverage, execution, financing, cost or
portfolio engines. Period-return representation must match the requested representation;
implicit percent scaling and simple/log component conversion are outside this contract.

Schedules are exact, finite canonical expected session/bar calendars backed by an immutable
evidence payload. They are not inferred from whichever observations survive. The executor
supports market-mark or explicit-set prediction anchors; anchor-mark or strictly subsequent
entry with a declared delay; trading-session, scheduled-bar, local-calendar-day and elapsed-second
horizons; exact endpoints or next expected marks within a positive bounded tolerance. Date
precision rejects elapsed-second policies. Calendar boundaries, holidays, shortened sessions
and daylight-saving transitions follow supplied expected marks and pinned IANA timezone bytes.
Missing endpoint prices remain missing; they never move the endpoint or compress a horizon.
Insufficient calendar coverage rejects preflight. This subsystem validates and consumes
certified schedules rather than inventing exchange holiday calendars.

First-defensible and pinned-later selection are implemented. First-published, first-archived
and first-ingested evidence are distinct and must match the selected policy. First selection
requires a complete defensible vintage history. Unknown availability can produce numerical
results only under an explicit uncertified policy. Label availability follows the economic
endpoint, all selected evidence and any finalization wait. Date-only labels cannot enter
training on that same date. Future endpoint, not-yet-available evidence, missing historical
endpoint, invalid input and execution failure are distinct outcomes.

## Contracts, identity, storage and historical use

Target schema 0.4.0 and identity/calculation profile `target_return.1.0.0` are explicit new
profiles. Original approved Feature definitions, historical schema examples and reports
remain unchanged. Authority notices in specifications 01, 03 and 12 point Target execution
to specification 18; the old draft UTC-only observations and request-only materialization key
are not silently reissued as the new contract.

Logical identity includes the SourceViews and their exact versions, source selections,
economic conventions, horizon and semantic timing policies. A Target is independent of
Feature, Signal, expected direction, Research Spec and results. Display names, execution
time, paths and actual appended observations/finite coverage do not change logical identity.
Scientific changes create distinct content IDs at version 1.0.0. One definition is reusable
across many research relationships.

Definitions use `definitions/targets/<TARGET_ID>/1.0.0.json`. Ready manifests use
`storage/catalog/target_store/<MATERIALIZATION_ID>/manifest.json`. Observation JSONL,
schedule/interval evidence, exact operand locators and pinned implementation artifacts use
only the existing shared `storage/payloads/sha256/` namespace. Upstream source records remain
referenced in their original snapshots; Target publication does not duplicate raw/PIT data.

The materialization key binds exact definition, source snapshots, schedule/anchor hashes,
knowledge cutoff and precision, actual implementation/environment dependencies and output
integrity. Code/schema and IANA TZif bytes are pinned. Execution timestamps are separate
operational attempt records. Payload and dependency verification precedes the atomic ready
manifest. Interrupted publication may retain reusable unreferenced blobs, but cannot expose
a ready Target pointing to missing payloads. Repeated requests reuse immutable artifacts.
Refresh is explicit and local to one requested Target, preserving all prior materializations.

Retrieval requires an explicit materialization ID; there is no scientific moving-latest
lookup. A supplied training cutoff and precision filter valid certified labels by historical
availability. Returned full records expose the actual interval and selected evidence for
future overlap/training-boundary handling. Feature alignment separately checks Feature
availability, evaluation time and reference time against the prediction anchor; Target
availability is checked against the training cutoff. No research/CV engine was added.

## Service, CLI and API

The service exports `create_target`, `preflight_request`, `materialize` / `refresh_target`,
`list_targets`, `get_definition`, `list_materializations`, `read_materialization` and
`retrieve_target`. A request pins `definition`, `sources` (role to PIT snapshot reference),
`schedule`, `anchors` and `knowledge_cutoff`. Canonical source JSONL is required; native
provider parsing, new downloads and other physical-format adapters remain upstream work.

From the platform root:

```sh
.venv/bin/python tools/targets.py register-policy --file POLICY_BODY.json
.venv/bin/python tools/targets.py create --file TARGET_BODY.json
.venv/bin/python tools/targets.py preflight --file REQUEST.json
.venv/bin/python tools/targets.py materialize --file REQUEST.json
.venv/bin/python tools/targets.py refresh --file REFRESH_REQUEST.json
.venv/bin/python tools/targets.py list
.venv/bin/python tools/targets.py definition --target-id TARGET_ID
.venv/bin/python tools/targets.py materializations --target-id TARGET_ID
.venv/bin/python tools/targets.py get --target-id TARGET_ID --materialization-id MATERIALIZATION_ID --training-cutoff 2024-01-09 --cutoff-precision date
```

`register-policy` and `create` input files contain `body` plus optional `display_name`.
The saved proof supplies executable exact request examples, rather than placeholder
scientific bindings. `--root` precedes the subcommand when reading its isolated store.

API: `GET /api/target-library`; detail at
`GET /api/target-library/<TARGET_ID>?materialization_id=<MATERIALIZATION_ID>`, optionally with
paired `training_cutoff` and `cutoff_precision`. Writes remain unavailable. The selector
has one option per unique Target and displays investment series, basis, representation,
horizon and readiness. Only verified materializations with certified valid labels enable
selection. With multiple certified versions, the display pins the lexicographically greatest
ID as an explicitly documented presentation preference; it is not a latest-vintage rule.
Actual research retrieval still requires an explicit snapshot and training eligibility check.

The restarted local UI was checked in the browser: **No stored Targets**, disabled,
with an actionable source-admission explanation. Existing Feature remains selectable with
187 observations, and PIT library still shows CES0500000003 with 247 reference observations.
Scope/Research Spec remain the pre-existing placeholders; this task did not implement research.

## Executed validation

Final commands ran from the actual installed platform, using its existing environment:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests/specifications -v
node --check ui/targets.js
```

- Main implementation and regression suite: **426 tests, 44.079 seconds,OK**.
- Specification suite: **24 tests, 0.174 seconds,OK**.
- New Target test methods included in the main suite: **142** (60 engine, 37 scheduling,
  17 adversarial,16 persistence,12 API/selector). This is separate from all earlier Feature counts.
- Zero final failures, errors or skips. JavaScript syntax passed. The actual `targets.js`
  also ran against empty, failed, unmaterialized, uncertified and ready catalogs in acceptance tests.
- Scheduling tests include 56 policy subcases; the engine includes 32 construction/timestamp
  horizon/entry subcases; persisted construction acceptance includes 12 combinations.
- Earlier fixture runs exposed integration issues in schema/version handling, artifact-role
  validation and corrupt-catalog isolation; those were corrected before these final results.
  Local HTTP tests ran with the required local-socket sandbox allowance; no provider network
  access, credentials or package installation was needed.

| Supported capability | Executable implementation | Executed acceptance coverage |
| --- | --- | --- |
| Simple/log price and spot | `engine._ratio`, economic preflight | Engine price reference tests; independent Decimal and `math.log`; persisted 12-case path |
| Total wealth and component returns | `engine._calculate_source` | Wealth income once; compound versus sum; log sum; period gaps/overlaps/duplicates/boundaries |
| Arithmetic/log benchmark excess | `engine.construct` | Distinct excess formulas, excess below −1, wealth/period comparisons, currency/coverage rejection |
| Economic and FX eligibility | `engine._economic_eligibility` | CES/macro/yield/futures rejection, ambiguous adjustments, specialized certified inputs, quote inversion/currency, provider independence |
| Numeric validity/null outcomes | contracts and engine | Zero/negative start/end, evidenced total loss, nonfinite source, overflow, missing/invalid source, component unit/representation |
| Expected schedules/four clocks | `scheduling.resolve_intervals` | 56-combination matrix, missing bars, calendar/session divergence, holidays/weekends, short sessions, DST, off-by-one, bounded match |
| Entry and precision | scheduling and preflight | Anchor versus strictly-next, delays, explicit set identities, date restrictions, timezone/offset and coverage rejection |
| Outcome versions and availability | engine + historical retrieval | First versus corrected state, archive/publish/ingest differences, delayed evidence, waits, pending versus missing, unknown eligibility |
| Leakage and alignment | engine, scheduling, service | Before/after correction cutoff, preserved old materialization, future source/Feature isolation, same-date ambiguity |
| Stable identities and refresh | contracts + service | Display/runtime/coverage invariance; semantic changes; same Target/new matured or corrected materialization; exact rerun reuse |
| Provenance and upstream reuse | adapter + store | Source metadata, snapshot integrity, exact payload row/index/hash, PIT-to-raw locator, no source byte duplication |
| Publication and integrity | store + service | Interrupted dependencies/payloads, recovery, missing/corrupt payloads, summary/identity mismatch, unrelated corrupt Target isolation |
| Independent persistent retrieval | service + CLI | Fresh process reads and unchanged old results; saved proof IDs below |
| API/selector | API/server/targets.js | 12 executed tests: real HTTP, explicit selection, historical cutoff, readiness/empty states, host/method protections |

Full captured logs accompany this report as `target_test_results.txt`; machine-readable
results and actual proof references are in `target_implementation_evidence.json`.

## Persisted end-to-end proof

Isolated store: `tests/fixtures/target_return_proof/`. It uses the same production
contracts, source adapter, computation, shared-payload layout, publication and retrieval.
It is never enumerated by the main production registry.

Logical Target:
`TARGET_d2e957f41300ab807ed696363141876b91d4c918eb7ccac55d6525d96b6a2e07`

| Saved version | Materialization ID | Result |
| --- | --- | --- |
| Pending, cutoff 2024-01-03 | `MATERIALIZATION_825a0d6d2560d174219cdab4e8c6c6f7be6c9eb1f8dfe2aa81cd1c5b93fb8f6f` | Null, future endpoint |
| Initial, cutoff 2024-01-05 | `MATERIALIZATION_1f0349c70c1948586236c435f5aa6f757e07dceeecb7e4b1a388db72aa65870d` | 100 → 121 over Jan 2–Jan 4: 0.21 |
| Corrected, cutoff 2024-01-09 | `MATERIALIZATION_f51d461e722e704376efbc39da40c69197863153e09873284ba989b619222238` | 100 → 125: 0.25; correction available Jan8 |

Both operands have exact persisted locators. At training cutoff Jan 7 the corrected label
is excluded; by Jan 9 it is eligible. The initial saved label remains 0.21 and is independently
retrievable in a fresh process after the correction. Repeating the corrected request reuses
its exact materialization. `proof.json`, `request_initial.json`, `request_corrected.json`,
canonical definitions, source snapshots, Target manifests and shared payloads remain saved.

Executed proof command in the isolated build copy, then copied its verified artifacts into
the actual project and independently retrieved them there:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python tools/run_target_fixture_proof.py
```

## Verified facts, decisions and remaining source prerequisite

Verified: the pre-task Target directory was reserved, the planned Target Store had no
implementation, and the Target selector contained mocks. The transformation foundation
actually contains 98 registered definitions and executable modules. The only onboarded
production source is CES0500000003. It remains an economic Feature, not an investment return.
All 779 pre-existing scientific definition/storage files checked against the captured baseline
are byte-for-byte unchanged. Existing provider/PIT/Feature code and historical reports are
preserved; only the shared API server and relevant current documentation/UI were extended.
No legacy data was migrated, deleted or written.

Implementation decisions are explicit in specification 18: strict endpoint dependency
validation, no stale price substitution, content-addressed Target definitions, output-bound
immutable materializations, conservative date availability, supplied certified calendars,
and decimal 50 arithmetic with finite binary64 output guard. These close the prior draft
scheduling, schema, constructor, storage, retrieval and UI gaps for the advertised return
scope. No further design task is required to execute qualifying canonical inputs.

**Real market data is not yet ready.** Legacy FX files are candidates, not admitted inputs.
The next bounded task is to certify and onboard one existing legacy FX price history into
a canonical PIT SourceView. Required evidence: selected close/mark semantics; pair and quote
orientation; measurement currency and economic coverage; timezone, calendar/version and
expected marks; first-archive/publication/ingestion distinctions; correction history and
historical availability limits. Then register its economic/schedule policies and one exact
Target binding, preflight, materialize and retrieve a bounded real trial. No additional
return engine or ad hoc horizon interpretation is needed. This source prerequisite is
separate from the completed tested implementation. No broader provider/instrument support
or production financial performance certification is claimed.
