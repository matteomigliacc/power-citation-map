#!/usr/bin/env python3
"""Compare a fresh copy of the Zotero database with the intended updates (zotero_write/payload_*.json + the test item)."""
import glob, json, os, shutil, sqlite3, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = os.path.join(tempfile.mkdtemp(), "z.sqlite")
for ext in ("", "-wal"):  # copy the write-ahead journal too, so the newest changes are included
    srcf = os.path.expanduser("~/Zotero/zotero.sqlite") + ext
    if os.path.exists(srcf):
        shutil.copy(srcf, tmp + ext)
db = sqlite3.connect(tmp)
lib = db.execute("select libraryID from groups where groupID=6719726").fetchone()[0]
FIELD = {"doi": "DOI", "isbn": "ISBN", "extra": "extra"}

want = [{"item_key": "7R76H8DV", "fields": {"doi": "10.1007/978-1-349-17227-6", "isbn": "9780333294215"}}]
for f in sorted(glob.glob(os.path.join(HERE, "zotero_write", "payload_*.json"))):
    want += json.load(open(f))

ok, bad = 0, []
for w in want:
    row = db.execute("select itemID from items where key=? and libraryID=?", (w["item_key"], lib)).fetchone()
    if not row:
        bad.append((w["item_key"], "item not found")); continue
    iid = row[0]
    vals = dict(db.execute("""select f.fieldName, v.value from itemData d join fields f using(fieldID)
        join itemDataValues v using(valueID) where d.itemID=?""", (iid,)).fetchall())
    tags = {t for (t,) in db.execute("select t.name from itemTags it join tags t using(tagID) where it.itemID=?", (iid,))}
    def same(k, have, v):
        if k == "isbn":
            import re
            return re.sub(r"[^0-9X]", "", (have or "").upper()) == re.sub(r"[^0-9X]", "", v.upper())
        if k == "extra":  # Zotero moves a 'DOI:' line into the DOI field when the type has one
            lines = [l for l in v.splitlines() if not (l.startswith("DOI: ") and vals.get("DOI") == l[5:])]
            return all(l in (have or "") for l in lines)
        return (have or "").strip().lower() == v.strip().lower()
    probs = [f"{k}: has {vals.get(FIELD[k])!r}" for k, v in w["fields"].items() if not same(k, vals.get(FIELD[k]), v)]
    if "clegg-ids-added" not in tags:
        probs.append("tag missing")
    if probs:
        bad.append((w["item_key"], "; ".join(probs)))
    else:
        ok += 1
print(f"{ok}/{len(want)} items match the intended update")
for k, p in bad:
    print(" ", k, p[:200])
