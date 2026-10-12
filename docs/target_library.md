# Return Target library

A Target is a reusable definition of a realized forward investment return, anchored
to a prediction opportunity. Its identity is independent of the Feature, Signal,
expected direction, Scope or Research Spec that might later use it. The Target
engine consumes canonical investment inputs; provider names never select a formula.

The authoritative implementation contract is [specification 18](../specs/18_return_targets.md).
The [implementation report](target_implementation_report.md) records the executed
tests and persisted proof. This library is limited to continuous investment returns.
It does not register macro percentage changes, return signs, ranks, volatility,
drawdown, barrier labels, strategies or execution models as Targets.

## Executable return constructions

All simple outputs are dimensionless fractions: `0.10` means 10%. Log outputs use
the natural logarithm. Nothing multiplies a return by 100 or annualizes it.
`entry` and `exit` below are the explicitly resolved economic interval, not process
execution times or whichever rows happen to be available.

| Construction | Exact calculation | Eligible canonical source and economic meaning | Numerical example |
| --- | --- | --- | --- |
| Price / spot, simple | `P_exit / P_entry - 1` | Certified investment price with a declared currency, measure, quote and observation convention; distributions excluded; an income-inclusive source must use an eligible total-return construction | 100 → 110 gives `0.10` |
| Price / spot, log | `ln(P_exit / P_entry)` | Same price requirements; strictly positive endpoints | 100 → 110 gives `ln(1.1)`, approximately `0.0953101798` |
| Total return from wealth index, simple | `W_exit / W_entry - 1` | Certified total-return/wealth index documenting income and corporate-action treatment | 100 → 112 gives `0.12`; the income already represented in the index is not added again |
| Total return from wealth index, log | `ln(W_exit / W_entry)` | Same certified wealth convention; strictly positive endpoints | 100 → 112 gives `ln(1.12)`, approximately `0.1133286853` |
| Total return from simple period returns | `product(1 + r_i) - 1` | Complete, contiguous, nonoverlapping canonical simple holding-period returns covering exactly entry → exit | `0.10` then `-0.10` gives `-0.01`, not zero |
| Total return from log period returns | `sum(log_return_i)` | Complete compatible log holding-period returns covering exactly the interval | `ln(1.1)` then `ln(0.9)` gives `ln(0.99)`, approximately `-0.0100503359` |
| Arithmetic benchmark excess | `R_instrument - R_benchmark` | Both simple returns over the identical interval with compatible currency, economic coverage and observation convention | `0.10 - 0.04 = 0.06` |
| Log benchmark excess | `L_instrument - L_benchmark` | Both log returns over the identical interval with compatible conventions | `ln(1.1) - ln(1.04)` ≈ `0.0560894667`; it is not `ln(1 + 0.06)` |

A source's declared economic basis is checked before arithmetic. A quoted yield,
spread, interest rate, macro observation or unsupported futures settlement series
cannot be converted into an investment return by relabeling percentage change.
Period input and Target output must have the same mathematical representation; there
is no implicit simple/log conversion. An ambiguous “adjusted price” description is insufficient evidence of total return.
Specialized instruments may enter through certified wealth or period-return series;
the subsystem does not supply missing valuation, roll, leverage, financing or cost
models. A gross source stays gross.

For FX spot, base currency, quote currency, quotation direction and return currency
are explicit. Inverting a quote is a different economic convention: `1.10 / 1.00 - 1`
is `0.10`, whereas the reversed quote return is `1.00 / 1.10 - 1`, approximately
`-0.0909090909`. The latter is not the negation of the former.

## Domains and failure behavior

Ordinary capital ratios require a positive start. An evidenced zero exit may produce
simple total loss (`-1`) only when source certification allows zero terminal value;
log endpoints must be strictly positive. Simple period factors must be nonnegative,
and a zero factor requires the same permission. Nonfinite values and overflow are
never valid output. Arithmetic excess has no universal lower bound of `-1`.

Definition incompatibility and source ineligibility reject preflight. Expected
pointwise failures preserve scheduled rows with null values and controlled reasons.
An endpoint beyond the declared evaluation/knowledge boundary is pending; a required
historical endpoint missing inside the resolved interval is missing. Unexpected
execution defects propagate separately and cannot be published as valid labels.
No implicit fill, interpolation, backfill, endpoint shift or zero substitution occurs.
Endpoint price construction needs its two endpoints, not unrelated interior prices.
Compounded period construction needs every component and rejects gaps, overlaps,
duplicate intervals and mismatched interval boundaries.

