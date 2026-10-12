# Application code

`contracts/` holds only pure structural validation and deterministic identity helpers.
`data/alfred_onboarding.py` implements bounded raw capture, vintage-date parsing and immutable
publication primitives for the documented ALFRED pilot. `data/alfred_pit.py` materializes its
2018 native vintage events, verifies provenance and supplies date-based as-of queries through
a rebuildable SQLite index. Run `tools/materialize_alfred_pit.py`; its contract is in
[specification 14](../specs/14_alfred_pit_store.md). Runtime dependency: jsonschema 4.25.1
([requirements](../requirements-data.txt)); SQLite is provided by Python. General readiness/data
services remain future work.
`research/p1_discovery/` and `p2_validation/` will contain reusable scientific testing modules;
`p3_forecasting/` and `p4_portfolios/` will implement the separately specified transformations.
`p5_allocation/` is provisional: its presence does not approve a P5 contract.

`runtime/` is for eventual execution state, recovery and orchestration; `api/` for shared
human/agent submission transport; `execution/` for eventual authorized order handling.
Research, runtime and execution modules remain unimplemented. `api/pit_library.py` now supplies
the first read-only metadata endpoint and local UI server; submission services remain future work. Research folders hold code,
not datasets or one custom script per experiment. Software verification lives in tests/.

`data/alfred_full_acquisition.py` and `data/alfred_full_history.py`, exposed by
`tools/onboard_alfred_full_history.py`, implement the separate complete-archive adapter.
See the [full-history report](../docs/alfred_full_history_report.md) for its verified scope.

The real 2018 pilot package has been retired and deleted. Its bounded helpers remain covered
by temporary synthetic fixtures. Full-history reads, queries, index rebuilds and identical
acquisition replay now operate independently of that pilot. New acquisition publication still
requires a versioned refresh implementation; this task introduces no live refresh service.

## Return Targets

`data/targets/` supplies closed 0.4 contracts, versioned economic/timing policies,
canonical source adaptation, schedule/interval resolution, forward return construction,
immutable Target storage, explicit historical retrieval and Feature alignment. It reuses
canonical temporal/identity utilities, PIT selection and the shared payload installer.
`api/target_library.py` exposes read-only discovery/pinned details through `api/server.py`;
`ui/targets.js` supplies the existing form with real Target readiness. See
[specification 18](../specs/18_return_targets.md) and the [Target library](../docs/target_library.md).
