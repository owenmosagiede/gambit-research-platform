"""Pure point-in-time row selection shared by adapters and feature execution.

Callers validate the source's partition, timestamp precision and availability
policy. Comparison keys must already be canonical comparable timestamps/dates;
this helper never infers availability, cadence, missing periods or revisions.
"""
from __future__ import annotations


def select_asof(rows, cutoff, *, reference_key='reference_time',
                availability_key='available_at', successor_key=None,
                reference=None, reference_cutoff=None, sort=True):
    """Copy rows visible at cutoff using explicit interval or latest-state rules.

    With successor_key, the interval is availability <= cutoff < successor
    (null successor means open). The successor field is removed from projections:
    it can disclose a revision unavailable at the evaluation cutoff. Input order
    is preserved when sort=False, matching the established ALFRED selector.

    Without successor_key, select the latest available row per reference. Tied
    availability with different content is ambiguous and raises ValueError; exact
    duplicate rows collapse. sort=True orders the selected reference keys.
    reference_cutoff, when supplied, separately bounds reference time; it does
    not replace the availability cutoff. This is a single-partition primitive.
    """
    selected=[]
    latest={}
    versions={}
    for row in rows:
        key=row[reference_key]
        if reference is not None and key!=reference:
            continue
        if reference_cutoff is not None and key>reference_cutoff:
            continue
        available=row[availability_key]
        if available>cutoff:
            continue
        if successor_key is not None:
            successor=row[successor_key]
            if successor is not None and cutoff>=successor:
                continue
            selected.append({k:v for k,v in row.items() if k!=successor_key})
        else:
            version=(key,available)
            if version in versions and versions[version]!=row:
                raise ValueError('Ambiguous point-in-time rows at the same reference and availability')
            versions[version]=dict(row)
            previous=latest.get(key)
            if previous is None or previous[availability_key]<available:
                latest[key]=dict(row)
    if successor_key is None:
        selected=list(latest.values())
    return sorted(selected,key=lambda row:row[reference_key]) if sort else selected
