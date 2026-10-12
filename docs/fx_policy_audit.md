# FX migration: policy and canonical reuse audit

Audit scope: read-only inspection of the active rebuilt platform and selected legacy metadata/code for the requested 18-source, 43-instrument migration. No project or legacy files changed. Actual per-source row/partition inventory is assigned to the separate source audit; this document does not certify that inventory.

Active root: `/Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/research_platform`.
Legacy root: `/Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data`.

## Verified production state

- `definitions/targets/` contains **zero Target JSON definitions**. It contains the README and `.gitkeep` only.
- Production registries contain one Dataset, one SourceView and one provider: ALFRED CES0500000003. None is an eligible spot FX source.
- Six Target 0.4.0 policies exist in production: one calculation, one validity, and four generic outcome-selection combinations. **No production `economic_source` or `target_schedule` policy exists.**
- Those four outcome policies are `first_published` with `unknown_availability=reject`, combining `first_defensible`/`pinned_later` and date/timestamp precision. Each has zero calendar-day finalization wait. They are supported reusable policies; they do not certify Twelve Data or select an FX horizon.
- The calculation policy is `decimal_50_then_binary64_guard` with version 1.0.0. The validity policy retains null failures, rejects nonfinite sources, forbids stale substitution, requires positive starting capital and exact component coverage.
- `docs/specification_decisions.md`, Q01, explicitly asks which exact Target basis and horizon clock applies to the first research case and states **“No global default is selected.”**
- `specs/18_return_targets.md` is authoritative for executable Targets. Its four clocks and entry/endpoint rules are capabilities requiring concrete binding, not a preselected production configuration.
- `tests/fixtures/target_return_proof/` contains synthetic production-path proof records. Their 2-session example, dates and source conventions are not production approvals.

### Installed generic Target policies

| Kind | ID suffix (all `POLICY_`, version 1.0.0) | Meaning |
| --- | --- | --- |
| Calculation | `cfdedb0164288be45088aa98636c1341e93a66d4ec8797696cdda1632c5bad8a` | Decimal 50 arithmetic and finite binary64 guard |
| Validity | `a1008eee9cd61df34c3fe9d884fa215222e9a02ca07b43b18604da5983247bbf` | Exact missing/domain/staleness/component policies |
| Outcome | `2b4b0f73a4feb2c517421cfa8cccf2d70fe1b34e79be0cf61b45a135c8cdd721` | First defensible, first published, date precision |
| Outcome | `7b5f007a68ddd825a4401cae824a31aefa47347b7af1f0674e9d7d66abe0ced8` | Pinned later, first published, date precision |
| Outcome | `b528025f5ecddac468ad8bbe700fe0ee5082609604b9b61cacf0f85aba63aad9` | First defensible, first published, exact timestamp |
| Outcome | `85b1a322398ad44cf291ca6f9290fcbecc87ceaef578b87c21d6b1f2bbba9c25` | Pinned later, first published, exact timestamp |

## Legacy evidence is not an approved new Target binding

`Data/docs/target-system.md` describes `return.forward_1d`, `7d`, `21d`, `63d`, `252d` as **subsequent valid observations**, with simple `end_close/start_close - 1`. Missing observations are removed from the valid sequence before counting in that legacy implementation. The active platform's `specs/03_features_targets_scopes.md` expressly preserves these historical meanings and forbids silently reissuing them as expected-session/bar horizons. The new request also forbids horizon compression after dropping missing dates. Therefore inheriting the five numbers as “trading sessions” would be a new scientific decision.

The user’s current request does settle: exact 18 inputs, exact 43 outputs, direct/inverse/cross arithmetic, gross spot return economic coverage, no carry/costs/account returns, preserved direction, positive finite required prices, no fill, and only endpoint fields. It does **not** select simple versus log (or both), any horizon amount, an expected calendar, anchor entry policy/delay, endpoint tolerance, or a retrospective alignment policy.

## Observed Twelve Data metadata limitations

Inspected examples: `production/twelve_data_fx/symbol=EUR_USD/page=0001/{source-registry.json,dataset-registry.json,raw-ingestion-manifest.json}` and the provider/backfill code. The source-audit owner must verify these findings across all 18.

