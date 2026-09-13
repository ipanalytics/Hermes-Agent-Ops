#!/usr/bin/env python3
"""Bulk-harvest a paper archive over OAI-PMH, then count what it contains — locally.

Search APIs rate-limit, return ranked snippets, and can change their rules; a harvesting protocol
exists precisely so that a client can walk a whole set. This tool walks OAI-PMH with a resumption
token, one request at a time, writes JSONL, and then counts terms over the harvested text with no
network at all. Counting locally is what makes week-over-week comparison honest: the same corpus,
the same regex, no index drift.

    oai_harvest.py --endpoint https://export.arxiv.org/oai2 --set cs:cs.AI --days 7 --out data/cs.AI.jsonl
    oai_harvest.py --count data/cs.AI.jsonl --terms terms.json
    oai_harvest.py --fixture response.xml --out parsed.jsonl     # offline: parse a saved response
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"oai": "http://www.openarchives.org/OAI/2.0/", "dc": "http://purl.org/dc/elements/1.1/",
      "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/"}
UA = "research-intake/1.0 (OAI-PMH harvest; contact: you@example.org)"


def parse_records(xml_text: str) -> tuple[list[dict], str | None]:
    """Return (records, resumption_token). Works on live responses and saved fixtures."""
    root = ET.fromstring(xml_text)
    records = []
    for rec in root.findall(".//oai:record", NS):
        header = rec.find("oai:header", NS)
        if header is not None and header.get("status") == "deleted":
            continue
        identifier = (header.findtext("oai:identifier", default="", namespaces=NS) if header is not None else "")
        meta = rec.find("oai:metadata", NS)
        title = abstract = created = ""
        subjects: list[str] = []
        if meta is not None:
            title = meta.findtext(".//dc:title", default="", namespaces=NS).strip()
            abstract = meta.findtext(".//dc:description", default="", namespaces=NS).strip()
            created = meta.findtext(".//dc:date", default="", namespaces=NS).strip()
            subjects = [s.text.strip() for s in meta.findall(".//dc:subject", NS) if s.text]
        if not identifier:
            continue
        records.append({"id": identifier, "title": title, "abstract": abstract,
                        "created": created, "subjects": subjects})
    token_el = root.find(".//oai:resumptionToken", NS)
    token = token_el.text.strip() if token_el is not None and token_el.text else None
    return records, token


def fetch(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="replace")


def harvest(endpoint: str, set_spec: str, days: int, out: Path, delay: float = 3.0) -> int:
    params = {"verb": "ListRecords", "metadataPrefix": "oai_dc", "set": set_spec}
    url = endpoint + "?" + urllib.parse.urlencode(params)
    written, seen = 0, set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(json.loads(line)["id"])
            except Exception:
                pass
    deadline = time.time() - days * 86400 if days else None
    with out.open("a", encoding="utf-8") as fh:
        while True:
            records, token = parse_records(fetch(url))
            stop = False
            for rec in records:
                if rec["id"] in seen:
                    continue
                seen.add(rec["id"])
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                written += 1
            if deadline and records:
                oldest = min((r["created"] or "9999") for r in records)
                if oldest[:10] < time.strftime("%Y-%m-%d", time.localtime(deadline)):
                    stop = True
            if token is None or stop:
                break
            url = endpoint + "?" + urllib.parse.urlencode({"verb": "ListRecords", "resumptionToken": token})
            time.sleep(delay)  # one request at a time: the protocol rewards patience
    return written


def count_terms(path: Path, terms: dict[str, str]) -> dict:
    counts = {name: 0 for name in terms}
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        total += 1
        try:
            rec = json.loads(line)
        except Exception:
            continue
        text = f"{rec.get('title', '')} {rec.get('abstract', '')}"
        for name, pattern in terms.items():
            if re.search(pattern, text, re.I):
                counts[name] += 1
    return {"records": total, "counts": counts,
            "shares": {k: round(v / total, 4) if total else 0.0 for k, v in counts.items()}}


def main() -> int:
    ap = argparse.ArgumentParser(description="OAI-PMH harvest + local term counting")
    ap.add_argument("--endpoint", default="https://export.arxiv.org/oai2")
    ap.add_argument("--set", dest="set_spec", default="cs:cs.AI")
    ap.add_argument("--days", type=int, default=0, help="stop when records are older than N days (0 = full set walk)")
    ap.add_argument("--out", default="data/harvest.jsonl")
    ap.add_argument("--fixture", help="parse a saved OAI response instead of fetching")
    ap.add_argument("--count", help="count terms in an existing JSONL file")
    ap.add_argument("--terms", default="examples/terms.json")
    args = ap.parse_args()

    out = Path(args.out)
    if args.count:
        result = count_terms(Path(args.count), json.loads(Path(args.terms).read_text(encoding="utf-8")))
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0

    if args.fixture:
        records, token = parse_records(Path(args.fixture).read_text(encoding="utf-8"))
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"разобрано записей: {len(records)} (дальше — {token or 'нет продолжения'})")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    written = harvest(args.endpoint, args.set_spec, args.days, out)
    print(f"добавлено записей: {written} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
