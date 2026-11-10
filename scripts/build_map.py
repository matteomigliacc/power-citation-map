#!/usr/bin/env python3
"""Step 6: embed graph.json into the map template -> power-map.html (standalone)."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
g = json.load(open(os.path.join(BASE, "graph.json")))
# keep the page lean: drop fields the map does not use
for n in g["nodes"]:
    n.pop("domain", None); n.pop("deep", None)
data = json.dumps(g, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
nz = sum(1 for n in g["nodes"] if n["zotero"] and not n.get("extra"))
ne = sum(1 for n in g["nodes"] if n.get("extra"))
no = len(g["nodes"]) - nz - ne
nd = sum(1 for e in g["edges"] if e["kind"] == "cite")
about = (f"{nz} papers from the Zotero collection “power” (filled nodes) and {no} outside papers that at least two of them cite "
         f"(hollow nodes). Links come from the reference lists in OpenAlex and Semantic Scholar: {nd} direct citations between "
         f"collection papers and {len(g['shared'])} pairs that share two or more references. "
         + (f"Clegg's Frameworks of Power (1989) is added as a reading; its links come from Lauren's transcription of its reference list. " if ne else "")
         + "Some papers have no reference list in either source; they are listed under Coverage gaps.")
html = open(os.path.join(HERE, "map_template.html")).read().replace("/*DATA*/", data).replace("/*ABOUT*/", about)
out = os.path.join(BASE, "power-map.html")
open(out, "w").write(html)
# artifact version: the publisher supplies the document wrapper, so drop ours
art = html.replace('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n', "")
art = art.replace("</head>\n<body>\n", "").replace("</body>\n</html>\n", "")
assert "<head>" not in art and "<body>" not in art and art.lstrip().startswith("<title>")
open(os.path.join(BASE, "power-map-artifact.html"), "w").write(art)
print(f"wrote {out}: {len(g['nodes'])} nodes, {len(g['edges'])} citation links, {len(g['shared'])} shared-reference pairs, {len(html)//1024} KB")
