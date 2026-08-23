"""Structured errors for MCP-facing functions.

Recoverable failures return a dict so hosts show them as tool results the agent
can read and retry. Do not raise from public tool functions.

Every error dict has ``error``. ``hint`` is included when there is a useful next step.
"""


def tool_error(error, hint=None, **extra):
	"""Build a standard ``{error, hint, ...}`` result dict."""
	out = {"error": str(error)}
	if hint:
		out["hint"] = hint
	for key, value in extra.items():
		if value is not None:
			out[key] = value
	return out
