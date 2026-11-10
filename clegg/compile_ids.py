#!/usr/bin/env python3
"""Combine automatic matches (ids_auto.json) with the Haiku reviews (review/batch_*_out.json)
into clegg_identifiers.csv / .json and print a summary."""
import csv, glob, json, os, collections

HERE = os.path.dirname(os.path.abspath(__file__))
items = {i["key"]: i for i in json.load(open(os.path.join(HERE, "clegg_items.json")))}
auto = {r["key"]: r for r in json.load(open(os.path.join(HERE, "ids_auto.json")))}
review = {}
for f in sorted(glob.glob(os.path.join(HERE, "review", "batch_*_out.json"))):
    for r in json.load(open(f)):
        review[r["key"]] = r
retry = os.path.join(HERE, "review", "retry_out.json")
if os.path.exists(retry):  # second pass: only fills gaps
    for r in json.load(open(retry)):
        if r["status"] == "found" or r["key"] not in review:
            review[r["key"]] = r
BOOKISH = ("book", "bookSection", "thesis", "manuscript")

rows = []
for key, a in auto.items():
    it = items[key]
    row = dict(key=key, type=it["type"], title=it["title"], first_author=(it["authors"] or [""])[0],
               zotero_year=it["year"], doi=None, isbn=None, edition_year=None, original_year=None,
               source="", status="", note="", in_zotero_doi=bool(it["doi"]), in_zotero_isbn=bool(it["isbn"]))
    if a.get("flag"):
        row.update(status="not_a_reference", note=a["flag"])
    elif key in review:
        r = review[key]
        row.update(doi=r.get("doi"), isbn=r.get("isbn"), edition_year=r.get("edition_year"),
                   original_year=r.get("original_year"), source="review", status=r.get("status"), note=r.get("note", ""))
        # keep a high-confidence automatic identifier the reviewer did not touch
        if not row["doi"] and a["doi_conf"] == "high":
            row["doi"] = a["doi"]
        if not row["isbn"] and a["isbn_conf"] == "high":
            row["isbn"] = a["isbn"]
    else:
        main_ok = a["isbn_conf"] == "high" if it["type"] in BOOKISH else a["doi_conf"] == "high"
        row.update(doi=a["doi"] if a["doi_conf"] == "high" else None,
                   isbn=a["isbn"] if a["isbn_conf"] in ("high", "medium") else None,
                   edition_year=(a.get("isbn_candidate") or {}).get("edition_year"),
                   source="automatic", status="confirmed" if main_ok else "unreviewed",
                   note=a.get("zotero_doi_mismatch", ""))
    rows.append(row)

order = [k for k in (i["key"] for i in json.load(open(os.path.join(HERE, "clegg_items.json"))))]
rows.sort(key=lambda r: order.index(r["key"]))
json.dump(rows, open(os.path.join(HERE, "clegg_identifiers.json"), "w"), ensure_ascii=False, indent=1)
with open(os.path.join(HERE, "clegg_identifiers.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

usable = [r for r in rows if r["status"] != "not_a_reference"]
has_id = [r for r in usable if r["doi"] or r["isbn"]]
print(f"{len(rows)} items, {len(usable)} usable references")
print(f"  with a DOI or ISBN: {len(has_id)}  ({len([r for r in usable if r['doi']])} DOI, {len([r for r in usable if r['isbn']])} ISBN)")
print(f"  new vs Zotero: {sum(1 for r in usable if r['doi'] and not r['in_zotero_doi'])} DOIs, "
      f"{sum(1 for r in usable if r['isbn'] and not r['in_zotero_isbn'])} ISBNs")
print("  status:", dict(collections.Counter(r["status"] for r in rows)))
print("  no identifier:", [f"{r['first_author'].split(',')[0]} {r['zotero_year'] or ''}: {(r['title'] or '')[:50]}" for r in usable if not (r["doi"] or r["isbn"])][:60])
print("  reprints after 1989:", sum(1 for r in usable if (r["zotero_year"] or "").isdigit() and int(r["zotero_year"]) > 1989))
