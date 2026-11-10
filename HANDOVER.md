# Handover: power citation map and the Clegg references

Two pieces of work, done with Claude Code in November 2026:

1. **A citation map of the Zotero collection "power"**: how the papers in it cite each other and what they
   cite in common.
2. **Clegg's *Frameworks of Power* (1989)**: DOIs and ISBNs for Lauren's transcription of its reference list,
   corrections to those Zotero records, and Clegg added to the map.

Everything here can be re-run. The scripts are plain Python (standard library only). Claude did the
orchestration, and cheap Claude Haiku agents did the parts that needed judgement (is this record the same
paper?).

---

## 1. The citation map

### Scope

- **Source:** Zotero group library *vidi* (group ID `6719726`), collection **power** (`94G2HG42`) including its
  subcollections (classic power, infrastructural power, platform power, training programs): **57 items**.
- **Not in scope:** the identically named collection in the personal library, which holds 8 of the same papers.
- **Data sources:** OpenAlex and Semantic Scholar (S2), queried with free API keys.

### Pipeline

| Step | What | Code / output |
|---|---|---|
| 1 Inventory | List the collection: title, authors, year, DOI, key. DOIs are read from the local Zotero database, because the MCP listing omits them. | `zotero_items.json` |
| 2 Database | SQLite with `works`, `refs` (source `oa`, `s2` or `zotero`) and `aliases`. Only the merge script writes to it. | `citations.sqlite` |
| 3 One agent per paper | 54 Haiku agents. Each resolves its paper in OpenAlex and S2, checks title, first author and year, and fetches both reference lists through `scripts/fetch_one.py`. | `agents/<zotero_key>.json` |
| 4 Merge and link | Unify records, compute direct citations, shared references and outside papers, then print a summary. | `scripts/merge.py` → `graph.json`, `merge_summary.txt` |
| 5 One level deeper | The 10 most-cited outside papers get their own reference lists fetched (`agents/OUT_*.json`). | linked in step 4 |
| 6 Map | A standalone d3 page with the data embedded. | `scripts/build_map.py`, `scripts/map_template.html` → `power-map.html` |

### Rules that matter when reading the map

- **Direct citation A → B:** B's OpenAlex or S2 ID appears in A's reference list. Line style shows the source: solid for both sources, dashed for S2 only, dotted for OpenAlex only, dash-dot for Clegg's list.
- **Shared references:** two collection papers that cite at least 2 of the same works (bibliographic coupling). The count is the **maximum** of the OpenAlex and S2 overlaps, never their sum, which would double-count.
- **Outside papers:** works cited by at least 2 collection papers that aren't in the collection themselves (172 of them).
- **Unifying records:** the same work often appears as several OpenAlex or S2 records. Records are merged when they match on:
  - DOI;
  - exact title, first author and year within ±1;
  - edition or reprint: the same main title and author, where at least one record has no subtitle, so two works with different subtitles stay apart;
  - book reviews and records with wrong author metadata that carry a book's exact title. Citations often land on these records instead of the book. Requires ≥ 3 title words, years within ±5 and no generic titles;
  - three manual fixes in `merge.py` (`MANUAL_ALIAS`, `LABEL_FIX`).
  
  The full list of merges is in `merge_summary.txt`.
- **Themes** (colour plus shape):
  - collection papers: assigned by hand from titles and abstracts (`ZTHEME` in `merge.py`);
  - outside papers: a rough keyword rule on the title and OpenAlex topic.
  
  Six colours can't all be told apart, especially by colour-blind readers, so each theme also has its own node shape.

### Decisions taken along the way

- **Doubtful matches,** both accepted:
  - Lukes, *Power: A Radical View*: the only OpenAlex record is the 1974 edition, oddly carrying a 1993 *Politologija* DOI.
  - Burkhardt 2019: the transcript chapter and its mediarep copy are treated as one work.
- **Not resolvable at all:**
  - the Meta blog post and the Common Wealth web page;
  - the Ada Lovelace Institute report;
  - Cheney-Lippold's *We Are Data*, which exists only as book reviews in both sources.
- **Duplicate in the collection:** Star 1999 is in Zotero twice; LDVMWKLZ is aliased to 5SFWEQ3K.

### Results (latest run)

