"""
cait.text — Text diff, embedding, similarity, and extractive summarization.

Uses the all-MiniLM-L6-v2 ONNX model already bundled with ChromaDB,
so no extra downloads or dependencies are required beyond chromadb itself.
"""

import difflib
import hashlib
import json
import re
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

from cait.fs import resolve_path
from cait.errors import tool_error

import numpy as np

# ── Chunk embedding cache ─────────────────────────────────────────────────────
# Maps (text_hash, unit) → (chunks, chunk_vecs). Bounded at _CHUNK_CACHE_SIZE
# entries with FIFO eviction. Keying on a short hash avoids storing large
# strings while still giving near-zero collision probability for this cache size.

_CHUNK_CACHE_SIZE = 8
_chunk_cache: OrderedDict = OrderedDict()


def _cache_key(text: str, unit: str) -> tuple:
	h = hashlib.sha256(text.encode()).hexdigest()[:16]
	return (h, unit)


def _get_chunk_vecs(text: str, unit: str):
	"""Return (chunks, chunk_vecs) for text+unit, using cache when available."""
	key = _cache_key(text, unit)
	if key in _chunk_cache:
		# Move to end to preserve recency for future eviction policy extensions
		_chunk_cache.move_to_end(key)
		return _chunk_cache[key], None

	chunks = _split_chunks(text, unit)
	if not chunks:
		return ([], []), None

	vecs, err = _embed(chunks)
	if err:
		return None, err

	if len(_chunk_cache) >= _CHUNK_CACHE_SIZE:
		_chunk_cache.popitem(last=False)  # evict oldest
	_chunk_cache[key] = (chunks, vecs)
	return (chunks, vecs), None


def _looks_like_path(s):
	"""True when *s* is probably a filesystem path, not a short literal string.

	Bare tokens like ``a`` / ``b`` are never treated as paths even if such files
	exist. Paths with a separator, ``~/``, ``./``, or a short alphanumeric
	suffix (``.md``, ``.py``) still resolve to files when they exist.
	"""
	if not isinstance(s, str) or not s or "\n" in s or "\r" in s:
		return False
	if len(s) > 512:
		return False
	p = Path(s)
	if p.is_absolute() or s.startswith("~/") or s.startswith("~\\"):
		return True
	if s.startswith("./") or s.startswith(".\\"):
		return True
	if "/" in s or "\\" in s:
		return True
	suffix = p.suffix
	return bool(suffix) and 2 <= len(suffix) <= 8 and suffix[1:].isalnum()


def _read_source(s):
	"""If s looks like an existing file path, return its text; otherwise return s."""
	if not _looks_like_path(s):
		return s
	try:
		p = resolve_path(s)
		if p.exists() and p.is_file():
			return p.read_text(encoding="utf-8")
	except (OSError, ValueError):
		pass
	return s


def _diff_source(s, default_label):
	"""Resolve a diff operand: file path → (contents, label), else literal text."""
	if not _looks_like_path(s):
		return s, default_label
	try:
		p = resolve_path(s)
		if p.exists() and p.is_file():
			return p.read_text(encoding="utf-8"), p.name
	except (OSError, ValueError):
		pass
	return s, default_label


def diff_text(a, b, context=3, label_a="a", label_b="b"):
	"""Return a unified diff between two strings or files.

	Args:
		a:        Original text or file path.
		b:        Modified text or file path.
		context:  Number of unchanged context lines shown around each change (default 3).
		label_a:  Label for the original in the diff header.
		label_b:  Label for the modified in the diff header.

	Returns dict with: diff (unified diff string), changed (bool), added, removed (line counts).
	"""
	a, label_a = _diff_source(a, label_a)
	b, label_b = _diff_source(b, label_b)

	lines_a = a.splitlines(keepends=True)
	lines_b = b.splitlines(keepends=True)
	chunks = list(difflib.unified_diff(lines_a, lines_b, fromfile=label_a, tofile=label_b, n=context))
	added   = sum(1 for line in chunks if line.startswith("+") and not line.startswith("+++"))
	removed = sum(1 for line in chunks if line.startswith("-") and not line.startswith("---"))
	return {
		"diff":    "".join(chunks),
		"changed": bool(chunks),
		"added":   added,
		"removed": removed,
	}


