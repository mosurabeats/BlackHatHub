"""Polite HTTP client for research retrieval.

* Per-host rate limiting (requests/minute)
* Exponential backoff on 429 / 5xx / network errors
* Short-lived response cache to avoid duplicate requests
* Response size cap; content is returned as data only
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from ..config import get_settings
from .base import AdapterError

MAX_BYTES = 25 * 1024 * 1024


@dataclass
class HttpResponse:
    url: str
    status: int
    text: str
    headers: dict[str, str]

    def json(self) -> Any:
        return json.loads(self.text)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8", "replace")).hexdigest()


class ResearchHttp:
    def __init__(self, transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        s = get_settings()
        self._client = httpx.Client(
            timeout=s.http_timeout_seconds,
            headers={"User-Agent": s.http_user_agent, "Accept": "application/json, text/xml, text/html;q=0.8, */*;q=0.5"},
            follow_redirects=True,
            transport=transport,
        )
        self._cache: dict[str, tuple[float, HttpResponse]] = {}
        self._last_request: dict[str, float] = {}
        self._lock = threading.Lock()
        self._cache_seconds = s.http_cache_minutes * 60
        self._sleep = sleep
        self.request_log: list[str] = []

    def close(self) -> None:
        self._client.close()

    def _throttle(self, host: str, per_minute: int) -> None:
        if per_minute <= 0:
            return
        min_interval = 60.0 / per_minute
        with self._lock:
            last = self._last_request.get(host, 0.0)
            wait = last + min_interval - time.monotonic()
            self._last_request[host] = max(time.monotonic(), last + min_interval)
        if wait > 0:
            self._sleep(wait)

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
        rate_per_minute: int = 30,
        retries: int = 3,
        use_cache: bool = True,
        accept_statuses: tuple[int, ...] = (200,),
    ) -> HttpResponse:
        full_url = url + ("?" + urlencode(params) if params else "")
        cache_key = hashlib.sha256(f"{method}|{full_url}|{json.dumps(json_body, sort_keys=True, default=str)}".encode()).hexdigest()
        if use_cache:
            hit = self._cache.get(cache_key)
            if hit and time.monotonic() - hit[0] < self._cache_seconds:
                return hit[1]
        host = urlparse(url).netloc
        attempt = 0
        last_error = ""
        while True:
            attempt += 1
            self._throttle(host, rate_per_minute)
            self.request_log.append(full_url)
            try:
                r = self._client.request(method, url, params=params, json=json_body, headers=headers)
                body = r.content[:MAX_BYTES].decode(r.encoding or "utf-8", "replace")
                resp = HttpResponse(url=str(r.url), status=r.status_code, text=body, headers=dict(r.headers))
                if r.status_code in accept_statuses:
                    if use_cache:
                        self._cache[cache_key] = (time.monotonic(), resp)
                    return resp
                if r.status_code in (401, 403):
                    raise AdapterError(
                        f"Access denied ({r.status_code}) by {host}",
                        retryable=False,
                        limitation=f"{host} refused automated access (HTTP {r.status_code}).",
                    )
                if r.status_code == 404:
                    raise AdapterError(f"Not found (404): {full_url}", retryable=False)
                retryable = r.status_code == 429 or r.status_code >= 500
                last_error = f"HTTP {r.status_code} from {host}: {body[:200]}"
                if not retryable:
                    raise AdapterError(last_error, retryable=False)
            except httpx.HTTPError as exc:
                last_error = f"Network error contacting {host}: {exc.__class__.__name__}"
            if attempt > retries:
                raise AdapterError(last_error, retryable=True)
            self._sleep(min(2 ** attempt, 30))

    def get(self, url: str, **kw) -> HttpResponse:
        return self.request("GET", url, **kw)

    def post_json(self, url: str, body: Any, **kw) -> HttpResponse:
        return self.request("POST", url, json_body=body, **kw)
