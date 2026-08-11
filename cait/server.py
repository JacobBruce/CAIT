"""
cait.server — FastMCP server exposing the CAIT toolkit as MCP tools.

Run with:
    python -m cait.server
    # or via fastmcp CLI:
    fastmcp run cait/server.py
"""

from typing import Annotated
import os

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from cait.fs import _DEFAULT_EXCLUDE, dir_info, file_info, file_read, file_write, file_download, fetch_url as _fetch_url
import cait.repl as _repl
import cait.code as _code
import cait.utils as _utils
import cait.wiki as _wiki
import cait.text as _text
import cait.arxiv as _arxiv
import cait.memory as _mem
import cait.document as _document


def _exclude_set(exclude: list[str] | None) -> set[str]:
	if exclude is None:
		return set(_DEFAULT_EXCLUDE)
	return set(exclude)


mcp = FastMCP(
	name="CAIT",
	instructions=(
		"Core AI Toolkit — 38 tools across 9 modules for file I/O, Python REPL, code analysis, "
		"semantic search, document tools, Wikipedia, arXiv, utilities, and persistent memory.\n\n"

		"FILE SYSTEM (fs): get_file_info / get_dir_info for metadata without reading content; "
		"read_file for bounded line reads or in-file regex search with context; "
		"write_file to create/overwrite or append file text; download_file to fetch a URL to local storage; "
		"fetch_url for HTTP GET/POST with optional save_to and convert=True for markdown conversion.\n"
		"  convert=True omits raw HTML and returns markdown (inline text capped ~100KB; use save_to for full pages).\n\n"

		"PYTHON REPL (repl): repl_exec runs code in a persistent session (variables survive between calls); "
		"repl_read inspects a variable without printing; repl_vars lists all user-defined variables "
		"in the session namespace; repl_reset clears the session.\n\n"

		"CODE ANALYSIS (code): find_definitions / find_calls / find_imports / find_references "
		"perform AST-aware search that skips comments and strings — more precise than text grep.\n\n"

		"TEXT SEARCH (text): search_text semantically searches or summarizes a plain-text string or file "
		"(query given → extract mode; query empty → summarize mode); encode_text returns raw 384-d embeddings; "
		"text_similarity returns a cosine score (0–1); diff_text returns a unified diff of two strings or files.\n\n"

		"DOCUMENT TOOLS (document): convert_doc converts PDF, DOCX, PPTX, HTML, and more to "
		"markdown/text via Docling or MarkItDown — use save_to to write output to a file; "
		"search_doc does the same thing as search_text but supports many document formats "
		"by calling convert_doc first and caching the result;\n\n"

		"WIKIPEDIA (wiki): wiki_search finds pages; wiki_sections lists a page's TOC; "
		"wiki_section fetches one section's text; wiki_page returns the full page or summary_only.\n\n"

		"ARXIV (arxiv): arxiv_search queries arXiv metadata; arxiv_paper fetches a paper — "
		"full_text=True downloads and converts the PDF; use save_to for large outputs.\n\n"

		"UTILITIES (utils): get_datetime with optional IANA timezone; timer_start / timer_stop / "
		"timer_list for wall-clock timing.\n\n"

		"MEMORY (memory): Persistent ChromaDB vector database. mem_add stores an entry (content is "
		"embedded for semantic search); mem_search retrieves by similarity; mem_get fetches by ID; "
		"mem_list lists entries; mem_set updates fields; mem_delete removes an entry; "
		"mem_find is a fast metadata scan (no embedding) — useful for avoiding duplicates; "
		"mem_edit edits content in-place (regex replace when pattern is given, or append when not). "
		"All memory tools accept scope='global' (default) or a project name for an isolated collection."
	),
)


# ── File metadata ─────────────────────────────────────────────────────────────

