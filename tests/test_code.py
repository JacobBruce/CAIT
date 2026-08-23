"""AST find_* caps, import aliases, tuple unpack."""

from cait.code import find_definitions, find_references


def test_find_references_import_from(tmp_path, monkeypatch):
	src = tmp_path / "use.py"
	src.write_text("from cait.fs import file_info\nprint(file_info)\n", encoding="utf-8")
	monkeypatch.setenv("CAIT_WORKSPACE", str(tmp_path))
	out = find_references("file_info", path=str(tmp_path))
	contexts = {r["context"] for r in out["results"]}
	assert "import" in contexts
	assert out["truncated"] is False
	assert out["count"] >= 2


def test_find_definitions_tuple_unpack(tmp_path, monkeypatch):
	src = tmp_path / "unpack.py"
	src.write_text("a, b = 1, 2\n", encoding="utf-8")
	monkeypatch.setenv("CAIT_WORKSPACE", str(tmp_path))
	out = find_definitions("a", path=str(src), kind="variable")
	assert out["count"] == 1
	assert out["results"][0]["kind"] == "variable"
	assert out["results"][0]["line"] == 1


def test_find_references_cap(tmp_path, monkeypatch):
	src = tmp_path / "many.py"
	src.write_text("x = 1\n" + "x\n" * 20, encoding="utf-8")
	monkeypatch.setenv("CAIT_WORKSPACE", str(tmp_path))
	out = find_references("x", path=str(src), max_results=5)
	assert out["count"] == 5
	assert out["truncated"] is True
	assert out["max_results"] == 5


def test_find_max_results_zero_is_error(tmp_path, monkeypatch):
	src = tmp_path / "x.py"
	src.write_text("x = 1\n", encoding="utf-8")
	monkeypatch.setenv("CAIT_WORKSPACE", str(tmp_path))
	out = find_references("x", path=str(src), max_results=0)
	assert "error" in out
	assert "hint" in out


def test_missing_path_is_error(tmp_path):
	out = find_references("x", path=str(tmp_path / "nope"))
	assert "error" in out
	assert "No such path" in out["error"]


def test_non_python_file_is_error(tmp_path):
	p = tmp_path / "notes.md"
	p.write_text("x = 1\n", encoding="utf-8")
	out = find_definitions("x", path=str(p))
	assert "error" in out


def test_invalid_kind_is_error(tmp_path):
	p = tmp_path / "a.py"
	p.write_text("def f():\n\tpass\n", encoding="utf-8")
	out = find_definitions("f", path=str(p), kind="func")
	assert "error" in out