- Source registry says timezone `UTC`, revision type `none`, vintages unavailable, with notes explicitly describing pilot policies needing reconciliation. This is evidence of the legacy implementation's convention, not measured daily valuation-time evidence.
- Dataset unit is `USD_per_EUR`, native symbol `EUR/USD`, concept spot FX, daily OHLC, and tag `vendor_history_snapshot`. Price basis is `not_applicable`, so midpoint/bid/ask status is **not established**.
- Dataset availability is `market_session_close`, `end_of_period`, precision `inferred`; publication metadata says release timestamps unavailable.
- `src/point_in_time_data/twelve_fx_backfill.py:214–229` manufactures the old availability/release label as the displayed bar day plus one calendar day at 00:00 UTC. It preserves `retrieved_at` and uses that as `vintage_id`; rows are `provisional` with `vendor_history_snapshot`. That old inferred label must remain provenance rather than becoming a newly certified publication time.
- The example receipt has a real retrieved timestamp `2026-09-06T21:03:46Z` and a content-addressed original JSON path under `raw/v1/twelve_data_fx/`. Such capture evidence can be preserved exactly. It does not prove which earlier values existed on historical prediction dates.
- The provider catalog advertises units quote currency per base currency and records explicit base/quote codes; it states `native_vintage_support=False`, `normally_final`, and `inferred_schedule`. “Normally final” is not complete revision history.
- `docs/twelve-data-fx-quality-resolution.md` documents a checksum/lineage/positive-close admission layer. It does not certify exact daily close times, midpoint status, full historical first-release availability or complete revision history. Its `valid` quality result cannot grant those capabilities.

No certified production Twelve Data expected-calendar or observation-convention policy was found in the active registry. A weekday calendar would be a proposed convention; it cannot be inferred from the price rows and silently described as an observed provider schedule. Date-matched cross arithmetic can be computed, but exact synchronization cannot be asserted without compatible underlying close evidence.

## Existing contracts and narrow reuse gaps

| Concern | Verified current contract/runtime | Minimal extension consistent with ownership |
| --- | --- | --- |
| Provider onboarding | `onboarding.schema.json` 0.1.0 provider is **const `FRED_ALFRED`**; spec13 explicitly describes a fixed ALFRED pilot, not a generic provider service | Add a separately versioned Twelve Data/general canonical onboarding profile; retain old schema/records unchanged; use the same provider, Dataset, SourceView, ingestion, evidence and assessment directories |
| External raw bytes | Platform 0.2 already defines `payload_locator_record` with hash, store ID, relative path, byte count, verification time, and `read_only_legacy` access. `config/storage.local.json` already maps `legacy_raw` to `Data/raw/v1` | Extend the shared resolver to honor verified external locators, safe configured roots and exact stable hashes. Original raw JSON paths fit the locator grammar. Keep newly required canonical rows in the existing shared payload namespace |
| Current payload resolver | `FeatureStore.payload` resolves only `storage/payloads/sha256/<prefix>/<hash>.<format>`; the external locator schema is not yet an implemented read path | Implement that path in the shared resolver rather than duplicating all raw bytes or introducing an FX-specific store. Preserve byte-count and content-hash checks |
| PIT representations | Platform snapshots already own `layer=raw|pit|membership`, SourceView references, upstream snapshots, policy bindings, implementation and lineage; Target adapter consumes canonical PIT JSONL | Add a versioned source-specific FX PIT adapter/schema, same snapshot catalog/shared payloads. Native legacy OHLC records may be retained externally; new close-only canonical data should preserve exact raw record coordinates and capture/vintage evidence |
| Unknown availability | Transformation contract 1.0.0 requires a non-null canonical `available_at` in the same precision as `reference_time`; target economics support `availability_basis=unknown`, `pinned_state`, `allow_uncertified`, and null label availability | Do not pass invented bar-date availability to satisfy a non-null field. Preserve actual capture/ingestion timestamps separately and add an explicit versioned retrospective source selection/availability representation. Unknown publication evidence stays unknown; snapshot storage is not historical certification |
| Price construction | Existing transformation foundation is single-source and explicitly rejects multi-source interactions; no registered FX reciprocal/triangulation kernel was found | Add a bounded versioned canonical quote-construction recipe/adapter (direct, reciprocal, USD triangulation) upstream of Target arithmetic, reusing transformation definitions, SourceViews, snapshots, lineage and shared payloads. Do not create Signals merely to persist source prices |
| Readiness | Existing assessment capability enum is `historical_replay` or `live_api_daily_pull`; decisions are `ready`, `unresolved`, `blocked`. Target states include `historically_certified`, `uncertified`, `no_valid_labels`, `unmaterialized` | Preserve those decisions and historical certification semantics. Add only the required versioned retrospective/construction capability dimensions, supported by exact evidence. A numeric retrospective result must not become historically certified or live-ready |
| UI | `ui/targets.js` enables only historically certified materializations with valid rows | If the user approves retrospective research, extend existing selector/inspection semantics explicitly to disclose and gate that scope; do not simply relabel these outputs as certified |
| Retrieval | Existing API and service pin exact Target/materialization and optional training cutoff; no instrument/horizon/date-range filtering yet | Add filtering/projections around the same persisted results with explicit snapshot/vintage rules, not a separate FX catalog of return values |

