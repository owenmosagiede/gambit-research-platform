# 19 — Legacy FX sources, reusable prices and return Targets

Status: additive implementation specification, amended by explicit user approval on
9 October 2026 for this FX gross spot return Target family. Retrospective cross alignment and
the five-horizon simple-return schedule are now approved as defined below. They are not global
defaults. Presence of a recipe or tested kernel is not evidence of published observations;
the execution report supplies actual completion, counts, materialization IDs and tests.

The earlier audit correctly recorded these decisions as pending at that time. This amendment
does not rewrite that history or pretend approval preceded the user's subsequent instruction.
The approval text has SHA-256
`30a1a93f2ca0dbc2fb199dcfeadd73e04abdc6f04a3d38d1639c63d79b410bfb`; its registered
approval evidence and policy references are pinned by the completion build.

## Authority and compatibility

The current user request authorizes onboarding the exact 18 existing Twelve Data sources,
registering the exact 43 economic instruments, constructing reusable prices and building real
return Targets wherever the approved contracts and source evidence permit. Legacy data stays
read only; no additional provider, instrument, download or trading eligibility is inferred.

[18 Return Targets](18_return_targets.md) remains the authority for return definition semantics.
Target definitions and scientific policies remain version **0.4.0**. The new **0.5.0** envelopes,
source profiles and compressed observation/manifests are additive adapters to the existing
registries, `FeatureStore`, `TargetStore`, locator records and content-addressed payload store.
They do not replace prior Feature, Signal or Target definitions, policy approvals or identities.
The source profile is `fx_snapshot.1.0.0`, reusable price profile is `fx_price.1.0.0`, and compact
Target materialization identity profile is `target_fx_snapshot.1.0.0`.


The registered completion bundle is `config/fx_retrospective_completion.json`. It pins
`EVIDENCE_63a162f8a975a25fda80701febe60896047eaf299903c3bcc8d83081f26b818c@1.0.0`
and retrospective policy
`POLICY_2ba9539c29b93277e30ee4c2b0752c3e54cbcf9a101ec19b2628dc5fb43ec14b@1.0.0`.
These are actual registered approval identities, not output-completion evidence.

## Verified evidence

The read-only source audit found 35 completed production pages containing **145,236 unique
completed close observations** and 580,944 OHLC field observations for the exact 18 sources.
Their histories begin between 1979 and 2020; all completed canonical histories end 2026-09-05.
All checked raw and canonical page hashes reconcile, and canonical closes agree with their raw
provider cells. There are no canonical close duplicates, conflicts, nonfinite values or
nonpositive values in this audited set.

The source archive has 38 relevant raw artifacts, including overlapping pilot EUR/USD
captures. Thirty-six unique source/date records labelled 2026-09-06 or 2026-09-07 were omitted
at original capture as incomplete or future bars. Their dates being in the past now does not
establish that those captured values were final. They remain raw evidence.

Catalog base/quote codes, provider currency names, native symbols and registered
`quote_per_base` units agree. USD/CNH explicitly identifies offshore yuan. CNY is not a valid
substitute. Raw metadata establishes a daily OHLC response and a close field; it does not
establish midpoint, bid, ask, timezone, bar boundaries, market sessions or publication times.
The old registry's UTC label and next-midnight availability are adapter inferences, not
independent timing evidence. All 18 histories contain weekend labels. No market calendar can
be certified from those labels alone.

Each completed source record is a retrospective vendor snapshot captured in September 2026.
The original `retrieved_at` is known; the legacy `vintage_id` repeats that capture timestamp
and `revision_number` is zero. Partition capture timestamps are not historical revision
vintages. The existing quality resolution validates structure, lineage and positive closes;
it does not certify exact synchronization, historical PIT completeness or live trading.

The audit flags 15 adjacent-date changes exceeding absolute `log(1.10)` for review. This is an
explicit audit diagnostic, not an approved exclusion rule; no observations are clipped or
winsorized. Session gaps and staleness cannot be certified without their missing contracts.

## Exact scope and quotation contract

Sources:

```text
AUD/USD EUR/USD GBP/USD NZD/USD USD/CNH
CAD/USD CHF/USD JPY/USD CZK/USD HKD/USD HUF/USD ILS/USD
MXN/USD NOK/USD PLN/USD SEK/USD SGD/USD ZAR/USD
```

