"""Download filename sanitization; no network."""

from cait import fs as fsmod


def test_download_strips_parent_segments(tmp_path, monkeypatch):
	def fake_http(*_a, **_k):
		return {"status": 200, "content_type": "text/plain", "raw": b"ok", "truncated": False}

	monkeypatch.setattr(fsmod, "_http_read", fake_http)
	out = fsmod.file_download("http://example.com/a", filename="../evil.txt", dirpath=str(tmp_path))
	assert "error" not in out
	assert out["filename"] == "evil.txt"
	assert out["path"] == str((tmp_path / "evil.txt").resolve())
	assert (tmp_path / "evil.txt").read_bytes() == b"ok"
