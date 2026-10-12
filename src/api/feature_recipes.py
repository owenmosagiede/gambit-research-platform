"""Read-only discovery of registered FX recipes, separate from stored Features."""
import re

INSTRUMENT_ID = re.compile(r'[A-Z]{6}\Z', re.ASCII)
_UNSIGNED = re.compile(r'(?:0|[1-9][0-9]*)\Z', re.ASCII)


class InvalidFeatureRecipeQuery(ValueError):
    pass


def _integer(value, default, minimum, maximum=None):
    if value is None:
        return default
    if isinstance(value, str) and _UNSIGNED.fullmatch(value):
        try:
            value = int(value)
        except ValueError:
            raise InvalidFeatureRecipeQuery('Invalid pagination value') from None
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise InvalidFeatureRecipeQuery('Invalid pagination value')
    return value


def list_feature_recipes(root, instrument_id=None, limit=None, offset=None):
    if instrument_id is not None and (not isinstance(instrument_id, str) or not INSTRUMENT_ID.fullmatch(instrument_id)):
        raise InvalidFeatureRecipeQuery('Use a registered six-letter FX instrument identity')
    limit = _integer(limit, 100, 1, 500)
    offset = _integer(offset, 0, 0)
    # The service owns registry verification and materialization status. Listing
    # never invokes preparation and never promotes an unmaterialized definition.
    from data.fx_feature_recipes import list_fx_recipes
    return list_fx_recipes(root, instrument_id=instrument_id, limit=limit, offset=offset)
