"""
Insights-Watchlist: beliebige Quellen beobachten (Research-Seiten von Banken, Blogs, YouTube-Kanaele) und neue
Beitraege im Dashboard zeigen. Gezeigt werden nur Titel, Datum und Link zur Originalseite, keine Inhalte.

Erkennung je Quelle (einmal ermittelt, dann gespeichert):
  1. YouTube-Kanal (youtube.com/@name, /channel/UC..., /c/...): offizieller RSS-Feed des Kanals
  2. RSS/Atom-Feed: direkt eingetragen oder auf der Seite verlinkt (<link rel="alternate" type="application/rss+xml">)
  3. sonst die Seite selbst: Links mit Artikel-Titeln unterhalb desselben Pfads (z. B. /insights/...); neu ist, was beim
     letzten Abruf noch nicht da war. Seiten, die ihre Liste erst per JavaScript nachladen, liefern hier wenig.
Abruf hoechstens alle paar Stunden je Quelle (Zwischenspeicher research/insights_items.json, Quellen in
research/insights_sources.json; beides lokal).
"""
import hashlib
import html as _html
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

AIF = Path(__file__).resolve().parents[1]
SOURCES = AIF / "research" / "insights_sources.json"
ITEMS = AIF / "research" / "insights_items.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
      "BLUMBOERG-insights")
DEFAULTS = [{"name": "J.P. Morgan Research", "url": "https://www.jpmorgan.com/insights/research"},
            {"name": "Goldman Sachs Insights", "url": "https://www.goldmansachs.com/insights"},
            {"name": "RBC Capital Markets", "url": "https://www.rbccm.com/en/insights"},
            {"name": "Citi Institute", "url": "https://www.citigroup.com/global/insights"},
            {"name": "Deutsche Bank Research", "url": "https://www.dbresearch.com/"}]
MAX_ITEMS = 400


