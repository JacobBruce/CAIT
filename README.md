<!-- mcp-name: io.github.JacobBruce/CAIT -->
# CAIT - Core AI Toolkit

A modular [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that extends AI assistants with practical capabilities: file I/O, a persistent Python REPL, AST-aware code analysis, semantic text search, document conversion, Wikipedia & arXiv tools, a persistent vector memory database, and other general utilities.

A total of **37 tools across 9 modules**. Each module can be disabled independently via the `CAIT_DISABLE` environment variable. Made by AI for AI.

## Requirements

- Python 3.11+
- Core: `fastmcp`, `chromadb`
- Online research: `wikipedia-api`, `arxiv`
- Document conversion: `docling` or `markitdown`
- Scientific computing (optional, for REPL use): `sympy`, `scipy`, `matplotlib`, `plotly`, `vispy`

## Installation

```bash
git clone https://github.com/JacobBruce/CAIT
cd CAIT
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install fastmcp chromadb wikipedia-api arxiv markitdown
```

Replace `markitdown` with `docling` for more robust document conversions. Then copy [copilot-instructions.md](https://github.com/JacobBruce/CAIT/instructions/copilot-instructions.md) or [CLAUDE.md](https://github.com/JacobBruce/CAIT/instructions/CLAUDE.md) into the correct location (more details below).

The instructions include general guidance for how to behave, how to use CAIT tools, and how to use the Firecrawl search tools. The instructions may need to be adapted to suite different setups.

If you are working in a Python environment you may want to make use of this agent prompt: [python-coder.agent.md](https://github.com/JacobBruce/CAIT/agents/python-coder.agent.md). There is also [research-assistant.agent.md](https://github.com/JacobBruce/CAIT/agents/research-assistant.agent.md) for deep research.

There is also a skill file called [project-planning.md](https://github.com/JacobBruce/CAIT/skills/project-planning.md) which is helpful for planning the implementation details of a project. The agent produces a PLAN.md file and TASKS.md file.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CAIT_FILES_PATH` | `~/.cait/files/` | Directory for downloaded files and document cache |
| `CAIT_DISABLE` | _(empty)_ | Comma-separated module names to exclude at startup (e.g. `wiki,arxiv`) |

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
      "cwd": "/absolute/path/to/CAIT"
    }
  }
}
```

> For user `settings.json`, nest the above under `"mcp": { ... }`.

Copy [copilot-instructions.md](https://github.com/JacobBruce/CAIT/instructions/copilot-instructions.md) into your project's `.github/` folder to give Copilot guidance on using CAIT tools effectively.

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
        "PYTHONPATH": "/absolute/path/to/CAIT"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add cait -e PYTHONPATH=/absolute/path/to/CAIT \
  -- /absolute/path/to/.venv/bin/python -m cait.server
```

Copy [CLAUDE.md](https://github.com/JacobBruce/CAIT/instructions/CLAUDE.md) to your project root (or to `~/.claude/CLAUDE.md` for global use) to give Claude Code guidance on using CAIT tools effectively.

## Recommended MCP Servers

### Firecrawl

[Firecrawl](https://firecrawl.dev) is a web scraping and search API that pairs naturally with CAIT, adding powerful web search, full-page scraping, and site crawling. A free API key is available at [firecrawl.dev](https://firecrawl.dev).

### Serena

[Serena](https://github.com/oraios/serena) provides many tools for semantic code retrieval and editing. Both CAIT and Serena include a similar memory system so it is recommended to disable one of them.

## Tool Reference

### File System — `fs`

| Tool | Description |
|------|-------------|
| `get_file_info` | Metadata for a single file: size, line count, permissions, timestamps. Does not read content. |
| `get_dir_info` | Directory listing with per-entry metadata. Supports glob patterns and recursion. |
| `append_file` | Append text to a file. Useful for NOTES.md, TASKS.md, log files. |
| `download_file` | Download a URL to `~/.cait/files/` (or `CAIT_FILES_PATH`). Returns the local path. |
| `fetch_url` | HTTP GET/POST with custom headers and body. Use `save_to` to avoid large responses in context. `convert=True` returns clean markdown via Docling or MarkItDown. |

### Persistent Python REPL — `repl`

| Tool | Description |
|------|-------------|
| `repl_exec` | Execute Python code in a persistent session. Variables, imports, and function definitions survive between calls. Returns stdout, stderr, and exception info. |
| `repl_read` | Inspect a named variable from the REPL session without executing code. Returns repr, type, and JSON value. |
| `repl_vars` | List all user-defined variables in the current REPL session. Returns name, type, repr, and JSON value for each. Useful for reviewing session state without running code. |
| `repl_reset` | Clear all variables and imports from the REPL session. |

### Code Analysis — `code`

All code tools perform **AST-aware** search — they skip occurrences in comments and strings, unlike text grep.

| Tool | Description |
|------|-------------|
| `find_definitions` | Find all definitions of a function, class, or variable. Returns file, line, docstring, and kind. |
| `find_calls` | Find all call sites of a function. Matches bare calls, method calls, and chained calls. |
| `find_imports` | Find all files that import a given module or name. |
| `find_references` | Find all uses of an identifier (loads, stores, deletes, attribute accesses). |

### Text Search & Embeddings — `text`

Uses `all-MiniLM-L6-v2` (bundled with ChromaDB — no separate download). Chunk embeddings are cached in memory so repeated queries on the same document skip re-embedding.

| Tool | Description |
|------|-------------|
| `search_text` | Semantically search or summarize a text string or plain text file (`.txt`, `.md`, `.rst`). Query given → extract mode (most relevant chunks). Query empty → summarize mode (most representative chunks). |
| `encode_text` | Return raw 384-dimensional float embeddings for one or more strings or files. |
| `text_similarity` | Cosine similarity between two texts (0–1). |

### Document Tools — `document`

| Tool | Description |
|------|-------------|
| `convert_doc` | Convert PDF, DOCX, PPTX, XLSX, HTML, LaTeX, images, audio, and more to markdown or plain text. Backends: `docling` (higher quality, layout-aware), `markitdown` (lighter, better for Office files), `auto` (tries docling, falls back to markitdown). Use `save_to` to write large outputs to a file. `strip_tables=True` removes noisy pipe-table syntax. `rich_pdf=True` enables Docling's code detection and formula extraction (slower). |
| `search_doc` | Same as `search_text` but handles many document formats (PDF, DOCX, HTML, URLs). Converts via `convert_doc` on first call and caches the result — repeat calls are instant. |

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
| `get_datetime` | Current date, time, timezone, UTC offset, weekday, and Unix timestamp. Accepts any IANA timezone name. |
| `timer_start` | Start a named wall-clock timer. |
| `timer_stop` | Stop a timer and return elapsed seconds. |
| `timer_list` | List all running timers and their current elapsed time. |
| `diff_text` | Unified diff between two strings or files. Returns diff text plus added/removed line counts. |

### Memory Database — `memory`

Persistent ChromaDB vector store at `~/.cait/files/` (shared across projects). Content is embedded with `all-MiniLM-L6-v2` for semantic retrieval.

| Tool | Description |
|------|-------------|
| `mem_add` | Add a new entry. Fields: `title`, `content` (embedded), `tags`, `description`, `source`, `entry_id`. |
| `mem_search` | Find entries by semantic similarity to a query. Optionally filter by tags. |
| `mem_get` | Retrieve a full entry by ID. |
| `mem_list` | List entries sorted by date (newest first). Content omitted for brevity. |
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
