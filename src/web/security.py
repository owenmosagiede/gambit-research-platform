import hashlib
import hmac
import time
from django.conf import settings
from django.db import transaction
from .models import RequestBudget

def consume(label, value, limit, seconds):
    """Fixed windows; SQLite IMMEDIATE transaction serializes concurrent workers."""
    key = hmac.new(settings.SECRET_KEY.encode(), (label + ':' + value).encode(), hashlib.sha256).hexdigest()
    window = int(time.time()) // seconds
    with transaction.atomic():
        record, _ = RequestBudget.objects.get_or_create(key=key, defaults={'window': window})
        if record.window != window:
            record.window, record.count = window, 0
        if record.count >= limit:
            return False
        record.count += 1
        record.save(update_fields=['window', 'count'])
    return True
