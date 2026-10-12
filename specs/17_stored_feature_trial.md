# 17. Stored Feature and parent Signal from approved archive-date PIT history

Status: the bounded adapter, scheduled executor, Feature Store writer and independent reader are implemented. This specification describes their contract. Actual production identities, counts, retrieval evidence and test results belong in the [completion report](../docs/first_signal_trial_report.md); specification text alone does not establish a successful publication.

This extends [16 Transformation execution](16_transformation_execution.md) and uses the locations in [12 Pipeline and storage](12_data_pipeline_and_storage.md). It authorizes one configured generic monthly `change.pct(k=1)` recipe, with dimensionless fractional-change output. There is no Target, P1/P2 trial, relationship metric or live-trading certification in this implementation.

## Authority, verified facts and limits

The user approved archive-date replay: one output at each actual stored native vintage date; select the latest reference month available by that date; divide its level by the immediately preceding calendar month's level from the same historical state and subtract one. A missing required month remains a scheduled null. This approval is encoded as the versioned `POL_TRANSFORM_EVALUATION_NATIVE_VINTAGES` selection policy, with an exact SourceView reference and stored specification evidence.

The source audit established monthly, date-precision, seasonally adjusted levels denominated in dollars per hour. Its full stored package contains 247 reference months and 1,587 PIT events across 187 native vintage dates, including 36 explicit missing observations. These are source-package facts, not permanent limits embedded in the recipe. Raw/PIT completion markers, manifests, payload checksums, source policies and native metadata are verified before adaptation. Existing raw/PIT content and legacy directories remain unchanged.

Archive dates do not establish intraday release timestamps, an executable trading-decision clock, real-time availability latency or a live deployment policy. A retrievable stored Feature is scientifically **untested** until a separately defined Target/Scope/direction/Research Spec relationship has been evaluated and validated.

## Implemented path and ownership

```text
configured native-series lookup + exact Dataset/SourceView/PIT snapshot
  → existing verified stored-PIT reader
  → canonical single-partition adapter with exact source operand locators
  → approved native-date schedule and same-state monthly operand selection
  → registered generic transformation engine
  → immutable Feature observations + materialization manifest
  → parent Signal Library links
  → independent canonical retrieval by Signal ID and materialization ID
```

| Concern | Implemented owner |
| --- | --- |
| Resolve native series against registered provider metadata; verify exact stored source | `src/data/stored_pit_source.py` — `load_source` |
| Convert declared native fields to the canonical envelope and compact operand records | `src/data/pit_feature_adapter.py` — `adapt_pit_history` |
| Enforce the approved SourceView-bound schedule | `src/data/feature_evaluation.py` — `resolve_native_schedule`, `execute_scheduled_recipe` |
| Cutoff selection and registered arithmetic | `src/data/pit_selection.py`; `src/data/transformations/engine.py` |
| Date-preserving stored-record validation | `src/data/feature_store_contracts.py`; `specs/schemas/feature_store.schema.json` |
| Publication and independent retrieval | `src/data/feature_store.py` — `publish_feature`, `read_materialization`, `retrieve_signal` |
| One explicit invocation and operational audit | `src/data/first_signal_trial.py`; `tools/run_first_signal_trial.py` |
| Selected source, exact operator/parameters and policy references | `config/first_signal_trial.json` |

Provider-specific field interpretation belongs upstream in the source profile. The numerical engine never branches on provider or native-series labels. Retrieval resolves registered definitions, manifest references, canonical PIT row locators and payloads; it does not download observations or invoke a provider payload parser to reinterpret a Signal.

## Evaluation and failure rules

The policy's exact approved parameters are:

| Parameter | Rule |
| --- | --- |
| `source_view` | Exact immutable SourceView reference |
| `cutoff_schedule` | `all_observed_native_vintage_dates` |
| `current_reference` | `latest_reference_month_at_cutoff` |
| `denominator_reference` | `previous_calendar_month` |
| `missing_required` | `retain_null` |
| `history_mode` | `resolved_state` |
| `temporal_precision` | `date` |
| `interpretation` | `archive_date_replay` |

