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

	# Attempt JSON serialization for primitive types; fall back to None
	try:
		json.dumps(obj)
		value = obj
	except (TypeError, ValueError):
		value = None

	return {"found": True, "name": name, "repr": repr_str, "type": type_name, "value": value}


def list_vars():
	"""Return all user-defined variables in the namespace with type, repr, and value."""
	import builtins
	builtin_names = set(dir(builtins))
	entries = {}
	for name, obj in namespace.items():
		if name.startswith("__") or name in builtin_names:
			continue
		repr_str = repr(obj)
		if len(repr_str) > 200:
			repr_str = repr_str[:200] + "…"
		try:
			json.dumps(obj)
			value = obj
		except (TypeError, ValueError):
			value = None
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

		sys.stdout.write(json.dumps(result) + "\n")
		sys.stdout.flush()


if __name__ == "__main__":
	main()