@lru_cache(maxsize=1)
def _get_ef():
	"""Return a cached instance of ChromaDB's default embedding function."""
	try:
		from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
		return DefaultEmbeddingFunction()
	except ImportError:
		return None


def _embed(texts):
	"""Embed a list of strings. Returns (list_of_np_arrays, error_dict_or_None)."""
	ef = _get_ef()
	if ef is None:
		return None, tool_error(
			"chromadb is not installed",
			hint="Run: pip install chromadb — encode_text, search_text, and mem_* need it.",
		)
	try:
		raw = ef(texts)
		return [np.array(v, dtype=np.float32) for v in raw], None
	except Exception as e:
		return None, tool_error(str(e), hint="The embedding model failed. Retry, or pass shorter text.")


def _cosine(a, b):
	n = np.linalg.norm(a) * np.linalg.norm(b)
	return float(np.dot(a, b) / n) if n else 0.0


def _split_sentences(text):
	"""Split text into sentences using punctuation boundaries."""
	parts = re.split(r'(?<=[.!?])\s+', text.strip())
	return [s.strip() for s in parts if s.strip()]


def _split_paragraphs(text):
	"""Split text into paragraphs (blocks separated by one or more blank lines)."""
	blocks = re.split(r'\n{2,}', text.strip())
	return [b.strip() for b in blocks if b.strip()]


def _split_chunks(text, unit):
	"""Split text into chunks by the given unit ('sentence' or 'paragraph')."""
	if unit == "paragraph":
		return _split_paragraphs(text)
	return _split_sentences(text)


def strip_tables(text):
	"""Remove markdown table syntax from text.

	Drops lines that consist entirely of table markup — pipe-delimited rows and
	separator lines (e.g. `| --- | --- |`) — then collapses runs of blank lines
	to a single blank line.

	Args:
		text: Input string to clean.

	Returns the cleaned string.
	"""
	_table_row = re.compile(r'^\s*\|.*\|\s*$')
	_separator  = re.compile(r'^\s*\|?[\s|:\-]+\|[\s|:\-]*$')

	cleaned_lines = []
	for line in text.splitlines():
		if _separator.match(line) or _table_row.match(line):
			continue
		cleaned_lines.append(line)

	# Collapse consecutive blank lines
	result = re.sub(r'\n{3,}', '\n\n', "\n".join(cleaned_lines))
	return result.strip()


# ── Public API ────────────────────────────────────────────────────────────────

_EF_MODEL_NAME = "all-MiniLM-L6-v2"

def encode_text(texts, save_to=""):
	"""Embed one or more texts using all-MiniLM-L6-v2.

	Args:
		texts:   A string or list of strings to embed.
		save_to: If given, write the 384-d vectors as JSON and omit them
		         from the return value.

	Returns dict with model name, embedding dimensions, count, and either
	embeddings (inline) or saved_to.
	"""
	if isinstance(texts, str):
		texts = [texts]
	if not texts:
		return {"model": _EF_MODEL_NAME, "dimensions": 0, "count": 0, "embeddings": []}
	texts = [_read_source(t) for t in texts]
	vecs, err = _embed(texts)
	if err:
		return err
	out = {
		"model":      _EF_MODEL_NAME,
		"dimensions": len(vecs[0]),
		"count":      len(vecs),
	}
	payload = [v.tolist() for v in vecs]
	if save_to:
		p = resolve_path(save_to)
		p.parent.mkdir(parents=True, exist_ok=True)
		p.write_text(json.dumps(payload), encoding="utf-8")
		out["saved_to"]   = str(p)
		out["size_bytes"] = p.stat().st_size
	else:
		out["embeddings"] = payload
	return out


def text_similarity(a, b):
	"""Compute cosine similarity between two texts.

	Args:
		a: First text string.
		b: Second text string.

	Returns dict with score (0–1), where 1 is identical meaning.
	"""
	vecs, err = _embed([_read_source(a), _read_source(b)])
	if err:
		return err
	return {
		"score": round(_cosine(vecs[0], vecs[1]), 4),
		"model": _EF_MODEL_NAME,
	}


