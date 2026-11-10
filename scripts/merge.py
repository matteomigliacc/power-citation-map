#!/usr/bin/env python3
"""Step 4: load agent JSON into citations.sqlite, link, fetch outside metadata, summarise.

  python3 scripts/merge.py [--accept KEY,KEY] [--min-cite 2] [--min-shared 2]

Only this script writes the database. Re-runnable: it rebuilds all tables each time.
Doubtful matches are kept out of the linking unless listed in --accept.
Writes graph.json (for the HTML map) and prints the summary.
"""
import argparse, collections, glob, itertools, json, os, re, sqlite3, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import fetch_one as F  # noqa: E402  (shared HTTP helper with keys + retries)

CACHE = os.path.join(BASE, "cache"); os.makedirs(CACHE, exist_ok=True)

# Zotero items with no scholarly record, and duplicates inside the collection
SKIP = {"WH88RAQI": "Meta blog post", "TFMG6CFR": "Common Wealth webpage"}
DUPES = {"LDVMWKLZ": "5SFWEQ3K"}  # second Zotero copy of Star 1999
CLEGG = "CLEGG1989"  # Clegg, Frameworks of Power: reference list transcribed by Lauren (Zotero 'clegg references')
MANUAL_ALIAS = {"10.1007/978-0-230-80257-5": "SI2UUXBS"}  # Palgrave 2005 'Power' = Lukes, Power: A Radical View 2nd ed.
# outside records whose metadata names the wrong author (checked by hand): DOI -> display label
LABEL_FIX = {"10.20396/rbi.v18i2.8654960": "Srnicek 2016*",  # Platform capitalism record credited to a reviewer
             "10.2307/2737970": "Foucault 1977",  # Discipline and Punish
             "10.1145/3170427.3170632": "GDPR 2016"}  # the Regulation itself; the record is a same-titled 2018 article  # Discipline and Punish: most-cited record is a 1978 review  # 'Platform capitalism' record credited to a reviewer

THEMES = {
    "theory": "Power theory",
    "platform": "Platform power & political economy",
    "infra": "Infrastructure & infrastructural power",
    "law": "Law & regulation of digital power",
    "algo": "Algorithms, data & society",
    "hci": "HCI, privacy & security practice",
    "other": "Other / outside the set's themes",
}
ZTHEME = {
    "8UBSED2J": "theory", "SI2UUXBS": "theory", "8C6EFGVM": "theory", "MWCFJ27J": "theory",
    "ZVAAR6UE": "theory", "6A99P4RN": "theory", "YFAWQ44C": "theory",
    "533IQCYR": "platform", "ZDKPD64T": "platform", "5RKX9NU3": "platform", "NR6PE48S": "platform",
    "9I4757G9": "platform", "3UC8JF9C": "platform", "8KJ28NNB": "platform", "5X5HD2ZQ": "platform",
    "UWDEECCC": "platform", "EMQH8QJG": "platform", "JAEVYMHV": "platform", "N8JCSANG": "platform",
    "TFMG6CFR": "platform", "WH88RAQI": "platform",
    "5SFWEQ3K": "infra", "LDVMWKLZ": "infra", "XWJSNKTV": "infra", "VSXUMV4K": "infra",
    "ASUH772N": "infra", "GF58GYBB": "infra", "UGKPBJGY": "infra", "RWYVRZCP": "infra",
    "JYJHQNVL": "infra", "VYK85GQ5": "infra", "3ZVQLBHB": "infra",
    "CD35LPMH": "law", "2VEJN9QH": "law", "7IVHJJK6": "law", "R3EJISTM": "law", "UQVVKC6F": "law",
    "5BLN39K9": "law", "QY5YFM67": "law", "U66YSF3L": "law", "JKE2I2YF": "law", "Y245QIIB": "law",
    "9HUCHXK2": "algo", "WLBGFS8J": "algo", "5HSC3YEN": "algo", "MRHT6VVC": "algo",
    "B26F5G5M": "algo", "AJSQSCMV": "algo", "H8WRWJQZ": "algo", "K7CKL63N": "algo",
    "2SKW9WWF": "hci", "R92FC6FK": "hci", "5QRTRGAB": "hci", "L59TFMJX": "hci",
    "7IKL5L9G": "hci", "H79URSEL": "hci", "YLKCBJ9E": "hci",
}
# keyword rules for outside papers (title + OpenAlex topic), first match wins
KW = [
    ("hci", r"\b(hci|user stud|usab|interview|participatory|design method|cookie|consent banner|dark pattern|privacy polic|developer|engineer|security|tracking|tracker|measurement|websites?)\b"),
    ("law", r"\b(law|legal|regulat|antitrust|competition|gdpr|data protection|dma|digital markets act|privacy|consumer|court|rights?|governance of)\b"),
    ("infra", r"\b(infrastructur|cloud|ethnograph|standard|boundary object|supply chain|software|interoperab|api)\b"),
    ("platform", r"\b(platform|big tech|capitalis|political economy|amazon|google|facebook|uber|gig|surveillance capitalism|monopol|ecosystem)\b"),
    ("algo", r"\b(algorithm|datafication|data|machine learning|artificial intelligence|\bai\b|automat|metric|quantif|colonial|feminis|big data)\b"),
    ("theory", r"\b(power|domination|hegemon|sociolog|structur|agency|social theory|transition|elite|authority|discipline|foucault)\b"),
]
OFF_DOMAINS = {"Health Sciences", "Life Sciences"}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"<[^>]+>", " ", s)
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s).split())


