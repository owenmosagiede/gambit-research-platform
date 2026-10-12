# PIT library display update

> Subsequent update: the redundant 2018 raw/PIT sample package was physically removed at the user’s request. The full-history dataset remains intact. See [the removal report](alfred_sample_removal.md). The results below describe the earlier task.

The sidebar now shows one dataset card with its title, native series ID and provider inside
the card. For CES0500000003, it reads **Average Hourly Earnings of All Employees, Total
Private — CES0500000003 — FRED / ALFRED**, with March 2006–September 2026 coverage and
247 observations.

Removed from the normal display: the retained 2018 sample card, the saved-snapshots count,
the Full history label and the Refresh library button. The 2018 underlying storage remains
intact; this was a display change. The API still preserves both immutable snapshots.

The five required placeholder dropdowns remain in place. Clicking the dataset opens its
stored coverage and vintage details. A Retry button is available only if loading fails or
entries cannot be verified.

Validation: JavaScript syntax check passed; all **13 existing API tests passed in 3.429s**;
browser verification confirmed one dataset card with the requested text and working details,
with no browser warnings/errors. All 170 existing storage/definition files matched their
prior byte hashes before new documentation was added.

Application changes: `ui/index.html`, `ui/library.js`, `ui/library.css`, `ui/README.md`,
`src/api/README.md`, all inside `Multi-Asset Model/research_platform`. API/data processing
code was unchanged.
