# FX data contracts and inspection

The FX extension keeps three distinct layers in the existing platform:

```text
Legacy provider raw evidence
  -> captured source history in PIT infrastructure
  -> normalized USD legs and reusable direct/inverse/cross prices
  -> forward return observations in the Target Store
```

A stored retrospective snapshot is not proof of historical PIT completeness. A registered
instrument is not a populated return Target. A numerically valid return is not evidence of
historical training eligibility or live-trading readiness.

## Approved completion scope

The user's subsequent 9 October 2026 instruction explicitly approves both former decisions
for this FX gross spot return family. It authorizes completing the 25 cross histories and
simple forward returns for all 43 instruments at exactly 1, 7, 21, 63 and 252 scheduled
weekdays: **215 logical combinations**, independent of physical file layout. Reuse the
existing 18 source registrations, 43-instrument manifest, migrated observations and completed
direct/inverse prices. No repeated onboarding or legacy modification is required.

The calendar is Monday–Friday with no holiday exclusions. Entry is the anchor date's close;
exit advances exactly h scheduled weekdays, excluding the anchor from the count. Resolve
these dates before looking up observations. Missing, invalid, conflicting or unavailable
endpoints stay null with reasons; there is no filling or move to the next observed close.
Missing interior prices do not invalidate an endpoint-only return. Stored fractions use
`0.01` for one percent. Seven weekdays is not a calendar week and 252 is not an exact year.

The approved cross policy uses equal provider date labels and accepts unknown exact timing
as a disclosed provisional retrospective limitation. Known incompatible sessions, wrong
quotation direction, currency mismatches and bad/conflicting observations remain blocked.
Do not invent a wall-clock tolerance, publication time, vintage history or midnight close.

Zero delay is a return anchor convention only, not proof an order could fill at that close
after a Signal was produced. Feature availability, historical label eligibility and training
cutoff protections remain unchanged. Neither approval applies to unrelated Target families.
No log-return or additional-horizon materializations are authorized by this completion.

Earlier audits correctly recorded these choices as pending. Their historical conclusions
remain unchanged; [specification 19](../specs/19_fx_sources_and_return_targets.md) records the
subsequent approval amendment and independent validation plan. Actual execution counts and
materialization IDs belong to the completed catalogs and execution report, not this policy.


The registered completion bundle is `config/fx_retrospective_completion.json`. It pins
`EVIDENCE_63a162f8a975a25fda80701febe60896047eaf299903c3bcc8d83081f26b818c@1.0.0`
and retrospective policy
`POLICY_2ba9539c29b93277e30ee4c2b0752c3e54cbcf9a101ec19b2628dc5fb43ec14b@1.0.0`.
These are actual registered approval identities, not output-completion evidence.

## Actual locations

The active platform root is:

```text
/Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/research_platform
```

The read-only legacy Data root is:

```text
/Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data
```

| Content | Path relative to its root |
| --- | --- |
| Legacy production pages | `Data/production/twelve_data_fx/symbol=<BASE>_<QUOTE>/page=NNNN/` relative to Multi-Asset Model |
| Legacy raw provider bytes | `Data/raw/v1/twelve_data_fx/<prefix>/<sha256>.json` relative to Multi-Asset Model |
| Legacy source catalog | `Data/catalog/latest/twelve_data_fx.catalog.json` relative to Multi-Asset Model |
| Provider contracts | `definitions/providers/<PROVIDER_id>/1.0.0.json` in research_platform |
| Source and constructed dataset definitions | `definitions/datasets/<DATASET_id>/1.0.0.json` |
| Source and constructed source views | `definitions/source_views/<SOURCE_VIEW_id>/1.0.0.json` |
| Canonical price recipes | `definitions/transformations/<TRANSFORM_id>/1.0.0.json` |
| Import, alignment and Target policies | `definitions/policies/<policy_id>/1.0.0.json` |
| Return Target definitions | `definitions/targets/<TARGET_id>/1.0.0.json` |
| Raw/PIT/normalized-leg/constructed-price snapshots | `storage/catalog/snapshots/<SNAPSHOT_id>/manifest.json` |
| Evidence and instrument registration projections | `storage/catalog/onboarding/evidence/<EVIDENCE_id>.json` |
| Original capture receipts | `storage/catalog/ingestions/records/<INGESTION_id>.json` |
| Readiness records | `storage/catalog/readiness/records/<READINESS_id>.json` |
| Full onboarding completion seal | `storage/catalog/onboarding/runs/<ONBOARDING_id>.json` |
| Return builds | `storage/catalog/target_store/<MATERIALIZATION_id>/manifest.json` |
| Shared payload bytes | `storage/payloads/sha256/<prefix>/<sha256>.<format>` |
| Existing raw locator records | `storage/catalog/locators/<blob_sha256>/<store_id>/<relative_path_digest>.json` |
| Local configured store roots | `config/storage.local.json` |

