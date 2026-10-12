"""Retained discovery kernels; callers must supply a frozen approved profile."""
from .engine import run_p1
from .contract import ResearchContractError

__all__ = ["run_p1", "ResearchContractError"]
