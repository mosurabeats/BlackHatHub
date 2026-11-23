"""Source Discovery: search the Socrata Discovery API for new official datasets.

Discovered datasets are PROPOSED (disabled) sources; the owner enables them.
"""
from __future__ import annotations

from ...models import Source
from ..base import ProposedSource, register

API = "https://api.us.socrata.com/api/catalog/v1"


@register
class SocrataCatalogDiscovery:
    name = "socrata_catalog"

    def discover(self, source: Source, http) -> list[ProposedSource]:
        cfg = source.config
        out: list[ProposedSource] = []
        for q in cfg.get("queries", []):
            resp = http.get(API, params={"q": q, "only": "dataset", "limit": int(cfg.get("limit", 20))}, rate_per_minute=20)
            for r in resp.json().get("results", []):
                res, meta = r.get("resource", {}), r.get("metadata", {})
                domain, ds = meta.get("domain"), res.get("id")
                if not domain or not ds:
                    continue
                name = str(res.get("name", ""))[:200]
                if cfg.get("name_must_include") and not any(t.lower() in name.lower() for t in cfg["name_must_include"]):
                    continue
                out.append(ProposedSource(
                    key=f"socrata:{domain}:{ds}",
                    name=f"{name} ({domain})",
                    adapter="socrata_dataset",
                    url=r.get("permalink") or f"https://{domain}/d/{ds}",
                    config={"domain": domain, "dataset": ds, "profile": cfg.get("profile", "unclaimed_property"),
                            "columns": res.get("columns_field_name", [])[:40], "fields": {}},
                    notes=f"Discovered via query '{q}'. Updated {res.get('data_updated_at')}. Field mapping must be configured before enabling.",
                ))
        return out

    def fetch(self, source, http, max_records):  # pragma: no cover - discovery-only adapter
        raise NotImplementedError

    def extract(self, source, record):  # pragma: no cover
        return None
