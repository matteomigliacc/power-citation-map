# Power citation map: notes for Claude

Citation map of the Zotero collection **power** plus Clegg's *Frameworks of Power*. Read HANDOVER.md for the
full history and decisions; SETUP.md for the environment.

## Zotero
- The data lives in the **group library "vidi" (group ID 6719726)**, not the personal library. Switch to it
  first: `zotero_switch_library(library_id="6719726", library_type="group")`.
- Collections: power `94G2HG42` (with subcollections); clegg references `H7YHCSFB` (Clegg's bibliography,
  transcribed by Lauren, checked against the SAGE back matter).
- The MCP listing does not return DOIs; scripts read a **copy** of `~/Zotero/zotero.sqlite` (+ `-wal`) for
  bulk reads. Never write to that file. All writes go through the Zotero MCP.
- Before any write to the group library: say what will change, ask, back up current values, tag the changed
  items, verify afterwards by reading back through the MCP. Only fill empty fields unless told otherwise.

## Pipeline
- `scripts/fetch_one.py candidates|write` — per-paper resolver used by Haiku agents (one per paper); writes
  `agents/<key>.json` only. API keys come from `.env`; never print or read it into the conversation.
- `scripts/merge.py --accept N8JCSANG,SI2UUXBS` — the only writer of `citations.sqlite`; produces
  `graph.json` and `merge_summary.txt`. Doubtful matches stay out unless listed in `--accept`.
- `scripts/export_clegg_refs.py` then `merge.py` adds Clegg (node `CLEGG1989`, source `list`/`zotero`).
- `scripts/build_map.py` — embeds `graph.json` into `scripts/map_template.html` → `power-map.html` and
  `power-map-artifact.html` (the latter is published at claude.ai/artifact/QwivkLdkRPJJQT7gjDFSLZ).
- `clegg/` — identifier pipeline: `resolve_ids.py` (auto), `lookup.py` (helper for reviewers),
  `retry_missing.py`, `compile_ids.py` → `clegg_identifiers.csv`.

## Conventions
- Keep it cheap: scripts do bulk API work; Haiku agents only for judgement (is this the same work?).
- Shared references = max of the OpenAlex and S2 overlaps, never the sum.
- Never accept a book review, a reprint chapter or a different edition as the work itself without saying so.
- Crossref/Open Library/Google Books are rate-limited: keep per-host pacing; Google Books keyless quota is tiny.
