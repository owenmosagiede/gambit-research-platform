# Five-year FX value research

The approved program has two fixed recipes. Each runs as an individual-pair TS
experiment against the existing simple spot-return Targets. P1 selects direction
per horizon through `DISCOVERY_SIGN_V1`. P2 uses that saved direction.

## WEO bilateral value

Use original IMF WEO annual average consumer-price inflation (`PCPIPCH`). Freeze
the first published actual for each completed calendar year. A current-year
actual flag is insufficient until that year has ended. EUR uses the official
Euro Area aggregate. CNH uses mainland China inflation. Preserve the original
edition, actual-status evidence, publication date, conservative availability
date, and original file checksum.

The price-level ratio starts at one for 2005. Advance it for the next consecutive
year once both currencies' first actuals are available. Multiply quote-per-base
spot by the base/quote price-level ratio. The feature is the logarithm of its
prior 1,260 valid scheduled-weekday median divided by the current real rate.
The current close is excluded from the median. Its score first applies at the
next scheduled weekday anchor. A missing preceding close supplies no daily score.

## Relative REER value

Use original ALFRED archives of BIS monthly broad real effective exchange rates.
Each of the 19 mapped currencies has a verified archive beginning 2014-02-18.
Those first snapshots include older reference observations that can supply the
five-year historical baseline. Dates before the first available vintage cannot
receive a reconstructed signal from later releases.

For each currency and archived vintage, find the latest published reference
month and its preceding 60 consecutive calendar months. Compute the logarithm
of that prior median divided by the latest value. Use one internally consistent
vintage for both numerator and denominator, including rebasing and revisions.
The pair feature is base-currency cheapness minus quote-currency cheapness.
An archived update is eligible strictly after its date and persists until the
next update. An invalid new state supersedes its predecessor.

Use `RBCNBIS`, the China renminbi index, as the expressly approved CNH proxy.
The remaining currencies map directly to the corresponding currency area.

## Windows and eligibility

The existing prospective schedule applies. For 1D, 7D and 21D, discovery ends
before 2022-01-01 and validation covers 2022-01-01 through 2024-12-31. For 63D,
discovery ends before 2017-01-01 and validation covers 2017-01-01 through
2024-12-31. Both target anchor and target endpoint must lie within the stage.
252D is excluded.

Coverage is computed separately for every recipe, pair and horizon. Require at
least horizon-plus-two matched discovery observations and the existing P2
minimum of 15 non-overlapping validation returns. These are admission minima.
The ordinary P1 and P2 statistical criteria still decide whether a signal passes.
Daily observations of a carried monthly REER score share the same macro update.
The coverage report retains distinct update counts and non-overlapping returns.

## Publication and execution

`tools/fx_value_research.py prepare` captures original provider files in immutable
payload storage, creates the two versioned definitions and their explicit
application bindings, and publishes pair-specific snapshots and coverage. It
creates a dedicated value Research Spec without replacing the momentum Spec.
Original source/Target identities and prior research records remain authoritative.

`queue` verifies the entire program and its frozen horizons before submission.
The default is a queue preview. `--apply` uses ordinary durable intake, stable
request IDs and the existing worker. Repeated submissions preserve the same
request and its history. Experiments contain source, recipe, pair, price and
Target bindings. Phase readers independently replay the original sources and
verify exact stored scores. They decode only their phase and its prevailing
pre-period state. Linux production publication supplies the canonical numerical
output for the deployed environment.

The macro archives provide vintage-date evidence. The underlying spot histories
retain their existing retrospective date-label classification. Research results
therefore retain the current historical-replay and live-readiness limitations.
The isolated EUR/USD pilots are research exposure and must be retained with the
program's audit artifacts. Repeating a pilot on the same validation period adds
no independent evidence.

Deployment must preserve the running momentum program's accepted envelopes,
staged intake, committed trials and execution compatibility. A new executor's
source fingerprint requires the existing controlled release and compatibility
review. Drain at a request boundary before replacing loaded research code.