def _load(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def _save(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    json.dump(d, open(p, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def _sid(url):
    return hashlib.sha1(url.strip().lower().rstrip("/").encode()).hexdigest()[:10]


def sources():
    """Eingetragene Quellen; neue Standardquellen werden einmal ergaenzt (geloeschte bleiben geloescht)."""
    s = _load(SOURCES, None)
    changed = s is None
    s = s or []
    removed = set(_load(ITEMS, {}).get("removed") or [])
    have = {x["id"] for x in s}
    for d in DEFAULTS:
        sid = _sid(d["url"])
        if sid not in have and sid not in removed:
            s.append({"id": sid, **d, "kind": None, "feed": None, "added": datetime.now().date().isoformat()})
            changed = True
    if changed:
        _save(SOURCES, s)
    return s


MEDIA_HINT = re.compile(r"(?i)youtube\.|youtu\.be|podcast|spotify\.|anchor\.fm|libsyn|buzzsprout|podbean|simplecast|"
                        r"megaphone\.fm|transistor\.fm|captivate|soundcloud")
CATS = {"research": "Bank research", "media": "Podcasts and videos"}


def category(src):
    """research (Bank-Research, Blogs) oder media (YouTube, Podcasts): selbst gewaehlt, sonst automatisch erkannt."""
    if src.get("cat") in CATS:
        return src["cat"]
    if src.get("kind") == "youtube" or src.get("media_feed") or MEDIA_HINT.search(src.get("url", "") + " " + src.get("name", "")):
        return "media"
    return "research"


def set_category(sid, cat):
    s = sources()
    for x in s:
        if x["id"] == sid:
            x["cat"] = cat if cat in CATS else None
    _save(SOURCES, s)


def add_source(url, name="", cat=None):
    url = url.strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url
    u = urlparse(url)
    if not u.netloc or "." not in u.netloc:
        raise ValueError("That does not look like a web address.")
    s = sources()
    sid = _sid(url)
    if any(x["id"] == sid for x in s):
        raise ValueError("Diese Quelle ist schon eingetragen.")
    nm = name.strip() or (u.path.strip("/").split("/")[0].lstrip("@") if "youtube." in u.netloc else u.netloc.replace("www.", ""))
    s.append({"id": sid, "name": nm[:60], "url": url, "kind": None, "feed": None, "cat": cat if cat in CATS else None,
              "added": datetime.now().date().isoformat()})
    _save(SOURCES, s)
    return sid


def remove_source(sid):
    _save(SOURCES, [x for x in sources() if x["id"] != sid])
    st = _load(ITEMS, {})
    st["removed"] = sorted(set(st.get("removed") or []) | {sid})
    st["items"] = [x for x in st.get("items", []) if x.get("src") != sid]
    st.get("checked", {}).pop(sid, None)
    _save(ITEMS, st)


# ------------------------------------------------------------------ Abruf und Erkennung
def _get(url, timeout=10):
    import requests
    # YouTube leitet Abrufe aus der EU sonst auf die Cookie-Zustimmungsseite um (dort steht keine Kanal-ID)
    cookies = {"CONSENT": "YES+cb", "SOCS": "CAI"} if "youtube.com" in url else None
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en,de;q=0.8"}, cookies=cookies, timeout=timeout)
    r.raise_for_status()
    return r.text


def _date(s):
    if not s:
        return None
    s = s.strip()
    for fn in (lambda x: parsedate_to_datetime(x), lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))):
        try:
            d = fn(s)
            return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()[:19]
        except Exception:
            continue
    return None


def parse_feed(xml):
    """RSS 2.0 oder Atom -> [{title, url, date}]."""
    xml = re.sub(r"^[^<]+", "", xml)
    root = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    out = []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        get = lambda name: next((c for c in it if c.tag.split("}")[-1] == name), None)
        t = get("title")
        title = _html.unescape("".join(t.itertext()).strip()) if t is not None else ""
        link = ""
        for c in it:
            if c.tag.split("}")[-1] == "link":
                link = c.get("href") or (c.text or "").strip()
                if c.get("rel") in (None, "alternate") and link:
                    break
        d = None
        for name in ("pubDate", "published", "updated", "date"):
            e = get(name)
            if e is not None and e.text:
                d = _date(e.text)
                if d:
                    break
        enc = next((c for c in it if c.tag.split("}")[-1] in ("enclosure", "content")
                    and str(c.get("type", "")).startswith(("audio", "video"))), None)
        if title and link:
            out.append({"title": title[:220], "url": link, "date": d, **({"media": True} if enc is not None else {})})
    return out


def _feed_link(page, base):
    for m in re.finditer(r"<link\b[^>]*>", page, re.I):
        tag = m.group(0)
        if re.search(r"rel=[\"']?alternate", tag, re.I) and re.search(r"application/(rss|atom)\+xml", tag, re.I):
            h = re.search(r"href=[\"']([^\"']+)", tag, re.I)
            if h:
                return urljoin(base, _html.unescape(h.group(1)))
    return None


def _youtube_feed(url, page=None):
    m = re.search(r"/channel/(UC[\w-]{22})", url)
    if m:
        cid = m.group(1)
    else:
        page = page or _get(url)
        fl = re.search(r"feeds/videos\.xml\?channel_id=(UC[\w-]{22})", page)
        if fl:
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={fl.group(1)}"
        m = (re.search(r'"channelId":"(UC[\w-]{22})"', page) or re.search(r'"externalId":"(UC[\w-]{22})"', page)
             or re.search(r'"browseId":"(UC[\w-]{22})"', page)
             or re.search(r'itemprop="(?:identifier|channelId)" content="(UC[\w-]{22})"', page)
             or re.search(r"/channel/(UC[\w-]{22})", page))
        if not m:
            return None
        cid = m.group(1)
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"


_NAV = re.compile(r"(?i)^(read more|learn more|more|see all|view all|subscribe|sign in|log in|contact us|privacy|cookie|"
                  r"terms|careers|about us|home|menu|search|share|download|watch|listen|next|previous|view articles|view more|"
                  r"explore|discover|find out more|read the report|listen now|all insights)\b")


_MON = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
_DATE_TXT = re.compile(rf"(?i)\b(?:(?:{_MON})[a-z]*\.?\s+\d{{1,2}},\s+\d{{4}}|\d{{1,2}}\.?\s+(?:{_MON})[a-z]*\.?\s+\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})\b")


def _date_txt(s):
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(re.sub(r"\.", "", s.replace("Sept", "Sep")).strip(), fmt).isoformat()[:19]
        except ValueError:
            continue
    return None


_SECTION = re.compile(r"(?i)(\.alias$|/(search|tags?|topics?|categor(y|ies)|authors?|experts?)(/|$)|_search)")


def _is_section(url):
    """Rubrik-, Such- oder Autorenseite statt Beitrag (z. B. dbresearch.com/.../RI_FEA.alias)."""
    return bool(_SECTION.search(urlparse(url).path))


def _num_id(url):
    """Laufende Beitragsnummer in der Adresse (z. B. PROD0000000000660035) – hoeher = neuer."""
    ids = re.findall(r"\d{5,}", urlparse(url).path)
    return int(max(ids, key=len)) if ids else None


def latest_of(items, top=None):
    """Neuester Beitrag einer Quelle: nach Datum, sonst nach laufender Nummer, sonst erster auf der Seite."""
    items = [x for x in items if x.get("is_article") is not False or x.get("date")]
    if not items:
        return None
    dated = [x for x in items if x.get("date")]
    if dated:
        return max(dated, key=lambda x: x["date"])
    num = [x for x in items if _num_id(x["url"]) is not None]
    if len(num) >= max(2, len(items) // 2):
        return max(num, key=lambda x: _num_id(x["url"]))
    for u in top or []:
        hit = next((x for x in items if x["url"] == u), None)
        if hit:
            return hit
    return items[0]


_META_DATE = [r'<meta[^>]+(?:property|name|itemprop)=["\'](?:article:published_time|og:published_time|published_time|'
              r'publish[-_]?date|date|dc\.date|dcterms\.date|datePublished|pubdate|sailthru\.date)["\'][^>]*content=["\']([^"\']+)',
              r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name|itemprop)=["\'](?:article:published_time|'
              r'og:published_time|publish[-_]?date|datePublished|date)["\']',
              r'"datePublished"\s*:\s*"([^"]+)"', r'<time[^>]+datetime=["\']([^"\']+)']


def article_date(url, timeout=8):
    """Erscheinungsdatum eines einzelnen Beitrags: Meta-Angaben bzw. JSON-LD der Artikelseite oder bei PDFs das
    Erstellungsdatum. Gibt (ISO-Datum oder None, ist_beitrag) zurueck. Seiten ohne jedes Datum sind meist Rubrik- oder
    Reihenseiten (z. B. Podcast-Uebersichten) und werden nicht als 'neuester Beitrag' gezeigt."""
    import requests
    h = {"User-Agent": UA, "Accept-Language": "en,de;q=0.8"}
    if urlparse(url).path.lower().endswith(".pdf"):
        for rng in ("bytes=0-131071", "bytes=-131072"):
            try:
                r = requests.get(url, headers={**h, "Range": rng}, timeout=timeout)
                b = r.content[:400000].decode("latin-1", "ignore")
            except Exception:
                continue
            m = re.search(r"/CreationDate\s*\(D:(\d{4})(\d{2})(\d{2})", b) or \
                re.search(r"<xmp:CreateDate>(\d{4})-(\d{2})-(\d{2})", b)
            if m:
                return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T00:00:00", True
        return None, True
    page = _get(url, timeout=timeout)
    for pat in _META_DATE:
        for m in re.finditer(pat, page, re.I):
            v = _html.unescape(m.group(1)).strip()
            d = _date(v)
            if not d:
                dm = _DATE_TXT.search(v)
                d = _date_txt(dm.group(0)) if dm else None
            if d and "2000" < d[:4] <= str(datetime.now().year + 1):
                return d, True
    return None, False


def _enrich(items, budget=5):
    """Fehlende oder nur monatsgenaue Daten der neuesten Beitraege nachschlagen (einmal je Beitrag)."""
    todo = [x for x in items if not x.get("dchk") and (not x.get("date") or x.get("date_prec") == "month"
                                                  or (not x.get("date_prec") and str(x.get("date")).endswith("-01T00:00:00")))]
    for x in todo[:budget]:
        x["dchk"] = True
        try:
            d, art = article_date(x["url"])
        except Exception:
            continue
        x["is_article"] = art
        if d:
            x["date"], x["date_prec"] = d, "day"


def parse_page(page, base):
    """Artikel-Links einer Uebersichtsseite: gleicher Host, unterhalb des ersten Pfadabschnitts der Seite, Linktext
    wie ein Titel (25-220 Zeichen, mehrere Woerter). Datum steht selten maschinenlesbar daneben -> None."""
    bu = urlparse(base)
    segs = [x for x in bu.path.strip("/").split("/") if x]
    lang = 1 if segs and re.fullmatch(r"[a-z]{2}(-[a-z]{2})?", segs[0]) else 0    # /en/insights -> /en/insights
    first = "/" + "/".join(segs[:(1 if len(segs) - lang <= 2 else 2) + lang]) if segs else "/"
    min_depth = (3 + lang) if len(segs) - lang <= 2 else len(segs) + 1        # Artikel liegen tiefer als Rubrikseiten
    base_dir = bu.path.rstrip("/") + "/"
    out, seen = [], set()
    for m in re.finditer(r"<a\b[^>]*href=[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", page, re.I | re.S):
        href = urljoin(base, _html.unescape(m.group(1)))
        u = urlparse(href)
        if u.netloc.replace("www.", "") != bu.netloc.replace("www.", "") or not u.path.startswith(first):
            continue
        under = u.path.startswith(base_dir) and u.path.rstrip("/") != bu.path.rstrip("/")
        if u.path.rstrip("/") in (bu.path.rstrip("/"), first.rstrip("/")) or len([x for x in u.path.split("/") if x]) < min_depth:
            continue
        if _is_section(href):
            continue
        inner = m.group(2)
        full = _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner))).strip()
        hm = re.search(r"<h[1-6][^>]*>(.*?)</h[1-6]>", inner, re.I | re.S)     # Ueberschrift im Link = Titel
        text = _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", hm.group(1)))).strip() if hm else full
        text = re.sub(r"\s+\b\d{1,2}:\d{2}(?::\d{2})?\b|\s+(Video|Podcast|Audio|Article)\s*$", "", text).strip()
        text = re.sub(r"\s{2,}", " ", text)
        lo_len, lo_words = (12, 2) if under else (25, 4)    # direkt unter der Rubrik: auch kurze Titel
        if not (lo_len <= len(text) <= 220) or len(text.split()) < lo_words or _NAV.match(text):
            continue
        dt = None
        dm = _DATE_TXT.search(full)
        if dm:
            dt = _date_txt(dm.group(0))
            text = text.replace(dm.group(0), "").strip(" |·-–,")
        if dt is None:
            ym = re.search(r"/(20\d\d)/(0?[1-9]|1[0-2])/", u.path)                 # z. B. /insights/2026/11/...
            dt = f"{ym.group(1)}-{int(ym.group(2)):02d}-01T00:00:00" if ym else None
            prec = "month" if ym else None
        else:
            prec = "day"
        key = u._replace(query="", fragment="").geturl().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": text, "url": key, "date": dt, "date_prec": prec})
    return out[:60]


