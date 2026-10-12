"""The public endpoint exposes no worker, backup, storage or research details."""
import json
from pathlib import Path
import time


def healthy(path, *, now=None):
    if path is None: return True  # Existing isolated and development deployments.
    try:
        value = json.loads(Path(path).read_text())
        age = (time.time() if now is None else now) - value['checked_at']
        return value.get('healthy') is True and 0 <= age <= 150
    except (OSError, ValueError, KeyError, TypeError):
        return False