def main_title(s):
    n = norm((s or "").split(":")[0].split("?")[0])
    return n


PARTICLES = {"van", "von", "de", "der", "den", "da", "di", "du", "la", "le", "del", "dos"}


def label_name(name):
    """Display surname, keeping particles: 'José van Dijck' -> 'van Dijck'."""
    if not name:
        return ""
    if "," in name:
        return name.split(",")[0].strip()
    toks = name.split()
    for i, t in enumerate(toks[:-1]):
        if i > 0 and t.lower() in PARTICLES:
            return " ".join(toks[i:])
    return toks[-1]


def surname(name):
    if not name:
        return ""
    name = name.split(",")[0] if "," in name else name.split()[-1]
    return norm(name).split()[-1] if norm(name) else ""


class UF:
    def __init__(self): self.p = {}
    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # keep Zotero roots as roots
            if rb.startswith("z:") and not ra.startswith("z:"):
                ra, rb = rb, ra
            self.p[rb] = ra
        return ra


def classify(title, topic):
    t = norm(title) + " " + norm(topic or "")
    for th, rx in KW:
        if re.search(rx.removesuffix(r"\b"), t):  # prefix match: 'platform' also hits 'platforms'
            return th
    return "other"


def fetch_oa_meta(ids):
    path = os.path.join(CACHE, "oa_meta.json")
    cache = json.load(open(path)) if os.path.exists(path) else {}
    todo = [i for i in ids if i not in cache]
    sel = "id,doi,display_name,publication_year,cited_by_count,authorships,primary_topic,type"
    for k in range(0, len(todo), 50):
        chunk = todo[k:k + 50]
        r = F.get(f"{F.OA}/works?filter=openalex:{'|'.join(chunk)}&per-page=50&select={sel}")
        if not r or "_error" in r:
            print("  OA batch failed:", r, file=sys.stderr); continue
        got = set()
        for w in r.get("results", []):
            wid = w["id"].rsplit("/", 1)[-1]; got.add(wid)
            a = w.get("authorships") or []
            pt = w.get("primary_topic") or {}
            cache[wid] = {"title": w.get("display_name"), "year": w.get("publication_year"),
                          "doi": (w.get("doi") or "").replace("https://doi.org/", "").lower() or None,
                          "cited_by": w.get("cited_by_count"), "type": w.get("type"),
                          "first_author": a[0]["author"]["display_name"] if a else None,
                          "topic": pt.get("display_name"), "domain": (pt.get("domain") or {}).get("display_name")}
        for wid in chunk:
            cache.setdefault(wid, None)  # merged/deleted records come back missing
        json.dump(cache, open(path, "w"))
    return cache