There is no separate FX price database. All source and derived-price observations use the
same snapshot catalog and shared content-addressed payloads. Return observations use the
already established Target catalog and shared payload namespace. Instrument registration is
an evidence projection linking real recipes and snapshots, not another mutable store of prices.

Raw provider artifacts are referenced through checksum-verified locators rooted in configured
read-only stores. The importer does not duplicate the raw library or modify legacy pages.
The reusable source close representation and lineage are new materializations; they avoid
copying all four legacy OHLC fields. Preserve original raw and canonical hashes so every
computed close resolves back to its provider cell.

## Schemas and payload format

`specs/schemas/fx.schema.json` introduces 0.5 source/recipe envelopes and compact FX Target
observation/materialization contracts. Runtime adapters validate profile semantics in addition
to schema structure. Existing return definitions and scientific policies continue to use 0.4
Target contracts. Earlier 0.1–0.3 records and approved identities are not rewritten.

Registry references retain the existing triple:

```json
{"id":"...","version":"1.0.0","content_sha256":"..."}
```

Year-partitioned payload members retain blob hash, byte count, row count, physical format and
role. Compressed members use `format: "bin"`, `codec: "gzip_jsonl"`, a year partition key,
native-date coverage and a semantic row digest. Each decompressed line is canonical JSON.
The compressed header contains no current time or host filename. Readers check physical and
semantic hashes. The compression format is a physical representation, not a new price store.

Source row decimal values are text. Native observation dates stay dates. `available_at` and
`source_vintage_at` are null. `original_ingested_at` records the actual legacy capture; the
current migration time exists only in the onboarding run seal. Unknown source timezone,
bar boundary, session convention and price basis remain explicit null/unknown metadata.
The earlier inferred `available_at` is retained only inside lineage evidence.

The source lineage index is a compressed batch, keyed by each row's `lineage_key`. It records
raw hash, datetime, cell field/value, row index/hash, canonical legacy page hash and row
index/hash. It does not create a filesystem record for every observation.

## Price identity and reuse

Every requested pair has separate economic identity, source dependencies and construction
recipe. Five pairs are direct, thirteen are reciprocals and twenty-five are USD-triangulated.
Recipes explicitly bind source direction, normalization and alignment; no direct/synthetic
fallback or unrelated provider is allowed. USD is a constant numeraire. CNH stays distinct
from CNY. A direct source price is retained without reciprocal round trips.

Canonical prices are reusable inputs to Features and Targets. Their recipe identity does not
contain their predictor/outcome role, Target horizon or a temporary evaluation window.
Constructed prices remain gross spot-price values with unknown basis for the actual sources;
do not call them midpoint, executable or account-equity observations.

Content identities and year partitions support selective reuse. Only the exact operand price
IDs enter a pure endpoint Target observation. A repaired interior date that is neither entry
nor exit does not invalidate that label. Unaffected row IDs and year payload hashes remain
reusable. Current batch verification may still recalculate rows; selective identity/storage
reuse is not advertised as a fully incremental computation scheduler.

## Return labels and readiness

