"""cait.document — Document conversion via Docling or MarkItDown."""

from __future__ import annotations

from cait.text import search_text
from cait.fs import _DEFAULT_FILEDIR

_DOC_CACHE_DIR        = _DEFAULT_FILEDIR / "doc_cache"
_PLAINTEXT_EXTENSIONS = {".txt", ".md", ".rst"}

def convert_doc(
	source: str,
	backend: str = "auto",
	output_format: str = "markdown",
	rich_pdf: bool = False,
	strip_tables: bool = False,
	save_to: str = "",
) -> dict:
	"""Convert a document (file path or URL) to text.

	Args:
		source:        File path or URL to convert.
		backend:       "docling", "markitdown", or "auto" (default — tries
		               docling first, falls back to markitdown on any error).
		output_format: Output format — "markdown" (default), "html", or "text".
		               Only applies to the docling backend; markitdown always
		               returns markdown.
		rich_pdf:      When True, enables Docling's PDF enrichment pipeline:
		               code block detection, formula extraction, and picture
		               description. Produces richer output but is significantly
		               slower. Docling backend only.
		strip_tables:  When True, remove markdown table syntax from the output.
		               Useful when the markitdown backend renders equation-heavy
		               PDFs as unreadable pipe-delimited tables.
		save_to:       If given, write the converted content to this file path
		               and omit 'content' from the return value. The directory
		               is created if it does not exist.

	Returns:
		Without save_to: {source, backend, output_format, content}
		With save_to:    {source, backend, output_format, saved_to, size_bytes}
	"""
	_backend = backend.lower()
	_format  = output_format.lower()

	if _backend not in ("docling", "markitdown", "auto"):
		raise ValueError(f"Unknown backend {backend!r}. Choose 'docling', 'markitdown', or 'auto'.")

	if _format not in ("markdown", "html", "text"):
		raise ValueError(f"Unknown output_format {output_format!r}. Choose 'markdown', 'html', or 'text'.")

	if _backend == "auto":
		try:
			result = _convert_docling(source, _format, rich_pdf)
		except Exception as docling_err:
			try:
				result = _convert_markitdown(source)
				result["fallback_reason"] = str(docling_err)
			except Exception as mid_err:
				raise RuntimeError(
					f"Both backends failed.\n"
					f"  Docling:    {docling_err!r}\n"
					f"  MarkItDown: {mid_err!r}"
				) from mid_err
	elif _backend == "docling":
		result = _convert_docling(source, _format, rich_pdf)
	else:
		# markitdown
		result = _convert_markitdown(source)

	if strip_tables and "content" in result:
		from cait.text import strip_tables as _strip
		result["content"] = _strip(result["content"])

	if save_to:
		from pathlib import Path
		p = Path(save_to)
		p.parent.mkdir(parents=True, exist_ok=True)
		p.write_text(result["content"], encoding="utf-8")
		result["saved_to"]   = str(p.resolve())
		result["size_bytes"] = p.stat().st_size
		del result["content"]

	return result


def search_doc(source, query="", sentences=5, unit="sentence", backend="auto", strip_tables=False):
	"""Search or summarize a document from a file path or URL.

	Single-call pipeline: converts the source document if needed (caching the
	result for repeat calls), then searches or summarizes the resulting text.

	Unlike extract_text / summarize_text (which only accept already-readable text
	or plain text files), search_doc handles PDFs, DOCX, URLs, and other document
	formats by routing them through convert_doc. Repeat calls with the same source
	skip conversion entirely — the cached markdown is reused.

	Args:
		source:       File path or URL to a document, or a plain text file path
		              (.txt, .md, .rst files are read directly without conversion).
		query:        Question or topic to search for. Leave empty for a summary.
		sentences:    Number of chunks to return (default 5).
		unit:         'sentence' (default) or 'paragraph'. Paragraph mode is
		              strongly recommended for academic PDFs and technical reports.
		backend:      Conversion backend — 'auto' (default), 'docling', or 'markitdown'.
		strip_tables: Strip markdown table syntax before searching. Recommended
		              when using markitdown on PDF files with heavy table content.

	Returns the same shape as search_text with added 'source' and 'cache_hit' fields.
	cache_hit=True means no conversion was performed — the cached version was used.
	"""
	try:
		text, cache_hit = _cached_convert(source, backend=backend, strip_tables=strip_tables)
	except Exception as e:
		return {"error": str(e), "source": source}

	result = search_text(text, query=query, sentences=sentences, unit=unit)
	result["source"]    = source
	result["cache_hit"] = cache_hit
	return result


