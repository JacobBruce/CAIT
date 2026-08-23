"""
cait.fs — File I/O, directory metadata, downloads, and HTTP fetch helpers.

All paths accept str or Path objects. Functions return plain dicts.
Recoverable failures return ``{error, hint, ...}`` rather than raising.
"""

import os
import re
import stat
import platform
from collections import deque
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from cait.errors import tool_error

_DEFAULT_MAX_DIR_RESULTS = 100
_HARD_MAX_DIR_RESULTS = 2000
_DEFAULT_FILEDIR = Path(os.environ.get("CAIT_FILES_PATH", Path.home() / ".cait" / "files"))
_DEFAULT_MAX_READ_BYTES = 256_000
# Cap for tool results returned inline (no save_to) — keeps MCP/agent context usable.
_DEFAULT_MAX_INLINE_BYTES = 100_000
_USER_AGENT = f"CAIT/1.0 (FastMCP; {platform.system()}; {platform.release()})"
_DEFAULT_HTTP_TIMEOUT = 30
_DEFAULT_FETCH_MAX_BYTES = 20 * 1024 * 1024
_DEFAULT_DOWNLOAD_MAX_BYTES = 100 * 1024 * 1024
_DATA_URI_RE = re.compile(
	r"data:[^\s\"'<>]*;base64,[A-Za-z0-9+/=\s]+",
	re.IGNORECASE,
)
_BINARY_SUFFIXES = {
	".o", ".obj", ".a", ".lib", ".so", ".dylib", ".dll", ".out",
	".AppImage", ".deb", ".rpm", ".msi", ".dmg", ".pkg", ".mpkg", ".app", ".exe",
	".pt", ".cpk", ".ckpt", ".pth", ".pkl", ".pickle", ".safetensors",
	".pdb", ".map", ".bin", ".dat", ".pcm", ".mo", ".pak",
	".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tif", ".tiff", ".avif",
	".woff", ".woff2", ".ttf", ".otf", ".eot",
	".pdf", ".zip", ".7z", ".gz", ".bz", ".bz2", ".xz", ".zst", ".tar", ".rar",
	".wasm", ".npz", ".pyc", ".pyo", ".class", ".jar", ".arc",
	".mp3", ".wma", ".weba", ".wav", ".ogg", ".flac", ".aac", ".m4a",
	".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp",
}
_DEFAULT_EXCLUDE = {
	"__pycache__", ".mypy_cache", ".pytest_cache",
	".git", ".venv", "venv", "node_modules", "vendor",
	"bin", "build", "dist", "target",
}

# ── helpers ──────────────────────────────────────────────────────────────────

def workspace_root():
	"""Directory relative paths resolve against.

	Hosts set CAIT_WORKSPACE (open project). Unset → process cwd (legacy).
	"""
	raw = str(os.environ.get("CAIT_WORKSPACE", "") or "").strip()
	if raw:
		return Path(raw).expanduser().resolve()
	return Path.cwd()


def resolve_path(path):
	"""Absolute/`~/` paths as-is; relative paths join workspace_root()."""
	if path is None or str(path).strip() == "":
		return workspace_root()
	p = Path(path).expanduser()
	if p.is_absolute():
		return p.resolve()
	return (workspace_root() / p).resolve()


def _human_size(n_bytes):
	"""Convert a byte count to a human-readable string (e.g. '1.4 MB')."""
	for unit in ("B", "KB", "MB", "GB", "TB"):
		if n_bytes < 1024 or unit == "TB":
			return f"{n_bytes:.1f} {unit}" if unit != "B" else f"{n_bytes} B"
		n_bytes /= 1024


def _iso(ts):
	"""Convert a POSIX timestamp to an ISO 8601 string in UTC."""
	return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def strip_data_uris(text: str) -> str:
	"""Replace embedded data:…;base64,… blobs with a short placeholder."""
	if not text:
		return text or ""
	return _DATA_URI_RE.sub("[omitted data URI]", text)