| Construction relative to original source | Requested instrument IDs |
| --- | --- |
| Direct — 5 | AUDUSD, EURUSD, GBPUSD, NZDUSD, USDCNH |
| Inverse — 13 | USDCAD, USDCHF, USDJPY, USDCZK, USDHKD, USDHUF, USDILS, USDMXN, USDNOK, USDPLN, USDSEK, USDSGD, USDZAR |
| USD triangulation — 25 | AUDCAD, AUDCHF, AUDJPY, AUDNZD, CADCHF, CADJPY, CHFJPY, EURAUD, EURCAD, EURCHF, EURGBP, EURJPY, EURNZD, GBPAUD, GBPCAD, GBPCHF, GBPJPY, GBPNZD, NZDCAD, NZDCHF, NZDJPY, EURCZK, EURHUF, EURNOK, EURPLN |

The runtime asserts exactly 18 distinct source symbols and 43 distinct economic instruments,
split 5/13/25. This is a requested research universe; FTMO account eligibility remains
unverified. Economic identity (`FX_<BASE>_<QUOTE>`) is separate from a provider symbol,
construction recipe, data materialization and account symbol.

For currency X, `U_X` is USD per unit of X. An X/USD source supplies `U_X` directly; USD/X
supplies its reciprocal. `U_USD = 1` is a mathematical constant, not a nineteenth source.
`P_A_B = U_A / U_B` has units B per unit of A. Thus EURJPY is EUR/USD divided by JPY/USD;
USDJPY is the reciprocal of JPY/USD. Requested USDCNH retains the original USD/CNH value even
though its normalized CNH leg is reciprocal. Direct prices avoid reciprocal round trips.

Normalize each input leg once for the universe. Prices have their own role-independent
recipe, source view, snapshots, lineage and identities so they can serve both Features and
Targets. Do not label a spot price series as a return Target.

## Source onboarding contract

Implementation: `src/data/fx_onboarding.py`, using `src/data/fx_records.py` and the existing
immutable installer. Public calls:

```python
onboard(root, legacy_root, audit_path, *, migration_time, interrupt_after=None)
read_source(root, pit_snapshot_reference)
```

`onboard` requires an audit containing the exact source set. It independently checks all
historical production pages, raw/canonical hashes, registries, quotation units, original
ingestion evidence, raw close cells, counts and coverage. An omitted page, changed checksum,
conflicting close or unsupported vintage profile stops that source publication. It does not
read credentials or request new provider data.

The result contains a `sources` list. Each entry carries the symbol, metadata, dataset,
provider contract, source view, raw/PIT snapshot references, original ingestion receipt
references, readiness assessment references, row count, coverage and reuse result.

| Canonical source row field | Meaning |
| --- | --- |
| `reference_time`, `observation_date` | Same native `YYYY-MM-DD` provider bar label; no claimed valuation instant |
| `value`, `status`, `reason_code` | Exact normalized decimal close, `valid`, null for the admitted completed source rows |
| `available_at` | Null: historical publication or usability time unknown |
| `original_ingested_at` | Actual original legacy capture timestamp, preserved separately |
| `source_vintage_at` | Null: no independently established source vintage timestamp |
| `legacy_vintage_id`, `legacy_revision_number` | Preserved legacy capture label and zero revision number; no invented revisions |
| `vintage_id` | Stable token derived from actual capture evidence, not a release date |
| `base_currency`, `quote_currency`, `unit` | Explicit source direction and quote currency per base currency |
| `source_record_id`, `source_ingestion_id` | Exact original provenance identifiers |
| `lineage_key`, `lineage` | Content identity resolving to the batched source lineage index |

The batched lineage index pins the canonical page hash and row index/hash, raw blob hash and
raw row index/hash, raw datetime, close field/value, original ingestion time and the old
inferred timing fields. Those old fields are retained as evidence and explicitly rejected as
historical availability evidence. There is no separate registry file for every row.

All raw evidence remains addressable through verified read-only locators. New source rows
and lineage use deterministic yearly gzip JSONL members in the shared payload store. The
source PIT manifest is installed only after dependency and payload verification. The full
onboarding run is sealed only after every requested source completes. A repeat with unchanged
inputs reuses identities and existing bytes; the first migration time stays operational run
metadata and does not enter scientific row or snapshot identity.

