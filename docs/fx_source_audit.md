# Legacy Twelve Data FX source audit

This is a read-only inventory of the exact 18 requested provider series. It does not certify a trading session, rewrite legacy data, or execute onboarding.

Legacy root: `/Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/Data`

## Verified coverage

| Provider source | Price units | Completed close dates | First | Last | Pages |
|---|---|---:|---|---|---:|
| AUD/USD | USD_per_AUD | 12,246 | 1979-12-24 | 2026-09-05 | 3 |
| EUR/USD | USD_per_EUR | 6,002 | 2003-12-01 | 2026-09-05 | 2 |
| GBP/USD | USD_per_GBP | 6,025 | 2003-12-01 | 2026-09-05 | 2 |
| NZD/USD | USD_per_NZD | 10,180 | 1988-03-01 | 2026-09-05 | 3 |
| USD/CNH | CNH_per_USD | 3,548 | 2013-07-17 | 2026-09-05 | 1 |
| CAD/USD | USD_per_CAD | 9,755 | 1989-10-16 | 2026-09-05 | 2 |
| CHF/USD | USD_per_CHF | 9,743 | 1989-10-16 | 2026-09-05 | 2 |
| JPY/USD | USD_per_JPY | 7,834 | 1996-10-30 | 2026-09-05 | 2 |
| CZK/USD | USD_per_CZK | 1,785 | 2020-04-14 | 2026-09-05 | 1 |
| HKD/USD | USD_per_HKD | 9,752 | 1989-10-25 | 2026-09-05 | 2 |
| HUF/USD | USD_per_HUF | 6,020 | 2003-12-01 | 2026-09-05 | 2 |
| ILS/USD | USD_per_ILS | 4,976 | 2008-02-21 | 2026-09-05 | 1 |
| MXN/USD | USD_per_MXN | 9,590 | 1990-05-30 | 2026-09-05 | 2 |
| NOK/USD | USD_per_NOK | 9,749 | 1989-10-16 | 2026-09-05 | 2 |
| PLN/USD | USD_per_PLN | 8,796 | 1993-06-15 | 2026-09-05 | 2 |
| SEK/USD | USD_per_SEK | 9,743 | 1989-10-16 | 2026-09-05 | 2 |
| SGD/USD | USD_per_SGD | 9,745 | 1989-10-26 | 2026-09-05 | 2 |
| ZAR/USD | USD_per_ZAR | 9,747 | 1989-10-16 | 2026-09-05 | 2 |

Total: **145,236 close observations**, **580,944 OHLC observations**, **35 canonical pages**. Zero canonical close duplicates, conflicts, nonfinite values or nonpositive values. Every raw/canonical checksum checked and every production close compared with its exact raw source matches.

## Source identity, fields and provenance

- Catalog base_code/quote_code, provider currency names, raw symbol and explicit dataset units agree with all requested quote directions. USD/CNH is explicitly Chinese Yuan (Offshore); CNY is not substituted.
- Price field is close from interval=1day OHLC data. No derived highs, lows, volume or bid/ask data are assumed.
- Registry price_basis is not_applicable, and raw metadata does not establish midpoint, bid, ask or executable price basis. Carry unknown price basis explicitly.
- Original production ingestion/retrieval timestamps span 2026-09-06T21:03:46Z–2026-09-06T21:42:24Z. Per-page timestamps, ingestion IDs and hashes are retained in the JSON audit. They are separate from observation dates and current migration time.
- Production vintage_id is the actual retrieval timestamp, revision_number is zero, and every row carries vendor_history_snapshot. Multiple page retrieval timestamps are partition captures, not proof of historical revisions.
- There is no genuine historical vintage evidence for these completed source closes. They are retrospective snapshots.
- Precision counts preserve the provider close string decimal places. Variable representation precision is not a certified tick size.

## Timing and readiness limitations