Simple and log returns apply the existing return engine to the constructed entry and exit
prices. The schedule is generated from the approved Monday–Friday/no-holiday policy before price lookup. Missing
endpoints remain null; the next nonmissing source row never silently replaces the intended
exit. The horizon unit is scheduled weekdays and is not inferred from a name ending in `d` or a legacy valid-observation clock.

0.5 FX Target rows contain:

- Exact Target reference and stable observation ID.
- Prediction anchor, entry, exit and intended end, with native date precision.
- Decimal return or null, `valid/missing/invalid/pending` status and reason.
- Exactly two entry/exit price observation references.
- Null `source_availability` and `label_available_at` for these snapshots.
- Original archived capture completion, separately from historical label availability.
- `historical_eligibility_certified: false` and elapsed/future endpoint maturity.

Readiness distinguishes stored PIT inputs, constructed prices, persisted return Targets,
retrospective research, historical replay and live use. Readiness for one does not imply the
others. No FTMO eligibility or live execution certification is produced by onboarding.
Under this approval, strict historical training retrieval still excludes labels whose
historical eligibility is uncertified. Future labels do not need to have been known at their
prediction anchor; they must satisfy the declared outcome/maturity policy before use.

## Python interfaces

Run these in the existing platform Python environment with `src` on the import path. Supply
real immutable references returned by the stored catalogs; the placeholders below are not IDs.

```python
from data.fx_onboarding import onboard, read_source
from data.fx_pipeline import register_and_construct, list_instruments
from data.targets.service import retrieve_target

# Reuse the existing saved onboarding result; do not call onboard again for completion.
source = read_source(platform_root, saved_onboarding["sources"][0]["pit_snapshot"])
registered = register_and_construct(platform_root, saved_onboarding,
                                    alignment_policy=approved_policy_bundle["alignment_policy"])
instruments = list_instruments(platform_root)

# Requires a real Target ID and its exact completed build, when one exists.
result = retrieve_target(platform_root, target_id, materialization_id)
```

The optional `training_cutoff` and `cutoff_precision` arguments invoke the existing strict
training filter. Do not omit that filter and interpret a retrospective result as historically
available. `data.targets.fx.materialize` additionally requires a complete explicitly approved
family policy and a knowledge cutoff. The approved bundle must resolve to the registered
user-approval evidence and versioned calendar/alignment records. A literal `approved` flag or
an unrelated policy is not a substitute for that exact binding.

## Existing CLI and API

The existing Target command continues to inspect stored results:

```text
python tools/targets.py list
python tools/targets.py definition --target-id <TARGET_id>
python tools/targets.py materializations --target-id <TARGET_id>
python tools/targets.py get --target-id <TARGET_id> --materialization-id <MATERIALIZATION_id>
```

The read-only API retains `/api/target-library`. Catalog filtering supports an exact
`instrument_id`, or paired `horizon_amount` and `horizon_unit`. The detail route
`/api/target-library/<TARGET_id>` requires `materialization_id`; optional training cutoff must
include its temporal precision. Optional range controls are `start_inclusive`, `end_exclusive`
and `range_precision`; bounds filter prediction anchors at the stored precision.

The existing Target selector uses catalog-backed definitions and completed results. Registered
instruments without return materializations may be inspected with their blockers but must not
be presented as ready selectable return Targets. Detail shows real construction, coverage,
lineage and readiness, with no invented metrics or data points.

## Evidence and remaining limitations

The read-only audit establishes 145,236 completed closes across the 18 requested sources,
with no canonical conflicting, duplicate or nonpositive/nonfinite closes. That statement is
source evidence, not a count of newly migrated or built records. Actual execution output must
be reported separately after the run.

The retrospective cross and first return-batch decisions are now resolved for this family.
Missing source evidence still includes historical publication timestamps, native historical
revision history, daily close conventions, timezone/DST handling, source price basis,
material-staleness evidence and verified account eligibility. The approval permits disclosed
retrospective calculations; it does not manufacture any of this evidence. Known incompatible
sessions and actual bad or missing endpoint observations continue to produce explicit
blockers or null labels. Future strategy decisions, execution timing and discovery/validation
boundaries are outside this completion.
