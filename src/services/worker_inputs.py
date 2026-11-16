"""Bounded input reuse and publication coordination for a worker subprocess."""
from contextlib import contextmanager
import fcntl
from pathlib import Path
from unittest.mock import patch

from data import verified_inputs
from data.feature_store import FeatureStore
from research.contracts import digest


PRICE_INPUTS = {"prices", "price_proof"}
PHASE_INPUTS = {"target_endpoints", "target_schedule", "fx_materialization", "feature_lookup"}


@contextmanager
def coordinated_inputs(root, implementation):
    """Keep exact source verifiers and their witnesses in a single lane.

    Guard catalog membership for the complete verifier, including acceptance
    of its read set. The native writer and pack index locks still apply.
    """
    root = Path(root).resolve()
    path = root / "storage/temporary/parallel-feature-catalog.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    shared = verified_inputs.VerifiedInputs(root, implementation, max_bytes=128 * 1024 * 1024)
    original_read = verified_inputs.verified_read
    original_memo = verified_inputs.VerifiedInputs.memo
    original_phase = verified_inputs.phase_inputs
    original_writer = FeatureStore.writer
    price_namespace = digest({"lane": "pinned-price-inputs", "implementation": implementation})
    active_window = None
    held = None

    @contextmanager
    def gate(mode):
        nonlocal held
        if held is not None:
            if held == fcntl.LOCK_SH and mode == fcntl.LOCK_EX:
                raise RuntimeError("A verified reader cannot also publish Feature lineage")
            yield
            return
        with path.open("a+b") as descriptor:
            fcntl.flock(descriptor, mode)
            held = mode
            try:
                yield
            finally:
                held = None

    @contextmanager
    def reader(workspace):
        if Path(workspace).resolve() != root:
            raise RuntimeError("Worker input reader escaped its workspace")
        with gate(fcntl.LOCK_SH), original_read(workspace):
            yield

    @contextmanager
    def writer(store):
        if store.root != root:
            raise RuntimeError("Worker publication escaped its workspace")
        with gate(fcntl.LOCK_EX), original_writer(store):
            yield

    @contextmanager
    def phase(workspace, plan, stage, *, period=None):
        nonlocal active_window
        previous = active_window
        window = plan["periods"][stage] if period is None else period
        active_window = digest({"lane": "phase-inputs", "stage": stage, "period": window,
                                "implementation": implementation})
        try:
            with original_phase(workspace, plan, stage, period=period):
                yield
        finally:
            active_window = previous

    def memo(context, kind, key, loader, **options):
        # Even raw price replay can resolve loose lineage and check whether it
        # has an identical packed counterpart. Guard indirect witnesses too.
        with gate(fcntl.LOCK_SH):
            scope = verified_inputs._PHASE.get()
            if (scope is None or active_window is None or context.root != shared.root
                    or context.implementation != shared.implementation or kind not in PRICE_INPUTS | PHASE_INPUTS):
                return original_memo(context, kind, key, loader, **options)

            def load_in_original_phase():
                token = verified_inputs._PHASE.set(scope)
                try:
                    return loader()
                finally:
                    verified_inputs._PHASE.reset(token)

            namespace = price_namespace if kind in PRICE_INPUTS else active_window
            token = verified_inputs._PHASE.set({"key": namespace, "end": scope["end"]})
            try:
                return original_memo(shared, kind, key, load_in_original_phase, **options)
            finally:
                verified_inputs._PHASE.reset(token)

    try:
        with patch.object(verified_inputs, "verified_read", reader), \
                patch.object(verified_inputs, "phase_inputs", phase), \
                patch.object(verified_inputs.VerifiedInputs, "memo", memo), \
                patch.object(FeatureStore, "writer", writer):
            yield
    finally:
        shared.clear()
