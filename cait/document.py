"""cait.document — Document conversion via Docling or MarkItDown."""

from __future__ import annotations

import threading
import time

from cait.text import search_text
from cait.fs import _DEFAULT_FILEDIR, resolve_path
from cait.errors import tool_error

_DOC_CACHE_DIR        = _DEFAULT_FILEDIR / "doc_cache"
_PLAINTEXT_EXTENSIONS = {".txt", ".md", ".rst"}
_URL_CACHE_TTL_SECONDS = 24 * 60 * 60
_THIN_CONTENT_CHARS    = 400
_THIN_HINT = (
	"Little extractable text after conversion. The source may be an image-only "
	"scan, a damaged file, or a format the backend cannot read."
)
_CONVERT_LOCK: threading.Lock = threading.Lock()
_DOCLING_CONVERTERS: dict[tuple[bool, bool], object] = {}


def _read_plaintext_source(source: str) -> dict | None:
	"""Read a local UTF-8 text file directly, skipping MarkItDown/Docling."""
	if "://" in source:
		return None
	p = resolve_path(source)
	if not p.is_file():
		return None
	if p.suffix.lower() not in _PLAINTEXT_EXTENSIONS:
		return None
	return {
		"source":        str(p.resolve()),
		"backend":       "native",
		"output_format": "markdown" if p.suffix.lower() == ".md" else "text",
		"content":       p.read_text(encoding="utf-8"),
	}


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
		               Docling first, falls back to MarkItDown on failure).
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
		return tool_error(
			f"Unknown backend {backend!r}. Choose 'docling', 'markitdown', or 'auto'.",
			hint="Leave backend as 'auto' unless you need a specific converter.",
			source=source,
		)

	if _format not in ("markdown", "html", "text"):
		return tool_error(
			f"Unknown output_format {output_format!r}. Choose 'markdown', 'html', or 'text'.",
			hint="output_format only applies to the docling backend.",
			source=source,
		)

	if source and "://" not in source:
		source = str(resolve_path(source))

	try:
		plain = _read_plaintext_source(source)
		if plain is not None:
			result = plain
		elif _backend == "auto":
			result = _auto_convert(source, _format, rich_pdf)
			if "error" in result:
				return result
		elif _backend == "docling":
			result = _convert_docling(source, _format, rich_pdf)
		else:
			result = _convert_markitdown(source)

		if strip_tables and "content" in result:
			from cait.text import strip_tables as _strip
			result["content"] = _strip(result["content"])

		if save_to:
			p = resolve_path(save_to)
			p.parent.mkdir(parents=True, exist_ok=True)
			p.write_text(result["content"], encoding="utf-8")
			result["saved_to"]   = str(p)
			result["size_bytes"] = p.stat().st_size
			del result["content"]

		return result
	except Exception as e:
		return tool_error(
			str(e),
			hint="Check the path/URL and that docling or markitdown is installed.",
			source=source,
		)


