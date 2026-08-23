"""dir_info walk/exclude/cap; file_write does not count lines."""

from cait.code import _collect_files
from cait.fs import dir_info, file_info, file_write


def _tree(tmp_path):
	"""Clone living under a folder named vendor, with a junk node_modules."""
	demo = tmp_path / "vendor" / "demo"
	(demo / "src").mkdir(parents=True)
	(demo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
	(demo / "readme.txt").write_text("hi\n", encoding="utf-8")
	(demo / "node_modules" / "pkg").mkdir(parents=True)
	(demo / "node_modules" / "pkg" / "x.py").write_text("y = 2\n", encoding="utf-8")
	return demo


def test_exclude_ignores_ancestor_vendor(tmp_path):
	demo = _tree(tmp_path)
	data = dir_info(str(demo), recursive=True)
	names = {e["name"] for e in data["entries"]}
	assert "a.py" in names
	assert "src" in names
	assert "readme.txt" in names
	assert "x.py" not in names
	assert data["truncated"] is False
	assert "lines" not in data["entries"][0]


def test_non_recursive_shows_layout_stubs(tmp_path):
	demo = _tree(tmp_path)
	data = dir_info(str(demo), recursive=False)
	names = {e["name"] for e in data["entries"]}
	assert names == {"node_modules", "readme.txt", "src"}
	assert "a.py" not in names
	assert "x.py" not in names


def test_recursive_lists_excluded_dir_stub(tmp_path):
	demo = _tree(tmp_path)
	data = dir_info(str(demo), recursive=True)
	stubs = [e for e in data["entries"] if e["name"] == "node_modules"]
	assert len(stubs) == 1
	assert stubs[0]["is_dir"] is True


def test_empty_exclude_walks_node_modules(tmp_path):
	demo = _tree(tmp_path)
	data = dir_info(str(demo), recursive=True, exclude=set())
	names = {e["name"] for e in data["entries"]}
	assert "x.py" in names
	assert "node_modules" in names


def test_max_results_truncates(tmp_path):
	d = tmp_path / "many"
	d.mkdir()
	for i in range(8):
		(d / f"f{i}.txt").write_text("x\n", encoding="utf-8")
	data = dir_info(str(d), recursive=False, max_results=3)
	assert data["count"] == 3
	assert data["truncated"] is True
	assert data["max_results"] == 3


def test_max_results_hard_cap(tmp_path):
	d = tmp_path / "one"
	d.mkdir()
	(d / "a.txt").write_text("x\n", encoding="utf-8")
	data = dir_info(str(d), max_results=50_000)
	assert data["max_results"] == 2000
	assert data["truncated"] is False


def test_max_results_rejects_zero(tmp_path):
	d = tmp_path / "one"
	d.mkdir()
	data = dir_info(str(d), max_results=0)
	assert "error" in data
	assert "hint" in data


def test_non_recursive_glob_does_not_descend(tmp_path):
	demo = _tree(tmp_path)
	(demo / "b.py").write_text("z = 3\n", encoding="utf-8")
	data = dir_info(str(demo), pattern="*.py", recursive=False)
	assert {e["name"] for e in data["entries"]} == {"b.py"}


def test_dir_info_and_write_skip_line_counts(tmp_path, monkeypatch):
	d = tmp_path / "d"
	d.mkdir()
	(d / "a.txt").write_text("a\nb\n", encoding="utf-8")

	def boom(*_a, **_k):
		raise AssertionError("_count_lines should not run")

	monkeypatch.setattr("cait.fs._count_lines", boom)
	listing = dir_info(str(d))
	assert listing["count"] == 1
	written = file_write(str(d / "b.txt"), "hello")
	assert "lines" not in written
	assert written["chars_written"] == 6  # hello + newline


def test_file_info_still_counts_lines(tmp_path):
	p = tmp_path / "n.txt"
	p.write_text("a\nb\nc\n", encoding="utf-8")
	info = file_info(str(p))
	assert info["lines"] == 3


def test_file_info_skips_line_count_for_binary(tmp_path):
	pdf = tmp_path / "scan.pdf"
	pdf.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"stream\n" + b"\x00" * 64)
	info = file_info(str(pdf))
	assert info["lines"] is None
	assert info["size_bytes"] > 0

	raw = tmp_path / "blob.dat"
	raw.write_bytes(b"abc\n" + b"\x00" + b"def\n")
	info = file_info(str(raw))
	assert info["lines"] is None


def test_collect_files_under_vendor_skips_node_modules(tmp_path):
	demo = _tree(tmp_path)
	files = [p.name for p in _collect_files(demo, recursive=True)]
	assert files == ["a.py"]