## Construction, synchronization and quality

Implementation: `src/data/transformations/fx.py` and `src/data/fx_pipeline.py`.
`register_and_construct(root, onboarding, alignment_policy=None)` registers all requested
recipes. The accepted completion uses the explicitly approved retrospective alignment policy
to build the 25 cross histories while retaining the existing verified 18 single-source
direct/inverse constructions. Existing source onboarding and completed observations must be
reused; completion does not repeat provider ingestion or alter legacy artifacts.

Supported alignment profiles distinguish `single_source_observation`,
`retrospective_date_label` and `exact_valuation`. The approved retrospective profile matches
equal native provider date labels with `max_date_gap = 0`; its wall-clock tolerance remains
unknown (`max_valuation_gap_seconds = null`). It permits approximate daily alignment where
historical synchronization evidence is absent. It does not approve known incompatible
session definitions, currency mismatches, wrong quote direction, invalid prices or conflicts.
Unknown timing and demonstrated timing incompatibility must be distinguished; the latter
remains blocked. Do not invent a numerical synchronization tolerance.

This approval is not exact synchronization. The exact profile requires documented timezone,
bar boundary and session convention and zero valuation-time difference. Converting labels or
timezones does not repair incompatible bar boundaries. Stored dates remain native dates;
they are never reinterpreted as observed midnight timestamps.

Missing, nonpositive, nonfinite, conflicting or explicitly evidenced stale operands yield
null output with a reason. No interpolation, carry-forward, zero substitution, future
observation substitution or direct/synthetic fallback is permitted. Unchanged prices alone
are not classified as stale. Each instrument uses its own required input dates; a source's
shorter history does not truncate unrelated instruments. Cross output coverage includes
explicit dependency failures rather than silently discarding missing dates.

Only endpoint close prices are constructed. Cross highs, lows, volume, bid/ask and executable
quotes are not inferred. Actual source price basis remains `unknown`; the actual data must
not be described as a midpoint proxy without new evidence. If a future admitted source
establishes midpoint basis, a triangulated midpoint remains a proxy rather than an observed
broker execution quote.

## Approved family-scoped return and endpoint policies

Implementation capability exists in `src/data/targets/fx.py`. It reuses the existing 0.4
Target definition constructor, policy validation, endpoint schedule resolver and return
arithmetic. The accepted batch binds the user's approval evidence and versioned policies;
it uses simple returns only. Log-return capability remains an implementation test surface,
not an additional convention to materialize in this completion.

For resolved endpoints:

```text
simple = exit_price / entry_price - 1
log    = log(exit_price / entry_price)
```

These are gross spot price returns. They exclude carry, financing, trading costs, leverage,
position size, account-currency conversion and account-equity returns. The positive direction
means the base currency appreciated relative to the quote currency. Cross simple returns are
calculated from the constructed endpoint ratio, never by subtracting leg simple returns.
Cross log returns equal the difference of normalized leg log returns over identical endpoints.

The approved production family is exactly **43 instruments × 5 horizons = 215 logical
instrument/horizon combinations**. This is a requested coverage matrix, not a required file
count or a claim that every row is available.

| Policy component | Explicitly approved rule |
| --- | --- |
| Return | `exit_price / entry_price - 1`, stored as decimal fractions; `0.01` means one percent |
| Horizon amounts | Exactly 1, 7, 21, 63 and 252 |
| Horizon unit | Scheduled weekdays; generic Target `scheduled_bars` is bound to the versioned weekday policy |
| Calendar | `RESEARCH_WEEKDAYS@1.0.0`: Monday through Friday, no holiday exclusions |
| Date convention | Stored provider date labels; date precision, without timestamp conversion |
| Anchor | Must be a scheduled weekday |
| Entry | Close assigned to the anchor date; zero scheduled entry delay |
| Exit | Close assigned to the date reached after advancing exactly h scheduled weekdays |
| Counting | Exclusive entry: the anchor is not forward increment one |
| Endpoint lookup | Resolve dates first, then require exact endpoint observations; zero substitution tolerance |
| Missing/invalid endpoint | Retain unavailable/null with the actual reason; do not move to the next observation |
| Interior values | Not required by a pure endpoint return |
| Cross alignment | Equal provider date labels, provisionally retrospective; known incompatible observations blocked |
| Outcome state | Pin selected input snapshots/vintage policy; preserve known availability and provenance |

