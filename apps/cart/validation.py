MAX_QUANTITY = 99


def parse_quantity(raw, default=1):
    if raw is None or raw == "":
        return default
    message = f"Quantity must be a whole number from 1 to {MAX_QUANTITY}."
    if isinstance(raw, bool):
        raise ValueError(message)
    if isinstance(raw, float) and not raw.is_integer():
        raise ValueError(message)
    try:
        quantity = int(raw)
    except (TypeError, ValueError):
        raise ValueError(message) from None
    if not 1 <= quantity <= MAX_QUANTITY:
        raise ValueError(message)
    return quantity


def parse_id(raw, what="item"):
    message = f"Invalid {what}."
    if raw is None or isinstance(raw, (bool, float)):
        raise ValueError(message)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(message) from None
    if value < 1:
        raise ValueError(message)
    return value
