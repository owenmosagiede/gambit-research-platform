"""Certified single-series operators and transient recipe execution.

Public entry points are intentionally explicit; importing this package performs
no observation reads, definition writes, network requests, or feature generation.
"""

from .engine import execute_recipe, execute_stages, InputError, RecipeError, ExecutionFailure
from .registry import Registry
from .identity import feature_id, signal_id, make_feature_definition

__all__ = ['Registry','execute_recipe','execute_stages','InputError','RecipeError',
           'ExecutionFailure','feature_id','signal_id','make_feature_definition']
