"""Literal strings must not be treated as existing filenames."""

from cait.text import _looks_like_path, _read_source, diff_text


def test_bare_token_is_not_a_path(tmp_path, monkeypatch):
	(tmp_path / "a").write_text("FILE-A", encoding="utf-8")
	(tmp_path / "b").write_text("FILE-B", encoding="utf-8")
	monkeypatch.setenv("CAIT_WORKSPACE", str(tmp_path))
	assert _looks_like_path("a") is False
	assert _read_source("a") == "a"
	out = diff_text("a", "b")
	assert out["changed"] is True
	assert "FILE-A" not in out["diff"]


def test_suffixed_name_is_a_path(tmp_path, monkeypatch):
	p = tmp_path / "note.md"
	p.write_text("hello from file", encoding="utf-8")
	monkeypatch.setenv("CAIT_WORKSPACE", str(tmp_path))
	assert _looks_like_path("note.md") is True
	assert _read_source(str(p)) == "hello from file"


def test_encode_text_save_to_omits_inline_vectors(monkeypatch, tmp_path):
	import numpy as np
	from cait.text import encode_text

	monkeypatch.setattr(
		"cait.text._embed",
		lambda texts: (np.zeros((len(texts), 384), dtype=float), None),
	)
	out = encode_text(["hello"])
	assert len(out["embeddings"][0]) == 384
	assert out["dimensions"] == 384

	dest = tmp_path / "vecs.json"
	saved = encode_text(["hello"], save_to=str(dest))
	assert "embeddings" not in saved
	assert dest.is_file()
