#!/usr/bin/env python3
"""Lookup helper for the Haiku reviewers (read-only, prints compact JSON).

  python3 lookup.py doi 10.2307/1952796            -> Crossref record (title, authors, year, type, container)
  python3 lookup.py search "Two Faces of Power" "Bachrach" [1962]   -> top Crossref + OpenAlex candidates with DOIs
  python3 lookup.py isbn 9780520057289             -> Open Library edition (title, authors, year, publisher)
  python3 lookup.py books "The Constitution of Society" "Giddens" [1984] -> Open Library editions with ISBNs + years
"""
import json, os, re, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve_ids as R  # cached HTTP + OpenAlex key handling


def cr(m):
    return {"doi": m.get("DOI"), "title": (m.get("title") or [""])[0], "type": m.get("type"), "year": R.cr_year(m),
            "authors": [a.get("family") for a in m.get("author", [])][:4],
            "editors": [a.get("family") for a in m.get("editor", [])][:3],
            "container": (m.get("container-title") or [""])[0], "publisher": m.get("publisher")}


def main(cmd, *a):
    if cmd == "doi":
        w = R.get(f"https://api.crossref.org/works/{urllib.parse.quote(a[0])}")
        return cr(w["message"]) if w and "message" in w else {"error": "DOI not found in Crossref"}
    if cmd == "search":
        title, author = a[0], (a[1] if len(a) > 1 else "")
        year = a[2] if len(a) > 2 else ""
        q = " ".join(filter(None, [title, author, year]))
        r = R.get("https://api.crossref.org/works?rows=6&query.bibliographic=" + urllib.parse.quote(q))
        out = {"crossref": [cr(m) for m in (r or {}).get("message", {}).get("items", [])]}
        o = R.F.get(f"{R.F.OA}/works?search={urllib.parse.quote(title)}&per-page=5&select=doi,display_name,publication_year,authorships,type")
        out["openalex"] = [{"doi": (w.get("doi") or "").replace("https://doi.org/", ""), "title": w["display_name"],
                            "year": w.get("publication_year"), "type": w.get("type"),
                            "authors": [x["author"]["display_name"] for x in w.get("authorships") or []][:4]}
                           for w in (o or {}).get("results", [])]
        return out
    if cmd == "isbn":
        d = R.get(f"https://openlibrary.org/isbn/{re.sub(r'[^0-9Xx]', '', a[0])}.json")
        if not d or "_error" in d:
            return {"error": "ISBN not found in Open Library"}
        return {"title": d.get("title"), "subtitle": d.get("subtitle"), "publish_date": d.get("publish_date"),
                "publishers": d.get("publishers"), "works": [w["key"] for w in d.get("works", [])]}
    if cmd == "books":
        params = {"title": a[0], "limit": "5", "fields": "key,title,author_name,first_publish_year,edition_count"}
        if len(a) > 1 and a[1]:
            params["author"] = a[1]
        r = R.get("https://openlibrary.org/search.json?" + urllib.parse.urlencode(params))
        out = []
        for d in (r or {}).get("docs", [])[:3]:
            eds = R.get(f"https://openlibrary.org{d['key']}/editions.json?limit=60") or {}
            ed = []
            for e in eds.get("entries", []):
                isb = [R.isbn13(x) for x in (e.get("isbn_13") or []) + (e.get("isbn_10") or [])]
                isb = [x for x in isb if x]
                if isb:
                    ed.append({"isbn": isb[0], "date": e.get("publish_date"), "publisher": (e.get("publishers") or [None])[0]})
            out.append({"work": d["key"], "title": d.get("title"), "authors": d.get("author_name", [])[:3],
                        "first_year": d.get("first_publish_year"), "editions_with_isbn": ed[:15]})
        return out
    return {"error": "usage: doi | search | isbn | books"}


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:]), ensure_ascii=False, indent=1))