One scheduled weekday from Monday ends Tuesday; one from Friday ends Monday. Seven scheduled
weekdays from Monday end Wednesday of the following week. Seven is not one calendar week;
252 is not an exact year. Holidays stay on this version's expected grid. If a holiday or other
date has no required close, report its unavailable endpoint rather than dropping that date
from the calendar. Do not label an unexplained missing date as a verified holiday.

This version is distinct from the legacy engine's subsequent-valid-observation count.
Neither its Target identity nor its counting behavior may be silently reused. It applies only
to this FX gross spot return Target family, not unrelated assets or Target families. Do not
materialize log returns or additional horizons during this completion.

Zero delay approves **return anchoring only**. It does not certify a fill at the anchor close
after a Feature or Signal was calculated. Prediction time, Feature availability, Target
anchoring and executable entry timing remain separate. Feature availability, label
availability and strict training cutoffs are unchanged. A later strategy evaluation must
establish its decision-time information set and achievable subsequent entry; execution
systems and scientific discovery/validation boundary changes are outside this task.

Unknown timing and missing original vintages alone no longer block materialization under
this approved provisional retrospective policy. Known defects, unavailable endpoints and
incompatible source definitions remain actual blockers. No further approval is required for
these two resolved choices; stop only affected work for a genuinely new defect or unresolved
requirement and complete independent valid results.

## Schedule, maturity, vintage and retrieval

The schedule resolves entry and intended exit before prices are looked up. Missing prices at
an endpoint retain a null row; they do not shift the horizon to the next valid row. An endpoint
return requires only its entry and exit prices, not every intervening value.

The compact 0.5 Target row preserves prediction anchor, entry, exit, intended end, decimal
value or null, status/reason and two operand references to exact price observation IDs.
`pending/FUTURE_ENDPOINT` distinguishes future endpoints from elapsed missing/invalid
endpoints. Economic maturity does not prove historical availability. Actual capture completion
is carried separately as `original_capture_complete_at`; `source_availability` and
`label_available_at` remain null and `historical_eligibility_certified` remains false.

Outcome selection is an explicitly pinned later snapshot under the approved provisional retrospective policy. It is neither an as-of historical
release reconstruction nor a future label claimed known at its prediction anchor. Existing
public `retrieve_target` requires exact Target and materialization IDs. When a training cutoff
is supplied, the existing strict filter excludes these historically uncertified rows. No
retrospective permission turns null historical availability into a timestamp.

Target manifests pin definition, selected source/price snapshots and vintage policy, exact schedule/anchors, knowledge cutoff,
implementation, approval evidence, row digest, yearly partitions, status/reason counts,
coverage and readiness. A completed manifest is installed last. Retrieval verifies stored
payload hashes, semantic content, definition identity and endpoint lineage and recalculates
against the pinned schedule; it does not serve temporary process memory.

## Identity and selective reuse

Logical provider, dataset and source-view identities exclude a capture window and migration
clock. A price recipe binds economic direction, source views, normalization, arithmetic,
quality, alignment and no-fallback semantics; it excludes Feature/Target role and output
coverage. Target definitions bind return semantics, schedule policy and construction recipe;
a separate materialization binds the resolved snapshot, schedule and cutoff.

Source, price and Target observations have content identities. A return observation depends
on its exact entry/exit price IDs. `affected_labels(observations, changed_price_ids)` selects
only endpoint dependencies, not every holding interval containing a repaired date. Unchanged
observation bytes retain their IDs; unchanged yearly compressed payloads reuse the same
content-addressed object. A revised endpoint may change its year's affected label partition
and produce a new immutable build while unrelated partitions remain reusable. This is a
claim about dependency and storage reuse, not a claim that the current batch runner avoids
recalculating every unchanged row. The runner may recompute deterministically to verify reuse.

## Storage, interfaces and acceptance

The exact paths and inspection examples are in [FX data contracts](../docs/fx_data_contracts.md).
`fx_records` resolves external raw locators through configured read-only roots and uses the
existing payload namespace. Source, normalized-leg and constructed-price snapshots share
`storage/catalog/snapshots`; no competing FX-only price store is introduced.

