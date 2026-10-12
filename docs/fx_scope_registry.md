# Fixed FX research universes and Scope selection

These groupings implement the user's explicit October 9, 2026 definitions. They are fixed
research references over the 43 existing economic FX pairs. Membership is not certification
of current or historical FTMO account eligibility, historical information availability,
live trading suitability, or a common directional exposure.

## Registered universes

Each universe has version `1.0.0`. Membership follows the pinned registered **base currency
and quote currency**, not the provider's source-series quotation. Individual instrument
scopes retain the registered instrument IDs; no instruments or observations are duplicated.

| Universe ID | Member count |
| --- | ---: |
| `FTMO_UNIVERSE` | 43 |
| `FX_G10` | 31 |
| `FX_NON_G10` | 12 |
| `FX_CORE_28` | 28 |
| `FX_USD_PAIRS` | 18 |
| `FX_NON_USD_CROSSES` | 25 |
| `FX_CORE_USD_PAIRS` | 7 |
| `FX_CORE_CROSSES` | 21 |
| `FX_NORDIC` | 3 |
| `FX_CENTRAL_EUROPE` | 6 |
| `FX_ASIA_CNH_HKD_SGD` | 3 |
| `FX_AUD_PAIRS` | 7 |
| `FX_CAD_PAIRS` | 7 |
| `FX_CHF_PAIRS` | 7 |
| `FX_EUR_PAIRS` | 11 |
| `FX_GBP_PAIRS` | 7 |
| `FX_JPY_PAIRS` | 7 |
| `FX_NZD_PAIRS` | 7 |

`CORE_CURRENCIES` is AUD, CAD, CHF, EUR, GBP, JPY, NZD, USD. `G10_CURRENCIES` adds NOK and
SEK. G10/non-G10 and USD/non-USD partition the parent universe. Core USD/Core Crosses
partition Core FX. All other overlaps are intentional. Non-G10 means only the complement
of G10 in this fixed parent set. Currency presence on either side does not change the
quotation, return sign, or Expected Direction.

## Storage and resolution

Universe and individual instrument definitions use the existing `scope_definition` contract
under `definitions/scopes/<id>/<version>.json`; universes are scopes with `body.kind=universe`.
The existing instrument registry remains authoritative for economic identities and currency
metadata. Scope membership and eligibility/exclusion rules are immutable policy references.
Resolved many-to-many membership rows use the existing content-addressed payload store and
`layer=membership` snapshots under `storage/catalog/snapshots/<snapshot_id>/manifest.json`.
These are metadata links to instruments, not copies of price or Target observations.

Membership snapshot period is a one-microsecond registration/resolution document interval;
its cutoff is the start of that same record interval.
They do not assert a historical membership or broker eligibility interval. Matching records
are reused on repeated execution; incompatible name/version definitions fail explicitly.
Unrelated scopes remain in the registry. Missing observations or incomplete Target builds
never shrink a stored membership set.

The read-only `/api/scope-library` endpoint lists registered scopes. Exact resolution uses
`/api/scope-library/<id>?version=<version>` and verifies the definition and membership
references. There is no implicit latest-version binding. The response supplies the existing
experiment contract's `experiment.scope`, `definition_bindings.scope`, and
`dependencies.scope_membership_and_eligibility` fragments. The membership artifact preserves
the exact resolved instrument set; no inline list is added to the canonical five-input contract.

The existing Scope dropdown groups **Instruments** and **Universes** and reads all options,
display names and member counts from this API. Selection resolves the exact registered
version and retains its immutable membership and policy references. A pending or failed
resolution clears the prior binding. Membership remains selectable independently of the
separate stored-price, retrospective, historical-replay and live-use readiness indicators.

This addition does not submit or execute experiments. The existing page's other unfinished
inputs and submission behavior remain as they were. Target categories, all five approved
horizons, return calculations, Feature and Expected Direction are unchanged. Research Spec remains removed
from the page as separately requested; its backend contract has not changed.

## Repeatable registration

Run the installed `tools/register_fx_scopes.py` with the platform Python environment and
`--request` pointing to the exact approved request text. `--root` optionally identifies the
platform root. This command only publishes scope definitions, policies, registration evidence
and membership snapshots/payloads. It does not call an onboarding, price, Target or trial builder.

An incompatible existing name/version is an explicit conflict, not a silent overwrite.
Original membership metadata and the registration interval are reused on an identical repeat,
including when a newer instrument readiness record exists.
