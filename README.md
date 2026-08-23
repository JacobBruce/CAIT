<!-- mcp-name: io.github.JacobBruce/CAIT -->
# CAIT - Core AI Toolkit

A modular [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that extends AI assistants with practical capabilities: file I/O, a persistent Python REPL, Python AST-aware code search, semantic text search, document conversion, Wikipedia & arXiv tools, a persistent vector memory database, and other general utilities.

A total of **40 tools across 9 modules**. Each module can be disabled independently via the `CAIT_DISABLE` environment variable. Made by AI for AI.

## Requirements

- Python 3.11+
- Core: `fastmcp`, `chromadb`
- Online research: `wikipedia-api`, `arxiv`
- Document conversion: `docling` or `markitdown[all]` (or `markitdown[pdf]` for PDF-only)
- Scientific computing (optional, for REPL use): `sympy`, `scipy`, `matplotlib`, `plotly`, `vispy`

## Installation

```bash
git clone https://github.com/JacobBruce/CAIT
cd CAIT
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Replace MarkItDown with Docling in `requirements.txt` if you want higher-quality layout-aware conversion (slower, heavier).

## Agents & Skills

CAIT includes several agent files, instructions/rules, and skills. To get the most from CAIT you should install [AGENTS.md](instructions/AGENTS.md) into your work environment (see **Agent Instructions** below).

The instructions include general guidance for how to behave, how to use CAIT tools, and how to use the Firecrawl search tools. The instructions may need to be adapted to suit different setups.

If you are working in a Python environment you may want to make use of this agent prompt: [python-coder.agent.md](agents/python-coder.agent.md). There is also [research-assistant.agent.md](agents/research-assistant.agent.md) for deep research.

For C++ programmers there is [cpp-style-guidelines.md](instructions/cpp-style-guidelines.md), although many of the guidelines are my personal preferences and may need to be adapted to other projects.

For project planning and onboarding, CAIT also includes these two complementary skills:

- [project-survey.md](skills/project-survey.md) — orient in an unfamiliar codebase; produces `SURVEY.md`
- [project-planning.md](skills/project-planning.md) — plan new features or roadmaps; produces `PLAN.md` and `TASKS.md`

**New:** CAIT now includes [game-master.agent.md](agents/game-master.agent.md) to help agents act as the Game Master of a roleplaying text-based adventure, with optional image generation support.

It contains detailed "Game Master Protocols" with a well thought out Markdown file system for maintaining the state of a roleplay world. There is also an accompanying [skill](skills/new-roleplay-world/) to help the agent setup a new roleplay world.

### Agent Instructions

To use the agent instructions, rename [AGENTS.md](instructions/AGENTS.md) and place it in the correct location:

| Tool | Where to put a copy |
|------|---------------------|
| **Cursor** | User rule, or `AGENTS.md` at project root |
| **Claude Code** | `CLAUDE.md` at project root (or `~/.claude/CLAUDE.md` globally) |
| **GitHub Copilot** | `.github/copilot-instructions.md` |
| **Other** | `AGENTS.md` at project root — increasingly recognized across tools |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CAIT_FILES_PATH` | `~/.cait/files/` | Directory for downloaded files and document conversion cache |
| `CAIT_MEMORY_PATH` | `~/.cait/memory` | ChromaDB storage for the persistent memory database |
| `CAIT_WORKSPACE` | process cwd | Host-supplied project folder. Relative paths (`README.md`, omitted `find_*` path) resolve here, not against MCP `cwd`. |
| `CAIT_DISABLE` | _(empty)_ | Comma-separated module names to exclude at startup (e.g. `wiki,arxiv`) |

Keep MCP `cwd` / `PYTHONPATH` pointing at the **CAIT install**. Set `CAIT_WORKSPACE` to the repo you are editing. Hosts that interpolate `${workspaceFolder}` (Cursor, VS Code Copilot, AI UI) use this one-time env line:

```json
"CAIT_WORKSPACE": "${workspaceFolder}"
```

## Client Configuration

### VS Code (GitHub Copilot)

Add to your workspace `.vscode/mcp.json` or user `settings.json`:

```json
{
  "servers": {
    "bitfreak/cait": {
      "type": "stdio",
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "cait.server"],
      "cwd": "/absolute/path/to/CAIT",
      "env": {
        "PYTHONPATH": "/absolute/path/to/CAIT",
        "CAIT_WORKSPACE": "${workspaceFolder}"
      }
    }
  }
}
```

> For user `settings.json`, nest the above under `"mcp": { ... }`.

Copy [AGENTS.md](instructions/AGENTS.md) to `.github/copilot-instructions.md` in your project.

### Claude Desktop

Edit `claude_desktop_config.json`:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "bitfreak/cait": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "cait.server"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/CAIT",
        "CAIT_WORKSPACE": "/absolute/path/to/your/project"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add cait -e PYTHONPATH=/absolute/path/to/CAIT \
  -e CAIT_WORKSPACE=/absolute/path/to/your/project \
  -- /absolute/path/to/.venv/bin/python -m cait.server
```

Copy [AGENTS.md](instructions/AGENTS.md) to your project root as `CLAUDE.md` (or `~/.claude/CLAUDE.md` for global use).

### Cursor

Add to your user `~/.cursor/mcp.json` (or project `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "cait": {
      "command": "/absolute/path/to/CAIT/.venv/bin/python",
      "args": ["-m", "cait.server"],
      "cwd": "/absolute/path/to/CAIT",
      "env": {
        "PYTHONPATH": "/absolute/path/to/CAIT",
        "CAIT_WORKSPACE": "${workspaceFolder}"
      }
    }
  }
}
```

**`PYTHONPATH` must point at the CAIT repo root** (the directory that contains the `cait/` package), not a `.venv` path. The MCP `command` is the interpreter (`…/.venv/bin/python`); `PYTHONPATH` is where `import cait` is resolved. Cursor does not always honor `cwd` for MCP subprocesses, so `PYTHONPATH` is required for `python -m cait.server` to resolve.

Add [AGENTS.md](instructions/AGENTS.md) as a user or project rule (Settings → Rules, Skills, Subagents), or copy it to `AGENTS.md` in the project root.

### AI UI

Same env line in `~/.aiui/mcp.json`. AI UI expands `${workspaceFolder}` at spawn (open project, or `~/.aiui` on Home). Keep `cwd` as the CAIT install.

## Recommended MCP Servers

### Firecrawl

[Firecrawl](https://firecrawl.dev) is a web scraping and search API that pairs naturally with CAIT, adding powerful web search, full-page scraping, and site crawling. A free API key is available at [firecrawl.dev](https://firecrawl.dev).

### Serena

[Serena](https://github.com/oraios/serena) provides many tools for semantic code retrieval and editing. Both CAIT and Serena include a similar memory system so it is recommended to disable one of them.

### codebase-memory-mcp

[codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) indexes a repository into a persistent **knowledge graph** (functions, classes, call chains, HTTP routes, packages) and exposes structural queries over MCP.

## Tool Reference

### File System — `fs`

| Tool | Description |
|------|-------------|
| `get_file_info` | Metadata for a single file: size, line count, permissions, timestamps. Does not read content. |
| `get_dir_info` | One-directory listing (size, permissions, timestamps). Prunes junk dirs while walking; `max_results` default 100. Not a file finder. |
| `read_file` | Stream a text file (does not slurp it). `lineno\|text` prefixes. `offset` + `limit` (negative `limit` = tail, e.g. `-50`). `has_more` if later lines exist; `truncated` only if the byte cap cut the payload. `total_lines` only when the pass reached EOF. |
| `search_file` | In-file regex grep. Returns match lines; `context=N` adds grep `-C` bodies (`(?i)` for case-insensitive). Optional `offset`/`limit` scopes the window. |
| `write_file` | Write text to a file. `mode='replace'` (default) creates/overwrites; `mode='append'` adds to an existing file (NOTES.md, TASKS.md, logs). |
| `download_file` | Download a URL to `~/.cait/files/` (or `CAIT_FILES_PATH`). 30s timeout, User-Agent set, 100 MB cap. |
| `fetch_url` | HTTP GET/POST with timeout, User-Agent, and a 20 MB body cap. Use `save_to` for large pages. `convert=True` returns markdown and omits raw HTML (inline text capped ~100KB). |

### Persistent Python REPL — `repl`

> **Security:** `repl_exec` runs arbitrary Python as the same OS user as the MCP server, with full filesystem and network access. Only enable the REPL module in environments you trust.

| Tool | Description |
|------|-------------|
| `repl_exec` | Execute Python code in a persistent session. Variables, imports, and function definitions survive between calls. Returns stdout, stderr, and exception info. |
| `repl_read` | Inspect a named variable from the REPL session without executing code. Returns repr, type, and JSON value. |
| `repl_vars` | List all user-defined variables in the current REPL session. Returns name, type, repr, and JSON value for each. Useful for reviewing session state without running code. |
| `repl_reset` | Clear all variables and imports from the REPL session. |

### Code Analysis — `code`

**Python only.** These tools parse `.py` files with the `ast` module. They skip comments and strings (unlike text grep) and do **not** search C, C++, JavaScript, or other languages.

| Tool | Description |
|------|-------------|
| `find_definitions` | Find definitions of a function, class, or variable in Python (including tuple unpack). Capped at 200 hits. |
| `find_calls` | Find call sites of a Python function. Matches bare calls, method calls, and chained calls. Capped at 200 hits. |
| `find_imports` | Find Python files that import a given module or name. Capped at 200 hits. |
| `find_references` | Find uses of a Python identifier (loads, stores, deletes, attribute accesses, import aliases). Capped at 200 hits. |

### Text Search & Embeddings — `text`

Uses `all-MiniLM-L6-v2` (bundled with ChromaDB — no separate download). Chunk embeddings are cached in memory so repeated queries on the same document skip re-embedding.

| Tool | Description |
|------|-------------|
| `search_text` | Semantically search or summarize a text string or plain text file (`.txt`, `.md`, `.rst`). Query given → extract mode (most relevant chunks). Query empty → summarize mode (most representative chunks). |
| `encode_text` | Return 384-d embeddings for one or more strings or files. Use `save_to` to write JSON and omit the vectors from the response. |
| `text_similarity` | Cosine similarity between two texts (0–1). |
| `diff_text` | Unified diff between two strings or files. Returns diff text plus added/removed line counts. |

### Document Tools — `document`

| Tool | Description |
|------|-------------|
| `convert_doc` | Convert PDF, DOCX, PPTX, XLSX, HTML, LaTeX, images, audio, and more to markdown or plain text. Backends: `docling` (higher quality, layout-aware, OCR on scans), `markitdown` (lighter, better for Office files), `auto` (tries Docling, falls back to MarkItDown). Use `save_to` to write large outputs to a file. `strip_tables=True` removes noisy pipe-table syntax. `rich_pdf=True` enables Docling's code detection and formula extraction (slower). |
| `search_doc` | Same as `search_text` but handles many document formats (PDF, DOCX, HTML, URLs). Converts via `convert_doc` on first call and caches the result. Pass `use_cache=False` to reconvert and refresh the cache. URL entries also expire after 24 hours. |

### Wikipedia — `wiki`

| Tool | Description |
|------|-------------|
| `wiki_search` | Search Wikipedia. Returns titles, snippets, word counts, and URLs. |
| `wiki_sections` | List all sections of a page as a table of contents (no text). |
| `wiki_section` | Get the text of a specific section. Use `wiki_sections` first to find section titles. |
| `wiki_page` | Get full page text or just the summary (`summary_only=True`). Supports non-English via `language` parameter. |

### arXiv — `arxiv`

| Tool | Description |
|------|-------------|
| `arxiv_search` | Search arXiv. Supports field prefixes (`ti:`, `au:`, `abs:`, `cat:`) and boolean operators. Returns metadata for up to 100 papers. |
| `arxiv_paper` | Fetch a paper by ID. `full_text=False` (default) returns abstract + metadata. `full_text=True` downloads and converts the full PDF. Use `save_to` for large outputs. |

### Datetime & Utilities — `utils`

| Tool | Description |
|------|-------------|
| `status` | Runtime snapshot: name, versions (CAIT, FastMCP, MCP protocol), Python, workspace vs cwd, enabled modules, memory/files paths, `cache_path`, `default_exclude`. No arguments. |
| `get_datetime` | Current date, time, timezone, UTC offset, weekday, and Unix timestamp. Accepts any IANA timezone name. |
| `timer_start` | Start a named wall-clock timer. |
| `timer_stop` | Stop a timer and return elapsed seconds. |
| `timer_list` | List all running timers and their current elapsed time. |

### Memory Database — `memory`

Persistent ChromaDB vector store at `~/.cait/memory` (override with `CAIT_MEMORY_PATH`; shared across projects). Content is embedded with `all-MiniLM-L6-v2` for semantic retrieval.

| Tool | Description |
|------|-------------|
| `mem_add` | Add a new entry. Fields: `title`, `content` (embedded), `tags`, `description`, `source`, `entry_id`. |
| `mem_search` | Find entries by semantic similarity. Tag filters apply before ranking. Returns a snippet; use `mem_get` for the full note. |
| `mem_get` | Retrieve a full entry by ID. |
| `mem_list` | List entries sorted by date (newest first). `count` is rows returned; `total` is matching rows. Content omitted. |
| `mem_set` | Update fields of an existing entry. Only non-empty values are applied. |
| `mem_edit` | Edits content in-place — regex replace when pattern is given, or append when not. |
| `mem_delete` | Permanently delete an entry by ID. |
| `mem_find` | Fast metadata scan — no embedding. Match by title substring, exact source URL, or tags. Use this for deduplication checks before `mem_add`. |

## Disabling Modules

Set `CAIT_DISABLE` to a comma-separated list of module names to exclude their tools at startup:

```bash
CAIT_DISABLE=wiki,arxiv python -m cait.server
```

Available module names: `fs`, `text`, `code`, `repl`, `wiki`, `arxiv`, `utils`, `memory`, `document`