def fetch(src):
    """Neueste Beitraege einer Quelle; bestimmt beim ersten Mal die Art (youtube, rss, page) und den Feed."""
    url, kind, feed = src["url"], src.get("kind"), src.get("feed")
    if kind in ("youtube", "rss") and feed:
        return kind, feed, parse_feed(_get(feed))
    host = urlparse(url).netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        feed = _youtube_feed(url)
        if not feed:
            raise ValueError("YouTube channel not recognised (please enter the channel address, e.g. youtube.com/@name)")
        return "youtube", feed, parse_feed(_get(feed))
    page = _get(url)
    if page.lstrip().startswith("<?xml") or re.search(r"<(rss|feed)\b", page[:500], re.I):
        return "rss", url, parse_feed(page)
    fl = _feed_link(page, url)
    if fl:
        try:
            items = parse_feed(_get(fl))
            if items:
                return "rss", fl, items
        except Exception:
            pass
    return "page", None, parse_page(page, url)


def refresh(max_age_h=6, force=False, only=None):
    """Faellige Quellen abrufen und neue Beitraege speichern. Rueckgabe: Anzahl neuer Beitraege."""
    srcs = sources()
    st = _load(ITEMS, {"items": [], "checked": {}, "seen_ts": None})
    st.setdefault("items", [])
    st.setdefault("checked", {})
    known = {(x["src"], x["url"]) for x in st["items"]}
    now = time.time()
    new, changed = 0, False
    for s in srcs:
        if only and s["id"] not in only:
            continue
        c = st["checked"].get(s["id"]) or {}
        if not force and now - c.get("ts", 0) < max_age_h * 3600:
            continue
        try:
            kind, feed, items = fetch(s)
            if kind != s.get("kind") or feed != s.get("feed"):
                s["kind"], s["feed"] = kind, feed
                changed = True
            if kind == "rss" and any(it.get("media") for it in items) and not s.get("media_feed"):
                s["media_feed"] = True                 # Podcast-Feed (Audio-/Video-Anhaenge)
                changed = True
            first_run = not any(x["src"] == s["id"] for x in st["items"])
            stamp = datetime.now(timezone.utc).isoformat()
            for it in items:
                if (s["id"], it["url"]) in known:
                    continue
                known.add((s["id"], it["url"]))
                st["items"].append({"src": s["id"], **it, "first_seen": stamp, "initial": first_run})
                new += 0 if first_run else 1
            if kind == "page":                       # Datum direkt auf den Beitragsseiten nachsehen
                top = [it["url"] for it in items][:12]
                mine = [x for x in st["items"] if x["src"] == s["id"]]
                _enrich(sorted(mine, key=lambda x: top.index(x["url"]) if x["url"] in top else 99))
            st["checked"][s["id"]] = {"ts": now, "ok": True, "kind": kind, "n": len(items),
                                      "top": [it["url"] for it in items if not _is_section(it["url"])][:5],
                                      "note": "no posts found (the page may load its list via JavaScript)"
                                      if not items else ""}
        except Exception as e:
            st["checked"][s["id"]] = {"ts": now, "ok": False, "error": str(e)[:160], "kind": s.get("kind")}
    st["items"] = sorted(st["items"], key=lambda x: x.get("date") or x.get("first_seen") or "", reverse=True)[:MAX_ITEMS]
    _save(ITEMS, st)
    if changed:
        _save(SOURCES, srcs)
    return new


