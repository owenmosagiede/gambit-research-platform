"""Retired batch compatibility imports; no preview, approval or dispatch service.

Historical envelopes remain readable for migration and an already-installed
release controller. Keeping their checksum format does not authorize execution.
Ordinary research requests use ResearchJobs.submit directly.
"""
from research.contracts import ResearchConflict
from data.legacy_batch_evidence import checked

MAX_BODY = 262144
BASE = 'storage/catalog/operations/research_batches'
RETIRED_MESSAGE = 'Research batches have been retired. Submit one explicitly reviewed experiment through the ordinary research queue.'


class ResearchBatches:
    """An explicit retirement error for old callers, with no active methods."""
    def __init__(self, *args, **kwargs):
        raise ResearchConflict(RETIRED_MESSAGE)