@mcp.tool(tags={"fs"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def get_file_info(
	path: Annotated[str, "Absolute or relative path to the file"],
) -> dict:
	"""Get metadata for a single file: size, line count, permissions, and timestamps.
	Does not read file content."""
	return file_info(path)


@mcp.tool(tags={"fs"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def read_file(
	path:         Annotated[str,  "Absolute or relative path to the file"],
	offset:       Annotated[int,  "First line to read, 1-based (default 1)"] = 1,
	limit:        Annotated[int | None, "Line cap. Positive: max lines from offset. Negative: last abs(limit) lines (offset ignored), e.g. -50 for a log tail. None = no line cap"] = None,
	max_bytes:    Annotated[int,  "Hard cap on returned content size in bytes (default 256000)"] = 256_000,
	pattern:      Annotated[str,  "Regex to search for. When set, returns matching lines plus context (grep mode) instead of a plain slice"] = "",
	context:      Annotated[int,  "Search mode only: lines before/after each pattern match in content, like grep -C (default 2). Ignored when pattern is empty"] = 2,
	ignore_case:  Annotated[bool, "Case-insensitive regex when pattern is set (default False)"] = False,
	max_matches:  Annotated[int,  "Stop after this many matching lines when pattern is set (default 100)"] = 100,
) -> dict:
	"""Read a text file with a strict size budget and optional in-file regex search.

	Unlike generic editor read tools, read_file enforces max_bytes, prefixes every
	line with its line number (``lineno|text``), and supports grep-style search via
	*pattern* with merged context windows — useful for large logs and generated files.

	Slice mode (no pattern): lines[offset : offset+limit], capped by max_bytes.
	Negative limit reads the file tail (e.g. limit=-100 after append-heavy logs).
	Search mode (pattern set): merged context around each regex hit; context controls
	grep -C window size. Optional offset/limit scopes the search window.

	Returns path, mode ('slice' or 'search'), total_lines, content, and truncated flag.
	Search mode also returns match_count and a matches list [{line, text}, ...]."""
	return file_read(
		path,
		offset=offset,
		limit=limit,
		max_bytes=max_bytes,
		pattern=pattern or None,
		context=context,
		ignore_case=ignore_case,
		max_matches=max_matches,
	)


@mcp.tool(tags={"fs"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def get_dir_info(
	path: Annotated[str, "Absolute or relative path to the directory"],
	pattern: Annotated[str, "Glob pattern to filter entries (default '*' = all)"] = "*",
	recursive: Annotated[bool, "If True, search all subdirectories"] = False,
	exclude: Annotated[
		list[str] | None,
		"Directory names to skip entirely. Defaults to [\".git\", \".venv\", \"__pycache__\", \".mypy_cache\", \".pytest_cache\", \"node_modules\"]."
	] = None,
) -> dict:
	"""List directory contents with metadata for each entry.
	Returns size, line count, permissions, and timestamps per file.
	Does not read file content."""
	return dir_info(path, pattern=pattern, recursive=recursive, exclude=_exclude_set(exclude))


@mcp.tool(tags={"fs"}, annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False))
def write_file(
	path:    Annotated[str,  "Absolute or relative path to the file"],
	text:    Annotated[str,  "Text to write"],
	mode:    Annotated[str,  "'replace' (default) overwrites or creates the file; 'append' adds to an existing file"] = "replace",
	newline: Annotated[bool, "Ensure the written text ends with a newline (default True)"] = True,
) -> dict:
	"""Write text to a file.

	Default mode='replace' creates or overwrites the file (parent dirs are created).
	Use mode='append' for NOTES.md, TASKS.md, log files, etc. (file must already exist).

	Returns the path, mode, characters written, and the new total line count."""
	return file_write(path, text, mode=mode, newline=newline)


@mcp.tool(tags={"fs"}, annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=True))
def download_file(
	url:      Annotated[str, "URL to download"],
	filename: Annotated[str, "Local filename. Defaults to the last path segment of the URL."] = "",
	dirpath:  Annotated[str, "Destination directory. Defaults to ~/.cait/files/ (overridable via CAIT_FILES_PATH)."] = "",
) -> dict:
	"""Download a file from a URL to local storage.

	Returns the local path, filename, and file size. Useful before passing a file
	to other tools (e.g. search_doc, diff_text) without loading its content
	through the context window."""
	return file_download(url, filename=filename or None, dirpath=dirpath or None)


@mcp.tool(tags={"fs"}, annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=True))
def fetch_url(
	url:     Annotated[str,       "URL to fetch"],
	method:  Annotated[str,       "HTTP method: 'GET' (default) or 'POST'"] = "GET",
	headers: Annotated[dict | None, "Optional request headers (e.g. {\"Authorization\": \"Bearer ...\"})"] = None,
	data:    Annotated[str | dict,  "Optional POST body. A dict is form-encoded; a str is sent as-is."] = "",
	save_to: Annotated[str,       "If given, write the response body to this file path instead of returning inline content."] = "",
	convert: Annotated[bool,      "If True, convert via Docling/MarkItDown and return 'markdown' (raw body is omitted). Prefer save_to for large pages."] = False,
) -> dict:
	"""Fetch a URL and return the response as text.

	Supports GET and POST, custom headers, and optional JSON/form bodies.
	Use save_to to write large responses (e.g. HTML pages, API results) to a file
	and avoid flooding the context window. Combine with convert=True to get clean
	markdown from HTML pages via MarkItDown/Docling (raw HTML is not returned when
	conversion succeeds). Inline content/markdown is capped at ~100KB.

	Returns: url, status_code, content_type, size_bytes.
	Plus 'content' unless save_to is given or convert succeeds.
	Plus 'saved_to' when save_to is given.
	Plus 'markdown' when convert=True succeeds."""
	return _fetch_url(
		url,
		method=method,
		headers=headers,
		data=data if data != "" else None,
		save_to=save_to,
		convert=convert,
	)


# ── Persistent REPL ───────────────────────────────────────────────────────────

@mcp.tool(tags={"repl"}, annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False))
def repl_exec(
	code: Annotated[str, "Python code to execute. Variables and imports persist between calls."],
	timeout: Annotated[int, "Seconds before execution is killed and the REPL is reset (default 30)"] = 30,
) -> dict:
	"""Execute Python code in a persistent REPL session.

	The namespace (variables, imports, function definitions) survives between calls,
	enabling iterative workflows: define a variable in one call, use it in the next.

	Returns stdout, stderr, and any exception traceback. If 'restarted' is True,
	the prior session state was lost (e.g. after a timeout or crash)."""
	return _repl.execute(code, timeout=timeout)


@mcp.tool(tags={"repl"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def repl_read(
	name: Annotated[str, "Variable name to look up in the REPL session namespace"],
) -> dict:
	"""Read the value of a variable from the persistent REPL session without executing code.

	Returns the repr, type name, and a JSON-serializable value if the type supports it.
	Use this to inspect results after a repl_exec call without printing."""
	return _repl.read_var(name)


@mcp.tool(tags={"repl"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def repl_vars() -> dict:
	"""List all user-defined variables currently in the REPL session namespace.

	Returns name, type, repr, and a JSON-serializable value (when possible) for each variable.
	Excludes dunder attributes and built-in names. Useful for inspecting session state
	between repl_exec calls without executing additional code."""
	return _repl.list_vars()


@mcp.tool(tags={"repl"}, annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False))
def repl_reset() -> dict:
	"""Clear all variables and imports from the persistent REPL session."""
	return _repl.reset()


# ── AST code search ──────────────────────────────────────────────────────────

_EXCLUDE_HINT = (
	"Directory names to skip entirely. "
	"Defaults to [\".git\", \".venv\", \"__pycache__\", \".mypy_cache\", \".pytest_cache\", \"node_modules\"]."
)

@mcp.tool(tags={"code"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def find_definitions(
	name:      Annotated[str,       "Symbol name to find definitions of (function, class, or variable)"],
	path:      Annotated[str,       "File or directory to search. Defaults to cwd if omitted"] = "",
	kind:      Annotated[str,       "Restrict to 'function', 'class', or 'variable'. Leave blank for all"] = "",
	recursive: Annotated[bool,      "Descend into subdirectories (default True)"] = True,
	exclude:   Annotated[list[str] | None, _EXCLUDE_HINT] = None,
) -> dict:
	"""Find all definitions of a symbol (function, class, or variable) in Python source files.

	Returns file path, line, column, source line, kind, and docstring for each match.
	Classes also include their base classes. Annotated variables include their type annotation."""
	return {
		"results": _code.find_definitions(
			name,
			path=path or None,
			kind=kind or None,
			recursive=recursive,
			exclude=_exclude_set(exclude),
		),
	}


@mcp.tool(tags={"code"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def find_calls(
	name:      Annotated[str,       "Function name to find call sites of"],
	path:      Annotated[str,       "File or directory to search. Defaults to cwd if omitted"] = "",
	recursive: Annotated[bool,      "Descend into subdirectories (default True)"] = True,
	exclude:   Annotated[list[str] | None, _EXCLUDE_HINT] = None,
) -> dict:
	"""Find all call sites of a function in Python source files.

	Matches bare calls (`name(...)`), method calls (`obj.name(...)`), and chained calls.
	Skips occurrences in comments and strings — unlike grep.
	Returns file, line, column, source line, call style, and the receiver object for attribute calls."""
	return {
		"results": _code.find_calls(
			name,
			path=path or None,
			recursive=recursive,
			exclude=_exclude_set(exclude),
		),
	}


@mcp.tool(tags={"code"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def find_imports(
	module:    Annotated[str,       "Module name to search for (e.g. 'os', 'os.path', 'pandas')"],
	path:      Annotated[str,       "File or directory to search. Defaults to cwd if omitted"] = "",
	recursive: Annotated[bool,      "Descend into subdirectories (default True)"] = True,
	exclude:   Annotated[list[str] | None, _EXCLUDE_HINT] = None,
) -> dict:
	"""Find all files that import a given module or name from it.

	Matches `import module`, `import module.submodule`, `from module import ...`,
	and `from package import module`. Returns file, line, import style, module name,
	and the names imported (for from-imports)."""
	return {
		"results": _code.find_imports(
			module,
			path=path or None,
			recursive=recursive,
			exclude=_exclude_set(exclude),
		),
	}


@mcp.tool(tags={"code"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def find_references(
	name:      Annotated[str,       "Identifier name to find all usages of"],
	path:      Annotated[str,       "File or directory to search. Defaults to cwd if omitted"] = "",
	recursive: Annotated[bool,      "Descend into subdirectories (default True)"] = True,
	exclude:   Annotated[list[str] | None, _EXCLUDE_HINT] = None,
) -> dict:
	"""Find all uses of an identifier in Python source files.

	Broader than find_calls — includes variable loads, stores, deletes, and attribute accesses.
	Use for tracking all usages of a variable, class name, or imported symbol.
	Note: very common names may return many results."""
	return {
		"results": _code.find_references(
			name,
			path=path or None,
			recursive=recursive,
			exclude=_exclude_set(exclude),
		),
	}


# ── Wikipedia ────────────────────────────────────────────────────────────────

@mcp.tool(tags={"wiki"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
def wiki_search(
	query:    Annotated[str, "Search query"],
	limit:    Annotated[int, "Maximum number of results (default 5)"] = 5,
	language: Annotated[str, "Wikipedia language code (default 'en')"] = "en",
) -> dict:
	"""Search Wikipedia and return matching pages with titles, snippets, word counts, and URLs."""
	return _wiki.wiki_search(query, limit=limit, language=language)


@mcp.tool(tags={"wiki"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
def wiki_sections(
	title:    Annotated[str, "Wikipedia page title"],
	language: Annotated[str, "Wikipedia language code (default 'en')"] = "en",
) -> dict:
	"""List all sections of a Wikipedia page as a table of contents (no text content).

	Use this to discover available section titles before calling wiki_section()."""
	return _wiki.wiki_sections(title, language=language)


@mcp.tool(tags={"wiki"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
def wiki_section(
	title:         Annotated[str, "Wikipedia page title"],
	section_title: Annotated[str, "Section heading to retrieve (e.g. 'History')"],
	language:      Annotated[str, "Wikipedia language code (default 'en')"] = "en",
) -> dict:
	"""Get the text content of a specific section of a Wikipedia page.

	Returns the section text plus any immediate subsections.
	Use wiki_sections() first to discover available section titles."""
	return _wiki.wiki_section(title, section_title, language=language)


@mcp.tool(tags={"wiki"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
def wiki_page(
	title:        Annotated[str, "Wikipedia page title (e.g. 'Python (programming language)')"],
	summary_only: Annotated[bool, "If True, return only the summary paragraph — much more token-efficient. If False (default), return the full page text."] = False,
	language:     Annotated[str, "Wikipedia language code (default 'en')"] = "en",
) -> dict:
	"""Get content from a Wikipedia page.

	With summary_only=True, returns just the introductory summary paragraph.
	With summary_only=False (default), returns the full page text — can be very long;
	prefer wiki_section() when you only need a specific part."""
	return _wiki.wiki_page(title, language=language, summary_only=summary_only)


# ── Datetime & timers ────────────────────────────────────────────────────────

@mcp.tool(tags={"utils"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def get_datetime(
	timezone: Annotated[str, "IANA timezone name (e.g. 'America/New_York', 'UTC'). Defaults to system local timezone."] = "",
) -> dict:
	"""Return the current date and time.

	Includes ISO 8601 datetime, date, time, timezone name, UTC offset, weekday, and Unix timestamp.
	Defaults to the system's local timezone when no timezone is given."""
	return _utils.get_datetime(timezone or None)


@mcp.tool(tags={"utils"}, annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False))
def timer_start(
	name: Annotated[str, "Timer name. Use distinct names to run multiple timers concurrently (default 'default')"] = "default",
) -> dict:
	"""Start (or restart) a named timer. Elapsed time is measured in wall-clock seconds."""
	return _utils.timer_start(name)


@mcp.tool(tags={"utils"}, annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False))
def timer_stop(
	name: Annotated[str, "Name of the timer to stop (default 'default')"] = "default",
) -> dict:
	"""Stop a named timer and return elapsed seconds. Removes it from the active set."""
	return _utils.timer_stop(name)


@mcp.tool(tags={"utils"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def timer_list() -> dict:
	"""List all currently running timers and their elapsed time so far."""
	return _utils.timer_list()


# ── Text embeddings & summarization ────────────────────────────────────────────

@mcp.tool(tags={"text"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def encode_text(
	texts: Annotated[list[str], "One or more strings to embed. Each element may be a file path — if it exists, the file contents are embedded instead."],
) -> dict:
	"""Embed texts using all-MiniLM-L6-v2 (the same model used by the memory DB).

	Returns 384-dimensional float vectors, one per input. Each element may be
	a file path — if it exists on disk, its contents are read and embedded.
	Useful for computing custom similarity scores or inspecting the embedding space."""
	return _text.encode_text(texts)


@mcp.tool(tags={"text"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def text_similarity(
	a: Annotated[str, "First text or file path"],
	b: Annotated[str, "Second text or file path"],
) -> dict:
	"""Compute the semantic similarity between two texts (cosine similarity, 0–1).

	1.0 = identical meaning, 0.0 = completely unrelated. Each argument may be
	a file path — if it exists on disk, its contents are used.
	Uses the all-MiniLM-L6-v2 embedding model."""
	return _text.text_similarity(a, b)


@mcp.tool(tags={"text"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def search_text(
	source:    Annotated[str, "Text string, or a plain text file path (.txt, .md, .rst)"],
	query:     Annotated[str, "Question or topic to search for. Leave empty for a document overview summary."] = "",
	sentences: Annotated[int, "Number of chunks to return (default 5)"] = 5,
	unit:      Annotated[str, "Chunking granularity: 'sentence' (default) or 'paragraph'."] = "sentence",
) -> dict:
	"""Semantically search or summarize a text string or plain text file.

	When query is given: returns the most relevant chunks (extract mode).
	When query is empty: returns the most representative chunks (summarize mode).

	For dense documents (academic PDFs, long articles), prefer unit='paragraph'
	so each extracted chunk carries more coherent meaning.
	
	For documents that require conversion (PDF, DOCX, HTML, URLs), use search_doc
	instead — it handles conversion and caching automatically."""
	return _text.search_text(source, query=query, sentences=sentences, unit=unit)


@mcp.tool(tags={"text"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def diff_text(
	a:       Annotated[str, "Original text or file path"],
	b:       Annotated[str, "Modified text or file path"],
	context: Annotated[int, "Unchanged context lines shown around each change (default 3)"] = 3,
	label_a: Annotated[str, "Label for original in diff header. Defaults to filename if a path is given."] = "a",
	label_b: Annotated[str, "Label for modified in diff header. Defaults to filename if a path is given."] = "b",
) -> dict:
	"""Return a unified diff between two strings or files.

	Each argument may be a file path — if it exists on disk, its contents are
	read and used. Returns the diff string plus counts of added and removed lines."""
	return _text.diff_text(a, b, context=context, label_a=label_a, label_b=label_b)


# ── arXiv ───────────────────────────────────────────────────────────────────────

@mcp.tool(tags={"arxiv"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
def arxiv_search(
	query:   Annotated[str, (
		"arXiv query string. Supports field prefixes: ti: (title), au: (author), "
		"abs: (abstract), cat: (category). Boolean operators: AND, OR, ANDNOT. "
		"Example: 'au:vaswani AND ti:attention'"
	)],
	limit:   Annotated[int, "Maximum number of results (default 10, max 100)"] = 10,
	sort_by: Annotated[str, "Sort order: 'relevance' (default), 'lastUpdated', or 'submitted'"] = "relevance",
) -> dict:
	"""Search arXiv and return metadata for matching papers.

	Each result includes paper_id, title, authors, abstract, published/updated dates,
	categories, pdf_url, arxiv_url, doi, journal_ref, and comment."""
	return _arxiv.arxiv_search(query, limit=limit, sort_by=sort_by)


@mcp.tool(tags={"arxiv"}, annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=True))
def arxiv_paper(
	paper_id:  Annotated[str,  "arXiv paper ID (e.g. '1706.03762', '1706.03762v5'). Version suffix is optional."],
	full_text: Annotated[bool, "If True, fetch and convert the full PDF to markdown. Default False returns abstract + metadata only."] = False,
	save_to:   Annotated[str,  "File path to save the markdown output to. If given, 'markdown' is omitted from the response to save tokens."] = "",
) -> dict:
	"""Fetch an arXiv paper by ID and return it as markdown.

	With full_text=False (default), returns a structured markdown document with
	title, authors, abstract, categories, and links — fast and token-efficient.

	With full_text=True, downloads and converts the full PDF via convert_doc.
	This may take a few seconds and returns the complete paper text.

	Use save_to to write large outputs directly to a file instead of returning
	them inline — useful when full_text=True produces a long document."""
	return _arxiv.arxiv_paper(paper_id, full_text=full_text, save_to=save_to)


# ── Memory ────────────────────────────────────────────────────────────────────

_SCOPE_HINT = "Memory scope: 'global' (default, shared across all projects) or a project name for an isolated collection (e.g. 'myproject')."


@mcp.tool(tags={"memory"}, annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False))
def mem_add(
	title:       Annotated[str,       "Short descriptive title for the entry"],
	content:     Annotated[str,       "Main text content — this is what gets embedded and searched semantically"],
	tags:        Annotated[list[str], "Tags for filtering (e.g. ['research', 'ai', 'python'])"] = [],
	description: Annotated[str,       "Optional one-line summary stored as metadata"] = "",
	source:      Annotated[str,       "Optional origin URL, file path, or 'manual'"] = "",
	entry_id:    Annotated[str,       "Optional custom ID. A UUID is generated if not provided."] = "",
	scope:       Annotated[str,       _SCOPE_HINT] = "global",
) -> dict:
	"""Add a new entry to the persistent memory database.

	Content is embedded using ChromaDB's built-in embedding model and can be
	retrieved later via semantic similarity search with mem_search().

	Use scope='global' (default) for cross-project knowledge. Use a project name
	(e.g. scope='myproject') for notes relevant only to that project."""
	return _mem.mem_add(title, content, tags=tags or None, description=description,
					   source=source, entry_id=entry_id or None, scope=scope)


@mcp.tool(tags={"memory"}, annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False))
def mem_set(
	entry_id:    Annotated[str,       "ID of the memory entry to update"],
	title:       Annotated[str,       "New title, or empty string to leave unchanged"] = "",
	content:     Annotated[str,       "New content (re-embeds the entry), or empty string to leave unchanged"] = "",
	tags:        Annotated[list[str], "New tag list (replaces existing tags), or empty list to leave unchanged"] = [],
	description: Annotated[str,       "New description, or empty string to leave unchanged"] = "",
	source:      Annotated[str,       "New source, or empty string to leave unchanged"] = "",
	scope:       Annotated[str,       _SCOPE_HINT] = "global",
) -> dict:
	"""Update fields of an existing memory entry. Only non-empty/non-null values are applied."""
	return _mem.mem_set(
		entry_id,
		title=title       or None,
		content=content   or None,
		tags=tags         or None,
		description=description or None,
		source=source     or None,
		scope=scope,
	)


@mcp.tool(tags={"memory"}, annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False))
def mem_edit(
	entry_id:    Annotated[str, "ID of the memory entry to edit"],
	pattern:     Annotated[str, "Regex pattern to find within the content. Leave empty to use append mode instead."] = "",
	text:        Annotated[str, "Replacement string for regex mode (default empty = delete matches). Appends text when pattern is empty."] = "",
	scope:       Annotated[str, _SCOPE_HINT] = "global",
) -> dict:
	"""Edit the content of a memory entry in-place.

	Two modes:
	  - Regex replace: provide pattern (and optionally replacement text).
	    Applies re.sub(pattern, text, content) and re-embeds the result.
	  - Append: provide text with no pattern. Appends to the existing
	    content with a newline separator if needed.

	Returns id, updated (bool), old_length, new_length.
	If content is unchanged after the operation, updated=False is returned."""
	return _mem.mem_edit(
		entry_id,
		pattern=pattern   or None,
		text=text,
		scope=scope,
	)


@mcp.tool(tags={"memory"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def mem_search(
	query: Annotated[str,       "Natural language query — finds entries with semantically similar content"],
	limit: Annotated[int,       "Maximum number of results (default 5)"] = 5,
	tags:  Annotated[list[str], "Filter results to entries that have all of these tags"] = [],
	scope: Annotated[str,       _SCOPE_HINT] = "global",
) -> dict:
	"""Search memory by semantic similarity.

	Returns entries whose content is most similar to the query, ranked by cosine
	similarity score (0–1). Optionally filter by tags before ranking."""
	return _mem.mem_search(query, limit=limit, tags=tags or None, scope=scope)


@mcp.tool(tags={"memory"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def mem_get(
	entry_id: Annotated[str, "ID of the memory entry to retrieve"],
	scope:    Annotated[str, _SCOPE_HINT] = "global",
) -> dict:
	"""Retrieve a specific memory entry by ID, including its full content."""
	return _mem.mem_get(entry_id, scope=scope)


@mcp.tool(tags={"memory"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def mem_list(
	tags:      Annotated[list[str], "Filter to entries that have all of these tags. Empty = return all."] = [],
	limit:     Annotated[int,       "Maximum number of entries to return (default 20)"] = 20,
	sort_by:   Annotated[str,       "Sort field: 'created_at' (default) or 'updated_at'"] = "created_at",
	ascending: Annotated[bool,      "If True, return oldest first. Default False (newest first)."] = False,
	scope:     Annotated[str,       _SCOPE_HINT] = "global",
) -> dict:
	"""List memory entries sorted by date, newest first by default.

	Content is omitted for brevity — use mem_get() to fetch the full content of an entry."""
	return _mem.mem_list(tags=tags or None, limit=limit, sort_by=sort_by, ascending=ascending, scope=scope)


@mcp.tool(tags={"memory"}, annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False))
def mem_delete(
	entry_id: Annotated[str, "ID of the memory entry to delete"],
	scope:    Annotated[str, _SCOPE_HINT] = "global",
) -> dict:
	"""Permanently delete a memory entry by ID."""
	return _mem.mem_delete(entry_id, scope=scope)


@mcp.tool(tags={"memory"}, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def mem_find(
	title:  Annotated[str,       "Case-insensitive substring to match against entry titles. Leave empty to skip."] = "",
	source: Annotated[str,       "Exact source string to match (URL, file path, or 'manual'). Leave empty to skip."] = "",
	tags:   Annotated[list[str], "Filter to entries that have ALL of these tags. Leave empty to skip."] = [],
	limit:  Annotated[int,       "Maximum number of entries to return (default 20)"] = 20,
	scope:  Annotated[str,       _SCOPE_HINT] = "global",
) -> dict:
	"""Fast metadata-only lookup without semantic embedding.

	Use this for quick deduplication checks before mem_add — it is much cheaper
	than mem_search because it does no embedding. At least one of title, source,
	or tags must be provided.

	Returns entries without content — use mem_get to fetch the full content of a match."""
	return _mem.mem_find(
		title=title   or None,
		source=source or None,
		tags=tags     or None,
		limit=limit,
		scope=scope,
	)


# ── Document tools ──────────────────────────────────────────────────────

@mcp.tool(tags={"document"}, annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=True))
def convert_doc(
	source:        Annotated[str,  "File path or URL to convert"],
	backend:       Annotated[str,  "Backend to use: 'docling', 'markitdown', or 'auto' (default — tries docling, falls back to markitdown)"] = "auto",
	output_format: Annotated[str,  "Output format: 'markdown' (default), 'html', or 'text'. Only applies to the docling backend."] = "markdown",
	rich_pdf:      Annotated[bool, "Enable Docling PDF enrichment (code detection, formula extraction, picture description). Slower. Docling only."] = False,
	strip_tables:  Annotated[bool, "Remove markdown table syntax from the output. Useful when markitdown renders PDF equations as unreadable pipe-delimited tables."] = False,
	save_to:       Annotated[str,  "File path to save the converted content to. If given, 'content' is omitted from the response to save tokens."] = "",
) -> dict:
	"""Convert a document to text using Docling or MarkItDown.

	Accepts local file paths and URLs. Supported input formats include PDF, DOCX,
	PPTX, XLSX, HTML, LaTeX, images, audio, and more (backend-dependent).

	Docling offers higher-quality conversion with layout understanding and
	optional PDF enrichment. MarkItDown is lighter-weight and better suited
	for Office documents and simple files.

	Recommended workflow for large documents — write to a file, then search it:
	    convert_doc(source, save_to='/tmp/doc.md', strip_tables=True)
	    search_text('/tmp/doc.md', query='...', unit='paragraph')

	Returns the source, backend used, output format, and the converted content.
	Use save_to to write large outputs directly to a file instead of returning
	them inline. Inline content is capped at ~100KB."""
	try:
		result = _document.convert_doc(
			source,
			backend=backend,
			output_format=output_format,
			rich_pdf=rich_pdf,
			strip_tables=strip_tables,
			save_to=save_to,
		)
	except (ValueError, RuntimeError) as e:
		return {"error": str(e), "source": source}
	if isinstance(result, dict) and "content" in result and not save_to:
		from cait.fs import cap_inline_text
		text, trunc_meta = cap_inline_text(result["content"])
		result["content"] = text
		if trunc_meta:
			result["truncated"] = True
			result["original_bytes"] = trunc_meta["original_bytes"]
			result["max_bytes"] = trunc_meta["max_bytes"]
	return result


@mcp.tool(tags={"document"}, annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=True))
def search_doc(
	source:       Annotated[str,  "File path or URL to a document (PDF, DOCX, HTML, …), or a plain text file path"],
	query:        Annotated[str,  "Question or topic to search for. Leave empty for a document overview summary."] = "",
	sentences:    Annotated[int,  "Number of chunks to return (default 5)"] = 5,
	unit:         Annotated[str,  "Chunking granularity: 'sentence' (default) or 'paragraph'. Use 'paragraph' for academic PDFs and technical reports."] = "sentence",
	backend:      Annotated[str,  "Conversion backend: 'auto' (default), 'docling', or 'markitdown'"] = "auto",
	strip_tables: Annotated[bool, "Strip markdown table syntax before searching. Recommended when markitdown renders PDFs with heavy table content."] = False,
) -> dict:
	"""Semantically search or summarize a document from a file path or URL.

	Handles the full pipeline: convert → cache → search. Repeat calls with the
	same source reuse the cached markdown — no re-download or re-conversion.

	Plain text files (.txt, .md, .rst) are read directly without conversion.
	All other formats (PDF, DOCX, HTML, URLs, …) go through convert_doc.

	When query is given: returns the most relevant chunks (extract mode).
	When query is empty: returns the most representative chunks (summarize mode).

	Result includes 'source', 'cache_hit' (True = no conversion was performed),
	and 'mode' ('extract' or 'summarize') in addition to the standard search fields."""
	return _document.search_doc(
		source,
		query=query,
		sentences=sentences,
		unit=unit,
		backend=backend,
		strip_tables=strip_tables,
	)


# ── Module enable/disable ────────────────────────────────────────────────────
# Set CAIT_DISABLE to a comma-separated list of module names to exclude their
# tools at startup. Available modules: fs, text, code, repl, wiki, arxiv, utils, memory, document
# Example: CAIT_DISABLE=wiki,arxiv

_disabled = {m.strip().lower() for m in os.environ.get("CAIT_DISABLE", "").split(",") if m.strip()}
if _disabled:
	mcp.disable(tags=_disabled)


if __name__ == "__main__":
	# Stdio MCP hosts (Cursor, VS Code) capture stderr as logs; Rich banners and
	# ANSI formatting can show up as spurious "undefined" lines — keep stderr plain.
	mcp.run(show_banner=False)
