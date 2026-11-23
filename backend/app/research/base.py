"""Research adapter interface.

An adapter knows how to *retrieve* records from one kind of source and how to
*extract* normalized opportunity candidates from them. Everything an adapter
retrieves is treated as untrusted data: it is parsed into typed fields and
never interpreted as instructions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from ..models import Source


class AdapterError(Exception):
    """Raised when a source cannot be retrieved. ``retryable`` drives job retries."""

    def __init__(self, message: str, *, retryable: bool = True, limitation: str | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.limitation = limitation or message


class CredentialsMissing(AdapterError):
    def __init__(self, what: str):
        super().__init__(f"Missing credentials: {what}", retryable=False, limitation=f"Source requires {what}; not configured.")


@dataclass
class RawRecord:
    external_id: str
    data: dict[str, Any]
    url: str | None
    retrieved_at: datetime


@dataclass
class FetchResult:
    records: list[RawRecord]
    request_urls: list[str] = field(default_factory=list)
    new_cursor: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    truncated: bool = False


@dataclass
class ContactInfo:
    name: str
    organization: str | None = None
    role: str | None = None
    address: str | None = None


@dataclass
class Candidate:
    external_key: str
    title: str
    summary: str
    entity_name: str | None
    category: str | None
    jurisdiction_code: str | None
    location: str | None
    reported_value: float | None
    source_url: str | None
    deadline: datetime | None = None
    data: dict[str, Any] = field(default_factory=dict)
    contacts: list[ContactInfo] = field(default_factory=list)
    excerpt: str = ""
    # Extraction confidence (0..1): deterministic structured mapping is high.
    extraction_confidence: float = 0.9
    extracted_by: str = "deterministic"


@dataclass
class ProposedSource:
    key: str
    name: str
    adapter: str
    url: str
    config: dict[str, Any]
    notes: str


class Adapter(Protocol):
    name: str

    def fetch(self, source: Source, http: Any, max_records: int) -> FetchResult: ...

    def extract(self, source: Source, record: RawRecord) -> Candidate | None: ...


_REGISTRY: dict[str, Any] = {}


def register(adapter_cls):
    _REGISTRY[adapter_cls.name] = adapter_cls()
    return adapter_cls


def get_adapter(name: str):
    from . import adapters  # noqa: F401  (populate registry)

    if name not in _REGISTRY:
        raise KeyError(f"Unknown adapter '{name}'")
    return _REGISTRY[name]


def adapter_names() -> list[str]:
    from . import adapters  # noqa: F401

    return sorted(_REGISTRY)
