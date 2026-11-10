#!/usr/bin/env python3
"""Find DOIs and ISBNs for the Clegg reference list (clegg_items.json).

DOIs: existing Zotero DOI checked against Crossref; else Crossref bibliographic search, then OpenAlex.
ISBNs: Open Library (prefers the edition whose year matches the cited year), Google Books as fallback.
Every candidate is scored on title similarity + first-author surname; results go to ids_auto.json with
confidence high / medium / low / none. All HTTP responses are cached in cache/ so re-runs are cheap.
"""
import difflib, hashlib, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import fetch_one as F  # OpenAlex helper with the user's key (from ../.env)

CACHE = os.path.join(HERE, "cache"); os.makedirs(CACHE, exist_ok=True)
UA = {"User-Agent": "power-map-clegg-resolver/1.0"}


import threading
MIN_GAP = {"api.crossref.org": 0.1, "openlibrary.org": 0.35, "www.googleapis.com": 0.6}  # seconds between request starts
_host_lock, _last = {}, {}
STATS = {"requests": 0, "cached": 0, "rate_limited": 0}
GOOGLE_OFF = threading.Event()


def throttle(url):
    host = urllib.parse.urlparse(url).netloc
    lk = _host_lock.setdefault(host, threading.Lock())
    with lk:
        wait = _last.get(host, 0) + MIN_GAP.get(host, 0.1) - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.time()


def get(url, pause=None):
    p = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest() + ".json")
    if os.path.exists(p):
        STATS["cached"] += 1
        return json.load(open(p))
    for attempt in range(6):
        throttle(url); STATS["requests"] += 1
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                d = json.load(r); break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                d = None; break
            if e.code == 429 and "googleapis" in url:
                STATS["rate_limited"] += 1; GOOGLE_OFF.set()
                print("      !! 429 from www.googleapis.com: Google Books fallback switched off for this run", flush=True)
                d = {"_error": 429}; break
            if e.code in (429, 500, 502, 503, 504) and attempt < 5:
                if e.code == 429:
                    STATS["rate_limited"] += 1
                print(f"      !! {e.code} from {urllib.parse.urlparse(url).netloc}, retrying in {5 * (attempt + 1)}s", flush=True)
                time.sleep(5 * (attempt + 1)); continue
            d = {"_error": e.code}; break
        except Exception as e:
            if attempt < 5:
                time.sleep(5); continue
            d = {"_error": str(e)}; break
    if not (isinstance(d, dict) and "_error" in d):
        json.dump(d, open(p, "w"))
    return d


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"<[^>]+>", " ", s)
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s).split())


def main_title(s):
    return norm(re.split(r"[:?.]", s or "")[0])


def tsim(a, b):
    """title similarity: best of full-title and main-title ratios"""
    full = difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()
    mt = difflib.SequenceMatcher(None, main_title(a), main_title(b)).ratio() if len(main_title(a)) > 8 else 0
    return max(full, mt * 0.97)


def surname(a):
    a = (a or "").split(",")[0] if "," in (a or "") else (a or "").split(" ")[-1]
    return norm(a).split()[-1] if norm(a) else ""


def author_ok(item_authors, cand_names):
    if not item_authors:
        return None  # unknown
    s = surname(item_authors[0])
    names = " ".join(norm(n) for n in cand_names)
    return bool(s) and s in names.split()


KIND = {"book": "book", "monograph": "book", "edited-book": "book", "reference-book": "book", "book-set": "book",
        "book-chapter": "chapter", "book-section": "chapter", "book-part": "chapter",
        "journal-article": "article", "article": "article", "proceedings-article": "article",
        "posted-content": "other", "preprint": "other", "dissertation": "thesis", "review": "review"}
ZKIND = {"book": "book", "bookSection": "chapter", "journalArticle": "article", "thesis": "thesis",
         "manuscript": None, "webpage": None}


def annotate(c, it):
    """type compatibility + year distance, used for ranking and confidence"""
    zk, ck = ZKIND.get(it["type"]), KIND.get(c.get("type"), "other")
    c["tc"] = zk is None or ck == zk or (zk == "chapter" and ck == "book")
    y = int(it["year"]) if (it["year"] or "").isdigit() else None
    c["dy"] = abs(c["year"] - y) if (y and c.get("year")) else None
    return c


def rank(c):
    return (bool(c.get("tc", True)), c["ts"] >= 0.9, bool(c["au"]), -(c.get("dy") or 0), c["ts"])


def conf(ts, au, tc=True, dy=None, is_book=False):
    year_ok = dy is None or dy <= 2 or is_book
    if not tc:
        return "low"
    if ts >= 0.92 and au and year_ok:
        return "high"
    if ts >= 0.92 and au is None and year_ok:
        return "medium"
    if ts >= 0.80 and au:
        return "medium"
    return "low"


def isbn13(x):
    x = re.sub(r"[^0-9Xx]", "", x or "")
    if len(x) == 13:
        return x
    if len(x) == 10:
        core = "978" + x[:9]
        s = sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(core))
        return core + str((10 - s % 10) % 10)
    return None


