#!/usr/bin/env python3
"""Check that identifiers moved from Extra into the DOI/ISBN fields landed (zotero_write/move_payload_*.json)."""
import glob, json, os, re, shutil, sqlite3, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = os.path.join(tempfile.mkdtemp(), "z.sqlite")
for ext in ("", "-wal"):
    src = os.path.expanduser("~/Zotero/zotero.sqlite") + ext
    if os.path.exists(src):
        shutil.copy(src, tmp + ext)
db = sqlite3.connect(tmp)
lib = db.execute("select libraryID from groups where groupID=6719726").fetchone()[0]
want = [w for f in sorted(glob.glob(os.path.join(HERE, "zotero_write", "move_payload_*.json"))) for w in json.load(open(f))]
digits = lambda s: re.sub(r"[^0-9X]", "", (s or "").upper())
ok, bad = 0, []
for w in want:
    iid = db.execute("select itemID from items where key=? and libraryID=?", (w["item_key"], lib)).fetchone()[0]
    v = dict(db.execute("""select fl.fieldName, val.value from itemData d join fields fl using(fieldID)
        join itemDataValues val using(valueID) where d.itemID=?""", (iid,)).fetchall())
    probs = []
    if "doi" in w["fields"] and (v.get("DOI") or "").lower() != w["fields"]["doi"].lower():
        probs.append(f"DOI is {v.get('DOI')!r}")
    if "isbn" in w["fields"] and digits(v.get("ISBN")) != digits(w["fields"]["isbn"]):
        probs.append(f"ISBN is {v.get('ISBN')!r}")
    if (v.get("extra") or "").strip() != w["fields"].get("extra", "").strip():
        probs.append(f"Extra is {(v.get('extra') or '')[:60]!r}")
    if probs:
        bad.append((w["item_key"], "; ".join(probs)))
    else:
        ok += 1
print(f"{ok}/{len(want)} items have their identifiers in the proper fields")
for k, p in bad:
    print(" ", k, p)
