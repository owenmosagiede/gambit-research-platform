# FX spot and modelled total-return targets

The `total_return` submission option requests both spot and modelled total-return
tests for one individual FX-pair TS Scope. The existing `price_return` option
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

Raw missing observations remain null. BIS rows explicitly marked “missing;
data cannot exist” may carry the preceding fixing for at most seven calendar
days. Other missing observations, missing calendar dates and longer gaps block
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

Currency-universe CS requests are deliberately rejected by this first paired
execution adapter; they require a declared funding reference and capital basis.
They are never silently reduced to a supported subset.
