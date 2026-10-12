from django.db import models

class RequestBudget(models.Model):
    """Shared across web processes; contains keyed hashes, never raw credentials."""
    key = models.CharField(max_length=64, primary_key=True)
    window = models.BigIntegerField()
    count = models.PositiveIntegerField(default=0)
