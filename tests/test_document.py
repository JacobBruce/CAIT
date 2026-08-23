"""backend='auto' uses Docling with OCR; MarkItDown is error fallback only."""

from cait.document import convert_doc, search_doc, _is_thin, _THIN_HINT


def test_is_thin():
	assert _is_thin("") is True
	assert _is_thin("   ") is True
	assert _is_thin("x" * 399) is True
	assert _is_thin("x" * 400) is False


def test_auto_uses_docling_with_ocr(monkeypatch):
	def fake_docling(*_a, **k):
		assert k.get("ocr") is True
		return {"source": "x.pdf", "backend": "docling", "output_format": "markdown",
		        "content": "A" * 500}

	def boom(*_a, **_k):
		raise AssertionError("markitdown should not run")

	monkeypatch.setattr("cait.document._convert_docling", fake_docling)
	monkeypatch.setattr("cait.document._convert_markitdown", boom)
	out = convert_doc("paper.pdf", backend="auto")
	assert out["backend"] == "docling"
	assert "warning" not in out


def test_auto_falls_back_to_markitdown_on_docling_error(monkeypatch):
	monkeypatch.setattr(
		"cait.document._convert_docling",
		lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("docling down")),
	)
	monkeypatch.setattr(
		"cait.document._convert_markitdown",
		lambda *_a, **_k: {"source": "x.pdf", "backend": "markitdown", "output_format": "markdown",
		                   "content": "ok"},
	)
	out = convert_doc("scan.pdf", backend="auto")
	assert out["backend"] == "markitdown"
	assert "docling down" in out["fallback_reason"]


def test_explicit_docling_requests_ocr(monkeypatch):
	seen = {}

	def fake_docling(*_a, **k):
		seen["ocr"] = k.get("ocr", True)
		return {"source": "x.pdf", "backend": "docling", "output_format": "markdown",
		        "content": "ok"}

	monkeypatch.setattr("cait.document._convert_docling", fake_docling)
	convert_doc("scan.pdf", backend="docling")
	assert seen["ocr"] is True


def test_search_doc_warns_on_thin_text(tmp_path):
	p = tmp_path / "notes.md"
	p.write_text("short", encoding="utf-8")
	out = search_doc(str(p), query="short", sentences=1)
	assert out["warning"] == _THIN_HINT
