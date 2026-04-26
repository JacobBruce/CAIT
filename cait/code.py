"""
cait.code — AST-aware code search tools for Python source files.

All search functions accept an optional `path` (file or directory).
If omitted they search the current working directory recursively.
Results are sorted by file path then line number.
"""

import ast
from pathlib import Path

from cait.fs import _DEFAULT_EXCLUDE


# ── Internal helpers ──────────────────────────────────────────────────────────

def _collect_files(path, recursive=True, exclude=_DEFAULT_EXCLUDE):
	"""Yield .py file paths under *path*, skipping excluded directory names."""
	p = Path(path)
	if p.is_file():
		if p.suffix == ".py":
			yield p
		return
	pattern = "**/*.py" if recursive else "*.py"
	for child in p.glob(pattern):
		if not any(part in exclude for part in child.parts):
			yield child


def _parse(path):
	"""Return (tree, lines) for a Python file, or (None, None) on failure."""
	try:
		source = Path(path).read_text(encoding="utf-8")
		return ast.parse(source, filename=str(path)), source.splitlines()
	except (SyntaxError, UnicodeDecodeError, OSError):
		return None, None


def _source_line(lines, lineno):
	"""Return the source line at *lineno* (1-indexed), stripped of trailing whitespace."""
	if 1 <= lineno <= len(lines):
		return lines[lineno - 1].rstrip()
	return ""


def _loc(filepath, node, lines, **extra):
	"""Build a standard location dict from an AST node."""
	return {
		"file": str(filepath),
		"line": node.lineno,
		"col":  node.col_offset,
		"code": _source_line(lines, node.lineno),
		**extra,
	}


# ── Public search functions ───────────────────────────────────────────────────

def find_definitions(name, path=None, kind=None, recursive=True, exclude=_DEFAULT_EXCLUDE):
	"""Find all definitions of *name* in Python source files.

	Args:
		name:      Symbol name to look for (function, class, or variable).
		path:      File or directory to search. Defaults to cwd.
		kind:      Restrict to "function", "class", or "variable". None = all.
		recursive: Descend into subdirectories (default True).
		exclude:   Set of directory names to skip entirely.

	Returns:
		List of dicts with keys: file, line, col, code, kind.
		Functions and classes also include a `docstring` key (may be None).
		Classes also include `bases` (list of base class expressions).
		Annotated variables include an `annotation` key.
	"""
	results = []
	search_path = Path(path) if path else Path.cwd()

	for filepath in _collect_files(search_path, recursive=recursive, exclude=exclude):
		tree, lines = _parse(filepath)
		if tree is None:
			continue

		for node in ast.walk(tree):
			if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
				if node.name == name and kind in (None, "function"):
					results.append(_loc(filepath, node, lines,
						kind="function",
						async_=isinstance(node, ast.AsyncFunctionDef),
						docstring=ast.get_docstring(node),
					))

			elif isinstance(node, ast.ClassDef):
				if node.name == name and kind in (None, "class"):
					results.append(_loc(filepath, node, lines,
						kind="class",
						bases=[ast.unparse(b) for b in node.bases],
						docstring=ast.get_docstring(node),
					))

			elif isinstance(node, ast.Assign) and kind in (None, "variable"):
				for target in node.targets:
					if isinstance(target, ast.Name) and target.id == name:
						results.append(_loc(filepath, target, lines, kind="variable"))

			elif isinstance(node, ast.AnnAssign) and kind in (None, "variable"):
				if isinstance(node.target, ast.Name) and node.target.id == name:
					results.append(_loc(filepath, node.target, lines,
						kind="variable",
						annotation=ast.unparse(node.annotation),
					))

	results.sort(key=lambda r: (r["file"], r["line"]))
	return results