The existing Target API and UI distinguish registered instruments, PIT inputs, constructed
prices and persisted return Targets. Recipe registration alone cannot create a selectable
Target. Instrument and horizon filters resolve real catalog content. Detail requires the
exact materialization and exposes coverage, policies, lineage and readiness. Account
eligibility and live readiness remain separate from retrospective research.

Acceptance requires exact source/output scope; raw lineage and preservation; numerical direct,
inverse and cross examples; reciprocal/triangular and log-return consistency; invalid,
missing, duplicate, stale, DST and incompatible-close behavior; source coverage independence;
unknown availability and future endpoint handling; exact horizon semantics; idempotency and
interruption recovery; endpoint-only invalidation; shared partition reuse; fresh-process
retrieval; and truthful API/UI projection.

The only existing direct-cross diagnostic is EUR/GBP over two completed overlapping dates.
Same-label level differences are approximately +0.396 and -0.512 basis points; the return
difference is -0.908 basis points. These are inside an explicit one-basis-point diagnostic
tolerance. They do not certify session compatibility or market/broker agreement. Compatible
independent direct comparisons remain unavailable for the requested cross universe.

## Independent completion validation plan

This plan defines checks to execute against persisted results. It supplies no invented pass
counts or completion claims. Actual outcomes belong in the execution report.

1. Load the saved onboarding completion and all 43 instrument registrations. Assert the exact
   18 provider sources, exact 5/13/25 construction split, unchanged original source references,
   and no additional provider or output instrument. Hash all 38 audited raw artifacts and
   35 canonical legacy pages against the preserved audit. Reuse the already migrated source
   snapshots; do not rerun ingestion merely to verify them.
2. Enumerate exactly 215 unique `(instrument, horizon)` definitions from actual persisted
   Target catalogs: the requested 43 instruments times `[1, 7, 21, 63, 252]`. Assert simple
   gross spot returns, decimal fractions, the same approved weekday policy/version,
   exclusive-entry counting, zero entry delay and exact endpoints. Assert no extra log-return
   or alternative-calendar variant is produced. Report a genuinely unpopulated combination
   explicitly rather than omitting it from the matrix.
3. Independently generate the Monday–Friday/no-holiday schedule from each instrument's own
   available range. Check the Monday, Friday and seven-weekday examples and prove missing
   observations do not shift dates. Compare every stored prediction anchor and intended exit
   to the generated schedule. Trace missing endpoints to source/price diagnostics, keeping
   holiday-attributed losses separate from unexplained missing dates.
4. In fresh processes, retrieve representative direct, inverse and cross builds through
   the public Target retrieval interface. Independently inspect every completed build and
   compare every stored valid return with an exact-rational endpoint ratio
   and match each entry/exit price ID to its exact source dependencies. Check both direct and
   reciprocal formulas and cross prices before returns. Algebraic reciprocal/triangular and
   log-difference identities test mathematics only; they do not certify market timing.
5. Verify every unavailable row retains null plus its reason, never a fabricated zero.
   Distinguish immature future endpoints from elapsed missing/invalid endpoints. Remove or
   repair an interior observation in a fixture to prove endpoint returns are unaffected;
   revise an actual endpoint in a fixture to verify only dependent IDs change.
6. Verify missing historical publication/vintage evidence stays disclosed for direct,
   inverse and cross instruments. Successful persistence and provisional retrospective
   eligibility may be ready while strict historical PIT and live readiness remain blocked
   or unresolved. Confirm strict training-cutoff retrieval does not acquire uncertified
   labels and an approved retrospective policy cannot bypass demonstrated session mismatch.
7. Verify hash-addressed payloads, complete manifests and original lineage in fresh reads.
   Repeat the approved completion with unchanged references; compare definition IDs,
   materialization IDs, row IDs, partition hashes and catalog counts. An interruption fixture
   must not expose a partial completed build. Unchanged year partitions must reuse existing
   shared payload objects. Explicit completed-run reuse must verify the exact manifests,
   current implementation fingerprint, policies, schedules, source references and all
   dependency/payload checksums before bypassing calculation; any mismatch fails closed.
8. Report one actual persisted retrieval example each for a direct instrument, an inverse
   instrument and a constructed cross, alongside the complete 215-row coverage matrix.
   Recheck the existing two-date EUR/GBP direct diagnostic without fetching or onboarding
   extra sources. Record numerical discrepancies and the still-unverified session match.
