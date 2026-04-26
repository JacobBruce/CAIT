"""
cait.utils — Lightweight utility tools: datetime, named timers, and text diff.
"""

import difflib
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# ── Named timers ──────────────────────────────────────────────────────────────

_timers: dict[str, float] = {}


def timer_start(name="default"):
	"""Start (or restart) a named timer."""
	_timers[name] = time.perf_counter()
	return {"name": name, "started": True}


def timer_stop(name="default"):
	"""Stop a named timer and return elapsed seconds. Removes it from the active set."""
	if name not in _timers:
		return {"name": name, "error": f"No timer named {name!r} is running"}
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
			return {"error": f"Unknown timezone {timezone!r}. Use an IANA name such as 'America/New_York' or 'UTC'."}
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


# ── Text diff ─────────────────────────────────────────────────────────────────

def diff_text(a, b, context=3, label_a="a", label_b="b"):
	"""Return a unified diff between two strings or files.

	Args:
		a:        Original text or file path.
		b:        Modified text or file path.
		context:  Number of unchanged context lines shown around each change (default 3).
		label_a:  Label for the original in the diff header. Defaults to filename if a path is given.
		label_b:  Label for the modified in the diff header. Defaults to filename if a path is given.

	Returns dict with: diff (unified diff string), changed (bool), added, removed (line counts).
	"""
	def _src(s, default_label):
		try:
			p = Path(s)
			if p.exists() and p.is_file():
				return p.read_text(encoding="utf-8"), p.name
		except (OSError, ValueError):
			pass
		return s, default_label

	a, label_a = _src(a, label_a)
	b, label_b = _src(b, label_b)

	lines_a = a.splitlines(keepends=True)
	lines_b = b.splitlines(keepends=True)
	chunks = list(difflib.unified_diff(lines_a, lines_b, fromfile=label_a, tofile=label_b, n=context))
	added   = sum(1 for l in chunks if l.startswith("+") and not l.startswith("+++"))
	removed = sum(1 for l in chunks if l.startswith("-") and not l.startswith("---"))
	return {
		"diff":    "".join(chunks),
		"changed": bool(chunks),
		"added":   added,
		"removed": removed,
	}