Every distinct native availability date in the complete adapted source produces one output. No daily expansion, inferred release events, fabricated midnight UTC timestamps or execution-time substitution occurs. Both operands must have reference time and availability at or before that cutoff. Each reference resolves to its latest permitted vintage independently; the preceding emitted Feature value is never used as the denominator.

For current month `m` at cutoff `t`, the sole operation is `x(m, t) / x(m−1 calendar month, t) − 1`. A revision can therefore produce another result for the same reference month at a later cutoff. Its output key retains both reference time and evaluation cutoff. `available_at` equals the evaluation cutoff under `derived_at_cutoff`; this is archive replay eligibility, not a newly certified historical publication timestamp.

An absent required calendar month yields null with `MISSING_PERIOD`. A real source missing/invalid value or zero denominator retains the generic engine's controlled failure reason. Null source rows are preserved. There is no filling, month skipping, fallback to a previous emitted result, or replacement with zero.

Complete contiguous states use a single scheduled engine call. If an older unrelated calendar gap prevents general whole-history execution, this bounded `k=1` wrapper delegates the two actual adjacent operands to the same engine. They are the complete mathematical support of this operation. The outer materialization still binds the complete original source and complete requested schedule. Missing operands are represented by absent lineage roles, never invented source observations. Unexpected engine failures remain exceptions.

## Versioned records and exact storage

Scoped Feature JSONL persistence now implements the previously reserved Feature Store paths. General Target storage and Parquet support remain future work.

The platform adds **0.3.0** stored Feature observations, materialization manifests, PIT operand records, Signal Library entries and operational execution audits. Feature definitions, lineage/implementation manifests and versioned policy/operator definitions retain their existing **0.2.0** schema conventions. The canonical calculation envelope remains **1.0.0**. The existing UTC-only 0.2 materialization utility and its identity vectors remain unchanged.

The new stored materialization uses the existing explicit `transformation_execution.1.0.0` identity profile with native date precision and an explicit output index. It is not represented as a UTC-only 0.2 manifest.

| Stored object | Authoritative location relative to the platform root |
| --- | --- |
| Feature definition and derived parent Signal ID | `definitions/features/<FEATURE_ID>/1.0.0.json` |
| Approved evaluation policy | `definitions/policies/POL_TRANSFORM_EVALUATION_NATIVE_VINTAGES/2.0.0.json` |
| Policy evidence | `storage/catalog/onboarding/evidence/<EVIDENCE_ID>.json` plus its checksum-addressed JSON payload |
| Feature materialization | `storage/catalog/feature_store/<MATERIALIZATION_ID>/manifest.json` |
| Feature observation partition | `storage/payloads/sha256/<prefix>/<sha256>.jsonl` |
| Exact PIT operand and output lineage records | `storage/catalog/lineage/<PIT_OPERAND_ID-or-LINEAGE_ID>/manifest.json` |
| Pinned code and environment manifest | `storage/catalog/implementations/<IMPLEMENTATION_ID>/manifest.json` plus immutable shared payloads |
| Signal Library link projection | `storage/catalog/signal_library/entries/<SIGNAL_ID>/<entry-content-sha256>.json` |
| Operational execution attempt | `storage/catalog/attempts/<attempt-id>/events/<event-content-sha256>.json` |

Each observation stores materialization ID, selected measure/entity/dimensions, reference date, evaluation cutoff, derived availability date, derived vintage ID, canonical finite decimal value or null, status/reason and lineage reference. Its manifest declares exact definition/input identity, native precision, units/semantics/cadence, policy bindings, partitions, bounds, row/status counts, semantic row digest and lineage references. Decimal serialization preserves the binary64 engine result; it does not imply arbitrary-precision arithmetic.

