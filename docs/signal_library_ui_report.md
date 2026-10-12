# Signal Library UI — completed

The local application at `http://127.0.0.1:8765/#signals` now has a Signal Library page,
a scrollable table of unique Signal IDs and clickable statistics/definition views.
The existing CES0500000003 monthly fractional-change Signal is the only row and the
only selectable Feature in the experiment form. Its Feature ID is used as the form
value; display labels do not replace scientific identity.

The library and Feature dropdown both load `GET /api/signal-library`. Opening a row
loads `GET /api/signal-library/<SIGNAL_ID>`, with an optional exact materialization ID
when selecting a stored version. The API verifies stored records and groups multiple
materializations under their one logical Signal. No registry, observations or research
results are copied or edited by the UI.

Details include 187 stored observations, coverage, units, transformation/parameters,
validity and null reasons, first/latest values, minimum/maximum, mean/median, sample
standard deviation, exact recipe/source metadata and lineage references. Observations
have their own scroll area. Summary statistics are descriptive read-only views; IC and
other research metrics remain unavailable because this Signal is scientifically untested.
Archive-date precision and fractional units are stated explicitly.

## Files

- New: `src/api/signal_library.py`, `src/api/server.py`, `ui/signals.js`,
  `tests/test_signal_library_api.py`, and this report.
- Updated: `ui/index.html`, `ui/library.css`, `ui/README.md`,
  `tools/serve_research_platform.py`, `src/api/README.md`, root README and documentation index.
- The scientific implementation, including the previously pinned `src/api/pit_library.py`,
  was preserved. The new server composes the existing PIT reader with the Signal API.

## Verification

Command run from the platform root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*library_api.py' -v
```

**29 tests passed in 5.004 seconds**, with no failures or skips: 13 existing PIT API
checks and 16 new Signal API checks. New tests cover distinct Signals, deduplication
across stored versions, explicit version selection, independent descriptive statistics,
null handling, empty/partial catalogs, corrupted dependencies, immutable reference
conflicts, read-only behavior and HTTP access/path/method constraints.

Browser verification at the running application confirmed one unique Signal, 187
observation rows, the sole real Feature option, click and keyboard opening, the
Feature-to-Signal detail link and unchanged PIT dataset navigation. No browser warnings
or errors were reported. The library and observation tables use bounded scroll areas.

Byte checks confirmed **all 781 pre-existing definition/storage files unchanged** and
**all 24 pinned scientific implementation files unchanged**. No recipes were executed,
and no new Signal or materialization was created during this UI task.

The regular local server was restarted at port 8765. Its read-only routes and local-only
binding remain in effect. Research submission and scientific testing remain separate work.
