"""Streamed file_search: in-file grep, total_lines only at EOF."""

from cait.fs import file_search


def _lines(n):
	return "".join(f"line-{i}\n" for i in range(1, n + 1))


def test_search_max_matches_omits_total_lines(tmp_path):
	p = tmp_path / "hits.txt"
	p.write_text("".join(f"hit {i}\n" for i in range(30)), encoding="utf-8")
	data = file_search(str(p), r"hit", max_matches=3)
	assert data["match_count"] == 3
	assert data["truncated"] is True
	assert "total_lines" not in data
	assert data["content"] == ""


def test_search_to_eof_has_total_lines(tmp_path):
	p = tmp_path / "few.txt"
	p.write_text("a\nhit\nb\nhit\nc\n", encoding="utf-8")
	data = file_search(str(p), r"hit", max_matches=10)
	assert data["match_count"] == 2
	assert data["truncated"] is False
	assert data["total_lines"] == 5
	assert data["matches"][0]["text"] == "hit"
	assert data["content"] == ""


def test_search_tail_has_total_lines(tmp_path):
	p = tmp_path / "tail.txt"
	p.write_text(_lines(10), encoding="utf-8")
	data = file_search(str(p), r"line-1", limit=-3)
	assert data["total_lines"] == 10
	assert data["match_count"] == 1
	assert data["matches"][0]["line"] == 10


def test_search_context_bodies(tmp_path):
	p = tmp_path / "ctx.txt"
	p.write_text("a\nhit\nb\n", encoding="utf-8")
	data = file_search(str(p), r"hit", context=1)
	assert data["match_count"] == 1
	assert "1|a" in data["content"]
	assert "2|hit" in data["content"]
	assert "3|b" in data["content"]


def test_search_inline_ignore_case(tmp_path):
	p = tmp_path / "case.txt"
	p.write_text("Hello\nHELLO\nhello\n", encoding="utf-8")
	plain = file_search(str(p), r"hello")
	assert plain["match_count"] == 1
	flagged = file_search(str(p), r"(?i)hello")
	assert flagged["match_count"] == 3