- **Size:** 229 nodes (56 collection papers, Clegg 1989 and 172 outside works), 61 direct citations and 102 shared-reference pairs.
- **Most cited within the set:** van Dijck et al. 2019 *Reframing platform power* (6), then Star 1999, Bucher 2018 and van der Vlist & Helmond 2021 (4 each).
- **Strongest shared-reference pairs:** Avelino 2009 ↔ Avelino 2021 (19), van der Vlist 2021 ↔ 2022 (11), Lawo 2026 ↔ Avelino 2021 (11), Lomborg ↔ Flensburg (9).
- **Outside works linking themes:** *The Platform Society*, Cohen's *Between Truth and Power* and Foucault's *Discipline and Punish*. Plantin et al. 2016 is the most cited outside work (12 papers).

### Caveats

- **Semantic Scholar often returns no reference list** ("publisher elided"): 22 of 49 papers. OpenAlex carries most links, which is why many arrows are dotted.
- **No reference list in either source,** so what they cite is missing: Mertens 2026, Abu Elyounes 2021, D'Ignazio & Klein 2020 and Van Rosmalen 2026. Very thin lists: Emerson, Lukes, Castells, Gilbert, Richards & Hartzog, Lynskey 2019.
- **Unconnected papers:** about 15 collection papers have no link at all, mostly 2025–26 HCI/privacy papers and items with no data.
- **Possibly wrong merge:** "Power and Knowledge" 2010 ⇐ 2015 may be two different works.

---

## 2. Clegg, *Frameworks of Power*: references, identifiers and Zotero fixes

Lauren transcribed the book's bibliography into **power → clegg references** (`H7YHCSFB`). The aim was to
find a DOI or ISBN for every entry, fix the records, and add Clegg to the map.

### Finding identifiers (`clegg/`)

