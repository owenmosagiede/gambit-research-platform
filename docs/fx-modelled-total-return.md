# FX spot and modelled total-return targets

The `total_return` submission option requests both spot and modelled total-return
tests for an individual FX-pair TS Scope or an activated matched currency-universe
CS Scope. The existing `price_return` option
continues to request spot only. The new option requires `DISCOVERY_SIGN_V1`.
It supports the four prospective horizons: 1, 7, 21 and 63 scheduled weekdays.
It does not add a new production worker or reopen research admissions.

## Approved financing model

Use BIS daily central-bank policy rates as proxies for AUD, CAD, CHF, CZK, EUR,
GBP, HKD, HUF, ILS, JPY, MXN, NOK, NZD, PLN, SEK, USD and ZAR. Use MAS SORA for SGD.
CNH is excluded; an onshore CNY rate is not substituted. The current 43-pair
roster therefore has 42 eligible financing pairs. USD/ILS funding is included;
OANDA's separate USD/ILS spread-data limitation does not exclude its BIS rates.

For a pair quoted in quote currency per base currency, initialize one unit of
base and borrow its initial quote notional. Accrue both balances using the
published annual benchmark percentages, ACT/365 fixed, compounded each calendar
day. Borrowing and lending use the same benchmark with no markup. At exit:

```
base_growth  = product(1 + base_rate_pct / 100 / 365)
quote_growth = product(1 + quote_rate_pct / 100 / 365)
modelled_total_return = (1 + spot_return) * base_growth - quote_growth
```

The denominator is initial quote notional, not margin or net starting cash.
This is a financed position's modelled P&L fraction. Zero rates reproduce the
spot return exactly. Under this explicitly symmetric model, reversing the
position negates P&L; this does not establish that real broker long/short swaps
are symmetric. Reciprocal instrument quotations still use their own base/quote
orientation and initial notional.

This daily-compounding proxy is not the official compounded SORA Index, nor an
executable overnight borrowing/lending contract. BIS rates can represent policy
targets, repo/discount rates or spliced historical instruments. Negative rates
are retained. No broker markup, spread, commission, slippage, leverage or
portfolio-capital allocation is included. Execution-cost modelling is separate.

Raw missing observations remain null. BIS series that omit Saturday/Sunday rows,
and rows explicitly marked “missing; data cannot exist”, may carry the preceding
fixing for at most seven calendar days. Other missing observations, missing
ordinary weekdays and longer gaps block
funding calculation. SORA applies from value date until the next fixing, with a
seven-day maximum interval; publication date is retained separately. No earlier
SGD history is fabricated before July 2005. Missing funding makes the affected
total-return label unavailable, never a spot-only or zero-financing substitute.

## Paired scientific execution

One immutable submission freezes the source spot Targets, funding snapshot,
model policy, modelled Targets, research windows and implementation. The data
and both Target definitions have different immutable identities. Existing spot
definitions, accepted jobs and historical results remain unchanged.

Feature preparation is reused across both branches for each phase/window. All
P1 horizons for both branches finish before any P2 test begins. Each branch has
its own admission, measured effect, discovered sign and P2 decision. Only that
branch's admitted horizons receive a P2 test. A spot rejection does not prevent
an admitted total-return branch from validating, and neither branch borrows the
other's direction. Both outcomes are reported; the system must not select the
passing Target after seeing results. The paired evaluation is additional
research exposure, not an untouched holdout or a free extra selection test.

Both branches retain the approved P1/P2 periods. Missing rate history reduces
eligible total-return observations; it does not move either frozen boundary or
silently shorten spot history. Outcomes remain provisional retrospective
research: historical source vintages and spot session times are uncertified.
Strict historically certified training queries continue to exclude these labels.

For P1, out-of-phase Target values are rejected from checksum-verified partition
bytes before JSON value decoding, even if a year partition spans both stages.
Phase reconstruction includes only in-phase outcomes. Source verification may
verify the full pinned primary captures; no future rate values enter a phase's
return arithmetic. The next SORA fixing date alone may witness an accrual
interval boundary, without exposing its later rate value to reconstruction.

## Data and activation

The primary BIS ZIP is streamed; its approximately 477 MB CSV member is not
expanded to disk. MAS's selected daily CSV contains blank separators between
years, which are preserved rather than mistaken for the end of its history.
Normalized observations reproduce both exact primary captures on verification.
HTML error pages, duplicate currency/dates and incompatible units are rejected.

Source code is deployed through the controlled release process only after the
accepted queue drains. The separate `tools/fx_total_return_release.py` migration
first produces a read-only plan. Its explicit apply mode requires closed
admissions, a verified idle queue and both native executor/writer locks. It
reuses the exact spot materializations pinned by the active Research Spec,
installs the modelled Target family, then publishes `config/fx_total_return.json`
last. Partial Target publications remain inert to submissions without that
complete config. Admissions remain closed after migration. An existing release
is not overwritten; a later funding refresh requires an explicit upgrade plan.

For this preparation, verified primary captures and normalized funding inputs
are staged on the server's boot disk under `/var/lib/gambit-funding-stage`,
outside the live research catalog. Staging does not deploy code, install live
definitions, restart services or admit research. No new carry Feature recipe,
forecast model, P4 cost model or broker execution integration is introduced.

## Currency-universe CS comparisons

The seven additive `FX_CCY_FUNDED_VS_{USD,EUR,GBP,JPY,CHF,CAD,AUD}` Scopes each
freeze seventeen currencies: exclude their own reference and the prespecified
unsupported CNH currency. The original eighteen-member `FX_CCY_VS_*` Spot
Scopes and their historical records retain their existing identities.
Both paired branches use exactly the same new seventeen-member membership.
Missing rates never shrink that membership or substitute zero financing.
The existing complete-date CS missing-data and inference rules apply separately
to each branch, so funding gaps can reduce usable total-return dates.

Each exposure already prices base currency C in reference currency R. Finance
the C balance at C's benchmark and borrow the initial R notional at R's benchmark,
using the same formula and initial-reference-notional normalization as TS. Inverse
and triangulated exposures use their own frozen oriented spot Targets, rather
than another canonical pair's Target or a sign-flipped return. This is a per-member
research label; it is not a portfolio weighting, leverage or capital-allocation
model. The CS statistical policy and historical windows remain unchanged.

All P1 branches finish before P2. Spot and total return discover their own signs,
admit independently, and validate only their own P1 direction. Shared preparation
and bounded verified input reuse do not merge their scientific decisions.

`tools/fx_total_return_cs_release.py` produces a hash-bound plan from an exact
active currency-release reference and the existing funding snapshot/model. Apply
requires that reviewed hash, closed admissions and the native idle/executor/writer
guards, in addition to the operator's code/backup controls. It adds 119 oriented
exposures × four horizons and publishes `config/fx_total_return_cs.json` last.
The TS funding config and its existing 168 targets are untouched. New Scope
definitions remain staged until the complete CS funding pointer exists.

The data-publication cache scope covers the full pinned input histories declared
in its reviewed plan. It retains only independently verified inputs under the
existing byte bound and dependency-witness checks; changed inputs invalidate
reuse. P1/P2 reads continue to use their separate, strictly bounded stage windows.
