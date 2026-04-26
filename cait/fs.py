"""
cait.fs — File and directory metadata tools.

Functions return plain dicts and never read file content into memory.
All paths accept str or Path objects.
"""

import os
import stat
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_EXCLUDE = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules"}
_DEFAULT_FILEDIR = Path(os.environ.get("CAIT_FILES_PATH", Path.home() / ".cait" / "files"))

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


def file_append(path, text, newline=True):
	"""Append text to an existing file.

	Args:
		path:    Path to the file (str or Path).
		text:    Text to append.
		newline: If True (default), ensure the appended text ends with a newline.

	Returns dict with path, appended_chars, and the file's new total line count.
	Raises FileNotFoundError if the file does not exist.
	"""
	p = Path(path).resolve()
	if not p.exists():
		raise FileNotFoundError(f"No such file: {p}")
	if not p.is_file():
		raise ValueError(f"Path is not a file: {p}")

	if newline and text and not text.endswith("\n"):
		text = text + "\n"

	with p.open("a", encoding="utf-8") as f:
		f.write(text)

	return {
		"path":           str(p),
		"appended_chars": len(text),
		"lines":          _count_lines(p),
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
