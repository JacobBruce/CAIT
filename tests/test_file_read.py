"""Streamed file_read: no full slurp; total_lines only at EOF."""

from pathlib import Path

from cait.fs import file_read


def _lines(n):
	return "".join(f"line-{i}\n" for i in range(1, n + 1))


def test_full_read_has_total_lines(tmp_path):
	p = tmp_path / "small.txt"
	p.write_text(_lines(4), encoding="utf-8")
	data = file_read(str(p))
	assert data["total_lines"] == 4
	assert data["truncated"] is False
	assert data["has_more"] is False
	assert data["line_count"] == 4
	assert data["size_bytes"] == p.stat().st_size
	assert "1|" in data["content"]
	assert "4|" in data["content"]


def test_limit_omits_total_lines(tmp_path):
	p = tmp_path / "long.txt"
	p.write_text(_lines(20), encoding="utf-8")
	data = file_read(str(p), offset=1, limit=5)
	assert data["truncated"] is False
	assert data["has_more"] is True
	assert data["line_count"] == 5
	assert data["end_line"] == 5
	assert "total_lines" not in data
	assert "6|" not in data["content"]


def test_limit_to_eof_has_total_lines(tmp_path):
	p = tmp_path / "exact.txt"
	p.write_text(_lines(5), encoding="utf-8")
	data = file_read(str(p), offset=1, limit=5)
	assert data["truncated"] is False
	assert data["has_more"] is False
	assert data["total_lines"] == 5


def test_tail_has_total_lines(tmp_path):
	p = tmp_path / "log.txt"
	p.write_text(_lines(12), encoding="utf-8")
	data = file_read(str(p), limit=-3)
	assert data["total_lines"] == 12
	assert data["line_count"] == 3
	assert data["offset"] == 10
	assert data["end_line"] == 12
	assert data["truncated"] is False
	assert data["has_more"] is False
	assert data["content"].startswith("10|")


def test_does_not_call_read_text(tmp_path, monkeypatch):
	p = tmp_path / "x.txt"
	p.write_text(_lines(8), encoding="utf-8")

	def boom(*_a, **_k):
		raise AssertionError("Path.read_text should not be used")

	monkeypatch.setattr(Path, "read_text", boom)
	data = file_read(str(p), offset=2, limit=2)
	assert "2|" in data["content"]
	assert "3|" in data["content"]
	assert "4|" not in data["content"]
	assert data["truncated"] is False
	assert data["has_more"] is True
	assert "total_lines" not in data


def test_missing_file_returns_error_dict(tmp_path):
	data = file_read(str(tmp_path / "nope.txt"))
	assert "error" in data
	assert "hint" in data
	assert data["error"].startswith("No such file")


def test_limit_zero_returns_error_dict(tmp_path):
	p = tmp_path / "x.txt"
	p.write_text("a\n", encoding="utf-8")
	data = file_read(str(p), limit=0)
	assert "error" in data
	assert "hint" in data

