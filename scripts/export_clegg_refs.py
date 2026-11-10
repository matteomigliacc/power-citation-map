#!/usr/bin/env python3
"""Export Lauren's 'clegg references' subcollection (vidi group, H7YHCSFB) from a snapshot of the local
Zotero database into clegg/clegg_refs_for_map.json: one record per reference with title, first author,
year (original date when set), DOI (field or 'DOI:' line in Extra) and ISBN. Notes and bare attachments
without a parent are left out."""
import json, os, re, shutil, sqlite3, tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = os.path.join(tempfile.mkdtemp(), "z.sqlite")
for ext in ("", "-wal"):
    src = os.path.expanduser("~/Zotero/zotero.sqlite") + ext
    if os.path.exists(src):
        shutil.copy(src, tmp + ext)
db = sqlite3.connect(tmp)
coll = db.execute("select collectionID from collections where key='H7YHCSFB'").fetchone()[0]
rows = db.execute("""select i.itemID, i.key, t.typeName from collectionItems ci join items i using(itemID)
    join itemTypes t using(itemTypeID) where ci.collectionID=? and i.itemID not in (select itemID from deletedItems)""", (coll,)).fetchall()
out = []
for iid, key, typ in rows:
    if typ in ("note", "attachment"):
        continue
    f = dict(db.execute("""select fl.fieldName, v.value from itemData d join fields fl using(fieldID)
        join itemDataValues v using(valueID) where d.itemID=?""", (iid,)).fetchall())
    cr = db.execute("""select c.lastName, c.firstName, ct.creatorType from itemCreators ic join creators c using(creatorID)
        join creatorTypes ct using(creatorTypeID) where ic.itemID=? order by ic.orderIndex""", (iid,)).fetchall()
    authors = [f"{l}, {fn}".strip(", ") for l, fn, t in cr if t in ("author", "bookAuthor")] or \
              [f"{l}, {fn}".strip(", ") for l, fn, t in cr if t == "editor"]
    year = re.match(r"\d{4}", f.get("originalDate") or f.get("date") or "")
    doi = f.get("DOI") or (re.search(r"^DOI:\s*(\S+)", f.get("extra") or "", re.M) or [None, None])[1]
    out.append(dict(key=key, type=typ, title=f.get("title"), first_author=authors[0] if authors else "",
                    year=int(year.group()) if year else None, doi=(doi or "").lower() or None,
                    isbn=re.sub(r"[^0-9X]", "", (f.get("ISBN") or "").upper()) or None))
json.dump(out, open(os.path.join(BASE, "clegg", "clegg_refs_for_map.json"), "w"), ensure_ascii=False, indent=1)
print(f"{len(out)} references exported; {sum(1 for r in out if r['doi'])} with a DOI, {sum(1 for r in out if r['isbn'])} with an ISBN")