There is no second independently editable Signal definition, copied observation library, or editable IC field. The Signal Library links the canonical Feature definition and materializations; `relationship_results` is empty for this untested Signal. Future research metrics must resolve to authoritative Trial/Validation result records.

## Logical identity, coverage and evidence

One exact recipe derives one Feature ID and one corresponding parent Signal ID. The SourceView, partition, operator/version, typed `k=1` parameter, output semantics and history/execution/evaluation policies bind logical identity. The evaluation policy describes a rule; observed vintage dates, row counts and selected snapshots describe a particular materialization.

Appending new source history under the same logical SourceView/rule does not create a different Signal. Changing the recipe, SourceView or policy does. Target assets/horizons, expected direction, Research Spec and evaluation relationships remain separate future research context.

A materialization binds the complete canonical input-series digest, exact source snapshot references, full evaluation-cutoff list, output reference/cutoff index, implementation and all applicable policies. Source evidence is not reduced to the rows that happened to contribute to a valid output. Display/provider labels, filesystem paths and wall-clock execution timestamps do not replace scientific identity.

Each output lineage has explicit `numerator` and `denominator` references when those operands exist. Each compact `pit_operand_record` pins Dataset, SourceView, PIT/raw snapshots, source policies, native precision, canonical key, full native PIT-row hash and locator, field mapping, raw blob and raw-cell coordinates. The explicit `raw_row_mapping` binds each raw selector field to its native PIT field, so raw-row key values must agree with the stored PIT row. It does not store another editable copy of the source value. Readers verify that the locator resolves to exactly one unchanged PIT row in the pinned snapshot and that the raw blob belongs to its pinned raw snapshot.

Source policies, native metadata evidence, snapshots, stored code, environment and operator/policy definitions remain in the verified dependency closure. Exact raw-cell coordinates are traceable evidence; canonical retrieval does not claim to reparse every provider's raw payload or rerun the numerical engine.

## Publication, retrieval and lifecycle

The writer installs immutable dependencies and an observation payload before publishing the complete materialization manifest. It verifies the dependency closure and rereads the durable manifest before installing the Signal Library projection. An interrupted payload-only attempt does not appear as a completed Signal. A retry can complete a manifest whose library projection was not yet written. Repeating the same scientific request reuses the same materialization; conflicting output under an existing identity rejects.

Operational attempt IDs and actual execution/completion timestamps live in audit events, outside logical Feature/Signal and scientific materialization identities. `run_trial` is an engineering execution entrypoint; this name does not create a P1/P2 Trial Ledger record.

`retrieve_signal(root, signal_id, materialization_id=None)` resolves the canonical Feature, verified materialization, stored observations and operand records. An explicit materialization is required when a Signal links more than one. A fresh read verifies schemas, identities, checksums, row counts/digests, dependency closure and historical operand eligibility; it does not recompute observations. The resulting lifecycle is `materialization_state: materialized`, `scientific_state: untested`.

All-invalid output is available as a transient diagnostic but is not published as a successfully materialized Feature. Failed rows in an otherwise publishable result remain explicit. Shared research submission, Targets, P1/P2, empirical metrics, release/live certification, recurring acquisition, automatic updates and a new UI are outside this task.

## Acceptance and remaining decisions

Synthetic acceptance covers exact native-date coverage, same-reference revisions, future-vintage/reference exclusion, calendar predecessor versus previous emission, missing months, missing values, zero denominators, unrelated historical gaps, complete-source identity, strict policy binding, immutable publication/retry boundaries and independent retrieval. Production acceptance additionally requires the completion report's actual first/middle/latest and revision-sensitive comparisons, fresh stored retrieval, repeat-run identity and unchanged source evidence.

The archive-date rule is settled for this SourceView. A separate live decision-clock policy, other source profiles/operators, a Target/outcome definition, Target horizon, Scope, expected direction and Research Spec remain explicit future choices. Stored materialization does not resolve or imply them.