## Three separate clocks

1. **Prediction anchor:** the research opportunity for which a future outcome is requested.
2. **Economic entry and exit:** the scheduled observations defining the holding interval.
3. **Label availability:** when the selected outcome and all evidence are defensibly usable.

Process execution time is a fourth operational fact and never substitutes for one
of these. Targets intentionally use future outcomes; requiring the exit price to be
known at the prediction anchor would prevent legitimate label construction.

A declared market schedule includes expected sessions or bars even where a price is
missing. Explicit canonical anchor sets are also supported. Horizon counting uses
that schedule and cannot compress five scheduled sessions into five surviving rows.
Calendar days and elapsed seconds have their own exact meanings and precision
requirements. Versioned policy definitions, entry/exit matching, resolved anchor
identities, bounded endpoint adjustment and concrete examples are in specification 18.

`anchor_mark` is a descriptive research convention, not a claim that one could both
observe and trade at that exact mark. Strictly subsequent entry selects the next
eligible scheduled mark after the anchor. The horizon counts from the resolved entry.

Date observations remain dates. A date alone does not order two events within that
date, and no midnight timestamp is manufactured. Historical training uses the
registered conservative precision rule; same-date evidence does not certify ordering.

## Revisions, availability and historical retrieval

The first-defensible policy requires evidence that the source supplies the declared
complete first-observation history. First publication, first archive and first local
ingestion remain distinct. The pinned-later policy chooses a source version under
an explicit knowledge cutoff; it cannot retroactively make a correction usable at
its original observation time. Finalization/waiting conditions participate in label
availability, together with the latest contributing source and benchmark evidence.
Unknown availability allows numerical output only with historical readiness uncertified.

Observation retrieval always pins a materialization ID. An optional historical
training cutoff is supplied together with its temporal precision; only labels usable
at that cutoff are returned as eligible. Earlier immutable evidence survives corrections
and newly matured outcomes. Refresh resolves the one requested Target and its pinned
dependencies; it does not replay the entire library.

Feature alignment is independent: Feature availability must precede or equal the
prediction cutoff under the registered precision rule. Target label availability is
checked against the later training cutoff. Matching calendar dates is insufficient.
The subsystem supplies this alignment check without implementing a research engine.

## Storage and UI

Versioned logical definitions live under `definitions/targets/`. Immutable Target
manifests live under `storage/catalog/target_store/<materialization_id>/manifest.json`.
Observation and execution evidence use the existing shared
`storage/payloads/sha256/<prefix>/<hash>.<format>` store. Source data is referenced,
not copied into definitions or duplicated into a Target-specific payload store.
Each value retains exact contributing record lineage and upstream metadata.

`GET /api/target-library` discovers verified Targets and their explicit readiness.
`GET /api/target-library/<TARGET_ID>?materialization_id=<MATERIALIZATION_ID>` retrieves
one pinned result. `training_cutoff` and `cutoff_precision` may be supplied together.
No detail request silently chooses a moving latest materialization.

The existing Target dropdown shows investment series, return basis, representation,
horizon and readiness. It has one option per Target and only enables a Target with a
verified materialization containing historically certified valid labels. Where several
are available, the lexicographically greatest certified materialization ID is an
explicit presentation preference, shown in the field note and pinned on the selection;
it is not a scientific recency rule. Actual historical use still requires each label's
training-cutoff check. Unmaterialized or uncertified definitions remain disabled with a
reason. Empty production storage shows an honest empty state and no mock alternatives.

## Current real-data boundary

Repository inspection found the implemented 98 transformation registrations and
numerical/contract/recipe modules described in the preserved foundation report. The
new platform's registered production dataset is CES0500000003, Average Hourly Earnings
of All Employees, Total Private, measured in USD per hour. It is a Feature source and
is economically ineligible as an investment return source. Legacy Twelve Data FX files
are source candidates, not already certified canonical new-platform Target inputs.

Consequently the bounded end-to-end proof uses isolated canonical investment fixtures
through the same production contracts, persistence and retrieval service. No fabricated
production Target is published. The first real Target requires an onboarded investment
source with exact measure/currency/quote/observation semantics, economic coverage,
historical availability and correction evidence, plus a declared market schedule matching
the source’s calendar/version, timezone and observation convention. This
is source certification work, not an unresolved return-construction implementation.