def cap_inline_text(
	text: str,
	max_bytes: int = _DEFAULT_MAX_INLINE_BYTES,
	*,
	hint: str = "Use save_to=... to keep the full response on disk, then search_doc or read_file.",
) -> tuple[str, dict]:
	"""Strip data URIs and truncate UTF-8 text to max_bytes for inline tool results.

	Returns (text, meta) where meta may include truncated/original_bytes/max_bytes.
	"""
	if text is None:
		text = ""
	text = strip_data_uris(str(text))
	encoded = text.encode("utf-8")
	if len(encoded) <= max_bytes:
		return text, {}
	cut = encoded[:max_bytes].decode("utf-8", errors="ignore")
	note = (
		f"\n\n[truncated: showing {max_bytes} of {len(encoded)} bytes. {hint}]"
	)
	return cut + note, {
		"truncated": True,
		"original_bytes": len(encoded),
		"max_bytes": max_bytes,
	}


def _looks_binary(path):
	"""True for known binary suffixes, or if the first 8 KB contains a NUL."""
	p = Path(path)
	if p.suffix.lower() in _BINARY_SUFFIXES:
		return True
	try:
		with open(p, "rb") as f:
			return b"\x00" in f.read(8192)
	except OSError:
		return False


def _count_lines(path):
	"""Count newlines in a text file. Returns None for binary files."""
	if _looks_binary(path):
		return None
	count = 0
	with open(path, "rb") as f:
		while chunk := f.read(1 << 16):	 # 64 KB blocks
			count += chunk.count(b"\n")
	return count


def _permission_string(mode):
	"""Return a Unix-style permission string, e.g. '-rw-r--r--'."""
	return stat.filemode(mode)


def _parse_max_dir_results(max_results):
	if max_results is None:
		return _DEFAULT_MAX_DIR_RESULTS, None
	try:
		n = int(max_results)
	except (TypeError, ValueError):
		return None, tool_error(
			"max_results must be an integer",
			hint="Pass a positive integer (default 100, hard max 2000).",
		)
	if n < 1:
		return None, tool_error(
			"max_results must be >= 1",
			hint="Use 1–2000, or omit for the default of 100.",
		)
	return min(n, _HARD_MAX_DIR_RESULTS), None


def _pattern_allows_hidden(pattern):
	pat = (pattern or "*").replace("\\", "/")
	return any(part.startswith(".") for part in pat.split("/") if part and part != "**")


def _is_hidden_name(name):
	return name.startswith(".") and name not in (".", "..")


def _entry_matches_pattern(root, entry, pattern, recursive):
	"""Match *entry* relative to *root* the way Path.glob / Path.rglob would."""
	pat = (pattern or "*").replace("\\", "/")
	try:
		rel = entry.relative_to(root)
	except ValueError:
		return False
	if pat in ("*", "**", "**/*"):
		return recursive or len(rel.parts) == 1
	if recursive:
		return rel.match(pat)
	pat_parts = PurePosixPath(pat).parts
	if not pat_parts:
		return False
	if len(pat_parts) == 1:
		return len(rel.parts) == 1 and rel.match(pat)
	if len(rel.parts) != len(pat_parts):
		return False
	return rel.match(pat)


def _iter_tree(root, recursive=False, exclude=(), files_only=False, include_hidden=False):
	"""Yield Path entries under *root*, never descending into excluded / hidden dirs.

	Exclude matches each directory's own name relative to *root*, not ancestors of
	*root*. Excluded dirs are still yielded (so a listing can show they exist)
	unless *files_only* is set.
	"""
	root = Path(root)
	exclude = set(exclude or ())

	def _skip_dir(name):
		if name in exclude:
			return True
		return (not include_hidden) and _is_hidden_name(name)

	def _skip_file(name):
		return (not include_hidden) and _is_hidden_name(name)

	if not recursive:
		try:
			names = sorted(os.listdir(root))
		except OSError:
			return
		for name in names:
			entry = root / name
			if files_only:
				if _skip_file(name):
					continue
				try:
					if entry.is_file():
						yield entry
				except OSError:
					continue
				continue
			if _is_hidden_name(name) and not include_hidden:
				continue
			yield entry
		return

	for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
		dirnames.sort()
		filenames.sort()
		base = Path(dirpath)
		keep = []
		for name in dirnames:
			if name in exclude:
				if not files_only and (include_hidden or not _is_hidden_name(name)):
					yield base / name
				continue
			if _skip_dir(name):
				continue
			keep.append(name)
		dirnames[:] = keep
		if not files_only:
			for name in dirnames:
				yield base / name
		for name in filenames:
			if _skip_file(name):
				continue
			yield base / name