def fetch_s2_meta(ids):
    path = os.path.join(CACHE, "s2_meta.json")
    cache = json.load(open(path)) if os.path.exists(path) else {}
    todo = [i for i in ids if i not in cache]
    for k in range(0, len(todo), 500):
        chunk = todo[k:k + 500]
        r = F.get(f"{F.S2}/paper/batch?fields=paperId,title,year,authors,externalIds,citationCount",
                  data={"ids": chunk})
        if not isinstance(r, list):
            print("  S2 batch failed:", r, file=sys.stderr); continue
        for pid, p in zip(chunk, r):
            if not p:
                cache[pid] = None; continue
            a = p.get("authors") or []
            cache[pid] = {"title": p.get("title"), "year": p.get("year"),
                          "doi": ((p.get("externalIds") or {}).get("DOI") or "").lower() or None,
                          "cited_by": p.get("citationCount"),
                          "first_author": a[0]["name"] if a else None}
        json.dump(cache, open(path, "w"))
    return cache


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accept", default="", help="comma-separated Zotero keys whose doubtful match to use")
    ap.add_argument("--min-cite", type=int, default=2)
    ap.add_argument("--min-shared", type=int, default=2)
    args = ap.parse_args()
    accept = {k for k in args.accept.split(",") if k}

    items = json.load(open(os.path.join(BASE, "zotero_items.json")))
    agents = {}
    for f in glob.glob(os.path.join(BASE, "agents", "*.json")):
        a = json.load(open(f)); agents[a["key"]] = a
    deep = {k: a for k, a in agents.items() if k.startswith("OUT_")}
    drop = set(json.load(open(os.path.join(BASE, "drop.json")))) if os.path.exists(os.path.join(BASE, "drop.json")) else set()

    db = sqlite3.connect(os.path.join(BASE, "citations.sqlite"))
    if "'zotero'" not in db.execute("select sql from sqlite_master where name='refs'").fetchone()[0]:
        db.executescript("""DROP TABLE refs; CREATE TABLE refs(citing_work_id INTEGER, cited_oa_id TEXT NOT NULL DEFAULT '',
            cited_s2_id TEXT NOT NULL DEFAULT '', source TEXT CHECK(source IN ('oa','s2','zotero')),
            PRIMARY KEY(citing_work_id, cited_oa_id, cited_s2_id, source));""")
    db.executescript("DELETE FROM refs; DELETE FROM aliases; DELETE FROM works;")

    uf = UF()
    zinfo = {}  # key -> dict
    for it in items:
        k = it["key"]; a = agents.get(DUPES.get(k, k)) if k not in SKIP else None
        if k in SKIP:
            status, note = "unresolved", SKIP[k]
        elif k in DUPES:
            status, note = "resolved", f"duplicate Zotero copy of {DUPES[k]}"
        elif not a or not (a.get("oa") or a.get("s2")):
            status, note = "unresolved", (a or {}).get("notes", "no agent output")
        elif a.get("doubtful") and k not in accept:
            status, note = "doubtful", a.get("notes", "")
        else:
            status, note = "resolved", (a or {}).get("notes", "")
        fa = it["authors"][0] if it["authors"] else ""
        label = {"TFMG6CFR": "Common Wealth n.d.", "WH88RAQI": "Meta 2025"}.get(k) or (a or {}).get("short_label") or f"{label_name(fa)} {it['year'] or ''}".strip()
        zinfo[k] = dict(key=k, title=it["title"], label=label, year=it["year"] or (a or {}).get("year"),
                        doi=(it.get("doi") or (a or {}).get("doi") or "").lower() or None,
                        oa=(a or {}).get("oa") if k not in DUPES else None,
                        s2=(a or {}).get("s2") if k not in DUPES else None,
                        cites=(a or {}).get("cites"), abstract=(a or {}).get("abstract"),
                        oa_refs=(a or {}).get("oa_refs", []) if status == "resolved" and k not in DUPES else [],
                        s2_refs=(a or {}).get("s2_refs", []) if status == "resolved" and k not in DUPES else [],
                        status=status, note=note, first_author=fa, theme=ZTHEME.get(k, "other"),
                        subcollections=it.get("subcollections", []), type=it.get("type"))
        z = "z:" + k
        uf.find(z)
        if status == "resolved" and k not in DUPES:
            if zinfo[k]["oa"]: uf.union(z, "oa:" + zinfo[k]["oa"])
            if zinfo[k]["s2"]: uf.union(z, "s2:" + zinfo[k]["s2"])

    clegg_path = os.path.join(BASE, "clegg", "clegg_refs_for_map.json")
    clegg_refs = json.load(open(clegg_path)) if os.path.exists(clegg_path) else []
    if clegg_refs:
        zinfo[CLEGG] = dict(key=CLEGG, title="Frameworks of Power", label="Clegg 1989", year=1989, doi=None,
                            oa=None, s2=None, cites=None, abstract=None, oa_refs=[], s2_refs=[],
                            list_refs=[r["key"] for r in clegg_refs], status="resolved",
                            note="Not in the power collection. Its reference list comes from Lauren's Zotero collection "
                                 "'clegg references' (checked against the SAGE bibliography), not from OpenAlex or Semantic Scholar.",
                            first_author="Clegg, Stewart R.", theme="theory", subcollections=[], type="book", extra_node=True)
        uf.find("z:" + CLEGG)

    citing = {k: v for k, v in zinfo.items() if v["status"] == "resolved" and (v["oa_refs"] or v["s2_refs"] or v.get("list_refs"))}
    # deep (step 5) outside papers act as extra citing works
    for k, a in deep.items():
        if a.get("doubtful") and k not in accept:
            continue
        citing[k] = dict(key=k, oa_refs=a.get("oa_refs", []), s2_refs=a.get("s2_refs", []), deep=True,
                         oa=a.get("oa"), s2=a.get("s2"))

    # ---- metadata for every cited outside record (cached) ----
    zoa = {v["oa"] for v in zinfo.values() if v["oa"]}
    zs2 = {v["s2"] for v in zinfo.values() if v["s2"]}
    all_oa = sorted({r for c in citing.values() for r in c["oa_refs"]} - zoa)
    all_s2 = sorted({r for c in citing.values() for r in c["s2_refs"]} - zs2)
    print(f"Fetching metadata: {len(all_oa)} OpenAlex + {len(all_s2)} S2 cited records (cached after first run)")
    oam = fetch_oa_meta(all_oa); s2m = fetch_s2_meta(all_s2)

    # ---- unify records: DOI, then exact title + surname + year±1 ----
    recs = {}  # node -> meta
    for i in all_oa:
        if oam.get(i): recs["oa:" + i] = oam[i]
    for i in all_s2:
        if s2m.get(i): recs["s2:" + i] = s2m[i]
    for k, v in zinfo.items():
        recs["z:" + k] = {"title": v["title"], "year": v["year"], "doi": v["doi"],
                          "first_author": v["first_author"], "cited_by": v["cites"]}
    for r in clegg_refs:  # each entry of Clegg's list is a record that goes through the same matching rules
        recs["cz:" + r["key"]] = {"title": r["title"], "year": r["year"], "doi": r["doi"],
                                  "first_author": r["first_author"], "cited_by": None}
    bydoi = {}
    for n, m in recs.items():
        d = m.get("doi")
        if d and not (n.startswith("z:") and zinfo[n[2:]]["status"] != "resolved"):
            if d in bydoi: uf.union(bydoi[d], n)
            else: bydoi[d] = n
    bytitle = collections.defaultdict(list)
    for n, m in recs.items():
        t = norm(m.get("title"))
        if t and len(t) >= 12:
            bytitle[(t, surname(m.get("first_author")))].append(n)
    for (t, sn), ns in bytitle.items():
        for a, b in itertools.combinations(ns, 2):
            ya, yb = recs[a].get("year"), recs[b].get("year")
            if not ya or not yb or abs(ya - yb) <= 1:
                uf.union(a, b)

    # ---- alias pass: same main title + same surname, any year (editions, reprints, review-as-book) ----
    alias_log = []
    bymain = collections.defaultdict(list)
    for n, m in recs.items():
        mt = main_title(m.get("title")); sn = surname(m.get("first_author"))
        if mt and len(mt) >= 12 and sn:
            bymain[(mt, sn)].append(n)
    def compatible(a, b):  # same full title, or at least one has no subtitle
        fa, fb = norm(recs[a].get("title")), norm(recs[b].get("title"))
        return fa == fb or fa == main_title(recs[a].get("title")) or fb == main_title(recs[b].get("title"))
    for (mt, sn), ns in bymain.items():
        ns = sorted(ns, key=lambda r: (not r.startswith("z:"), -((recs.get(r) or {}).get("cited_by") or 0)))
        for a, b in itertools.combinations(ns, 2):
            if uf.find(a) != uf.find(b) and compatible(a, b):
                alias_log.append((uf.find(a), uf.find(b), f"edition/reprint: '{mt}' by {sn}"))
                uf.union(a, b)
    # same title, different first author: reviews / records with wrong author metadata that carry a book's title.
    # Guarded: main title >= 3 words, >= 10 chars, not generic, and titles compatible (no conflicting subtitles).
    GENERIC = {"introduction", "editorial", "conclusion", "preface", "foreword", "book review", "review", "editor s note", "editors note"}
    ANY_YEAR = {"discipline and punish"}  # classics whose citations sit on a decades-old review record
    bymain_any = collections.defaultdict(list)
    for n, m in recs.items():
        mt = main_title(m.get("title"))
        if mt and len(mt) >= 10 and len(mt.split()) >= 3 and mt not in GENERIC:
            bymain_any[mt].append(n)
    for mt, ns in bymain_any.items():
        ns = sorted(ns, key=lambda r: (not r.startswith("z:"), -((recs.get(r) or {}).get("cited_by") or 0)))
        for a, b in itertools.combinations(ns, 2):
            ya, yb = recs[a].get("year"), recs[b].get("year")
            near = mt in ANY_YEAR or not ya or not yb or abs(ya - yb) <= 5
            if uf.find(a) != uf.find(b) and near and compatible(a, b) and not (a.startswith("z:") and b.startswith("z:")):
                alias_log.append((uf.find(a), uf.find(b), f"same title '{mt}', different first author (review or wrong metadata)"))
                uf.union(a, b)
    # manual aliases checked by hand (DOI -> Zotero key)
    for n, m in recs.items():
        if m.get("doi") in MANUAL_ALIAS:
            k = MANUAL_ALIAS[m["doi"]]
            alias_log.append(("z:" + k, uf.find(n), f"manual: DOI {m['doi']} is an edition of {zinfo[k]['label']}"))
            uf.union("z:" + k, n)
    # citations attached to a review (or other record) that carries a Zotero book's exact title
    for k, v in zinfo.items():
        if k in DUPES: continue
        zt, zm = norm(v["title"]), main_title(v["title"])
        isbook = v["type"] in ("book", "bookSection")
        for n, m in recs.items():
            if n.startswith("z:") or uf.find(n) == uf.find("z:" + k): continue
            t = norm(m.get("title"))
            if (len(zt) >= 15 and t == zt) or (isbook and len(zm) >= 12 and main_title(m.get("title")) == zm and compatible("z:" + k, n)):
                alias_log.append(("z:" + k, uf.find(n), f"record titled like Zotero {'book' if isbook else 'work'} {v['label']} (e.g. a review)"))
                uf.union("z:" + k, n)

    groups = collections.defaultdict(set)
    for n in list(recs) + ["oa:" + i for i in all_oa] + ["s2:" + i for i in all_s2]:
        groups[uf.find(n)].add(n)

    def zkey(root):
        return root[2:] if root.startswith("z:") else None

    # ---- citers per group ----
    citers = collections.defaultdict(lambda: collections.defaultdict(set))  # root -> citing key -> {oa,s2}
    for ck, c in citing.items():
        for r in c["oa_refs"]: citers[uf.find("oa:" + r)][ck].add("oa")
        for r in c["s2_refs"]: citers[uf.find("s2:" + r)][ck].add("s2")
        for r in c.get("list_refs", []): citers[uf.find("cz:" + r)][ck].add("list")
    zroots = {"z:" + k for k in zinfo}

    # direct citations between Zotero papers
    direct = []
    for root in zroots:
        tk = root[2:]
        if tk in DUPES:
            continue
        for ck, src in citers.get(root, {}).items():
            if ck == tk or ck.startswith("OUT_"):
                continue
            direct.append((ck, tk, "both" if len(src) == 2 else next(iter(src))))

    # bibliographic coupling (per namespace, on unified groups; max not sum)
    zc = {k: c for k, c in citing.items() if not k.startswith("OUT_")}
    def refsets(c):
        if c.get("list_refs"):  # Clegg: one list, compared with both namespaces of the other paper
            s = {uf.find("cz:" + r) for r in c["list_refs"]}
            return (s, s)
        return ({uf.find("oa:" + r) for r in c["oa_refs"]}, {uf.find("s2:" + r) for r in c["s2_refs"]})
    sets = {k: refsets(c) for k, c in zc.items()}
    coupling = []
    for a, b in itertools.combinations(sorted(sets), 2):
        o = len(sets[a][0] & sets[b][0]); s = len(sets[a][1] & sets[b][1])
        if max(o, s) >= args.min_shared:
            coupling.append((a, b, max(o, s), o, s))
    coupling.sort(key=lambda x: -x[2])

    # outside papers cited by >= min-cite Zotero papers
    outside, dropped_auto = [], []
    for root, cs in citers.items():
        if root in zroots:
            continue
        zcs = {k for k in cs if not k.startswith("OUT_") and k != CLEGG}  # Clegg does not count toward the threshold
        if len(zcs) < args.min_cite:
            continue
        members = groups[root] or {root}
        # the group is shown by its most-cited OpenAlex record (falls back to any record), not by ID order
        cand = [m for m in members if m.startswith("oa:") and m in recs] or [m for m in members if m in recs and not m.startswith("cz:")] \
               or [m for m in members if m in recs]
        meta = recs[max(cand, key=lambda m: (recs[m].get("cited_by") or 0, m))] if cand else {}
        if not meta.get("title"):
            dropped_auto.append((root, None, "no metadata")); continue
        if root in drop or any(m in drop for m in members):
            dropped_auto.append((root, meta.get("title"), "drop.json")); continue
        dom = next((recs[m].get("domain") for m in members if m in recs and recs[m].get("domain")), None)
        outside.append(dict(root=root, members=sorted(members), citers=sorted(zcs), meta=meta, domain=dom,
                            theme=classify(meta.get("title"), next((recs[m].get("topic") for m in members if m in recs and recs[m].get("topic")), ""))))
    outside.sort(key=lambda o: -len(o["citers"]))

    # ---- write the database ----
    wid = {}
    def ins(**kw):
        cols = ",".join(kw); q = ",".join("?" * len(kw))
        cur = db.execute(f"INSERT INTO works({cols}) VALUES({q})", list(kw.values()))
        return cur.lastrowid
    used_oa, used_s2, used_doi = set(), set(), set()
    def uniq(v, used):
        if v and v not in used:
            used.add(v); return v
        return None
    for k, v in zinfo.items():
        wid[k] = ins(oa_id=uniq(v["oa"], used_oa), s2_id=uniq(v["s2"], used_s2),
                     doi=uniq(v["doi"], used_doi) if k not in DUPES else None,
                     title=v["title"], short_label=v["label"], year=v["year"], cited_by=v["cites"],
                     in_zotero=0 if v.get("extra_node") else 1, zotero_key=None if v.get("extra_node") else k,
                     status=v["status"], first_author=v["first_author"],
                     abstract=v["abstract"], theme=THEMES[v["theme"]])
    for k, canon in DUPES.items():
        db.execute("INSERT INTO aliases VALUES(?,?,?)", (wid[k], wid[canon], "duplicate Zotero item"))
    for o in outside:
        oa = next((m[3:] for m in o["members"] if m.startswith("oa:")), None)
        s2 = next((m[3:] for m in o["members"] if m.startswith("s2:")), None)
        m = o["meta"]
        o["work_id"] = ins(oa_id=uniq(oa, used_oa), s2_id=uniq(s2, used_s2), doi=uniq(m.get("doi"), used_doi),
                           title=m.get("title"), short_label=f"{label_name(m.get('first_author'))} {m.get('year') or ''}".strip(),
                           year=m.get("year"), cited_by=m.get("cited_by"), in_zotero=0, status="resolved",
                           first_author=m.get("first_author"), theme=THEMES[o["theme"]])
        sn = surname(m.get("first_author"))  # earliest year among records by the same author (original, not reprint)
        ys = [recs[x]["year"] for x in o["members"] if x in recs and recs[x].get("year") and surname(recs[x].get("first_author")) == sn]
        o["label"] = LABEL_FIX.get(m.get("doi")) or f"{label_name(m.get('first_author')) or (m.get('title') or '?')[:20]} {min(ys) if ys else (m.get('year') or '')}".strip()
        # extra records of the same work -> alias rows
        for extra in [x for x in o["members"] if x.startswith("oa:")][1:] + [x for x in o["members"] if x.startswith("s2:")][1:]:
            ns, i = extra.split(":", 1)
            em = recs.get(extra, {})
            aid = ins(**({"oa_id": uniq(i, used_oa)} if ns == "oa" else {"s2_id": uniq(i, used_s2)}),
                      title=em.get("title"), year=em.get("year"), in_zotero=0, status="resolved",
                      first_author=em.get("first_author"))
            db.execute("INSERT INTO aliases VALUES(?,?,?)", (aid, o["work_id"], "same work, extra record"))
    # outside records merged into Zotero works
    zalias = []
    for k in zinfo:
        root = uf.find("z:" + k)
        mine = {zinfo[k]["oa"] and "oa:" + zinfo[k]["oa"], zinfo[k]["s2"] and "s2:" + zinfo[k]["s2"]}
        for extra in sorted(groups.get(root, set())):
            if extra.startswith(("z:", "cz:")) or extra in mine:
                continue
            ns, i = extra.split(":", 1); em = recs.get(extra, {})
            aid = ins(**({"oa_id": uniq(i, used_oa)} if ns == "oa" else {"s2_id": uniq(i, used_s2)}),
                      title=em.get("title"), year=em.get("year"), in_zotero=0, status="resolved",
                      first_author=em.get("first_author"))
            db.execute("INSERT INTO aliases VALUES(?,?,?)", (aid, wid[k], "other record of Zotero work"))
            zalias.append((k, extra, em.get("title"), em.get("year")))
    for ck, c in citing.items():
        w = wid.get(ck)
        if w is None:  # deep outside paper
            root = uf.find("oa:" + c["oa"]) if c.get("oa") else uf.find("s2:" + c["s2"])
            w = next((o["work_id"] for o in outside if o["root"] == root), None)
            if w is None:
                continue
        db.executemany("INSERT OR IGNORE INTO refs VALUES(?,?,?,?)", [(w, r, "", "oa") for r in c["oa_refs"]])
        db.executemany("INSERT OR IGNORE INTO refs VALUES(?,?,?,?)", [(w, "", r, "s2") for r in c["s2_refs"]])
        rows = []
        for r in c.get("list_refs", []):  # source 'zotero': Clegg's list; IDs filled in where the entry matched a record
            g = sorted(groups.get(uf.find("cz:" + r), set()))
            oa = next((m[3:] for m in g if m.startswith("oa:")), "")
            s2 = next((m[3:] for m in g if m.startswith("s2:")), "")
            rows.append((w, oa or "zotero:" + r, s2, "zotero"))
        db.executemany("INSERT OR IGNORE INTO refs VALUES(?,?,?,?)", rows)
    db.commit()

    # ---- graph.json for the map ----
    root2id = {"z:" + k: k for k in zinfo}
    for o in outside:
        root2id[o["root"]] = "X" + str(o["work_id"])
    nodes = []
    indeg = collections.Counter(t for _, t, _ in direct)
    for k, v in zinfo.items():
        if k in DUPES:
            continue
        nodes.append(dict(id=k, label=v["label"], title=v["title"], year=v["year"], zotero=True, status=v["status"],
                          theme=v["theme"], cited_by=v["cites"] or max([(recs.get(m) or {}).get("cited_by") or 0
                                                         for m in groups.get(uf.find("z:" + k), ())] or [0]),
                          in_set=indeg[k], doi=v["doi"],
                          oa=v["oa"], s2=v["s2"], noref=not (v["oa_refs"] or v["s2_refs"] or v.get("list_refs")), note=v["note"],
                          extra=bool(v.get("extra_node")), nrefs=len(v.get("list_refs", []))))
    for o in outside:
        m = o["meta"]
        nodes.append(dict(id=root2id[o["root"]], label=o["label"], title=m.get("title"), year=m.get("year"),
                          zotero=False, theme=o["theme"], cited_by=m.get("cited_by") or 0, in_set=len(o["citers"]),
                          doi=m.get("doi"), domain=o["domain"], deep=any(("OUT_" + x.split(":", 1)[1]) in deep for x in o["members"])))
    edges = [dict(source=a, target=b, kind="cite", src=s) for a, b, s in direct]
    for o in outside:
        for ck in o["citers"]:
            src = citers[o["root"]][ck]
            edges.append(dict(source=ck, target=root2id[o["root"]], kind="cite_out", src="both" if len(src) == 2 else next(iter(src))))
        if CLEGG in citers[o["root"]]:
            edges.append(dict(source=CLEGG, target=root2id[o["root"]], kind="cite_out", src="list"))
    # deep: outside paper -> Zotero / outside
    for ck, c in citing.items():
        if not ck.startswith("OUT_"):
            continue
        sroot = uf.find("oa:" + c["oa"]) if c.get("oa") else uf.find("s2:" + c["s2"])
        sid = root2id.get(sroot)
        if not sid:
            continue
        tgt = collections.defaultdict(set)
        for r in c["oa_refs"]: tgt[uf.find("oa:" + r)].add("oa")
        for r in c["s2_refs"]: tgt[uf.find("s2:" + r)].add("s2")
        for troot, src in tgt.items():
            tid = root2id.get(troot)
            if tid and tid != sid:
                edges.append(dict(source=sid, target=tid, kind="cite_deep", src="both" if len(src) == 2 else next(iter(src))))
    shared = [dict(source=a, target=b, weight=w, oa=o, s2=s) for a, b, w, o, s in coupling]
    json.dump(dict(nodes=nodes, edges=edges, shared=shared, themes=THEMES), open(os.path.join(BASE, "graph.json"), "w"), ensure_ascii=False)

    # ---- summary ----
    L = lambda k: zinfo[k]["label"] if k in zinfo else k
    print(f"\nZotero items: {len(zinfo)}  resolved: {sum(v['status']=='resolved' for v in zinfo.values())}  "
          f"doubtful (held out): {[k for k,v in zinfo.items() if v['status']=='doubtful']}  "
          f"unresolved: {[L(k) for k,v in zinfo.items() if v['status']=='unresolved']}")
    print(f"Direct citations inside the set: {len(direct)}  (both {sum(s=='both' for *_,s in direct)}, "
          f"OA only {sum(s=='oa' for *_,s in direct)}, S2 only {sum(s=='s2' for *_,s in direct)})")
    print("\nMost-cited within the set:")
    for k, n in indeg.most_common(12):
        print(f"  {n:2d}  {L(k)} — {zinfo[k]['title'][:70]}")
    linked = {a for a, _, _ in direct} | {b for _, b, _ in direct} | {a for a, *_ in coupling} | {b for _, b, *_ in coupling}
    print("\nUnconnected (no direct citation, no shared-reference pair ≥ %d):" % args.min_shared)
    for k, v in zinfo.items():
        if k not in linked and k not in DUPES:
            print(f"  {v['label']:<24} [{v['status']}]")
    print("\nNo reference list in either source (outgoing links missing):")
    for k, v in zinfo.items():
        if k in DUPES or zinfo[k].get("extra_node"): continue
        a = agents.get(k) or {}
        if not a.get("oa_refs") and not a.get("s2_refs"):
            print(f"  {v['label']:<24} {(v['note'] or '')[:80]}")
    print("\nThin reference lists (< 5 refs in both):")
    for k, v in zinfo.items():
        a = agents.get(k) or {}
        n = max(len(a.get("oa_refs", [])), len(a.get("s2_refs", [])))
        if 0 < n < 5: print(f"  {v['label']:<24} {n}")
    print("\nStrongest shared-reference pairs (max of OA/S2 overlap):")
    for a, b, w, o, s in coupling[:15]:
        print(f"  {w:3d}  {L(a)}  ↔  {L(b)}   (OA {o}, S2 {s})")
    print(f"\nOutside papers cited by ≥{args.min_cite} Zotero papers: {len(outside)}")
    for o in outside[:25]:
        m = o["meta"]
        print(f"  {len(o['citers']):2d}  {o['label']:<22} {(m.get('title') or '')[:60]}  [{THEMES[o['theme']][:14]}]{'  DOMAIN='+o['domain'] if o['domain'] in OFF_DOMAINS else ''}")
    print("\nBridging outside papers (cited from ≥3 themes):")
    br = []
    for o in outside:
        th = {zinfo[k]["theme"] for k in o["citers"]}
        if len(th) >= 3: br.append((len(th), len(o["citers"]), o, th))
    for nth, nc, o, th in sorted(br, key=lambda x: (-x[0], -x[1]))[:15]:
        print(f"  {nth} themes / {nc} papers  {o['label']:<20} {(o['meta'].get('title') or '')[:55]}")
    print("\nSuspicious outside matches (off-topic domain) — candidates for drop.json:")
    for o in outside:
        if o["domain"] in OFF_DOMAINS:
            print(f"  {o['root']:<18} {o['label']:<20} {(o['meta'].get('title') or '')[:60]}  [{o['domain']}]")
    print("\nAlias merges among outside records:")
    for a, b, why in alias_log:
        print(f"  {recs.get(a,{}).get('title','?')[:45]} ({recs.get(a,{}).get('year')})  ⇐  {recs.get(b,{}).get('title','?')[:45]} ({recs.get(b,{}).get('year')})  [{why}]")
    print("\nOutside records merged into Zotero works:")
    for k, extra, t, y in zalias:
        print(f"  {L(k):<22} ⇐ {extra:<16} {(t or '')[:55]} ({y})")
    if CLEGG in zinfo:
        cl = [(t, s) for a, t, s in direct if a == CLEGG]
        clo = [o for o in outside if CLEGG in citers[o["root"]]]
        matched = sum(1 for r in zinfo[CLEGG]["list_refs"] if any(m.startswith(("oa:", "s2:", "z:")) for m in groups.get(uf.find("cz:" + r), ())))
        print(f"\nClegg 1989: {len(zinfo[CLEGG]['list_refs'])} references in Lauren's list; {matched} match a record cited in the set")
        print("  cites these collection papers:", [L(t) for t, _ in cl])
        print(f"  cites {len(clo)} of the {len(outside)} outside papers:", [o["label"] for o in clo][:40])
        print("  cited by:", [L(a) for a, t, _ in direct if t == CLEGG])
        print("  shared references with:", [(L(b if a == CLEGG else a), w) for a, b, w, *_ in coupling if CLEGG in (a, b)][:15])
    print("\nTop outside papers for step 5:")
    for o in outside[:10]:
        print(f"  {o['root']:<18} {len(o['citers'])}  {o['label']}  {(o['meta'].get('title') or '')[:60]}")


if __name__ == "__main__":
    main()