1. **`resolve_ids.py`, automatic pass:**
   - DOIs: an existing Zotero DOI is checked in Crossref; otherwise Crossref and then OpenAlex are searched.
   - ISBNs: Open Library, preferring the edition whose year matches the cited year; Google Books as a fallback.
   - Every match is scored on title, first author, **type** (book ↔ book, so a JSTOR review isn't taken for the book) and year.
   - It runs 4 workers with per-service pacing. Google Books rate-limits keyless clients quickly and is switched off after the first refusal.
2. **Review:** 145 uncertain items went to 6 Haiku reviewers in batches of 25, using `lookup.py`. Their verdicts are in `review/batch_*_out.json`.
3. **`retry_missing.py`:** a second pass for the not-found items. Open Library files translated books under their original-language title (*Legitimationsprobleme…*, *Philosophische Untersuchungen*), so the retry matches English editions inside those records.
4. **`compile_ids.py`** → `clegg_identifiers.csv` / `.json`: **398 of 427 usable references** have a DOI or ISBN. The 29 without one are mostly chapters, conference papers and newspaper pieces.

### Checked against the source

The SAGE online edition's bibliography (436 references) was compared with the Zotero list, item by item, in
the browser. Results:

- **10 references were missing** and have been added: Lukes 1974, 1976, 1977 and 1982, Locke 1959, Lockwood 1964, Ball 1978 and 1988, Littler & Salaman 1982, and Benton 1977.
- **Several "problems" found earlier were faithful to Clegg:**
  - Jessop 1987 really is a mimeo, and Meyer 1987 a conference paper.
  - "The Social Theory of Talcott Parsons" is Clegg's own (wrong) title for Savage 1981.
  - Wilkinson & Oliver 1988 has no title in Clegg's list either.
  - Cutler et al. is cited as two volumes (1979a/b).
- **Spellings:** Zotero is right where Clegg's list has typos (Asad, Elliott, Gutman, McLennan, Oestreich, Lieff).

### What changed in the Zotero group library

Every change was made through the Zotero MCP and read back through it afterwards. Changed items are tagged:

| Tag | Meaning | Items |
|---|---|---|
| `clegg-ids-added` | DOI/ISBN filled into an empty field (no existing value overwritten) | 287 |
| `clegg-ids-in-fields` | an identifier first parked in Extra as "Other edition …" moved into the DOI/ISBN field | 113 |
| `clegg-fix-applied` | metadata corrections (below) | ~30 |
| `added-from-clegg-bibliography` | new records | 11 |

Corrections:
- **Item types:**
  - *Powers of Theory*: web page → book (Alford & Friedland, CUP 1985).
  - *Lenin and Philosophy*: journal article → book (Althusser; Brewster as translator).
  - *The Origins of Capitalism*: web page → book (Baechler, Blackwell 1975).
  - Ball, "Models of Power": web page → article in *J. Hist. Behavioral Sciences* 11(3).
- **Bare PDFs given parent records:** the Benton preview PDF and the "Two Faces of Power" PDF (a new Bachrach & Baratz 1962 record).
- **Wilkinson & Oliver 1988:** title "Editorial" (*Industrial Relations Journal* 19(1)), with its DOI.
- **Cutler et al.:** the two records' volume numbers swapped, so the vol. 1 ISBN sits on vol. 1.
- **Dates:**
  - 4 blank dates filled with Clegg's year;
  - 13 reprint-dated items got Clegg's year in Zotero's **Original Date** field. The edition data stays as entered.

**Edition mismatches:** after the move into proper fields, some DOIs and ISBNs belong to **a different edition** from the one in the record. For example, a 1948 Weber record carries a 2014 Routledge DOI. `clegg_identifiers.csv` keeps the edition year of every identifier. The pre-change Extra values are backed up on Matteo's machine (not in this repo, because they hold other Extra data).

**Still open:** see [`clegg/zotero_fixes.md`](clegg/zotero_fixes.md).
- V2IC7W53 is a saved link to "american_bachrach.pdf", either the 1962 or the 1963 Bachrach & Baratz article.
- Five small year differences against Clegg.
- 29 references without an identifier.

### Clegg on the map

- **How it's added:** *Frameworks of Power* is a filled "Added reading" node. Its arrows come from Lauren's list (`scripts/export_clegg_refs.py` → `clegg/clegg_refs_for_map.json`). Each entry runs through the same unification rules, so it links to whatever record the collection papers cite.
- **Threshold:** Clegg doesn't count toward the "cited by ≥ 2" rule for outside papers.
- **Finding:** only **18 of 439** of Clegg's references overlap with anything the collection cites. On the map, Clegg points to Lukes, *Discipline and Punish*, Bachrach & Baratz 1962 and Mann 1986. It shares references with Avelino 2021 (6), Avelino 2009, Lawo 2026 and Culpepper 2020 (4 each) and Emirbayer 1997 (3). Lawo and both Avelino papers cite it.
- **Not a matching gap:** most of Clegg's canon (Dahl, *Who Governs?*, Weber's *Economy and Society*, Habermas) is simply never cited by these 2010s–2020s papers. This was checked by hand.

---

## Files

```
zotero_items.json          inventory of the power collection
agents/                    one JSON per paper (+ OUT_* for the deeper step)
citations.sqlite           works / refs / aliases
graph.json                 nodes and edges for the map
merge_summary.txt          last merge: rankings, gaps, every alias merge
power-map.html             the map (standalone); power-map-artifact.html = same page for claude.ai
scripts/
  fetch_one.py             per-paper resolver + reference download (used by the agents)
  merge.py                 step 4 (and 5): load, unify, link, write db + graph.json
  export_clegg_refs.py     reads 'clegg references' from the local Zotero DB for the merge
  map_template.html        the map page; build_map.py embeds graph.json into it
clegg/
  clegg_items.json         Lauren's list as first exported (433 items)
  resolve_ids.py lookup.py retry_missing.py compile_ids.py   identifier pipeline
  review/                  Haiku review verdicts
  clegg_identifiers.csv    one row per reference: DOI, ISBN, edition year, source, status, note
  zotero_fixes.md          what changed in Zotero and what is still open
```

## Continuing

- **Re-run after Zotero changes:**
  ```bash
  python3 scripts/export_clegg_refs.py
  python3 scripts/merge.py --accept N8JCSANG,SI2UUXBS
  python3 scripts/build_map.py
  ```
- **New papers in the collection:** add them to `zotero_items.json` (or ask Claude to redo step 1), then run one agent per new paper with `fetch_one.py` (see `CLAUDE.md`), then merge.
- **Possible next steps:**
  - fetch reference lists for more outside papers (step 5 with a higher N);
  - add more books the way Clegg was added;
  - check the 29 unidentified Clegg references by hand.
