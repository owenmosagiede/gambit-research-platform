# Transformation execution package

The public package provides `Registry`, `execute_recipe` and `execute_stages`, plus
canonical Feature/Signal identity helpers. It accepts canonical in-memory input;
it neither loads provider payloads nor publishes observations or definitions.

See [specification 16](../../../specs/16_transformation_execution.md) for the exact
contract, historical semantics, execution policies and production gates, and the
[generated library](../../../docs/transformation_library.md) for all 98 registrations.
The executable example builders in `tests/test_transformation_engine.py` construct
synthetic source envelopes and exact recipes, including composed and release cases.

From the platform root, run the fixture acceptance suite:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_transformation*.py' -v
```

`Registry.enumerate_grid` requires an explicit bounded request and never executes
or registers candidates. The transformation definition files are authoritative;
the Markdown catalogue is generated and checked against them by tests.
