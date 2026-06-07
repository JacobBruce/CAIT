"""
cait.fs — File I/O, directory metadata, downloads, and HTTP fetch helpers.

All paths accept str or Path objects. Functions return plain dicts.
"""

import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_EXCLUDE = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules"}
_DEFAULT_FILEDIR = Path(os.environ.get("CAIT_FILES_PATH", Path.home() / ".cait" / "files"))
_DEFAULT_MAX_READ_BYTES = 256_000

# ── helpers ──────────────────────────────────────────────────────────────────

def _human_size(n_bytes):
	"""Convert a byte count to a human-readable string (e.g. '1.4 MB')."""
	for unit in ("B", "KB", "MB", "GB", "TB"):
		if n_bytes < 1024 or unit == "TB":
			return f"{n_bytes:.1f} {unit}" if unit != "B" else f"{n_bytes} B"
		n_bytes /= 1024


def _iso(ts):
	"""Convert a POSIX timestamp to an ISO 8601 string in UTC."""
	return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _count_lines(path):
	"""Count newlines in a file efficiently without loading it all into memory."""
	count = 0
	with open(path, "rb") as f:
		while chunk := f.read(1 << 16):	 # 64 KB blocks
			count += chunk.count(b"\n")
	return count


def _permission_string(mode):
	"""Return a Unix-style permission string, e.g. '-rw-r--r--'."""
	return stat.filemode(mode)


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
	p = Path(path).resolve()
	if not p.exists():
		raise FileNotFoundError(f"No such file: {p}")
	if not p.is_file():
		raise ValueError(f"Path is not a file: {p}")

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


def file_read(
	path,
	offset=1,
	limit=None,
	max_bytes=_DEFAULT_MAX_READ_BYTES,
	pattern=None,
	context=2,
	ignore_case=False,
	max_matches=100,
):
	"""Read a text file with optional line slice or regex search.

	Slice mode (pattern empty): returns lines from *offset* (1-based), stopping at
	*limit* lines and/or when *max_bytes* of output would be exceeded. A negative
	*limit* reads the last ``abs(limit)`` lines (*offset* is ignored).

	Search mode (pattern set): finds regex matches and returns merged context windows
	around each hit (like grep -C). *context* is the number of lines before/after each
	match included in *content* (ignored in slice mode). *offset* / *limit* optionally
	restrict the line range searched; negative *limit* searches only the file tail.
	Stops after *max_matches* matching lines.

	Returns numbered content (``lineno|text``), total file line count, and truncation flags.
	"""
	p = Path(path).resolve()
	if not p.exists():
		raise FileNotFoundError(f"No such file: {p}")
	if not p.is_file():
		raise ValueError(f"Path is not a file: {p}")
	if offset < 1:
		raise ValueError(f"offset must be >= 1, got {offset}")
	if limit == 0:
		raise ValueError("limit must not be 0; use a positive line count or a negative value for tail reads (e.g. -50)")
	if context < 0:
		raise ValueError(f"context must be >= 0, got {context}")
	if max_matches < 1:
		raise ValueError(f"max_matches must be >= 1, got {max_matches}")

	if _is_probably_binary(p):
		return {
			"error": "File appears to be binary — read_file only supports text files",
			"path":  str(p),
		}

	try:
		raw_lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
	except OSError as e:
		return {"error": str(e), "path": str(p)}

	total_lines = len(raw_lines)
	if limit is not None and limit < 0:
		tail_count = -limit
		offset = max(1, total_lines - tail_count + 1)
		limit = tail_count
	end_offset = total_lines if limit is None else min(total_lines, offset - 1 + limit)
	search_end = end_offset

	if pattern:
		try:
			flags = re.IGNORECASE if ignore_case else 0
			regex = re.compile(pattern, flags)
		except re.error as e:
			return {"error": f"Invalid regex pattern: {e}", "path": str(p)}

		ranges = []
		match_lines = []
		for lineno in range(offset, search_end + 1):
			if lineno > total_lines:
				break
			line = raw_lines[lineno - 1]
			if not regex.search(line):
				continue
			match_lines.append({"line": lineno, "text": line})
			lo = max(1, lineno - context)
			hi = min(total_lines, lineno + context)
			ranges.append((lo, hi))
			if len(match_lines) >= max_matches:
				break

		if not match_lines:
			return {
				"path":        str(p),
				"mode":        "search",
				"pattern":     pattern,
				"total_lines": total_lines,
				"match_count": 0,
				"matches":     [],
				"content":     "",
				"truncated":   False,
			}

		parts = [
			_format_numbered_lines(raw_lines[start - 1:end], start)
			for start, end in _merge_line_ranges(ranges)
		]
		content = "\n--\n".join(parts)
		truncated = len(match_lines) >= max_matches
		if len(content.encode("utf-8")) > max_bytes:
			content = content.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
			truncated = True

		return {
			"path":        str(p),
			"mode":        "search",
			"pattern":     pattern,
			"total_lines": total_lines,
			"match_count": len(match_lines),
			"matches":     match_lines,
			"content":     content,
			"truncated":   truncated,
			"max_matches": max_matches,
		}

	# Slice mode
	selected = []
	bytes_used = 0
	truncated = False
	for lineno in range(offset, search_end + 1):
		if lineno > total_lines:
			break
		line = raw_lines[lineno - 1]
		# Estimate formatted line size (+1 for newline when joined)
		est = len(str(lineno)) + 1 + len(line) + 1
		if selected and bytes_used + est > max_bytes:
			truncated = True
			break
		selected.append(line)
		bytes_used += est
		if limit is not None and len(selected) >= limit:
			break

	has_more = truncated or (offset + len(selected) - 1) < total_lines
	return {
		"path":        str(p),
		"mode":        "slice",
		"total_lines": total_lines,
		"offset":      offset,
		"end_line":    offset + len(selected) - 1 if selected else offset - 1,
		"line_count":  len(selected),
		"content":     _format_numbered_lines(selected, offset) if selected else "",
		"truncated":   has_more,
		"max_bytes":   max_bytes,
	}


