"""Staff PINs: 4–6 digits, argon2id. Never plaintext, never md5/sha1."""

import re

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_hasher = PasswordHasher(time_cost=2, memory_cost=64 * 1024, parallelism=2)
_PIN_RE = re.compile(r"^\d{4,6}$")


def validate_pin_format(pin: str) -> None:
    if not _PIN_RE.match(pin):
        raise ValueError("PIN must be 4 to 6 digits")


def hash_pin(pin: str) -> str:
    validate_pin_format(pin)
    return _hasher.hash(pin)


def verify_pin(pin_hash: str, pin: str) -> bool:
    try:
        return _hasher.verify(pin_hash, pin)
    except VerificationError:
        return False
    except Exception:
        return False
