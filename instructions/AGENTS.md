# General Guidelines

- If you are unsure about something important ask for more clarification before proceeding with a task
- Never fabricate facts or data, acknowledge when you don't know the answer to something
- Search the web if you lack knowledge on a subject or need up-to-date information
- Search large files for relevant content rather than filling up the context window with a big chunk of the file
- Don't be overly agreeable, provide the user with constructive criticism when you think they are factually wrong
- Don't immediately start work on a task if you think there's a better approach, discuss it with the user first
- Avoid unnecessary repetition and filler, try to be efficient with tokens
- Avoid excessively long continuous streams of thought, try to break up your actions
- Use deep reasoning when necessary but avoid getting lost on tangents unrelated to the current task

## Web Search

Use the Firecrawl tool for web searches when appropriate. Key parameters:

- **`query`** — supports operators: `"exact phrase"`, `-exclude`, `site:domain.com`, `filetype:pdf`, `intitle:word`
- **`sources`** — array of `"web"`, `"news"`, `"images"` (default `web`)
- **`categories`** — array of `"github"` and/or `"research"` to target those specific sources
  - `"research"` searches academic/scientific sites: arXiv, Nature, IEEE, PubMed, etc.
  - `"github"` searches GitHub repositories and code
  - Cannot be combined with `sources` — use one or the other
- **`limit`** — number of results (default 5, max 10 recommended)
- **`scrapeOptions`** — optionally fetch full page content inline; use sparingly with limit ≤ 5

## Project orientation

Use the CAIT skills in this order when entering a repo:

- **Unfamiliar repo** → `project-survey` skill (produces `SURVEY.md`)
- **New feature or roadmap** → `project-planning` skill (produces `PLAN.md` + `TASKS.md`)

`SURVEY.md` = what exists. `PLAN.md` = what to build. `TASKS.md` = what to do now.

If `SURVEY.md` is missing and you need to make changes, run **project-survey** before planning or coding.

## Codebase graph (codebase-memory-mcp)

Use **codebase-memory-mcp** for **structural truth in the repo you are editing** — call graphs, packages, entry points, and change impact. It is not a substitute for CAIT `mem_*` (cross-session notes) or for reading arbitrary files line-by-line when the graph already answers the question.

### Index first

If the project is not indexed yet, call `index_repository` with the repo root (or check `list_projects` / `index_status`). Re-index after large refactors if results look stale. Prefer graph tools over grepping the whole tree for “who calls X?” or “what depends on Y?”.

### When to use which tool

| Situation | Tool |
|-----------|------|
| New or unfamiliar repo | Run **project-survey** skill; it uses `get_architecture`, `search_graph`, etc. |
| Before changing a function or type | `trace_path` (inbound and/or outbound) |
| After editing files (uncommitted) | `detect_changes` for affected symbols and blast radius |
| Need the implementation body | `get_code_snippet` (use qualified names from `search_graph`) |
| Find symbols by name or kind | `search_graph` |
| Ad-hoc graph questions | `query_graph` (read-only Cypher) |
| Small Python-only repo, no index | CAIT `find_definitions` / `find_calls` |

Use CAIT `read_file` when you need exact source lines, or `search_file` to regex a known file. Neither is a first step to map the whole codebase.

### vs CAIT memory

- **codebase-memory-mcp** — how *this* codebase is wired right now (derived from the index).
- **CAIT `mem_*`** — facts you want to remember *across projects* (decisions, patterns, research summaries). Do not store call graphs or “file X imports Y” in memory when the index can answer that.

## Memory Database

Use the CAIT memory tools to store and retrieve
knowledge that is worth preserving across sessions and projects.

### When to use memory vs files

- **Memory DB** — cross-project, reusable knowledge: code patterns, research findings, technical references,
  documentation summaries, wiki pages, anything worth recalling in a future project months from now
- **NOTES.md / TASKS.md** — project-scoped ephemeral state: active tasks, in-progress decisions, architecture
  notes specific to the current codebase, key results, important insights, user preferences, etc

### Memory creation

Before calling `mem_add`, use `mem_find` to check for existing entries with the same title or source.
`mem_find` does **no embedding** — it's a fast metadata scan, much cheaper than `mem_search`.

```
# Check by title substring
mem_find(title="Dirac-Milne")

# Check by source URL
mem_find(source="https://arxiv.org/abs/1110.3054")
```

All memory tools accept a `scope` parameter:

- `scope="global"` (default) — shared collection, persists across all projects
- `scope="myproject"` — isolated per-project collection

```
mem_add("Design decision", "...", scope="myproject")
mem_search("architecture", scope="myproject")
```

**Mandatory tagging rules** — always include the appropriate tags when saving:

| Content type | Required tags |
|---|---|
| Self-contained reusable code | `code-snippet` + language tag (e.g. `python`) |
| Scientific or technical document | `research`, `documentation`, `user-manual`, etc |
| Book / novel or short story | `book` / `short-story` + genre (e.g. `sci-fi`, `non-fiction`, `biography`) |
| Wikipedia or other external source | `wiki`, `github`, `web`, `news`, `paper`, etc |
| Content published before today | `pub:DD-MM-YYYY` where day and month are optional (e.g. `pub:2019`) |

**Field usage:**

- `title` — short, searchable label
- `content` — the main body; this is what gets semantically embedded and searched
- `description` — one-line summary shown in `mem_list` results without fetching content
- `source` — URL, file path, or `"manual"` if written directly
- `tags` — use the rules above; prefer specific tags over vague ones
- `entry_id` — omit unless you need a stable deterministic ID

**Note:** `created_at` is stored automatically. Only add a `pub:date` tag when the content's original
publication date differs from today (i.e. for secondhand / archived content).

## Document Workflow

For large documents, always use `search_doc` — it handles conversion and caching automatically:

```
# Single call: converts, caches, and searches
search_doc(source, query="your question here", unit="paragraph")
```

For repeated searches over the same document, `search_doc` reuses the cached markdown.
Pass `use_cache=False` to force a fresh conversion (live HTML, updated PDFs).
Use `strip_tables=True` when the markitdown backend produces noisy table output.

If you need the raw converted text (e.g. to pass to another tool), use `convert_doc` with `save_to`:

```
# Step 1 — convert and save
convert_doc(source, save_to="/tmp/doc.md", strip_tables=True)

# Step 2 — extract what you need
search_text("/tmp/doc.md", query="your question here", unit="paragraph")
```

Useful tips:

- Use `unit="paragraph"` for dense documents (academic PDFs, technical reports) — each paragraph
  carries distinct meaning and produces more coherent results than sentence-level chunking.
- Use `unit="sentence"` (default) for general text or when hunting for specific short facts.
- Leave `query` empty in `search_doc` to get a representative overview (summarize mode).
- `convert_doc` and `search_doc` accept a URL to a document as well as file paths.