def dir_info(path, pattern="*", recursive=False, exclude=None):
	"""Return metadata for entries in a directory.

	Args:
		path:      Path to the directory (str or Path).
		pattern:   Glob pattern to filter entries (default '*', all entries).
		recursive: If True, search all subdirectories.
		exclude:   Set of directory names to skip entirely (default: .git,
		           .venv, __pycache__, .mypy_cache, .pytest_cache, node_modules).
		           Pass an empty set to disable all exclusions.

	Returns:
		dict with keys:
			path     Absolute path string
			entries  List of dicts, each with the same keys as file_info() plus
			         is_dir=True / is_file=False for subdirectories.
			         Subdirectories do not include line counts or sizes.
			count    Total number of matching entries
	"""
	if exclude is None:
		exclude = _DEFAULT_EXCLUDE
	exclude = set(exclude)

	p = Path(path).resolve()
	if not p.exists():
		raise FileNotFoundError(f"No such directory: {p}")
	if not p.is_dir():
		raise ValueError(f"Path is not a directory: {p}")

	def _is_excluded(entry):
		# Reject any entry whose path contains an excluded directory name
		return any(part in exclude for part in entry.parts)

	glob = p.rglob(pattern) if recursive else p.glob(pattern)

	entries = []
	for entry in sorted(glob):
		if _is_excluded(entry):
			continue
		try:
			st = entry.stat()
		except OSError:
			continue

		if entry.is_dir():
			entries.append({
				"path":        str(entry),
				"name":        entry.name,
				"size_bytes":  None,
				"size":        None,
				"lines":       None,
				"modified":    _iso(st.st_mtime),
				"created":     _iso(st.st_ctime),
				"permissions": _permission_string(st.st_mode),
				"is_file":     False,
				"is_dir":      True,
			})
		else:
			lines = None
			try:
				lines = _count_lines(entry)
			except OSError:
				pass

			entries.append({
				"path":        str(entry),
				"name":        entry.name,
				"size_bytes":  st.st_size,
				"size":        _human_size(st.st_size),
				"lines":       lines,
				"modified":    _iso(st.st_mtime),
				"created":     _iso(st.st_ctime),
				"permissions": _permission_string(st.st_mode),
				"is_file":     True,
				"is_dir":      False,
			})

	return {
		"path":    str(p),
		"entries": entries,
		"count":   len(entries),
	}