# ── Internal helpers ──────────────────────────────────────────────────────────

def _convert_docling(source: str, output_format: str, rich_pdf: bool) -> dict:
	from docling.document_converter import DocumentConverter, PdfFormatOption, InputFormat
	from docling.datamodel.pipeline_options import PdfPipelineOptions

	if rich_pdf:
		opts = PdfPipelineOptions(
			do_code_enrichment=True,
			do_formula_enrichment=True,
			do_picture_description=True,
		)
		converter = DocumentConverter(
			format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
		)
	else:
		converter = DocumentConverter()

	result = converter.convert(source)
	doc    = result.document

	if output_format == "html":
		content = doc.export_to_html()
	elif output_format == "text":
		content = doc.export_to_text()
	else:
		content       = doc.export_to_markdown()
		output_format = "markdown"

	return {
		"source":        source,
		"backend":       "docling",
		"output_format": output_format,
		"content":       content,
	}


def _convert_markitdown(source: str) -> dict:
	from markitdown import MarkItDown

	mid    = MarkItDown()
	result = mid.convert(source)

	return {
		"source":        source,
		"backend":       "markitdown",
		"output_format": "markdown",
		"content":       result.text_content,
	}


# ── Document cache ────────────────────────────────────────────────────────────

def _cache_key(source: str, backend: str, strip_tables: bool) -> str:
	"""Compute a short hex key that uniquely identifies a specific conversion."""
	import hashlib
	from pathlib import Path as _Path

	h = hashlib.sha256()
	h.update(source.encode())
	# For local files include mtime+size so edits invalidate the cache.
	if "://" not in source:
		p = _Path(source)
		if p.exists():
			st = p.stat()
			h.update(f"{st.st_mtime:.6f}:{st.st_size}".encode())
	h.update(f"|{backend}|{strip_tables}".encode())
	return h.hexdigest()[:20]


def _cached_convert(source: str, backend: str = "auto", strip_tables: bool = False):
	"""Convert a document, returning cached content when available.

	Plain text files (.txt, .md, .rst) are read directly without conversion
	or caching — they don't need it.

	For everything else (PDFs, DOCX, URLs, etc.):
	  - Cache hit:  return stored markdown from _DOC_CACHE_DIR, no network or
	                disk-intensive conversion.
	  - Cache miss: run convert_doc, persist the result, then return it.

	The cache key encodes the source path/URL, backend, strip_tables flag, and
	(for local files) the file's mtime + size so edits always invalidate it.

	Args:
		source:       File path or URL to convert.
		backend:      Conversion backend — 'auto', 'docling', or 'markitdown'.
		strip_tables: Strip markdown table syntax from the output before caching.

	Returns:
		(content: str, cache_hit: bool)

	Raises RuntimeError if conversion fails.
	"""
	from pathlib import Path as _Path

	# Plain text files: read directly, no conversion or caching needed.
	if "://" not in source:
		p = _Path(source)
		if p.exists() and p.suffix.lower() in _PLAINTEXT_EXTENSIONS:
			return p.read_text(encoding="utf-8"), False

	key        = _cache_key(source, backend, strip_tables)
	cache_path = _DOC_CACHE_DIR / f"{key}.md"

	if cache_path.exists():
		return cache_path.read_text(encoding="utf-8"), True

	# Cache miss — convert and persist.
	result = convert_doc(source, backend=backend, strip_tables=strip_tables)
	if "error" in result:
		raise RuntimeError(result["error"])

	content = result["content"]
	_DOC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
	cache_path.write_text(content, encoding="utf-8")
	return content, False
