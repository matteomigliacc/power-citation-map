# Power citation map

A citation map of the Zotero collection **power** (shared group library *vidi*) and of Clegg's
*Frameworks of Power* (1989), whose reference list Lauren transcribed into the subcollection **clegg references**.

**Live map:** <https://claude.ai/artifact/QwivkLdkRPJJQT7gjDFSLZ> (same page as `power-map.html` in this repo;
open the HTML file in any browser).

It shows how the 56 papers in the collection relate: who cites whom (from OpenAlex and Semantic Scholar
reference lists), which pairs share references, and the 172 outside works that at least two of them cite.

| Read | For |
|---|---|
| [HANDOVER.md](HANDOVER.md) | What was done, the decisions behind it, results, caveats, and what changed in Zotero |
| [SETUP.md](SETUP.md) | Setting up Claude (Desktop or Code), Zotero, the Zotero MCP and the API keys to continue the work |
| [CLAUDE.md](CLAUDE.md) | Context Claude Code reads automatically when you open this folder |

## Quick start

```bash
git clone https://github.com/matteomigliacc/power-citation-map.git && cd power-citation-map
cp .env.example .env            # add your OpenAlex and Semantic Scholar keys
python3 scripts/merge.py --accept N8JCSANG,SI2UUXBS   # rebuild database + graph.json (uses agents/*.json)
python3 scripts/build_map.py    # writes power-map.html and power-map-artifact.html
open power-map.html
```

The scripts use only the Python standard library (3.9+). The first `merge.py` run refetches metadata for
about 4,500 cited records, because the API caches are not in the repo; that takes a few minutes.
