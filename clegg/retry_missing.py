#!/usr/bin/env python3
"""Second pass for references still without an identifier after the review.
Open Library free-text search across the top records (books are often split over several), the ISBN list in
the search hit as a fallback, and Crossref restricted to book types. Accepts only title >= 0.90 + author match.
Writes review/retry_out.json in the same shape as the review batches."""
import glob, json, os, re, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve_ids as R

HERE = os.path.dirname(os.path.abspath(__file__))
items = {i["key"]: i for i in json.load(open(os.path.join(HERE, "clegg_items.json")))}
auto = {r["key"]: r for r in json.load(open(os.path.join(HERE, "ids_auto.json")))}
review = {r["key"]: r for f in glob.glob(os.path.join(HERE, "review", "batch_*_out.json")) for r in json.load(open(f))}
BOOKISH = ("book", "bookSection", "thesis", "manuscript", "webpage", "attachment")

todo = [k for k, r in review.items() if r["status"] == "not_found"]
todo += [k for k, a in auto.items() if k not in review and not a.get("flag") and items[k]["type"] in BOOKISH
         and a["isbn_conf"] == "none" and a["doi_conf"] != "high"]


GENERIC = {"introduction", "conclusion", "preface", "foreword", "editorial", "bibliography", "review"}


def ol_isbn(title, author, year):
    if R.norm(title) in GENERIC or len(R.norm(title)) < 8:
        return None  # too generic to identify safely
    q = " ".join(filter(None, [R.main_title(title) if len(R.main_title(title)) > 8 else R.norm(title), author]))
    r = R.get("https://openlibrary.org/search.json?" + urllib.parse.urlencode(
        {"q": q, "limit": "8", "fields": "key,title,author_name,first_publish_year,isbn"}))
    # records by this author; the record title may be the original-language title of a translation
    docs = [d for d in (r or {}).get("docs", [])
            if not author or author in R.norm(" ".join(d.get("author_name", []))).split()]
    want = int(year) if (year or "").isdigit() else None
    cands = []
    for d in docs[:5]:
        work_match = R.tsim(title, d.get("title", "")) >= 0.90
        eds = R.get(f"https://openlibrary.org{d['key']}/editions.json?limit=200") or {}
        for e in eds.get("entries", []) if "_error" not in eds else []:
            et = (e.get("title") or "") + (": " + e["subtitle"] if e.get("subtitle") else "")
            if not (work_match or R.tsim(title, et) >= 0.90):
                continue
            isb = [R.isbn13(x) for x in (e.get("isbn_13") or []) + (e.get("isbn_10") or [])]
            isb = [x for x in isb if x]
            y = re.search(r"(1[5-9]\d\d|20\d\d)", e.get("publish_date") or "")
            if isb:
                cands.append((int(y.group(1)) if y else None, isb[0], et or d["title"], d.get("first_publish_year"),
                              "" if work_match else f" (filed under '{d['title'][:40]}')"))
    if cands:
        def rank(c):
            return (2, c[0] or 9999) if (want is None or c[0] is None) else (0 if c[0] == want else 1, abs(c[0] - want))
        y, isb, t, fy, under = sorted(cands, key=rank)[0]
        return dict(isbn=isb, edition_year=y, original_year=fy, title=t, via="openlibrary edition" + under)
    for d in docs:  # fallback: ISBN list on a search hit whose own title matches (edition year unknown)
        if R.tsim(title, d.get("title", "")) < 0.90:
            continue
        isb = [x for x in (R.isbn13(i) for i in d.get("isbn", [])) if x]
        if isb:
            return dict(isbn=isb[0], edition_year=None, original_year=d.get("first_publish_year"), title=d["title"],
                        via="openlibrary search hit")
    return None


def crossref_book(title, author):
    q = " ".join(filter(None, [title, author]))
    r = R.get("https://api.crossref.org/works?rows=5&filter=type:book,type:monograph,type:edited-book&query.bibliographic="
              + urllib.parse.quote(q[:250]))
    for m in ((r or {}).get("message") or {}).get("items", []) if r and "_error" not in r else []:
        t = (m.get("title") or [""])[0]
        names = [a.get("family", "") for a in m.get("author", []) + m.get("editor", [])]
        if R.tsim(title, t) >= 0.90 and (not author or author in R.norm(" ".join(names)).split()):
            return dict(doi=m["DOI"].lower(), title=t, year=R.cr_year(m), via="crossref (books only)")
    return None


out = []
for k in todo:
    it = items[k]
    title = it.get("book") if it["type"] == "bookSection" and it.get("book") else it["title"]
    author = R.surname(it["authors"][0]) if it["authors"] and it["type"] != "bookSection" else ""
    rec = dict(key=k, status="not_found", doi=None, isbn=None, edition_year=None, original_year=None, note="retry: nothing verifiable")
    if it["type"] != "journalArticle":
        b = ol_isbn(title, author, it["year"])
        if b:
            rec.update(status="found", isbn=b["isbn"], edition_year=b["edition_year"], original_year=b["original_year"],
                       note=f"retry: {b['via']} '{b['title'][:60]}'")
        c = crossref_book(title, author)
        if c:
            rec.update(status="found", doi=c["doi"], note=rec["note"] if rec["isbn"] else f"retry: {c['via']} '{c['title'][:60]}' ({c['year']})")
    else:
        c = R.crossref_search(it)
        if c and c["ts"] >= 0.92 and c["au"] and c["tc"] and (c["dy"] is None or c["dy"] <= 2):
            rec.update(status="found", doi=c["doi"], note=f"retry: crossref '{c['title'][:60]}' ({c['year']})")
    print(f"{rec['status']:<10} {k}  {(it['title'] or '')[:55]:<55} DOI {rec['doi'] or '-':<30} ISBN {rec['isbn'] or '-'}", flush=True)
    out.append(rec)
json.dump(out, open(os.path.join(HERE, "review", "retry_out.json"), "w"), ensure_ascii=False, indent=1)
print(f"retried {len(out)}: found {sum(r['status'] == 'found' for r in out)}")
