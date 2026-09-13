#!/usr/bin/env python3
"""Ransomware feed monitor for DE/AT/CH/RU/US regions: only new items since the last run.

Config: RANSOM_RSS (feed URL), RANSOM_STATE (state file path).
"""

import json
import os
import re
import sys
import html
import time
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

RSS_URL = os.environ.get("RANSOM_RSS", "https://www.ransomware.live/rss")
STATE_FILE = os.path.expanduser(os.environ.get("RANSOM_STATE", "~/.hermes/data/ransom_rss_state.json"))
TIMEOUT = 45
MAX_ITEMS = 25
SEEN_CAP = 2000

REGION_NAMES = {
    "de": ["Germany", "German", "Deutschland", "Berlin", "München", "Munich", "Köln", "Cologne",
           "Frankfurt am Main", "Frankfurt", "Hamburg", "Stuttgart", "Düsseldorf", "Dusseldorf",
           "Leipzig", "Dresden", "Hannover", "Nürnberg", "Nuremberg", "Heilbronn", "Bremen",
           "Dortmund", "Essen", "GmbH", "Universität", "Hochschule", "e.V."],
    "at": ["Austria", "Austrian", "Wien", "Vienna", "Graz", "Linz", "Salzburg", "Innsbruck"],
    "ch": ["Switzerland", "Swiss", "Schweiz", "Zürich", "Zurich", "Genf", "Geneva", "Basel", "Lausanne"],
    "ru": ["Russia", "Russian", "Moskva", "Moscow"],
    "us": ["USA", "U.S.A.", "United States", "American"],
}
# 2-letter codes — только как ЦЕЛЫЙ токен внутри скобок вида (DE), (US)
REGION_CODES = {"de": {"DE"}, "at": {"AT"}, "ch": {"CH"}, "ru": {"RU"}, "us": {"US", "America"}}

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

RFC822_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

def parse_rfc822(dt_str):
    dt_str = dt_str.strip()
    m = re.match(r'(?:\w{3},\s*)?(\d{1,2})\s+(\w{3})\s+(\d{4})\s+(\d{2}):(\d{2}):(\d{2})\s*(\w+|[+-]\d{4})?', dt_str)
    if not m:
        raise ValueError(f"Cannot parse RFC822 date: {dt_str}")
    day, mon, year, hour, minute, second, tz = m.groups()
    month = RFC822_MONTHS.get(mon)
    if not month:
        raise ValueError(f"Unknown month: {mon}")
    dt = datetime(int(year), month, int(day), int(hour), int(minute), int(second), tzinfo=timezone.utc)
    return dt

def strip_html(text):
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_group_victim(title):
    title = re.sub(r'^\s*[^\w\s]+\s*', '', title)
    marker = "has just published a new victim :"
    idx = title.find(marker)
    if idx == -1:
        markers = ["has just published a new victim:", "published a new victim:", "victim :"]
        for m in markers:
            idx = title.find(m)
            if idx != -1:
                marker = m
                break
    if idx == -1:
        return title.strip(), "Unknown"
    group = title[:idx].strip()
    victim = title[idx + len(marker):].strip()
    return group, victim

def _norm_token(tok):
    return re.sub(r'[^A-Za-z.\- ]', '', tok).strip()

def match_token(token):
    for part in re.split(r'[/,&;]+', token):
        part = _norm_token(part)
        if not part:
            continue
        up = part.upper()
        for code, syns in REGION_CODES.items():
            if up in syns:
                return code, part
        for reg, names in REGION_NAMES.items():
            for nm in names:
                if up == nm.upper():
                    return reg, part
    return None, None

def extract_brackets(desc, limit=400):
    return re.findall(r'\(([^()]{1,60})\)', (desc or "")[:limit])

def find_region(desc):
    desc = desc or ""
    # 1) токен в скобках В НАЧАЛЕ описания: "Name (USA/Global) ..." — самый надёжный сигнал
    for tok in extract_brackets(desc, limit=160):
        reg, label = match_token(tok)
        if reg:
            return reg, label
    # 2) fallback: полные названия стран ЦЕЛЫМИ словами ТОЛЬКО в первых ~300 символах
    #    (описания-сводки упоминают чужие страны/филиалы в хвосте: "Alabama, USA", "US Bristow Group")
    for reg, names in REGION_NAMES.items():
        for nm in names:
            if re.search(r'\b' + re.escape(nm) + r'\b', desc[:300], re.IGNORECASE):
                return reg, nm
    return None, None

