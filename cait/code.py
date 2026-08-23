"""
cait.code — AST-aware code search tools for Python source files.

All search functions accept an optional `path` (file or directory).
If omitted they search the workspace (CAIT_WORKSPACE, else cwd) recursively.
Results are sorted by file path then line number.
"""

import ast
from pathlib import Path

from cait.fs import _DEFAULT_EXCLUDE, _iter_tree, resolve_path, workspace_root
from cait.errors import tool_error


# ── Internal helpers ──────────────────────────────────────────────────────────

def _collect_files(path, recursive=True, exclude=_DEFAULT_EXCLUDE):
	"""Yield .py file paths under *path*, skipping excluded directory names."""
	p = resolve_path(path)
	if p.is_file():
		if p.suffix == ".py":
			yield p
		return
	exclude = set(exclude) if exclude is not None else set()
	for child in _iter_tree(p, recursive=recursive, exclude=exclude, files_only=True):
		if child.suffix == ".py":
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


_DEFAULT_MAX_FIND = 200
_HARD_MAX_FIND = 2000


def _parse_max_find(max_results):
	if max_results is None:
		return _DEFAULT_MAX_FIND, None
	try:
		n = int(max_results)
	except (TypeError, ValueError):
		return None, tool_error(
			"max_results must be an integer",
			hint="Pass a positive integer (default 200, hard max 2000).",
		)
	if n < 1:
		return None, tool_error(
			"max_results must be >= 1",
			hint="Use 1–2000, or omit for the default of 200.",
		)
	return min(n, _HARD_MAX_FIND), None


def _assign_name_nodes(target):
	"""Yield Name nodes in an assignment target, including tuple/list unpack.

	Skips attributes (self.x), subscripts, and other non-name targets.
	"""
	if isinstance(target, ast.Name):
		yield target
	elif isinstance(target, (ast.Tuple, ast.List)):
		for elt in target.elts:
			yield from _assign_name_nodes(elt)
	elif isinstance(target, ast.Starred):
		yield from _assign_name_nodes(target.value)


def _resolve_search_path(path):
	"""Return (path, None) or (None, error_dict) for AST search roots."""
	search_path = resolve_path(path) if path else workspace_root()
	if not search_path.exists():
		return None, tool_error(
			f"No such path: {search_path}",
			hint="Pass an existing .py file or directory, or omit path to search CAIT_WORKSPACE.",
			path=str(search_path),
		)
	if search_path.is_file() and search_path.suffix != ".py":
		return None, tool_error(
			f"Not a Python file: {search_path}",
			hint="AST search only reads .py files. Use search_file for other languages.",
			path=str(search_path),
		)
	return search_path, None


def _pack_find(results, truncated, cap):
	results.sort(key=lambda r: (r["file"], r["line"]))
	return {
		"results":     results,
		"count":       len(results),
		"truncated":   truncated,
		"max_results": cap,
	}


# ── Public search functions ───────────────────────────────────────────────────

