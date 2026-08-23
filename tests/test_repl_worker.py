"""REPL worker namespace must exist (used by execute/read_var)."""

from cait import _repl_worker


def test_namespace_is_defined():
	assert _repl_worker.namespace["__name__"] == "__repl__"