# ---------------- DOI ----------------
def cr_year(m):
    ys = [((m.get(k) or {}).get("date-parts") or [[None]])[0][0] for k in ("published-print", "published-online", "issued")]
    ys = [y for y in ys if y]
    return min(ys) if ys else None


def crossref_check(doi, it):
    w = get(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}")
    if not w or "_error" in w:
        return None
    m = w["message"]
    t = (m.get("title") or [""])[0]
    names = [a.get("family", "") for a in m.get("author", [])] + [a.get("family", "") for a in m.get("editor", [])]
    return annotate(dict(doi=doi.lower(), title=t, year=cr_year(m),
                type=m.get("type"), ts=round(tsim(it["title"], t), 3), au=author_ok(it["authors"], names), via="zotero+crossref"), it)


def crossref_search(it):
    q = " ".join(filter(None, [it["title"], surname(it["authors"][0]) if it["authors"] else "", it["year"] or ""]))
    r = get("https://api.crossref.org/works?rows=5&query.bibliographic=" + urllib.parse.quote(q[:300]))
    best = None
    for m in ((r or {}).get("message") or {}).get("items", []) if r and "_error" not in r else []:
        t = (m.get("title") or [""])[0]
        if not t:
            continue
        names = [a.get("family", "") for a in m.get("author", [])] + [a.get("family", "") for a in m.get("editor", [])]
        c = dict(doi=m["DOI"].lower(), title=t, year=cr_year(m),
                 type=m.get("type"), ts=round(tsim(it["title"], t), 3), au=author_ok(it["authors"], names), via="crossref")
        # never take a review of the work as the work
        if re.match(r"(book )?review", norm(t)) and not re.match(r"(book )?review", norm(it["title"])):
            continue
        annotate(c, it)
        if not best or rank(c) > rank(best):
            best = c
    return best


def openalex_search(it):
    q = urllib.parse.quote(it["title"][:200])
    r = F.get(f"{F.OA}/works?search={q}&per-page=5&select=id,doi,display_name,publication_year,authorships,type")
    best = None
    for w in (r or {}).get("results", []) if r and "_error" not in r else []:
        if not w.get("doi"):
            continue
        names = [a["author"]["display_name"] for a in w.get("authorships") or []]
        c = dict(doi=w["doi"].replace("https://doi.org/", "").lower(), title=w["display_name"], year=w.get("publication_year"),
                 type=w.get("type"), ts=round(tsim(it["title"], w["display_name"] or ""), 3), au=author_ok(it["authors"], names), via="openalex")
        annotate(c, it)
        if not best or rank(c) > rank(best):
            best = c
    return best


# ---------------- ISBN ----------------
def openlibrary(it):
    title = it["book"] if it["type"] == "bookSection" and it.get("book") else it["title"]
    params = {"title": main_title(title) if len(main_title(title)) > 8 else norm(title), "limit": "5",
              "fields": "key,title,author_name,first_publish_year,edition_count"}
    if it["authors"] and it["type"] != "bookSection":
        params["author"] = surname(it["authors"][0])
    r = get("https://openlibrary.org/search.json?" + urllib.parse.urlencode(params), pause=0.4)
    best = None
    for d in (r or {}).get("docs", []) if r and "_error" not in r else []:
        c = dict(work=d["key"], title=d.get("title"), first_year=d.get("first_publish_year"),
                 ts=round(tsim(title, d.get("title", "")), 3),
                 au=None if it["type"] == "bookSection" else author_ok(it["authors"], d.get("author_name", [])))
        if not best or (c["ts"], bool(c["au"])) > (best["ts"], bool(best["au"])):
            best = c
    if not best or best["ts"] < 0.75:
        return None
    eds = get(f"https://openlibrary.org{best['work']}/editions.json?limit=100", pause=0.4) or {}
    want = int(it["year"]) if (it["year"] or "").isdigit() else None
    cands = []
    for e in eds.get("entries", []) if "_error" not in eds else []:
        isb = [isbn13(x) for x in (e.get("isbn_13") or []) + (e.get("isbn_10") or [])]
        isb = [x for x in isb if x]
        if not isb:
            continue
        y = re.search(r"(1[5-9]\d\d|20\d\d)", e.get("publish_date") or "")
        cands.append((int(y.group(1)) if y else None, isb[0], (e.get("publishers") or [None])[0]))
    if not cands:
        return dict(best, isbn=None, edition_year=None)
    # prefer the cited year's edition, then the closest year at or after it, then the earliest
    def rank(c):
        y = c[0]
        if want is None or y is None:
            return (2, y or 9999)
        return (0 if y == want else 1, abs(y - want))
    y, isb, pub = sorted(cands, key=rank)[0]
    return dict(best, isbn=isb, edition_year=y, publisher=pub, via="openlibrary")