def find_calls(name, path=None, recursive=True, exclude=_DEFAULT_EXCLUDE):
	"""Find all call sites of a function named *name*.

	Catches bare calls (`name(...)`), method calls (`obj.name(...)`), and
	chained attribute calls. Does not match occurrences inside comments or strings.

	Args:
		name:      Function name to search for.
		path:      File or directory to search. Defaults to cwd.
		recursive: Descend into subdirectories (default True).
		exclude:   Set of directory names to skip entirely.

	Returns:
		List of dicts with keys: file, line, col, code, style.
		`style` is "bare" for `name(...)` or "attribute" for `obj.name(...)`.
		Attribute calls also include an `on` key (the receiver expression).
	"""
	results = []
	search_path = Path(path) if path else Path.cwd()

	for filepath in _collect_files(search_path, recursive=recursive, exclude=exclude):
		tree, lines = _parse(filepath)
		if tree is None:
			continue

		for node in ast.walk(tree):
			if not isinstance(node, ast.Call):
				continue
			func = node.func
			if isinstance(func, ast.Name) and func.id == name:
				results.append(_loc(filepath, func, lines, style="bare"))
			elif isinstance(func, ast.Attribute) and func.attr == name:
				results.append(_loc(filepath, func, lines,
					style="attribute",
					on=ast.unparse(func.value),
				))

	results.sort(key=lambda r: (r["file"], r["line"]))
	return results


def find_imports(module, path=None, recursive=True, exclude=_DEFAULT_EXCLUDE):
	"""Find all files that import *module* or names from it.

	Matches `import module`, `import module.sub`, `from module import ...`,
	and `from package import module`.

	Args:
		module:    Module name to search for (e.g. "os", "os.path", "pandas").
		path:      File or directory to search. Defaults to cwd.
		recursive: Descend into subdirectories (default True).
		exclude:   Set of directory names to skip entirely.

	Returns:
		List of dicts with keys: file, line, col, code, style, module.
		`style` is "import" for `import ...` or "from" for `from ... import ...`.
		"import" results include an `alias` key (the `as` name, or None).
		"from" results include a `names` list and a `level` (relative import depth).
	"""
	results = []
	search_path = Path(path) if path else Path.cwd()

	for filepath in _collect_files(search_path, recursive=recursive, exclude=exclude):
		tree, lines = _parse(filepath)
		if tree is None:
			continue

		for node in ast.walk(tree):
			if isinstance(node, ast.Import):
				for alias in node.names:
					if alias.name == module or alias.name.startswith(module + "."):
						results.append(_loc(filepath, node, lines,
							style="import",
							module=alias.name,
							alias=alias.asname,
						))

			elif isinstance(node, ast.ImportFrom):
				mod = node.module or ""
				if mod == module or mod.startswith(module + "."):
					# from module import x, y
					results.append(_loc(filepath, node, lines,
						style="from",
						module=mod,
						names=[a.name for a in node.names],
						level=node.level,
					))
				elif any(a.name == module for a in node.names):
					# from package import module
					results.append(_loc(filepath, node, lines,
						style="from",
						module=mod,
						names=[a.name for a in node.names],
						level=node.level,
					))

	results.sort(key=lambda r: (r["file"], r["line"]))
	return results


def find_references(name, path=None, recursive=True, exclude=_DEFAULT_EXCLUDE):
	"""Find all uses of *name* as an identifier anywhere in the source.

	Includes loads, stores, deletes, and attribute accesses. This is broader
	than find_calls — use it to track all usages of a variable or symbol.
	Note: common names (e.g. 'i', 'x') may produce many results.

	Args:
		name:      Identifier name to search for.
		path:      File or directory to search. Defaults to cwd.
		recursive: Descend into subdirectories (default True).
		exclude:   Set of directory names to skip entirely.

	Returns:
		List of dicts with keys: file, line, col, code, context.
		`context` is "load", "store", "del", "attribute.load", etc.
		Attribute references also include an `on` key (the object expression).
	"""
	results = []
	search_path = Path(path) if path else Path.cwd()

	for filepath in _collect_files(search_path, recursive=recursive, exclude=exclude):
		tree, lines = _parse(filepath)
		if tree is None:
			continue

		for node in ast.walk(tree):
			if isinstance(node, ast.Name) and node.id == name:
				ctx = type(node.ctx).__name__.lower()
				results.append(_loc(filepath, node, lines, context=ctx))
			elif isinstance(node, ast.Attribute) and node.attr == name:
				ctx = type(node.ctx).__name__.lower()
				results.append(_loc(filepath, node, lines,
					context=f"attribute.{ctx}",
					on=ast.unparse(node.value),
				))

	results.sort(key=lambda r: (r["file"], r["line"]))
	return results