def _listing_entry(entry):
	try:
		st = entry.stat()
	except OSError:
		return None
	try:
		is_dir = entry.is_dir()
	except OSError:
		return None
	if is_dir:
		return {
			"path":        str(entry),
			"name":        entry.name,
			"size_bytes":  None,
			"size":        None,
			"modified":    _iso(st.st_mtime),
			"created":     _iso(st.st_ctime),
			"permissions": _permission_string(st.st_mode),
			"is_file":     False,
			"is_dir":      True,
		}
	return {
		"path":        str(entry),
		"name":        entry.name,
		"size_bytes":  st.st_size,
		"size":        _human_size(st.st_size),
		"modified":    _iso(st.st_mtime),
		"created":     _iso(st.st_ctime),
		"permissions": _permission_string(st.st_mode),
		"is_file":     True,
		"is_dir":      False,
	}


# ── public API ────────────────────────────────────────────────────────────────

def file_info(path):
	"""Return metadata for a single file.

	Args:
		path: Path to the file (str or Path).

	Returns:
		dict with keys:
			path        Absolute path string
			name        File name
			size_bytes  Size in bytes
			size        Human-readable size string
			lines       Line count (None for binary/unreadable files)
			modified    Last modified time (ISO 8601 UTC)
			created     Creation/ctime (ISO 8601 UTC)
			permissions Unix permission string (e.g. '-rw-r--r--')
			is_file     True
			is_dir      False
	"""
	p = resolve_path(path)
	if not p.exists():
		return tool_error(
			f"No such file: {p}",
			hint="Pass an existing file path (absolute, or relative to CAIT_WORKSPACE).",
			path=str(p),
		)
	if not p.is_file():
		return tool_error(
			f"Path is not a file: {p}",
			hint="Use get_dir_info for directories.",
			path=str(p),
		)

	st = p.stat()

	lines = None
	try:
		lines = _count_lines(p)
	except (OSError, UnicodeDecodeError):
		pass

	return {
		"path":        str(p),
		"name":        p.name,
		"size_bytes":  st.st_size,
		"size":        _human_size(st.st_size),
		"lines":       lines,
		"modified":    _iso(st.st_mtime),
		"created":     _iso(st.st_ctime),
		"permissions": _permission_string(st.st_mode),
		"is_file":     True,
		"is_dir":      False,
	}


def _is_probably_binary(path):
	"""True if the file contains a NUL byte in its first 8 KiB."""
	try:
		with open(path, "rb") as f:
			return b"\0" in f.read(8192)
	except OSError:
		return True


def _format_numbered_lines(lines, start_line):
	"""Prefix lines with fixed-width line numbers for agent-friendly navigation."""
	width = max(len(str(start_line + len(lines) - 1)), 1)
	return "\n".join(f"{start_line + i:{width}}|{line}" for i, line in enumerate(lines))


def _merge_line_ranges(ranges):
	"""Merge inclusive 1-based (start, end) ranges that overlap or touch."""
	if not ranges:
		return []
	ranges = sorted(ranges)
	merged = [ranges[0]]
	for start, end in ranges[1:]:
		prev_start, prev_end = merged[-1]
		if start <= prev_end + 1:
			merged[-1] = (prev_start, max(prev_end, end))
		else:
			merged.append((start, end))
	return merged


def _iter_text_lines(path):
	"""Yield (1-based lineno, line without newline). Does not slurp the file."""
	with open(path, encoding="utf-8", errors="replace") as f:
		for lineno, line in enumerate(f, 1):
			yield lineno, line.rstrip("\r\n")


def _est_numbered(lineno, line):
	return len(str(lineno)) + 1 + len(line.encode("utf-8")) + 1


def _result_size(result, path):
	try:
		result["size_bytes"] = path.stat().st_size
	except OSError:
		pass
	return result


