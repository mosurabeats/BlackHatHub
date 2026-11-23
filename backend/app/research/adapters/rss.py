"""Generic RSS / Atom feed adapter (market intelligence, news, notices).

Feed items are unstructured text. Extraction uses the AI Research Analyst
when available (budget permitting); otherwise a deterministic fallback keeps
the item with low confidence. Feed content is untrusted data.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from ...models import Source
from ..base import AdapterError, Candidate, FetchResult, RawRecord, register
from ..normalize import clean_text, fingerprint, parse_date

ATOM = "{http://www.w3.org/2005/Atom}"


def parse_feed(text: str) -> list[dict]:
    head = text[:4096].upper()
    if "<!DOCTYPE" in head or "<!ENTITY" in head:
        raise AdapterError("Feed contains DTD/entity declarations; refused for safety", retryable=False)
    root = ET.fromstring(text)
    items = []
    for it in root.iter("item"):
        items.append({
            "title": clean_text(it.findtext("title")),
            "link": clean_text(it.findtext("link")),
            "summary": clean_text(it.findtext("description"), 2000),
            "published": clean_text(it.findtext("pubDate")),
            "guid": clean_text(it.findtext("guid")),
        })
    for it in root.iter(f"{ATOM}entry"):
        link = it.find(f"{ATOM}link")
        items.append({
            "title": clean_text(it.findtext(f"{ATOM}title")),
            "link": link.get("href") if link is not None else "",
            "summary": clean_text(it.findtext(f"{ATOM}summary") or it.findtext(f"{ATOM}content"), 2000),
            "published": clean_text(it.findtext(f"{ATOM}updated") or it.findtext(f"{ATOM}published")),
            "guid": clean_text(it.findtext(f"{ATOM}id")),
        })
    return items


@register
class RSSFeedAdapter:
    name = "rss_feed"
    unstructured = True

    def fetch(self, source: Source, http, max_records: int) -> FetchResult:
        url = source.config.get("url") or source.url
        if not url:
            raise AdapterError("Feed URL not configured", retryable=False)
        resp = http.get(url, rate_per_minute=source.rate_limit_per_minute)
        now = datetime.now(timezone.utc)
        recs = []
        for item in parse_feed(resp.text)[:max_records]:
            ident = item.get("guid") or item.get("link") or fingerprint(item.get("title", ""))
            recs.append(RawRecord(external_id=ident[:200], data=item, url=item.get("link") or url, retrieved_at=now))
        return FetchResult(records=recs, request_urls=[url])

    def extract(self, source: Source, record: RawRecord) -> Candidate | None:
        d = record.data
        if not d.get("title"):
            return None
        kw = [k.lower() for k in source.config.get("keywords", [])]
        text = f"{d.get('title')} {d.get('summary')}".lower()
        if kw and not any(k in text for k in kw):
            return None
        return Candidate(
            external_key=f"{source.key}:{record.external_id}",
            title=d["title"][:300],
            summary=d.get("summary", "")[:1000],
            entity_name=None,
            category=source.config.get("category", "market_signal"),
            jurisdiction_code=None,
            location=None,
            reported_value=None,
            source_url=record.url,
            data={"published": d.get("published"), "published_at": (parse_date(d.get("published")) or record.retrieved_at).isoformat()},
            excerpt=d.get("summary", "")[:600],
            extraction_confidence=0.4,
            extracted_by="deterministic_fallback",
        )