def googlebooks(it):
    if GOOGLE_OFF.is_set():
        return None
    title = it["book"] if it["type"] == "bookSection" and it.get("book") else it["title"]
    q = f"intitle:{main_title(title) or norm(title)}"
    if it["authors"] and it["type"] != "bookSection":
        q += f"+inauthor:{surname(it['authors'][0])}"
    r = get("https://www.googleapis.com/books/v1/volumes?maxResults=5&q=" + urllib.parse.quote(q, safe=":+"), pause=0.6)
    best = None
    for v in (r or {}).get("items", []) if r and "_error" not in r else []:
        vi = v.get("volumeInfo", {})
        ids = {x["type"]: x["identifier"] for x in vi.get("industryIdentifiers", [])}
        isb = isbn13(ids.get("ISBN_13") or ids.get("ISBN_10"))
        if not isb:
            continue
        t = vi.get("title", "") + (": " + vi["subtitle"] if vi.get("subtitle") else "")
        y = re.match(r"\d{4}", vi.get("publishedDate", ""))
        c = dict(isbn=isb, title=t, edition_year=int(y.group()) if y else None, publisher=vi.get("publisher"),
                 ts=round(tsim(title, t), 3), au=None if it["type"] == "bookSection" else author_ok(it["authors"], vi.get("authors", [])),
                 via="googlebooks")
        if not best or (c["ts"], bool(c["au"])) > (best["ts"], bool(best["au"])):
            best = c
    return best


def process(it):
    rec = dict(key=it["key"], type=it["type"], title=it["title"], authors=it["authors"][:3], year=it["year"],
               zotero_doi=it["doi"], zotero_isbn=it["isbn"])
    if it["type"] == "note" or not it["title"] or it["title"].startswith("http") or "title missing" in (it["title"] or "").lower():
        rec.update(doi=None, isbn=None, doi_conf="none", isbn_conf="none", flag="not a usable reference (note, bare PDF or missing title)")
        return rec
    d = crossref_check(it["doi"], it) if it["doi"] else None
    if not d or d["ts"] < 0.80 or not d["tc"]:
        alt = crossref_search(it)
        if alt and (not d or rank(alt) > rank(d)):
            if d:
                rec["zotero_doi_mismatch"] = f"Zotero DOI {it['doi']} has title '{d['title'][:80]}'"
            d = alt
        if not d or conf(d["ts"], d["au"], d["tc"], d["dy"], it["type"] == "book") != "high":
            o = openalex_search(it)
            if o and (not d or rank(o) > rank(d)):
                d = o
    rec["doi_candidate"] = d
    rec["doi"] = d["doi"] if d else None
    rec["doi_conf"] = conf(d["ts"], d["au"], d["tc"], d["dy"], it["type"] == "book") if d else "none"
    b = None
    if it["type"] in ("book", "bookSection", "thesis", "manuscript"):
        if it["isbn"]:
            b = dict(isbn=isbn13(it["isbn"].split()[0]), via="zotero", ts=1.0, au=True, edition_year=None)
        else:
            b = openlibrary(it)
            if not b or not b.get("isbn"):
                g = googlebooks(it)
                if g and (not b or g["ts"] >= b.get("ts", 0)):
                    b = g
    rec["isbn_candidate"] = b
    rec["isbn"] = b.get("isbn") if b else None
    rec["isbn_conf"] = conf(b["ts"], b["au"], True, None, True) if b and b.get("isbn") else "none"
    return rec


def main():
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import collections
    items = json.load(open(os.path.join(HERE, "clegg_items.json")))
    workers = int(os.environ.get("WORKERS", "4"))
    res, t0, done = {}, time.time(), 0
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(process, it): i for i, it in enumerate(items)}
        for f in as_completed(futs):
            i = futs[f]; it = items[i]
            try:
                rec = f.result()
            except Exception as e:
                rec = dict(key=it["key"], type=it["type"], title=it["title"], doi=None, isbn=None,
                           doi_conf="none", isbn_conf="none", flag=f"error: {e}")
            res[i] = rec; done += 1
            rate = done / max(1e-6, (time.time() - t0) / 60)
            if rec.get("flag"):
                print(f"{done:3d}/{len(items)}  {it['key']}  skipped: {rec['flag']}", flush=True)
            else:
                print(f"{done:3d}/{len(items)}  {it['key']}  {(it['title'] or '')[:48]:<48}  "
                      f"DOI {rec['doi'] or '-':<32} [{rec['doi_conf']}]  ISBN {rec['isbn'] or '-':<13} [{rec['isbn_conf']}]  "
                      f"({rate:.0f}/min)", flush=True)
            if done % 10 == 0:
                json.dump([res[k] for k in sorted(res)], open(os.path.join(HERE, "ids_auto.json"), "w"), ensure_ascii=False, indent=1)
    out = [res[k] for k in sorted(res)]
    json.dump(out, open(os.path.join(HERE, "ids_auto.json"), "w"), ensure_ascii=False, indent=1)
    print(f"done in {(time.time() - t0) / 60:.1f} min with {workers} workers; "
          f"{STATS['requests']} requests, {STATS['cached']} from cache, {STATS['rate_limited']} rate-limited")
    print("DOI:", collections.Counter(r["doi_conf"] for r in out))
    print("ISBN:", collections.Counter(r["isbn_conf"] for r in out if r["type"] in ("book", "bookSection", "thesis", "manuscript")))


if __name__ == "__main__":
    main()