def _tail_pairs(path, n):
	"""Last n (lineno, line) pairs. Scans the file once; RAM is O(n). Also returns total_lines."""
	buf = deque(maxlen=n)
	total = 0
	for lineno, line in _iter_text_lines(path):
		total = lineno
		buf.append((lineno, line))
	return list(buf), total


def _require_window(offset, limit):
	if offset < 1:
		return tool_error(
			f"offset must be >= 1, got {offset}",
			hint="Line numbers are 1-based.",
		)
	if limit == 0:
		return tool_error(
			"limit must not be 0",
			hint="Use a positive line count, or a negative value for tail reads (e.g. -50).",
		)
	return None


def _require_text_file(path, tool):
	p = resolve_path(path)
	if not p.exists():
		return None, tool_error(
			f"No such file: {p}",
			hint="Pass an existing file path (absolute, or relative to CAIT_WORKSPACE).",
			path=str(p),
		)
	if not p.is_file():
		return None, tool_error(
			f"Path is not a file: {p}",
			hint="Use get_dir_info for directories.",
			path=str(p),
		)
	if _is_probably_binary(p):
		return None, tool_error(
			f"File appears to be binary — {tool} only supports text files",
			hint="This tool is for text. Use get_file_info for binary metadata.",
			path=str(p),
		)
	return p, None


def file_read(path, offset=1, limit=None):
	"""Read a text file as a numbered line slice.

	Returns lines from *offset* (1-based), stopping at *limit* lines and/or an
	internal size cap. A negative *limit* reads the last ``abs(limit)`` lines
	(*offset* is ignored). Streamed: the file is not loaded in full.
	*has_more* is True when lines exist after this window (a requested *limit*
	is not a truncation). *truncated* is True only when the byte cap cut the
	payload. *total_lines* is included only when this pass reached EOF.
	"""
	err = _require_window(offset, limit)
	if err:
		return err
	p, err = _require_text_file(path, "read_file")
	if err:
		return err
	try:
		return _result_size(_read_slice(p, offset, limit), p)
	except OSError as e:
		return tool_error(str(e), hint="Check file permissions and that the path is readable.", path=str(p))


def file_search(
	path,
	pattern,
	offset=1,
	limit=None,
	context=0,
	max_matches=100,
):
	"""Regex-search a text file (in-file grep).

	Returns a *matches* list ``[{line, text}, ...]``. *context* is grep -C:
	0 (default) returns matches only; N adds numbered bodies with N lines
	before/after each hit. Case-insensitive: put ``(?i)`` in *pattern*.
	*offset* / *limit* optionally restrict the line range; negative *limit*
	searches only the file tail. Stops after *max_matches* matching lines.
	Streamed; *total_lines* only when this pass reached EOF.
	"""
	if not pattern:
		return tool_error(
			"pattern is required",
			hint="Pass a Python re regex. Use read_file for a plain line slice.",
		)
	err = _require_window(offset, limit)
	if err:
		return err
	if context < 0:
		return tool_error(
			f"context must be >= 0, got {context}",
			hint="context is grep -C (lines before/after each match). Use 0 for matches only.",
		)
	if max_matches < 1:
		return tool_error(
			f"max_matches must be >= 1, got {max_matches}",
			hint="Use a positive cap (default 100).",
		)
	p, err = _require_text_file(path, "search_file")
	if err:
		return err
	try:
		return _result_size(
			_run_search(p, offset, limit, pattern, context, max_matches),
			p,
		)
	except OSError as e:
		return tool_error(str(e), hint="Check file permissions and that the path is readable.", path=str(p))


