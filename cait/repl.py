"""
cait.repl — Persistent Python REPL manager.

Maintains a long-lived subprocess whose namespace persists between execute()
calls. Useful for iterative computation, SymPy sessions, and multi-step
data analysis where intermediate variables must survive across calls.
"""

import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

_WORKER = Path(__file__).parent / "_repl_worker.py"

_process = None
_lock = threading.Lock()


def _start():
	"""Spawn a fresh worker subprocess."""
	return subprocess.Popen(
		[sys.executable, str(_WORKER)],
		stdin=subprocess.PIPE,
		stdout=subprocess.PIPE,
		stderr=subprocess.DEVNULL,	# worker's own startup noise; not user code stderr
		text=True,
		bufsize=1,	# line-buffered so responses arrive immediately
	)


def _get_process():
	"""Return the running worker, starting or restarting it if needed."""
	global _process
	restarted = False
	if _process is None or _process.poll() is not None:
		if _process is not None:
			_process.wait()	# reap zombie
		_process = _start()
		restarted = True
	return _process, restarted


def _send_recv(proc, request, timeout):
	"""Send a JSON request to the worker and return the parsed response, or None on timeout/crash.

	Uses a reader thread instead of select() so timeouts work on Windows pipes.
	"""
	proc.stdin.write(request)
	proc.stdin.flush()

	box = queue.Queue(maxsize=1)

	def _read_line():
		try:
			box.put(("ok", proc.stdout.readline()))
		except Exception as exc:
			box.put(("err", exc))

	threading.Thread(target=_read_line, daemon=True).start()
	try:
		kind, payload = box.get(timeout=timeout)
	except queue.Empty:
		return None, "timeout"
	if kind == "err":
		return None, "crash"
	line = payload
	if not line:
		return None, "crash"
	try:
		return json.loads(line), None
	except json.JSONDecodeError:
		return {"stdout": line, "stderr": "", "error": None}, None


def _run_request(payload, timeout):
	"""Send payload to the worker, handling restarts and failures.

	Returns (result_dict, restarted).
	"""
	global _process
	proc, restarted = _get_process()
	request = json.dumps(payload) + "\n"

	try:
		result, failure = _send_recv(proc, request, timeout)
	except BrokenPipeError:
		proc.kill()
		proc.wait()
		proc = _start()
		_process = proc
		restarted = True
		result, failure = _send_recv(proc, request, timeout)

	if failure == "timeout":
		proc.kill()
		proc.wait()
		_process = None
		return {"error": f"Execution timed out after {timeout}s — REPL has been reset", "hint": "Simplify the code, or pass a higher timeout to repl_exec."}, True
	if failure == "crash":
		proc.wait()
		_process = None
		return {"error": "REPL worker crashed unexpectedly — REPL has been reset", "hint": "Re-run the last snippet. Session variables were cleared."}, True

	return result, restarted


def execute(code, timeout=30):
	"""Execute Python code in the persistent REPL and return captured output.

	Args:
		code:    Python source code to execute (may be multi-line).
		timeout: Seconds before the worker is killed and reset (default 30).

	Returns:
		dict with keys:
			stdout     Captured standard output from the executed code
			stderr     Captured standard error from the executed code
			error      Exception traceback string, or None if no error
			restarted  True if the REPL was restarted (prior state is lost)
	"""
	with _lock:
		result, restarted = _run_request({"code": code}, timeout)
	result.setdefault("stdout", "")
	result.setdefault("stderr", "")
	result.setdefault("error", None)
	result["restarted"] = restarted
	return result


def read_var(name, timeout=10):
	"""Read the value of a variable from the persistent REPL namespace.

	Args:
		name:    Variable name to look up.
		timeout: Seconds before the request times out (default 10).

	Returns:
		dict with keys:
			found  True if the variable exists in the session namespace
			name   The requested variable name
			repr   repr() string of the value, or None if not found
			type   Type name of the value, or None if not found
			value  JSON-serializable value if possible, otherwise None
	"""
	with _lock:
		result, _ = _run_request({"read": name}, timeout)
	return result


def reset():
	"""Kill the worker process and clear all session state.

	Returns:
		dict with a 'message' key describing what happened.
	"""
	global _process
	with _lock:
		if _process is not None and _process.poll() is None:
			_process.kill()
			_process.wait()
		_process = None
	return {"message": "REPL reset — all session variables have been cleared"}


def list_vars(timeout=10):
	"""List all user-defined variables in the persistent REPL namespace.

	Args:
		timeout: Seconds before the request times out (default 10).

	Returns:
		dict with keys:
			count  Number of user-defined variables
			vars   Dict mapping name → {type, repr, value}
			       value is JSON-serializable when possible, otherwise None
	"""
	with _lock:
		result, _ = _run_request({"vars": True}, timeout)
	return result


def status():
	"""Return the current state of the worker process.

	Returns:
		dict with keys:
			running  True if the worker process is alive
			pid      Process ID, or None if not running
	"""
	with _lock:
		if _process is None or _process.poll() is not None:
			return {"running": False, "pid": None}
		return {"running": True, "pid": _process.pid}