A proposed extension should preserve one common source series per original provider quotation and reuse normalized currency-leg results across dependent recipes. Economic instrument identity must remain independent of provider symbol, transformation recipe, Target horizon, Feature/Signal and account eligibility. The USD numeraire is a defined constant, not a nineteenth onboarded provider series. Keep direct USDCNH bytes/values without an unnecessary reciprocal round trip; its normalized CNH leg can still be separately reused and referenced.

## Exact scientific decisions or evidence needed

These are unresolved production bindings, not missing arithmetic implementations:

1. **Target variants:** approved representation (`simple`, `log`, or an explicit limited set), horizon amounts, and clock (`trading_sessions`, `scheduled_bars`, `calendar_days`, `elapsed_seconds`). The legacy numbers do not decide the clock.
2. **Anchor/interval conventions:** expected valuation calendar and version; prediction anchors; `anchor_mark` versus `next_scheduled`; declared delay; exact endpoint versus named bounded matching tolerance. No calendar inferred from surviving records is admissible.
3. **Valuation and cross alignment:** documentary daily bar boundaries/timezone/close convention and price basis, or an expressly approved retrospective date-label proxy convention with disclosed approximate synchronization and a defined tolerance. A timestamp relabel is insufficient.
4. **Retrospective vintage/readiness:** approve the pinned retrospective-history policy and its limited research use. Preserve actual archived capture timestamps, unknown historical publication times and absent revision history. Strict historical replay remains unresolved/blocked for periods not supported by actual vintage evidence.

Parent-facing question can bundle (1–2) as one concrete initial Target policy choice, and (3–4) as a decision about research use of disclosed retrospective proxies. The user’s own instruction says not to invent missing scientific fields; that is the reason these bindings need resolution. No additional confirmation is needed to audit, hash/reference legacy artifacts, onboard all 18 without fabricated availability, register exact 43 recipes, implement reusable arithmetic and tests, or preserve every unaffected direct/inverse result while the decisions remain open.

## Recommended bounded implementation order (proposed, not newly approved policy)

1. Extend existing onboarding/external locators and canonical source schema; admit exactly 18 complete histories with exact legacy capture/provenance and explicit snapshot classification. Publish historical-replay limitations using existing readiness ownership.
2. Register the exact economic 43-instrument universe and versioned reusable price recipes; execute all defensible direct/inverse construction. Cross arithmetic must preserve its unresolved timing qualification unless an explicit retrospective proxy policy is approved. Do not insert guessed close times or midpoint claims.
3. Once exact schedule/horizon/retrospective bindings are approved, populate the existing Target Store through current service/publication/retrieval, update the existing selector, and run full-history persisted integration, idempotency and dependency-specific invalidation checks. Keep unresolved work distinguishable from completed numerical results.

## Sources inspected

Active: `specs/18_return_targets.md`, `specs/03_features_targets_scopes.md`, `specs/02_data_and_readiness.md`, `specs/12_data_pipeline_and_storage.md`, `specs/13_provider_onboarding.md`, `specs/16_transformation_execution.md`, `docs/specification_decisions.md`, `docs/target_implementation_report.md`, `docs/target_library.md`, actual production definitions, `config/storage.local.json`, `specs/schemas/{onboarding,platform,target_store}.schema.json`, `src/data/{alfred_onboarding,alfred_full_history,feature_store,stored_pit_source}.py`, `src/data/targets/{adapter,contracts,service}.py`, and `ui/targets.js`.

Legacy: `docs/target-system.md`, `docs/twelve-data-fx-quality-resolution.md`, `src/point_in_time_data/providers/twelve_data_fx.py`, `src/point_in_time_data/twelve_fx_backfill.py`, selected EUR/USD production source/dataset/raw-ingestion manifests. Applicable instruction search found no AGENTS.md/CLAUDE.md in the inspected project tree; ancestor instruction state remained as previously inspected.
