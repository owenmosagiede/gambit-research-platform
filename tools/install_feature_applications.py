"""Install explicit capability bindings for verified existing Features; no research."""
from pathlib import Path
from api.feature_library import list_feature_library
from research.feature_applications import install_binding, load_definition, PER_MEMBER, SINGLE_SERIES


def install(root):
    catalog = list_feature_library(root)
    if catalog["issues"]:
        raise ValueError("Resolve Feature catalog issues before installing application bindings")
    counts = {PER_MEMBER: 0, SINGLE_SERIES: 0}
    for item in catalog["features"]:
        kind = PER_MEMBER if item["kind"] == "reusable_fx_recipe" else SINGLE_SERIES
        install_binding(root, load_definition(root, item), kind)
        counts[kind] += 1
    return counts


if __name__ == "__main__":
    import json
    print(json.dumps(install(Path(__file__).resolve().parents[1]), indent=2))