def _read_slice(path, offset, limit):
	cap = _DEFAULT_MAX_READ_BYTES
	if limit is not None and limit < 0:
		pairs, total = _tail_pairs(path, -limit)
		selected = []
		bytes_used = 0
		truncated = False
		start = pairs[0][0] if pairs else 1
		for lineno, line in pairs:
			est = _est_numbered(lineno, line)
			if selected and bytes_used + est > cap:
				truncated = True
				break
			selected.append(line)
			bytes_used += est
		end_line = start + len(selected) - 1 if selected else start - 1
		out = {
			"path":        str(path),
			"total_lines": total,
			"offset":      start,
			"end_line":    end_line,
			"line_count":  len(selected),
			"content":     _format_numbered_lines(selected, start) if selected else "",
			"truncated":   truncated,
			"has_more":    truncated,
		}
		if truncated:
			out["note"] = f"output capped at {cap} bytes; use offset/limit for a smaller window"
		return out

	selected = []
	bytes_used = 0
	truncated = False
	hit_eof = True
	last_seen = 0
	start = offset
	for lineno, line in _iter_text_lines(path):
		last_seen = lineno
		if lineno < offset:
			continue
		if limit is not None and len(selected) >= limit:
			hit_eof = False
			break
		est = _est_numbered(lineno, line)
		if selected and bytes_used + est > cap:
			truncated = True
			hit_eof = False
			break
		selected.append(line)
		bytes_used += est
	end_line = start + len(selected) - 1 if selected else start - 1
	out = {
		"path":       str(path),
		"offset":     start,
		"end_line":   end_line,
		"line_count": len(selected),
		"content":    _format_numbered_lines(selected, start) if selected else "",
		"truncated":  truncated,
		"has_more":   not hit_eof,
	}
	if hit_eof:
		out["total_lines"] = last_seen
	if truncated:
		out["note"] = f"output capped at {cap} bytes; use offset/limit for a smaller window"
	return out


def _run_search(path, offset, limit, pattern, context, max_matches):
	try:
		regex = re.compile(pattern)
	except re.error as e:
		return tool_error(
			f"Invalid regex pattern: {e}",
			hint="Use Python re syntax. For a literal string, re.escape it first. Case-insensitive: prefix (?i).",
			path=str(path),
		)

	search_end = None
	total_known = None
	if limit is not None and limit < 0:
		pairs, total_known = _tail_pairs(path, -limit)
		if pairs:
			offset = pairs[0][0]
		search_end = pairs[-1][0] if pairs else 0
		line_iter = pairs
	else:
		if limit is not None:
			search_end = offset - 1 + limit
		line_iter = _iter_text_lines(path)

	want_ctx = context > 0
	prev = deque(maxlen=context) if want_ctx else None
	match_lines = []
	kept = {}
	ranges = []
	after_left = 0
	last_seen = 0
	hit_eof = True
	truncated = False

	for lineno, line in line_iter:
		last_seen = lineno
		if lineno < offset:
			continue
		if search_end is not None and lineno > search_end:
			hit_eof = False
			break

		if want_ctx and after_left > 0:
			kept[lineno] = line
			after_left -= 1

		if len(match_lines) < max_matches and regex.search(line):
			match_lines.append({"line": lineno, "text": line})
			if want_ctx:
				for pln, ptxt in prev:
					kept[pln] = ptxt
				kept[lineno] = line
				ranges.append((max(1, lineno - context), lineno + context))
				after_left = max(after_left, context)
			if len(match_lines) >= max_matches:
				truncated = True
				if after_left == 0:
					hit_eof = False
					break
		elif truncated and after_left == 0:
			hit_eof = False
			break

		if want_ctx:
			prev.append((lineno, line))
	else:
		hit_eof = True

	out = {
		"path":        str(path),
		"pattern":     pattern,
		"match_count": len(match_lines),
		"matches":     match_lines,
		"content":     "",
		"truncated":   truncated,
		"max_matches": max_matches,
	}
	if hit_eof or total_known is not None:
		out["total_lines"] = total_known if total_known is not None else last_seen
	if not match_lines or not want_ctx:
		return out

	parts = []
	for start, end in _merge_line_ranges(ranges):
		chunk = []
		first = None
		for i in range(start, end + 1):
			if i not in kept:
				continue
			if first is None:
				first = i
			chunk.append(kept[i])
		if chunk and first is not None:
			parts.append(_format_numbered_lines(chunk, first))
	content = "\n--\n".join(parts)
	cap = _DEFAULT_MAX_READ_BYTES
	if len(content.encode("utf-8")) > cap:
		content = content.encode("utf-8")[:cap].decode("utf-8", errors="ignore")
		truncated = True
		out["note"] = f"output capped at {cap} bytes; narrow the pattern or lower max_matches"
	out["content"] = content
	out["truncated"] = truncated
	return out