def summarize_text(text, sentences=5, unit="sentence"):
	"""Extractive summarization: select the most representative chunks.

	Embeds the full text and each chunk, then ranks chunks by cosine similarity
	to the whole document. The top N are returned in their original order so the
	summary reads naturally. Chunk embeddings are cached in memory so repeated
	calls on the same text with different parameters skip re-embedding.

	Args:
		text:      Input text to summarize, or a file path to read from.
		sentences: Number of chunks to keep (default 5).
		unit:      Chunking granularity — 'sentence' (default) or 'paragraph'.
		           Paragraph mode is better for dense documents like academic papers.

	Returns dict with the summary string, method info, and chunk counts.
	"""
	text = _read_source(text)

	cached, err = _get_chunk_vecs(text, unit)
	if err:
		return err
	chunks, chunk_vecs = cached

	if len(chunks) <= sentences:
		return {
			"summary":  text.strip(),
			"method":   "full_text",
			"unit":     unit,
			"selected": len(chunks),
			"total":    len(chunks),
		}

	# Embed only the document vector — chunk vecs come from cache
	doc_vecs, err = _embed([text])
	if err:
		return err
	doc_vec = doc_vecs[0]

	scores = [_cosine(doc_vec, cv) for cv in chunk_vecs]

	# Pick top-N indices, preserve original document order
	top_idx = sorted(
		sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:sentences]
	)
	summary = "\n\n".join(chunks[i] for i in top_idx) if unit == "paragraph" else " ".join(chunks[i] for i in top_idx)

	return {
		"summary":  summary,
		"method":   "extractive",
		"model":    _EF_MODEL_NAME,
		"unit":     unit,
		"selected": sentences,
		"total":    len(chunks),
	}


def extract_text(source, query, sentences=5, unit="sentence"):
	"""Find chunks in a text that are most semantically similar to a query.

	Unlike summarize_text (which finds what is representative of the whole document),
	this extracts chunks that best answer or relate to a specific question.
	Useful for Q&A-style retrieval from long files without loading the full content.
	Chunk embeddings are cached in memory so repeated queries on the same text
	skip re-embedding the document chunks.

	Args:
		source:    Input text, or a file path to read from.
		query:     Query or question to match chunks against.
		sentences: Maximum number of results to return (default 5).
		unit:      Chunking granularity — 'sentence' (default) or 'paragraph'.
		           Paragraph mode returns more coherent context for dense documents.

	Returns dict with query, results (sorted by score descending), total chunk count, and model.
	Each result includes: sentence, score (0-1), and index (original document position).
	"""
	text = _read_source(source)

	cached, err = _get_chunk_vecs(text, unit)
	if err:
		return err
	chunks, chunk_vecs = cached

	if not chunks:
		return {"query": query, "results": [], "total": 0, "model": _EF_MODEL_NAME}

	# Embed only the query vector — chunk vecs come from cache
	query_vecs, err = _embed([query])
	if err:
		return err
	query_vec = query_vecs[0]

	scored = sorted(
		[(i, _cosine(query_vec, cv)) for i, cv in enumerate(chunk_vecs)],
		key=lambda x: x[1],
		reverse=True,
	)[:sentences]

	return {
		"query":   query,
		"results": [
			{"sentence": chunks[i], "score": round(score, 4), "index": i}
			for i, score in scored
		],
		"total": len(chunks),
		"unit":  unit,
		"model": _EF_MODEL_NAME,
	}


def search_text(source, query="", sentences=5, unit="sentence"):
	"""Unified semantic text search combining extract and summarize modes.

	When a query is provided, finds the chunks most relevant to that question
	(extract mode). When query is empty, selects the most representative chunks
	for an overview summary (summarize mode).

	Args:
		source:    Input text, or a file path to read from.
		query:     Question or topic to search for. Leave empty for a summary.
		sentences: Number of chunks to return (default 5).
		unit:      Chunking granularity — 'sentence' (default) or 'paragraph'.
		           Paragraph mode is strongly recommended for academic PDFs and
		           long-form documents where each paragraph carries distinct meaning.

	Returns the same shape as extract_text when query is given, or summarize_text
	when query is empty, with an added 'mode' field ('extract' or 'summarize').
	"""
	if query:
		result = extract_text(source, query, sentences=sentences, unit=unit)
		result["mode"] = "extract"
	else:
		result = summarize_text(source, sentences=sentences, unit=unit)
		result["mode"] = "summarize"
	return result

