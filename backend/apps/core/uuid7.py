"""UUIDv7 — time-ordered ids, generated client-side for anything the client originates."""

import uuid

import uuid6


def uuid7() -> uuid.UUID:
    return uuid6.uuid7()


def is_uuid7(value: uuid.UUID | str) -> bool:
    try:
        u = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return u.version == 7