def format_dt_berlin(dt):
    year = dt.year
    dst_start = datetime(year, 3, 31, 1, 0, tzinfo=timezone.utc)
    while dst_start.weekday() != 6:
        dst_start -= timedelta(days=1)
    dst_end = datetime(year, 10, 31, 1, 0, tzinfo=timezone.utc)
    while dst_end.weekday() != 6:
        dst_end -= timedelta(days=1)
    if dst_start <= dt < dst_end:
        berlin_offset = 2
    else:
        berlin_offset = 1
    berlin_dt = dt + timedelta(hours=berlin_offset)
    return berlin_dt.strftime("%d.%m %H:%M")

def truncate_description(desc, max_len=250):
    text = strip_html(desc)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    result = ""
    for s in sentences[:2]:
        if len(result) + len(s) > max_len:
            if not result:
                result = s[:max_len]
            break
        result += s + " "
    result = result.strip()
    if len(text) > max_len and not result.endswith("..."):
        if len(result) > max_len - 3:
            result = result[:max_len-3].rsplit(' ', 1)[0] + "..."
        else:
            result += "..."
    return result

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            last_dt = datetime.fromisoformat(data.get("last_dt", ""))
            seen = set(data.get("seen", []))
            return last_dt, seen
        except Exception:
            pass
    default_dt = datetime.now(timezone.utc) - timedelta(hours=24)
    return default_dt, set()

def save_state(last_dt, seen):
    seen_list = list(seen)
    if len(seen_list) > SEEN_CAP:
        seen_list = seen_list[-SEEN_CAP:]
    data = {
        "last_dt": last_dt.isoformat(),
        "seen": seen_list,
    }
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def fetch_rss(attempts=3):
    last_err = None
    for i in range(attempts):
        try:
            req = Request(RSS_URL, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=TIMEOUT) as response:
                data = response.read()
            try:
                return data.decode('utf-8')
            except UnicodeDecodeError:
                m = re.search(br'encoding="([^"]+)"', data)
                if m:
                    enc = m.group(1).decode('ascii', errors='ignore')
                    return data.decode(enc, errors='replace')
                return data.decode('utf-8', errors='replace')
        except Exception as e:
            last_err = e
            if i < attempts - 1:
                time.sleep(5 * (i + 1))
    raise last_err

def parse_items(xml_text):
    root = ET.fromstring(xml_text)
    items = []
    channel = root.find('channel')
    if channel is not None:
        for item in channel.findall('item'):
            items.append(parse_item(item))
    return items

def parse_item(item_elem):
    def get(tag):
        el = item_elem.find(tag)
        # el.text is None for empty/self-closing tags (e.g. <description/>):
        # never hand None downstream — it crashes on the first slice/subscript.
        if el is None or el.text is None:
            return ""
        return el.text
    return {
        "title": get("title"),
        "description": get("description"),
        "pubDate": get("pubDate"),
        "link": get("link"),
        "guid": get("guid") or get("link"),
    }

def main():
    try:
        last_dt, seen = load_state()
        try:
            xml_text = fetch_rss()
        except Exception as e:
            print(f"Fetch error: {e}", file=sys.stderr)
            print("⚠️ Ransom-монитор: фид ransomware.live недоступен (3 попытки), соберу заново завтра.")
            return 0
        items = parse_items(xml_text)
        new_items = []
        max_pub_dt = last_dt
        for item in items:
            # одна кривая запись в фиде не должна убивать весь отчёт
            try:
                if not item["guid"]:
                    continue
                try:
                    pub_dt = parse_rfc822(item["pubDate"])
                except Exception:
                    continue
                if pub_dt <= last_dt or item["guid"] in seen:
                    continue
                desc = item["description"]
                group, victim = extract_group_victim(item["title"])
                region_key, matched = find_region(desc)
                if not region_key:
                    region_key, matched = find_region(f"{group} {victim}")
                if not region_key:
                    continue
                new_items.append({
                    "group": group,
                    "victim": victim,
                    "pub_dt": pub_dt,
                    "region": matched or region_key,
                    "description": desc,
                    "link": item["link"],
                    "guid": item["guid"],
                })
                if pub_dt > max_pub_dt:
                    max_pub_dt = pub_dt
            except Exception as e:
                print(f"Skip item: {e}", file=sys.stderr)
                continue
        new_items.sort(key=lambda x: x["pub_dt"], reverse=True)
        if new_items:
            displayed = new_items[:MAX_ITEMS]
            remaining = len(new_items) - MAX_ITEMS
            for it in displayed:
                desc_short = truncate_description(it["description"])
                dt_str = format_dt_berlin(it["pub_dt"])
                print(f"🦠 {it['group']} — {it['victim']}")
                print(f"📅 {dt_str} | 🌍 {it['region']}")
                print(f"✂️ {desc_short}")
                print(f"🔗 {it['link']}")
                print()
            if remaining > 0:
                print(f"+{remaining} ещё…")
        new_seen = seen | {it["guid"] for it in new_items}
        save_state(max_pub_dt, new_seen)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
