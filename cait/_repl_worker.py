#!/usr/bin/env python3
"""
Persistent REPL worker process for cait.repl.

Reads JSON requests from stdin, executes Python code in a shared namespace,
and writes JSON responses to stdout. Runs as a subprocess managed by repl.py.
"""

import io
import json
import sys
import traceback

_MAX_REPR = 4000
_MAX_LIST_REPR = 200
_MAX_VALUE_JSON = 8000

# Shared namespace that persists across all executions
namespace = {"__name__": "__repl__", "__doc__": None}


def execute(code):
	"""Execute code in the shared namespace, capturing stdout/stderr."""
	captured_out = io.StringIO()
	captured_err = io.StringIO()
	real_stdout = sys.stdout
	real_stderr = sys.stderr
	error = None

	sys.stdout = captured_out
	sys.stderr = captured_err
	try:
		exec(compile(code, "<repl>", "exec"), namespace)
	except SystemExit as e:
		# Catch sys.exit() so it doesn't kill the worker
		error = f"SystemExit({e.code})"
	except Exception:
		error = traceback.format_exc()
	finally:
		# Always restore — even if the executed code replaced sys.stdout/stderr
		sys.stdout = real_stdout
		sys.stderr = real_stderr

	return {
		"stdout": captured_out.getvalue(),
		"stderr": captured_err.getvalue(),
		"error":  error,
	}


def read_var(name):
	"""Return structured info about a variable in the shared namespace."""
	if name not in namespace:
		return {"found": False, "name": name, "repr": None, "type": None, "value": None}

	obj = namespace[name]
	type_name = type(obj).__name__
	repr_str = repr(obj)
	repr_truncated = False
	if len(repr_str) > _MAX_REPR:
		repr_str = repr_str[:_MAX_REPR] + "…"
		repr_truncated = True

	# Attempt JSON serialization for primitive types; fall back to None
	value = None
	try:
		encoded = json.dumps(obj)
		if len(encoded) <= _MAX_VALUE_JSON:
			value = obj
	except (TypeError, ValueError):
		pass

	return {
		"found":          True,
		"name":           name,
		"repr":           repr_str,
		"repr_truncated": repr_truncated,
		"type":           type_name,
		"value":          value,
	}


def list_vars():
	"""Return all user-defined variables in the namespace with type, repr, and value."""
	import builtins
	builtin_names = set(dir(builtins))
	entries = {}
	for name, obj in namespace.items():
		if name.startswith("__") or name in builtin_names:
			continue
		repr_str = repr(obj)
		if len(repr_str) > _MAX_LIST_REPR:
			repr_str = repr_str[:_MAX_LIST_REPR] + "…"
		value = None
		try:
			encoded = json.dumps(obj)
			if len(encoded) <= _MAX_VALUE_JSON:
				value = obj
		except (TypeError, ValueError):
			pass
		entries[name] = {"type": type(obj).__name__, "repr": repr_str, "value": value}
	return {"vars": entries, "count": len(entries)}


def main():
	for line in sys.stdin:
		line = line.strip()
		if not line:
			continue
		try:
			req = json.loads(line)
		except (json.JSONDecodeError, ValueError):
			result = {"stdout": "", "stderr": "", "error": "Invalid JSON request"}
		else:
			if "read" in req:
				result = read_var(req["read"])
			elif "vars" in req:
				result = list_vars()
			else:
				result = execute(req.get("code", ""))

		try:
			sys.stdout.write(json.dumps(result) + "\n")
		except (TypeError, ValueError) as e:
			sys.stdout.write(json.dumps({
				"stdout": "",
				"stderr": "",
				"error":  f"Result not JSON-serializable: {e}",
			}) + "\n")
		sys.stdout.flush()


if __name__ == "__main__":
	main()