The legacy adapter creates original_release_at and available_at from observation date + 1 UTC day and labels precision inferred. This is visible in src/point_in_time_data/twelve_fx_backfill.py, not independently established provider release evidence. The registry UTC label is adapter configuration; raw provider metadata does not declare timezone, daily-bar boundary, session close, market calendar, DST handling or publication time. Never promote these inferred midnight fields into strict historical availability.

All 18 series contain Saturday and Sunday labels. Their existence does not establish when a trading session ended. Unknown sessions mean neither a Monday–Friday calendar nor a remaining-row horizon is justified. Date gaps are recorded in JSON, but no total of missing expected sessions can be certified without an approved calendar. Staleness cannot be proved from unchanged prices; update timestamps and a material-staleness policy are absent.

The quality resolution proves canonical/raw lineage consistency and finite positive closes. It does not remedy historical PIT, session alignment or midpoint evidence. Onboarding into PIT infrastructure may preserve these snapshots and their actual ingestion time. Strict historical replay, exact cross synchronization and live readiness remain uncertified. Retrospective calculations require an explicit disclosed policy; choosing an unsupported close time would be a scientific decision, not a representation detail.

## Raw overlaps and excluded records

The raw archive includes 38 artifacts for these 18 sources, including historical pilot EUR/USD captures. Every raw path and available manifest is indexed in the JSON. Unmanifested raw captures retain unknown ingestion time; filesystem timestamps must not fill this gap.

Each source has raw-only bars labelled 2026-09-06 and 2026-09-07. The original adapter excluded these because its inferred end-of-day time exceeded actual capture time. That is 36 unique source/date exclusions. Their becoming past dates now does not prove captured bars were final. Preserve them as raw evidence; do not silently promote them into completed closes.

AUD/USD, NZD/USD and ILS/USD each contain one exact provider duplicate omitted by the old ingestion. Canonical pages have no duplicates. Pilot EUR/USD captures overlap production and disagree on the incomplete 2026-09-06 close. Completed canonical history has no overlapping conflicting close values.

The diagnostic audit flags 15 adjacent-date changes with absolute log change greater than log(1.10): AUD 1, EUR 3, CHF 1, JPY 3, MXN 5, ZAR 2. This audit threshold is explicitly an implementation diagnostic, not an approved scientific exclusion policy. Values remain unchanged; no clipping, winsorization or presumed error classification is performed. Dates and values are in the JSON.

## Existing direct cross comparison

Only EUR/GBP direct pilot raw observations exist among the 25 requested cross instruments. There are three raw captures, with two completed overlapping dates (2026-09-04 and 2026-09-05), plus an incomplete 2026-09-06 bar. The two completed levels are equal across captures. No comparison source is onboarded.

A same-display-date numerical diagnostic produces relative constructed/direct level differences +0.395702 and −0.512174 basis points. Both are within an explicitly declared diagnostic tolerance of 1 basis point. The 2026-09-04→2026-09-05 simple-return difference is −0.908231 basis points, within the same 1-basis-point diagnostic tolerance. These calculations are not verified session-matched comparisons because neither the direct pilot nor legs provide close/session evidence. A certified compatible direct comparison is unavailable for all 25 crosses.

## Artifact locations

Production page template: `production/twelve_data_fx/symbol=<BASE>_<QUOTE>/page=NNNN/` contains observations.jsonl.gz, dataset-registry.json, source-registry.json, entity-registry.json, raw-ingestion-manifest.json and page-manifest.json. Pair manifests are one level above.

Raw blobs use `raw/v1/twelve_data_fx/<sha256-prefix>/<sha256>.json`. Catalog: `catalog/latest/twelve_data_fx.catalog.json`. Existing structural quality resolution: `derived/quality-resolutions/twelve_data_fx/v1.0.0/resolution.json`. Pilot evidence: `pilots/twelve_data_fx/latest/`.

The JSON audit contains each exact artifact path, original ingestion timestamp, checksum, coverage, duplicate/conflict details, quality limitations and comparison calculation. No credential files or provider network calls were used.
