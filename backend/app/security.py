"""Security primitives: Argon2id hashing, tokens, password policy, rate limiting, redaction."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

# Argon2id with OWASP-recommended baseline parameters (m=64MiB, t=3, p=4).
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16, type=Type.ID)
# Cheaper hasher for tests only (set via configure_fast_hashing()).
_active_hasher = _hasher


def configure_fast_hashing() -> None:
    global _active_hasher
    _active_hasher = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1, type=Type.ID)


def hash_secret(value: str) -> str:
    return _active_hasher.hash(value)


def verify_secret(hash_: str, value: str) -> bool:
    try:
        return _active_hasher.verify(hash_, value)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hash_: str) -> bool:
    try:
        return _active_hasher.check_needs_rehash(hash_)
    except InvalidHashError:
        return True


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


COMMON_PASSWORDS = {
    "password", "password123", "123456789012", "qwertyuiop", "letmein", "welcome123",
    "executivehub", "admin12345", "changeme", "iloveyou", "1234567890",
}


def password_problems(password: str, username: str = "") -> list[str]:
    problems = []
    if len(password) < 12:
        problems.append("Password must be at least 12 characters.")
    classes = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if classes < 3:
        problems.append("Use at least three of: lowercase, uppercase, digits, symbols.")
    if password.lower() in COMMON_PASSWORDS:
        problems.append("Password is too common.")
    if username and username.lower() in password.lower():
        problems.append("Password must not contain the username.")
    return problems


def pin_problems(pin: str) -> list[str]:
    if not re.fullmatch(r"\d{4,8}", pin or ""):
        return ["PIN must be 4-8 digits."]
    return []


class SlidingWindowLimiter:
    """Simple in-process sliding-window rate limiter (single-host deployment)."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: float) -> bool:
        """Record a hit; return True if allowed, False if over the limit."""
        now = time.monotonic()
        with self._lock:
            q = self._events[key]
            while q and now - q[0] > window_seconds:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


limiter = SlidingWindowLimiter()

_SENSITIVE_KEYS = re.compile(r"(pass(word)?|pin|secret|token|api[_-]?key|authorization|cookie|totp)", re.I)
_SECRET_VALUE_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN-shaped
]


def redact(value: Any) -> Any:
    """Recursively redact secrets for logs and audit records."""
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if _SENSITIVE_KEYS.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        out = value
        for pat in _SECRET_VALUE_PATTERNS:
            out = pat.sub("[REDACTED]", out)
        return out
    return value
