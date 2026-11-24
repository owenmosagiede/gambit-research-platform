# Five retrospective carry recipes

The user authorized testing the fixed five recipes on 31 selected G10 pairs on
24 November 2026 using existing retrospective data. Official central-bank
release reconstruction is separate future production work. These features never
assert historical point-in-time or live certification.

Rate-only lookbacks can use rate observations before the pair price history
begins; published feature outputs still begin within the pair price scope.

The immutable definitions in `data.fx_carry` fix nominal base-minus-quote carry,
carry divided by prior 63-weekday annualized spot log-return volatility, a
63-weekday differential change, a prior-1260-weekday differential z-score, and a
real-rate proxy subtracting first-published actual annual inflation. All use
long-base/short-quote orientation. Real carry uses the latest common available
annual reference year and the existing WEO first-actual freeze, not expected
inflation. Missing and zero-denominator scores remain explicit unavailable rows.

Rates use retrospective reference dates, assumed usable on the following
scheduled weekday. The seven-calendar-day reference-state ceiling and treatment
of BIS nonexistent-day nulls follow the existing benchmark input convention;
ordinary unknown nulls and missing weekdays reset the state. This is a declared
research assumption, not evidence of publication timing. Rates used in a feature
never include realized future financing. The current close is excluded from the
risk baseline; the current differential is excluded from the z-score baseline.

`tools/fx_carry_research.py` explicitly registers new definitions, application
bindings, histories and a separate Research Spec. It never submits research.
Existing immutable records are not rewritten. Each history binds the original
funding snapshot, exact pair price snapshot and optional original inflation
capture. Phase readers independently replay those operands and compare the
stored phase rows. P1 does not decode P2 feature scores. Selection and intake
remain metadata-only, and normal intake preserves native duplicate detection.

Execution must use ordinary ResearchJobs submissions and DISCOVERY_SIGN_V1.
Total-return submissions retain separately reported matched Spot and Modelled
Total Return branches. Keep 1/7/21D discovery before 2022 and validation in
2022-2024; keep 63D discovery before 2017 and validation in 2017-2024. Preserve
prior exposure and all normal statistical criteria. Correlated recipes/pairs
are not independent confirmations, and financing mechanically contributes to
Modelled Total Return.

Deploy application code through the controlled release first. Install the new
records through a separately reviewed additive registration while research is
idle, pin all inputs and implementation, preflight every candidate, then submit
the authorized finite cohort. Do not alter the old Value or held Carry proposals,
rewrite old identities, bypass source verification or use test fixtures in
production. Numerical tests use isolated synthetic data only.