def dir_info(path, pattern="*", recursive=False, exclude=None, max_results=None):
	"""Return metadata for entries in a directory.

	This is a directory listing, not a file finder. Excluded directory names are
	matched relative to *path* (ancestors of the search root do not count) and
	are not descended into. Immediate excluded dirs still appear as stubs.

	Args:
		path:        Path to the directory (str or Path).
		pattern:     Glob pattern to filter entries (default '*', all entries).
		recursive:   If True, walk subdirectories (still pruned + capped).
		exclude:     Directory names to skip descending into (default:
		             ``_DEFAULT_EXCLUDE``). Pass an empty set to walk everything.
		max_results: Cap on returned entries (default 100, hard max 2000).

	Returns:
		dict with keys:
			path         Absolute path string
			entries      List of dicts (path, name, size, timestamps, permissions,
			             is_file / is_dir). No line counts.
			count        Number of entries in this result
			truncated    True if more matching entries exist beyond the cap
			max_results  Cap applied
	"""
	if exclude is None:
		exclude = _DEFAULT_EXCLUDE
	exclude = set(exclude)
	cap, err = _parse_max_dir_results(max_results)
	if err:
		return err

	p = resolve_path(path)
	if not p.exists():
		return tool_error(
			f"No such directory: {p}",
			hint="Pass an existing directory path. Use get_file_info for files.",
			path=str(p),
		)
	if not p.is_dir():
		return tool_error(
			f"Path is not a directory: {p}",
			hint="Use get_file_info or read_file for files.",
			path=str(p),
		)

	include_hidden = _pattern_allows_hidden(pattern)
	entries = []
	truncated = False
	for entry in _iter_tree(
		p,
		recursive=recursive,
		exclude=exclude,
		files_only=False,
		include_hidden=include_hidden,
	):
		if not _entry_matches_pattern(p, entry, pattern, recursive):
			continue
		item = _listing_entry(entry)
		if item is None:
			continue
		if len(entries) >= cap:
			truncated = True
			break
		entries.append(item)

	return {
		"path":        str(p),
		"entries":     entries,
		"count":       len(entries),
		"truncated":   truncated,
		"max_results": cap,
	}


def file_write(path, text, mode="replace", newline=True):
	"""Write text to a file (replace or append).

	Args:
		path:    Path to the file (str or Path).
		text:    Text to write.
		mode:    'replace' (default) overwrites or creates the file; 'append' adds to an existing file.
		newline: If True (default), ensure the written text ends with a newline.

	Returns dict with path, mode, and chars_written.
	"""
	if mode not in ("append", "replace"):
		return tool_error(
			f"mode must be 'append' or 'replace', got {mode!r}",
			hint="Use mode='replace' to create/overwrite, or mode='append' to add to an existing file.",
		)

	p = resolve_path(path)

	if mode == "append":
		if not p.exists():
			return tool_error(
				f"No such file: {p}",
				hint="append requires an existing file. Use mode='replace' to create it.",
				path=str(p),
			)
		if not p.is_file():
			return tool_error(
				f"Path is not a file: {p}",
				hint="write_file only writes files, not directories.",
				path=str(p),
			)
	else:
		try:
			p.parent.mkdir(parents=True, exist_ok=True)
		except OSError as e:
			return tool_error(str(e), hint="Cannot create parent directories. Check permissions.", path=str(p))

	if newline and text and not text.endswith("\n"):
		text = text + "\n"

	try:
		if mode == "append":
			with p.open("a", encoding="utf-8") as f:
				f.write(text)
		else:
			p.write_text(text, encoding="utf-8")
	except OSError as e:
		return tool_error(str(e), hint="Check file permissions and that the path is writable.", path=str(p))

	return {
		"path":          str(p),
		"mode":          mode,
		"chars_written": len(text),
	}