def file_write(path, text, mode="append", newline=True):
	"""Write text to a file (append or replace).

	Args:
		path:    Path to the file (str or Path).
		text:    Text to write.
		mode:    'append' adds to an existing file; 'replace' overwrites or creates it.
		newline: If True (default), ensure the written text ends with a newline.

	Returns dict with path, mode, chars_written, and the file's total line count.
	Raises FileNotFoundError if mode is 'append' and the file does not exist.
	"""
	if mode not in ("append", "replace"):
		raise ValueError(f"mode must be 'append' or 'replace', got {mode!r}")

	p = Path(path).resolve()

	if mode == "append":
		if not p.exists():
			raise FileNotFoundError(f"No such file: {p}")
		if not p.is_file():
			raise ValueError(f"Path is not a file: {p}")
	else:
		p.parent.mkdir(parents=True, exist_ok=True)

	if newline and text and not text.endswith("\n"):
		text = text + "\n"

	if mode == "append":
		with p.open("a", encoding="utf-8") as f:
			f.write(text)
	else:
		p.write_text(text, encoding="utf-8")

	return {
		"path":          str(p),
		"mode":          mode,
		"chars_written": len(text),
		"lines":         _count_lines(p),
	}


def file_download(url, filename=None, dirpath=None):
	"""Download a file from a URL to local storage.

	Args:
		url:      URL to download.
		filename: Local filename. Defaults to the last path segment of the URL.
		dirpath:  Destination directory. Defaults to CAIT_FILES_PATH (~/.cait/files/).

	Returns dict with path, filename, size_bytes, size, and url.
	"""
	import urllib.request

	dest_dir = Path(dirpath) if dirpath else _DEFAULT_FILEDIR
	dest_dir.mkdir(parents=True, exist_ok=True)

	if not filename:
		filename = url.split("/")[-1].split("?")[0].split("#")[0]
		if not filename:
			filename = "download"

	dest = dest_dir / filename
	try:
		urllib.request.urlretrieve(url, str(dest))
	except Exception as e:
		return {"error": f"Download failed: {e}", "url": url}

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
		convert:  If True, feed the saved/fetched content through convert_doc and return
		          'markdown' in the result. Requires save_to when the response is binary
		          (e.g. PDF); for text responses convert works inline.

	Returns dict with: url, status_code, content_type, size_bytes.
	Plus 'content' (str) unless save_to is given.
	Plus 'saved_to' (path) when save_to is given.
	Plus 'markdown' (str) when convert=True.
	"""
	import urllib.request
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

	req = urllib.request.Request(url, data=body, headers=req_headers, method=method.upper())

	try:
		with urllib.request.urlopen(req) as resp:
			status  = resp.status
			ctype   = resp.headers.get("Content-Type", "")
			raw     = resp.read()
	except urllib.error.HTTPError as e:
		return {"error": f"HTTP {e.code}: {e.reason}", "url": url, "status_code": e.code}
	except Exception as e:
		return {"error": str(e), "url": url}

	result = {"url": url, "status_code": status, "content_type": ctype, "size_bytes": len(raw)}

	if save_to:
		p = Path(save_to)
		p.parent.mkdir(parents=True, exist_ok=True)
		p.write_bytes(raw)
		result["saved_to"] = str(p.resolve())
	else:
		# Try to decode as text
		encoding = "utf-8"
		if "charset=" in ctype:
			encoding = ctype.split("charset=")[-1].split(";")[0].strip()
		try:
			result["content"] = raw.decode(encoding, errors="replace")
		except Exception:
			result["content"] = raw.decode("latin-1", errors="replace")

	if convert:
		# Lazy import to avoid circular dependency at module load time
		from cait.document import convert_doc
		src = result.get("saved_to") or save_to
		if src:
			md = convert_doc(src)
			result["markdown"] = md.get("content", md.get("error", ""))
		else:
			# No file saved — wrap inline text in a temp file for conversion
			import tempfile, os
			suffix = ".html" if "html" in ctype else ".txt"
			with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode="w", encoding="utf-8") as f:
				f.write(result.get("content", ""))
				tmp = f.name
			try:
				md = convert_doc(tmp)
				result["markdown"] = md.get("content", md.get("error", ""))
			finally:
				os.unlink(tmp)

	return result
