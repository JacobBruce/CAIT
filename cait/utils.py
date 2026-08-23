"""
cait.utils — Lightweight utility tools: datetime, named timers, and runtime status.
"""

import importlib.util
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cait.fs import _DEFAULT_EXCLUDE, _DEFAULT_FILEDIR, workspace_root
from cait.errors import tool_error

_ALL_MODULES = (
	"fs", "text", "code", "repl", "wiki", "arxiv", "utils", "memory", "document",
)

# ── Named timers ──────────────────────────────────────────────────────────────

_timers: dict[str, float] = {}


def timer_start(name="default"):
	"""Start (or restart) a named timer."""
	_timers[name] = time.perf_counter()
	return {"name": name, "started": True}


def timer_stop(name="default"):
	"""Stop a named timer and return elapsed seconds. Removes it from the active set."""
	if name not in _timers:
		return tool_error(
			f"No timer named {name!r} is running",
			hint="Call timer_start first with the same name.",
			name=name,
		)
	elapsed = time.perf_counter() - _timers.pop(name)
	return {"name": name, "elapsed_s": round(elapsed, 6)}


def timer_list():
	"""Return all currently running timers and their elapsed time so far."""
	now = time.perf_counter()
	return {
		"timers": [
			{"name": name, "elapsed_s": round(now - start, 6)}
			for name, start in _timers.items()
		]
	}


# ── Datetime ──────────────────────────────────────────────────────────────────

def get_datetime(timezone=None):
	"""Return the current date and time.

	Args:
		timezone: IANA timezone name (e.g. "America/New_York", "UTC").
		          Defaults to the system local timezone.

	Returns dict with: datetime (ISO 8601), date, time, timezone, utc_offset, weekday, unix.
	"""
	if timezone:
		try:
			tz = ZoneInfo(timezone)
		except ZoneInfoNotFoundError:
			return tool_error(
				f"Unknown timezone {timezone!r}",
				hint="Use an IANA name such as 'America/New_York' or 'UTC'.",
			)
		now = datetime.now(tz)
	else:
		now = datetime.now().astimezone()	# system local timezone

	return {
		"datetime":   now.isoformat(),
		"date":       now.date().isoformat(),
		"time":       now.time().strftime("%H:%M:%S"),
		"timezone":   str(now.tzinfo),
		"utc_offset": now.strftime("%z"),
		"weekday":    now.strftime("%A"),
		"unix":       now.timestamp(),
	}


# ── Runtime status ────────────────────────────────────────────────────────────

def _pkg_version(name):
	try:
		from importlib.metadata import version
		return version(name)
	except Exception:
		return None


def _mcp_protocol_version():
	try:
		from mcp.types import LATEST_PROTOCOL_VERSION
		return str(LATEST_PROTOCOL_VERSION)
	except Exception:
		return None


def status():
	"""Runtime snapshot for diagnosing CAIT environment (no arguments).

	Returns toolkit name, versions, Python, workspace vs cwd, enabled modules,
	memory/files/cache paths, default junk-dir excludes, MCP information, and
	whether chromadb is importable.
	"""
	ws_env = str(os.environ.get("CAIT_WORKSPACE", "") or "").strip()
	disabled = {
		m.strip().lower()
		for m in os.environ.get("CAIT_DISABLE", "").split(",")
		if m.strip()
	}
	try:
		from cait import __version__ as version
	except Exception:
		version = "unknown"
	memory_path = Path(os.environ.get("CAIT_MEMORY_PATH", Path.home() / ".cait" / "memory"))
	files_path = Path(os.environ.get("CAIT_FILES_PATH", str(_DEFAULT_FILEDIR)))
	try:
		cwd = str(Path.cwd())
	except OSError:
		cwd = ""
	return {
		"name": "CAIT - Core AI Toolkit",
		"version": version,
		"python": sys.version.split()[0],
		"python_executable": sys.executable,
		"workspace": str(workspace_root()),
		"workspace_env_set": bool(ws_env),
		"cwd": cwd,
		"memory_path": str(memory_path.expanduser()),
		"files_path": str(files_path.expanduser()),
		"cache_path": str((files_path / "doc_cache").expanduser()),
		"chromadb": importlib.util.find_spec("chromadb") is not None,
		"fastmcp": _pkg_version("fastmcp"),
		"mcp": _pkg_version("mcp"),
		"mcp_protocol": _mcp_protocol_version(),
		"default_exclude": sorted(_DEFAULT_EXCLUDE),
		"modules": {
			"enabled": [m for m in _ALL_MODULES if m not in disabled],
			"disabled": [m for m in _ALL_MODULES if m in disabled],
		}
	}