def search_doc(source, query="", sentences=5, unit="sentence", backend="auto", strip_tables=False, use_cache=True):
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
		use_cache:    If True (default), reuse a cached conversion when available.
		              If False, reconvert and overwrite the cache (live HTML, edited PDFs).

	Returns the same shape as search_text with added 'source' and 'cache_hit' fields.
	cache_hit=True means no conversion was performed — the cached version was used.
	"""
	try:
		text, cache_hit = _cached_convert(
			source, backend=backend, strip_tables=strip_tables, use_cache=use_cache,
		)
	except Exception as e:
		return tool_error(
			str(e),
			hint="Check the path/URL. Pass use_cache=False to force a fresh conversion.",
			source=source,
		)

	result = search_text(text, query=query, sentences=sentences, unit=unit)
	result["source"]    = source
	result["cache_hit"] = cache_hit
	if _is_thin(text):
		result["warning"] = _THIN_HINT
	return result


# ── Internal helpers ──────────────────────────────────────────────────────────

def _is_thin(content: str | None, min_chars: int = _THIN_CONTENT_CHARS) -> bool:
	return not content or len(content.strip()) < min_chars


def _auto_convert(source: str, output_format: str, rich_pdf: bool) -> dict:
	"""Docling first (OCR on), MarkItDown only if Docling raises."""
	try:
		return _convert_docling(source, output_format, rich_pdf, ocr=True)
	except Exception as docling_err:
		try:
			result = _convert_markitdown(source)
			result["fallback_reason"] = str(docling_err)
			return result
		except Exception as mid_err:
			return tool_error(
				f"Both backends failed.\n  Docling:    {docling_err!r}\n  MarkItDown: {mid_err!r}",
				hint="Install docling and/or markitdown. For a local file, check the path exists.",
				source=source,
			)


def _docling_converter(ocr: bool, rich_pdf: bool):
	"""Reuse DocumentConverter instances — constructing one reloads layout weights."""
	key = (bool(ocr), bool(rich_pdf))
	cached = _DOCLING_CONVERTERS.get(key)
	if cached is not None:
		return cached

	from docling.document_converter import DocumentConverter, PdfFormatOption, InputFormat
	from docling.datamodel.pipeline_options import PdfPipelineOptions

	opts = PdfPipelineOptions(
		do_ocr=ocr,
		do_code_enrichment=rich_pdf,
		do_formula_enrichment=rich_pdf,
		do_picture_description=rich_pdf,
	)
	converter = DocumentConverter(
		format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
	)
	_DOCLING_CONVERTERS[key] = converter
	return converter


def _convert_docling(source: str, output_format: str, rich_pdf: bool, ocr: bool = True) -> dict:
	# One conversion at a time: Docling/torch are not safe to re-enter, and two
	# cold starts in parallel are what dropped the MCP connection during testing.
	with _CONVERT_LOCK:
		converter = _docling_converter(ocr, rich_pdf)
		result = converter.convert(source)
	doc = result.document

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
	plain = _read_plaintext_source(source)
	if plain is not None:
		return plain

	from markitdown import MarkItDown

	try:
		result = MarkItDown().convert(source)
	except UnicodeDecodeError:
		# MarkItDown's plaintext handler may decode as ASCII; fall back for UTF-8 files.
		if "://" not in source:
			p = resolve_path(source)
			if p.is_file():
				return {
					"source":        str(p),
					"backend":       "native",
					"output_format": "text",
					"content":       p.read_text(encoding="utf-8"),
				}
		raise

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

	h = hashlib.sha256()
	h.update(source.encode())
	# For local files include mtime+size so edits invalidate the cache.
	if "://" not in source:
		p = resolve_path(source)
		if p.exists():
			st = p.stat()
			h.update(f"{st.st_mtime:.6f}:{st.st_size}".encode())
	h.update(f"|{backend}|{strip_tables}".encode())
	return h.hexdigest()[:20]


def _cached_convert(source: str, backend: str = "auto", strip_tables: bool = False, use_cache: bool = True):
	"""Convert a document, returning cached content when available.

	Plain text files (.txt, .md, .rst) are read directly without conversion
	or caching — they don't need it.

	For everything else (PDFs, DOCX, URLs, etc.):
	  - Cache hit:  return stored markdown from _DOC_CACHE_DIR, no network or
	                disk-intensive conversion.
	  - Cache miss: run convert_doc, persist the result, then return it.

	The cache key encodes the source path/URL, backend, strip_tables flag, and
	(for local files) the file's mtime + size so edits always invalidate it.
	URL entries expire after 24 hours so live HTML is not reused forever.
	Pass use_cache=False to skip the cache, reconvert, and overwrite the entry.

	Args:
		source:       File path or URL to convert.
		backend:      Conversion backend — 'auto', 'docling', or 'markitdown'.
		strip_tables: Strip markdown table syntax from the output before caching.
		use_cache:    If False, ignore any existing cache entry.

	Returns:
		(content: str, cache_hit: bool)

	Raises RuntimeError if conversion fails.
	"""
	if source and "://" not in source:
		source = str(resolve_path(source))

	# Plain text files: read directly, no conversion or caching needed.
	plain = _read_plaintext_source(source)
	if plain is not None:
		return plain["content"], False

	key        = _cache_key(source, backend, strip_tables)
	cache_path = _DOC_CACHE_DIR / f"{key}.md"

	if use_cache and cache_path.exists():
		if "://" in source:
			age = time.time() - cache_path.stat().st_mtime
			if age > _URL_CACHE_TTL_SECONDS:
				try:
					cache_path.unlink()
				except OSError:
					pass
			else:
				return cache_path.read_text(encoding="utf-8"), True
		else:
			return cache_path.read_text(encoding="utf-8"), True

	# Cache miss or use_cache=False — convert and persist.
	result = convert_doc(source, backend=backend, strip_tables=strip_tables)
	if "error" in result:
		raise RuntimeError(result["error"])

	content = result["content"]
	_DOC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
	cache_path.write_text(content, encoding="utf-8")
	return content, False
