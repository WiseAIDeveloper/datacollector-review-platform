"""Canonical binary class policy for the MyKad26 002 collection batches."""

ATTACKS = frozenset({
    'PrintBW', 'PrintColor', 'PrintCutBW', 'PrintCutColor',
    'ReplayMobile', 'ReplayMonitor', 'ReplayTablet', 'ReplayFrameless',
    'Mobile', 'Monitor',
})


def batch_label(batch):
    """Return the declared 002 batch class, rejecting unknown 002 attack types."""
    if not isinstance(batch, str) or not batch.startswith('002_'):
        return None
    attack = batch.split('_')[1]
    if attack == 'Genuine':
        return 'genuine'
    if attack in ATTACKS:
        return 'recapture'
    raise ValueError('Unknown 002 batch attack type: ' + attack)


def validate_label(batch, row, *, require=False):
    """Reject explicit class contradictions; return the authoritative batch label."""
    expected = batch_label(batch)
    if expected is None:
        return None
    for key in ('fraud_type', 'fraudType'):
        actual = row.get(key)
        if actual not in (None, '') and actual != expected:
            raise ValueError(f'{batch}: {key}={actual!r} conflicts with {expected!r}')
    if require and row.get('fraud_type') != expected:
        raise ValueError(f'{batch}: fraud_type must be {expected!r}')
    return expected


def normalize_attributes(attributes, batch):
    """Fill missing class metadata while rejecting contradictory explicit values."""
    expected = validate_label(batch, attributes)
    if expected:
        attributes['fraud_type'] = expected
    return attributes