def find_definitions(name, path=None, kind=None, recursive=True, exclude=_DEFAULT_EXCLUDE, max_results=None):
	"""Find all definitions of *name* in Python source files.

	Args:
		name:        Symbol name to look for (function, class, or variable).
		path:        File or directory to search. Defaults to workspace (CAIT_WORKSPACE, else cwd).
		kind:        Restrict to "function", "class", or "variable". None = all.
		recursive:   Descend into subdirectories (default True).
		exclude:     Set of directory names to skip entirely.
		max_results: Cap on returned hits (default 200, hard max 2000).

	Returns:
		dict with results, count, truncated, max_results.
		Each result has keys: file, line, col, code, kind.
		Functions and classes also include a `docstring` key (may be None).
		Classes also include `bases` (list of base class expressions).
		Annotated variables include an `annotation` key.
	"""
	results = []
	cap, err = _parse_max_find(max_results)
	if err:
		return err
	if kind not in (None, "function", "class", "variable"):
		return tool_error(
			f"kind must be 'function', 'class', or 'variable', got {kind!r}",
			hint="Leave kind empty to search all definition kinds.",
		)
	search_path, err = _resolve_search_path(path)
	if err:
		return err

	for filepath in _collect_files(search_path, recursive=recursive, exclude=exclude):
		tree, lines = _parse(filepath)
		if tree is None:
			continue

		for node in ast.walk(tree):
			hit = None
			if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
				if node.name == name and kind in (None, "function"):
					hit = _loc(filepath, node, lines,
						kind="function",
						async_=isinstance(node, ast.AsyncFunctionDef),
						docstring=ast.get_docstring(node),
					)

			elif isinstance(node, ast.ClassDef):
				if node.name == name and kind in (None, "class"):
					hit = _loc(filepath, node, lines,
						kind="class",
						bases=[ast.unparse(b) for b in node.bases],
						docstring=ast.get_docstring(node),
					)

			elif isinstance(node, ast.Assign) and kind in (None, "variable"):
				for target in node.targets:
					for name_node in _assign_name_nodes(target):
						if name_node.id == name:
							if len(results) >= cap:
								return _pack_find(results, True, cap)
							results.append(_loc(filepath, name_node, lines, kind="variable"))
				continue

			elif isinstance(node, ast.AnnAssign) and kind in (None, "variable"):
				if isinstance(node.target, ast.Name) and node.target.id == name:
					hit = _loc(filepath, node.target, lines,
						kind="variable",
						annotation=ast.unparse(node.annotation),
					)

			if hit is None:
				continue
			if len(results) >= cap:
				return _pack_find(results, True, cap)
			results.append(hit)

	return _pack_find(results, False, cap)


def find_calls(name, path=None, recursive=True, exclude=_DEFAULT_EXCLUDE, max_results=None):
	"""Find all call sites of a function named *name*.

	Catches bare calls (`name(...)`), method calls (`obj.name(...)`), and
	chained attribute calls. Does not match occurrences inside comments or strings.

	Args:
		name:        Function name to search for.
		path:        File or directory to search. Defaults to workspace (CAIT_WORKSPACE, else cwd).
		recursive:   Descend into subdirectories (default True).
		exclude:     Set of directory names to skip entirely.
		max_results: Cap on returned hits (default 200, hard max 2000).

	Returns:
		dict with results, count, truncated, max_results.
		Each result has keys: file, line, col, code, style.
		`style` is "bare" for `name(...)` or "attribute" for `obj.name(...)`.
		Attribute calls also include an `on` key (the receiver expression).
	"""
	results = []
	cap, err = _parse_max_find(max_results)
	if err:
		return err
	search_path, err = _resolve_search_path(path)
	if err:
		return err

	for filepath in _collect_files(search_path, recursive=recursive, exclude=exclude):
		tree, lines = _parse(filepath)
		if tree is None:
			continue

		for node in ast.walk(tree):
			if not isinstance(node, ast.Call):
				continue
			func = node.func
			hit = None
			if isinstance(func, ast.Name) and func.id == name:
				hit = _loc(filepath, func, lines, style="bare")
			elif isinstance(func, ast.Attribute) and func.attr == name:
				hit = _loc(filepath, func, lines,
					style="attribute",
					on=ast.unparse(func.value),
				)
			if hit is None:
				continue
			if len(results) >= cap:
				return _pack_find(results, True, cap)
			results.append(hit)

	return _pack_find(results, False, cap)