def _http_read(url, *, method="GET", headers=None, data=None,
	timeout=_DEFAULT_HTTP_TIMEOUT, max_bytes=_DEFAULT_FETCH_MAX_BYTES):
	"""GET/POST a URL with timeout, User-Agent, and a hard body-size cap.

	Returns dict: status, content_type, raw (bytes), truncated.
	Raises urllib.error.URLError / HTTPError / TimeoutError on failure.
	"""
	import urllib.request

	req_headers = dict(headers or {})
	req_headers.setdefault("User-Agent", _USER_AGENT)
	req = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
	with urllib.request.urlopen(req, timeout=timeout) as resp:
		status = resp.status
		ctype = resp.headers.get("Content-Type", "")
		chunks = []
		n = 0
		hit_cap = False
		while n < max_bytes:
			buf = resp.read(min(65536, max_bytes - n))
			if not buf:
				break
			chunks.append(buf)
			n += len(buf)
		else:
			if resp.read(1):
				hit_cap = True
		return {
			"status":       status,
			"content_type": ctype,
			"raw":          b"".join(chunks),
			"truncated":    hit_cap,
		}


def file_download(url, filename=None, dirpath=None):
	"""Download a file from a URL to local storage.

	Args:
		url:      URL to download.
		filename: Local filename. Defaults to the last path segment of the URL.
		dirpath:  Destination directory. Defaults to CAIT_FILES_PATH (~/.cait/files/).

	Returns dict with path, filename, size_bytes, size, and url.
	Times out after 30s; bodies larger than 100 MB are rejected.
	"""
	import urllib.error

	dest_dir = resolve_path(dirpath) if dirpath else _DEFAULT_FILEDIR

	if not filename:
		filename = url.split("/")[-1].split("?")[0].split("#")[0]
	filename = Path(filename).name
	if not filename or filename in (".", ".."):
		filename = "download"

	dest = (dest_dir / filename).resolve()
	try:
		dest.relative_to(dest_dir.resolve())
	except ValueError:
		return tool_error(
			f"Refusing to write outside the download directory: {filename}",
			hint="Pass a plain filename with no directory components.",
			url=url,
		)

	try:
		dest_dir.mkdir(parents=True, exist_ok=True)
	except OSError as e:
		return tool_error(str(e), hint="Cannot create the download directory. Check CAIT_FILES_PATH permissions.", path=str(dest_dir))
	try:
		got = _http_read(url, timeout=_DEFAULT_HTTP_TIMEOUT, max_bytes=_DEFAULT_DOWNLOAD_MAX_BYTES)
	except urllib.error.HTTPError as e:
		return tool_error(
			f"HTTP {e.code}: {e.reason}",
			hint="Check the URL. Some hosts block requests without a browser User-Agent; CAIT already sends one.",
			url=url,
			status_code=e.code,
		)
	except Exception as e:
		return tool_error(
			f"Download failed: {e}",
			hint="Check the URL, or retry; downloads time out after 30s.",
			url=url,
		)

	if got["truncated"]:
		return tool_error(
			f"Download exceeded {_DEFAULT_DOWNLOAD_MAX_BYTES} bytes",
			hint="File is larger than the 100 MB download cap.",
			url=url,
		)

	dest.write_bytes(got["raw"])
	st = dest.stat()
	return {
		"path":       str(dest),
		"filename":   dest.name,
		"size_bytes": st.st_size,
		"size":       _human_size(st.st_size),
		"url":        url,
	}


