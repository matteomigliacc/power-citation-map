# Setup: Claude, Zotero and the MCP

This gets you to the point where you can open this repo in Claude and say "re-run the merge" or
"find DOIs for the new items in clegg references", and Claude can read and write the shared Zotero library.
macOS is assumed (that's what this was built on); Windows and Linux differ only in paths.

## 1. Claude

You need a paid Claude plan (Pro or Max). Pick one way to run Claude Code:

- **Claude Desktop** (what Matteo uses). Download it from <https://claude.ai/download>, sign in, and use the
  **Code** tab. Open this repo folder as the project. It has a built-in browser pane, which was used to read
  the SAGE bibliography.
- **Claude Code CLI**, if you prefer the terminal:
  ```bash
  curl -fsSL https://claude.ai/install.sh | bash   # or: npm install -g @anthropic-ai/claude-code
  cd power-citation-map && claude
  ```

Either way, Claude reads [`CLAUDE.md`](CLAUDE.md) in this folder automatically. That's where the project
context lives.

## 2. Zotero

- **Zotero 10** desktop (built with 10.0.8). Join the **vidi** group library if you haven't already, and let it sync.
- **Local API:** Settings → Advanced → tick **Allow other applications on this computer to communicate with
  Zotero**. The MCP talks to the running Zotero app through this, so Zotero must be open while you work.

## 3. The Zotero MCP server

The MCP server is [`zotero-mcp-server`](https://pypi.org/project/zotero-mcp-server/) (built with 0.15.2),
installed with [uv](https://docs.astral.sh/uv/):

```bash
brew install uv                                   # or: curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install "zotero-mcp-server[all]"          # installs the zotero-mcp command in ~/.local/bin
zotero-mcp setup                                  # local mode; writes the Claude Desktop config for you
zotero-mcp authorize-local                        # Zotero shows a dialog: choose "Always Allow" (needed for writes)
```

`setup` asks about semantic search. It's optional and wasn't used here, so `--skip-semantic-search` is fine.

**Claude Desktop:** restart it after `setup`. The config lands in
`~/Library/Application Support/Claude/claude_desktop_config.json`, roughly:

```json
{ "mcpServers": { "zotero": { "command": "/Users/<you>/.local/bin/zotero-mcp", "env": { "ZOTERO_LOCAL": "true" } } } }
```

**Claude Code CLI:** register the same server there too:

```bash
claude mcp add zotero -s user -e ZOTERO_LOCAL=true -- ~/.local/bin/zotero-mcp
```

**Check it works:** ask Claude "list my Zotero libraries". You should see your personal library and **vidi**
(group 6719726). The power collection lives in the group library, so tell Claude to switch to it
("switch to the vidi group library"). `CLAUDE.md` already says so.

If writes fail with "no writable backend", run `zotero-mcp authorize-local` again with Zotero open.

## 4. API keys for OpenAlex and Semantic Scholar

Both are free and make the lookups much more reliable. OpenAlex title search is throttled without a key.

- **OpenAlex:** get a free API key via <https://openalex.org/rest-api> (the page OpenAlex itself points to
  when it rate-limits anonymous requests).
- **Semantic Scholar:** request a key at <https://www.semanticscholar.org/product/api#api-key-form>. It takes a
  day or two; everything runs without it, only slower.

```bash
cp .env.example .env    # then fill in OPENALEX_API_KEY and S2_API_KEY
```

`scripts/fetch_one.py` reads `.env` and sends the keys with each request. Agents and logs never see them.
`.env` is git-ignored, so don't paste keys into the chat.

## 5. Python

Python 3.9 or newer, standard library only. Nothing to install.

```bash
python3 scripts/merge.py --accept N8JCSANG,SI2UUXBS && python3 scripts/build_map.py && open power-map.html
```

`scripts/export_clegg_refs.py` and the database checks read a **copy** of `~/Zotero/zotero.sqlite`. They never
write to it; all writes go through the MCP. If your Zotero data directory is elsewhere, change the path at the
top of that script.

## 6. Working with Claude on this

Things that worked well, so you don't have to rediscover them:

- **Say how cheap you want it.** For example: "Python scripts do the bulk API work, Haiku agents only where
  judgement is needed." Claude then writes a script and hands only the uncertain cases to agents.
- **Ask for the plan before writes.** Zotero writes go to the shared library. Claude asks before changing
  records, tags every change and keeps a backup. Keep it that way.
- **Agents write files; only the merge script writes the database.** That keeps `citations.sqlite` free of
  duplicates and locking problems.
- **Check matches yourself where it matters.** Reviews of a book, reprints and editions with the wrong year are
  the usual traps. `merge_summary.txt` lists every merge so you can spot bad ones.
- **Long runs:** ask Claude to show a live log in a terminal tab. It can run background jobs and tell you when
  they finish.
