"""
cait.utils — Lightweight utility tools: datetime and named timers.
"""

import time
from datetime import datetime
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
