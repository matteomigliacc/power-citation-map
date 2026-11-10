#!/usr/bin/env python3
"""Per-paper helper for the Haiku agents. No API keys.

  candidates --doi DOI --title "T" [--year Y]
      Prints OpenAlex and Semantic Scholar candidates (DOI lookup, then title search)
      with title / first author / year so the agent can judge the match.

  write --key K --title T --short-label L --year Y [--doi D] [--oa W123] [--s2 abc]
        [--doubtful] --notes "..."
      Downloads both reference lists for the chosen IDs and writes agents/K.json.
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
AGENTS = os.path.join(os.path.dirname(HERE), "agents")
UA = {"User-Agent": "power-map-citation-script/1.0"}
OA = "https://api.openalex.org"
S2 = "https://api.semanticscholar.org/graph/v1"

# Optional keys from power-map/.env (OPENALEX_API_KEY=..., S2_API_KEY=...). Never printed.
_env = os.path.join(os.path.dirname(HERE), ".env")
if os.path.exists(_env):
    for _l in open(_env):
        if "=" in _l and not _l.lstrip().startswith("#"):
            _k, _v = _l.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
OA_KEY = os.environ.get("OPENALEX_API_KEY")
S2_KEY = os.environ.get("S2_API_KEY")


def get(url, retry_codes=(429, 503, 500, 502, 504), data=None):
    headers = dict(UA)
    if url.startswith(OA) and OA_KEY:
        url += ("&" if "?" in url else "?") + "api_key=" + urllib.parse.quote(OA_KEY)
    if url.startswith(S2) and S2_KEY:
        headers["x-api-key"] = S2_KEY
    if data is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode()
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers, data=data), timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in retry_codes and attempt < 5:
                wait = 5
                try:
                    wait = min(45, max(5, int(json.loads(e.read()).get("retryAfter", 5))))
                except Exception:
                    pass
                time.sleep(wait); continue
            return {"_error": e.code}
        except Exception as e:  # network hiccup
            if attempt < 5:
                time.sleep(5); continue
            return {"_error": str(e)}


def oa_short(w):
    if not w or "_error" in w:
        return w
    a = w.get("authorships") or []
    return {"oa": w["id"].rsplit("/", 1)[-1], "title": w.get("display_name"),
            "first_author": a[0]["author"]["display_name"] if a else None,
            "year": w.get("publication_year"), "type": w.get("type"), "doi": w.get("doi"),
            "cited_by": w.get("cited_by_count"), "n_refs": len(w.get("referenced_works") or [])}


def s2_short(p):
    if not p or "_error" in p:
        return p
    a = p.get("authors") or []
    return {"s2": p.get("paperId"), "title": p.get("title"), "first_author": a[0]["name"] if a else None,
            "year": p.get("year"), "doi": (p.get("externalIds") or {}).get("DOI"),
            "cited_by": p.get("citationCount"), "n_refs": p.get("referenceCount")}


S2F = "paperId,title,year,authors,externalIds,citationCount,referenceCount"


def candidates(a):
    out = {"openalex": [], "semantic_scholar": []}
    if a.doi:
        out["openalex_by_doi"] = oa_short(get(f"{OA}/works/doi:{urllib.parse.quote(a.doi)}"))
        out["s2_by_doi"] = s2_short(get(f"{S2}/paper/DOI:{urllib.parse.quote(a.doi)}?fields={S2F}"))
    q = urllib.parse.quote(a.title[:250])
    ok = lambda x: x and "_error" not in x
    if not ok(out.get("openalex_by_doi")) or a.force_search:
        r = get(f"{OA}/works?search={q}&per-page=5") or {}
        out["openalex"] = [oa_short(w) for w in r.get("results", [])] or r.get("_error", "no results")
    if not ok(out.get("s2_by_doi")) or a.force_search:
        r = get(f"{S2}/paper/search/match?query={q}&fields={S2F}") or {}
        out["semantic_scholar"] = [s2_short(p) for p in (r.get("data") or [])] or r.get("_error", "no results")
    print(json.dumps(out, indent=1, ensure_ascii=False))


def write(a):
    rec = {"key": a.key, "title": a.title, "short_label": a.short_label, "year": a.year, "doi": a.doi,
           "oa": a.oa, "s2": a.s2, "cites": None, "oa_refs": [], "s2_refs": [], "doubtful": a.doubtful,
           "notes": a.notes or ""}
    extra = []
    if a.oa:
        w = get(f"{OA}/works/{a.oa}")
        if w and "_error" not in w:
            rec["oa_refs"] = [x.rsplit("/", 1)[-1] for x in (w.get("referenced_works") or [])]
            rec["cites"] = w.get("cited_by_count")
            rec["oa_title"] = w.get("display_name")
            inv = w.get("abstract_inverted_index")
            if inv:
                pos = sorted((p, t) for t, ps in inv.items() for p in ps)
                rec["abstract"] = " ".join(t for _, t in pos)[:1500]
        else:
            extra.append(f"OpenAlex fetch failed: {w}")
    if a.s2:
        refs, off = [], 0
        while True:
            r = get(f"{S2}/paper/{a.s2}/references?fields=paperId&limit=1000&offset={off}")
            if not r or "_error" in r:
                extra.append(f"S2 references fetch failed: {r}"); break
            data = r.get("data")
            if data is None:
                extra.append("S2 reference list null (publisher elided)"); break
            refs += [d["citedPaper"]["paperId"] for d in data if d.get("citedPaper") and d["citedPaper"].get("paperId")]
            if r.get("next"):
                off = r["next"]
            else:
                break
        if not refs and not any("S2" in e for e in extra):
            extra.append("S2 reference list empty (likely publisher elided)")
        rec["s2_refs"] = sorted(set(refs))
        if rec["cites"] is None:
            p = get(f"{S2}/paper/{a.s2}?fields=citationCount")
            if p and "_error" not in p:
                rec["cites"] = p.get("citationCount")
    if extra:
        rec["notes"] = (rec["notes"] + " | " if rec["notes"] else "") + "; ".join(extra)
    os.makedirs(AGENTS, exist_ok=True)
    path = os.path.join(AGENTS, f"{a.key}.json")
    json.dump(rec, open(path, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"written": path, "oa": a.oa, "s2": a.s2, "oa_refs": len(rec["oa_refs"]),
                      "s2_refs": len(rec["s2_refs"]), "cites": rec["cites"], "notes": rec["notes"]}, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(); sp = p.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("candidates"); c.add_argument("--doi"); c.add_argument("--title", required=True); c.add_argument("--year")
    c.add_argument("--force-search", action="store_true", help="title-search even if the DOI resolved")
    w = sp.add_parser("write")
    for f in ("--key", "--title", "--short-label"):
        w.add_argument(f, required=True)
    w.add_argument("--year", type=int); w.add_argument("--doi"); w.add_argument("--oa"); w.add_argument("--s2")
    w.add_argument("--doubtful", action="store_true"); w.add_argument("--notes", default="")
    a = p.parse_args()
    (candidates if a.cmd == "candidates" else write)(a)