def fetch_url(url, method="GET", headers=None, data=None, save_to="", convert=False):
	"""Fetch a URL and return the response body as text.

	Args:
		url:      URL to fetch.
		method:   HTTP method — "GET" (default) or "POST".
		headers:  Optional dict of request headers (e.g. {"Authorization": "Bearer ..."}).
		data:     Optional body for POST requests. A dict is form-encoded; a str is
		          sent as-is with Content-Type: text/plain unless overridden in headers.
		save_to:  If given, write the response body to this file path and omit 'content'
		          from the returned dict. The directory is created if it does not exist.
		convert:  If True, run the response through convert_doc and return 'markdown'.
		          On success, raw 'content' is omitted (same idea as save_to). Large pages
		          should still use save_to — inline markdown is capped at ~100KB.

	Returns dict with: url, status_code, content_type, size_bytes.
	Plus 'content' (str) unless save_to is given or convert succeeds.
	Plus 'saved_to' (path) when save_to is given.
	Plus 'markdown' (str) when convert=True succeeds.
	Inline text fields are capped (~100KB); truncated results include truncation flags.
	"""
	import urllib.parse
	import urllib.error

	req_headers = dict(headers or {})

	# Build body
	body = None
	if data is not None:
		if isinstance(data, dict):
			body = urllib.parse.urlencode(data).encode()
			req_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
		else:
			body = data.encode() if isinstance(data, str) else data
			req_headers.setdefault("Content-Type", "text/plain")

	try:
		got = _http_read(
			url,
			method=method,
			headers=req_headers,
			data=body,
			timeout=_DEFAULT_HTTP_TIMEOUT,
			max_bytes=_DEFAULT_FETCH_MAX_BYTES,
		)
	except urllib.error.HTTPError as e:
		return tool_error(
			f"HTTP {e.code}: {e.reason}",
			hint="Check the URL and method. CAIT sends a User-Agent; add headers if the host requires auth.",
			url=url,
			status_code=e.code,
		)
	except Exception as e:
		return tool_error(
			str(e),
			hint="fetch_url times out after 30s. Use download_file or save_to for large bodies.",
			url=url,
		)

	status = got["status"]
	ctype = got["content_type"]
	raw = got["raw"]
	result = {"url": url, "status_code": status, "content_type": ctype, "size_bytes": len(raw)}
	if got["truncated"]:
		result["truncated"] = True
		result["note"] = f"response body capped at {_DEFAULT_FETCH_MAX_BYTES} bytes"

	decoded = None
	encoding = "utf-8"
	if "charset=" in ctype:
		encoding = ctype.split("charset=")[-1].split(";")[0].strip() or "utf-8"
	try:
		decoded = raw.decode(encoding, errors="replace")
	except Exception:
		decoded = raw.decode("latin-1", errors="replace")

	if save_to:
		p = resolve_path(save_to)
		p.parent.mkdir(parents=True, exist_ok=True)
		p.write_bytes(raw)
		result["saved_to"] = str(p)
	else:
		result["content"] = decoded

	if convert:
		from cait.document import convert_doc
		import tempfile, os

		src = result.get("saved_to") or ""
		tmp = None
		try:
			if not src:
				suffix = ".html" if "html" in (ctype or "").lower() else ".txt"
				with tempfile.NamedTemporaryFile(
					delete=False, suffix=suffix, mode="w", encoding="utf-8",
				) as f:
					f.write(decoded or "")
					tmp = f.name
				src = tmp
			md = convert_doc(src)
			md_text = md.get("content")
			if not md_text:
				raise RuntimeError(md.get("error") or "convert_doc returned empty content")
			md_text, trunc_meta = cap_inline_text(md_text)
			result["markdown"] = md_text
			if md.get("backend"):
				result["convert_backend"] = md["backend"]
			if trunc_meta:
				result["markdown_truncated"] = True
				result["markdown_original_bytes"] = trunc_meta["original_bytes"]
				result["markdown_max_bytes"] = trunc_meta["max_bytes"]
			# Never ship raw HTML/body alongside converted markdown.
			result.pop("content", None)
		except Exception as e:
			result.pop("content", None)
			result["error"] = f"convert failed: {e}"
			result["hint"] = (
				"Save the page with save_to=... then use convert_doc or search_doc "
				"on the saved file instead of returning it inline."
			)
			if decoded and not save_to:
				preview, _ = cap_inline_text(
					decoded,
					max_bytes=min(2_000, _DEFAULT_MAX_INLINE_BYTES),
					hint="Full body omitted after convert failure.",
				)
				result["content_preview"] = preview
		finally:
			if tmp:
				try:
					os.unlink(tmp)
				except OSError:
					pass
		return result

	if "content" in result:
		text, trunc_meta = cap_inline_text(result["content"])
		result["content"] = text
		if trunc_meta:
			result["truncated"] = True
			result["original_bytes"] = trunc_meta["original_bytes"]
			result["max_bytes"] = trunc_meta["max_bytes"]

	return result