def find_imports(module, path=None, recursive=True, exclude=_DEFAULT_EXCLUDE, max_results=None):
	"""Find all files that import *module* or names from it.

	Matches `import module`, `import module.sub`, `from module import ...`,
	and `from package import module`.

	Args:
		module:      Module name to search for (e.g. "os", "os.path", "pandas").
		path:        File or directory to search. Defaults to workspace (CAIT_WORKSPACE, else cwd).
		recursive:   Descend into subdirectories (default True).
		exclude:     Set of directory names to skip entirely.
		max_results: Cap on returned hits (default 200, hard max 2000).

	Returns:
		dict with results, count, truncated, max_results.
		Each result has keys: file, line, col, code, style, module.
		`style` is "import" for `import ...` or "from" for `from ... import ...`.
		"import" results include an `alias` key (the `as` name, or None).
		"from" results include a `names` list and a `level` (relative import depth).
	"""
	results = []
	cap, err = _parse_max_find(max_results)
	if err:
		return err
	search_path, err = _resolve_search_path(path)
	if err:
		return err

	for filepath in _collect_files(search_path, recursive=recursive, exclude=exclude):
		tree, lines = _parse(filepath)
		if tree is None:
			continue

		for node in ast.walk(tree):
			hit = None
			if isinstance(node, ast.Import):
				for alias in node.names:
					if alias.name == module or alias.name.startswith(module + "."):
						hit = _loc(filepath, node, lines,
							style="import",
							module=alias.name,
							alias=alias.asname,
						)
						break

			elif isinstance(node, ast.ImportFrom):
				mod = node.module or ""
				if mod == module or mod.startswith(module + "."):
					hit = _loc(filepath, node, lines,
						style="from",
						module=mod,
						names=[a.name for a in node.names],
						level=node.level,
					)
				elif any(a.name == module for a in node.names):
					hit = _loc(filepath, node, lines,
						style="from",
						module=mod,
						names=[a.name for a in node.names],
						level=node.level,
					)

			if hit is None:
				continue
			if len(results) >= cap:
				return _pack_find(results, True, cap)
			results.append(hit)

	return _pack_find(results, False, cap)


def find_references(name, path=None, recursive=True, exclude=_DEFAULT_EXCLUDE, max_results=None):
	"""Find all uses of *name* as an identifier anywhere in the source.

	Includes loads, stores, deletes, attribute accesses, and import aliases.
	This is broader than find_calls — use it to track all usages of a variable
	or symbol. Note: common names (e.g. 'i', 'x') may produce many results.

	Args:
		name:        Identifier name to search for.
		path:        File or directory to search. Defaults to workspace (CAIT_WORKSPACE, else cwd).
		recursive:   Descend into subdirectories (default True).
		exclude:     Set of directory names to skip entirely.
		max_results: Cap on returned hits (default 200, hard max 2000).

	Returns:
		dict with results, count, truncated, max_results.
		Each result has keys: file, line, col, code, context.
		`context` is "load", "store", "del", "attribute.load", "import", etc.
		Attribute references also include an `on` key (the object expression).
	"""
	results = []
	cap, err = _parse_max_find(max_results)
	if err:
		return err
	search_path, err = _resolve_search_path(path)
	if err:
		return err

	for filepath in _collect_files(search_path, recursive=recursive, exclude=exclude):
		tree, lines = _parse(filepath)
		if tree is None:
			continue

		for node in ast.walk(tree):
			hit = None
			if isinstance(node, ast.Name) and node.id == name:
				ctx = type(node.ctx).__name__.lower()
				hit = _loc(filepath, node, lines, context=ctx)
			elif isinstance(node, ast.Attribute) and node.attr == name:
				ctx = type(node.ctx).__name__.lower()
				hit = _loc(filepath, node, lines,
					context=f"attribute.{ctx}",
					on=ast.unparse(node.value),
				)
			elif isinstance(node, ast.Import):
				for alias in node.names:
					bound = alias.asname or alias.name.split(".")[-1]
					if bound == name or alias.name == name:
						hit = _loc(filepath, node, lines, context="import")
						break
			elif isinstance(node, ast.ImportFrom):
				for alias in node.names:
					if alias.name == "*":
						continue
					bound = alias.asname or alias.name
					if alias.name == name or bound == name:
						hit = _loc(filepath, node, lines, context="import")
						break

			if hit is None:
				continue
			if len(results) >= cap:
				return _pack_find(results, True, cap)
			results.append(hit)

	return _pack_find(results, False, cap)