def mark_seen():
    st = _load(ITEMS, {"items": [], "checked": {}})
    st["seen_ts"] = datetime.now(timezone.utc).isoformat()
    _save(ITEMS, st)


def payload(limit=40):
    """Fuer die App: Beitraege (neueste zuerst) mit Quellenname und Neu-Markierung, Quellen mit Status."""
    srcs = {s["id"]: s for s in sources()}
    st = _load(ITEMS, {"items": [], "checked": {}})
    seen = st.get("seen_ts") or ""
    items = []
    for x in st.get("items", []):
        s = srcs.get(x["src"])
        if not s or _is_section(x["url"]) or _NAV.match(x.get("title") or ""):
            continue
        items.append({**x, "source": s["name"], "cat": category(s),
                      "new": bool(x.get("first_seen", "") > seen and not x.get("initial"))})
    status = []
    for sid, s in srcs.items():
        c = st.get("checked", {}).get(sid) or {}
        status.append({"id": sid, "name": s["name"], "url": s["url"], "kind": s.get("kind") or c.get("kind"),
                       "cat": category(s), "cat_set": s.get("cat") in CATS,
                       "ok": c.get("ok"), "error": c.get("error"), "note": c.get("note"), "n": c.get("n"),
                       "checked": datetime.fromtimestamp(c["ts"]).strftime("%d.%m. %H:%M") if c.get("ts") else None})
    latest = []
    for sid, s in srcs.items():
        mine = [x for x in items if x["src"] == sid]
        top = (st.get("checked", {}).get(sid) or {}).get("top")
        x = latest_of(mine, top)
        if x:
            latest.append(x)
    latest.sort(key=lambda x: x.get("date") or x.get("first_seen") or "", reverse=True)
    return {"items": items[:limit], "latest": latest, "n_new": sum(i["new"] for i in items), "sources": status}
