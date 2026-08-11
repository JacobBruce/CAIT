"""
cait.arxiv — arXiv search and paper retrieval tools.

Uses the `arxiv` library for API access and cait.document to convert
PDFs to markdown when full_text is requested.
"""

from functools import lru_cache
from cait.fs import _DEFAULT_FILEDIR
from cait.wiki import _USER_AGENT

import arxiv as _arxiv

_SORT_MAP = {
	"relevance":    _arxiv.SortCriterion.Relevance,
	"lastUpdated":  _arxiv.SortCriterion.LastUpdatedDate,
	"submitted":    _arxiv.SortCriterion.SubmittedDate,
}


@lru_cache(maxsize=1)
def _client():
	return _arxiv.Client()


def _fmt_result(r):
	"""Convert an arxiv.Result to a plain dict."""
	return {
		"paper_id":    r.get_short_id(),
		"title":       r.title,
		"authors":     [a.name for a in r.authors],
		"abstract":    r.summary,
		"published":   r.published.strftime("%Y-%m-%d") if r.published else None,
		"updated":     r.updated.strftime("%Y-%m-%d") if r.updated else None,
		"primary_category": r.primary_category,
		"categories":  r.categories,
		"pdf_url":     r.pdf_url,
		"arxiv_url":   f"https://arxiv.org/abs/{r.get_short_id()}",
		"doi":         r.doi or None,
		"journal_ref": r.journal_ref or None,
		"comment":     r.comment or None,
	}


def arxiv_search(query, limit=10, sort_by="relevance"):
	"""Search arXiv and return metadata for matching papers.

	Args:
		query:   arXiv query string. Supports field prefixes:
		         ti: (title), au: (author), abs: (abstract), cat: (category).
		         Boolean operators: AND, OR, ANDNOT.
		         Example: 'au:vaswani AND ti:attention'
		limit:   Maximum number of results (default 10, max 100).
		sort_by: One of 'relevance' (default), 'lastUpdated', or 'submitted'.

	Returns dict with query, count, and results list.
	"""
	criterion = _SORT_MAP.get(sort_by, _arxiv.SortCriterion.Relevance)
	search = _arxiv.Search(
		query=query,
		max_results=min(limit, 100),
		sort_by=criterion,
	)
	try:
		results = [_fmt_result(r) for r in _client().results(search)]
	except Exception as e:
		return {"error": str(e)}

	return {
		"query":   query,
		"sort_by": sort_by,
		"count":   len(results),
		"results": results,
	}


def arxiv_paper(paper_id, full_text=False, save_to=""):
	"""Fetch a paper by arXiv ID and return it as markdown.

	With full_text=False (default), returns structured metadata formatted as
	markdown: title, authors, abstract, categories, and links.

	With full_text=True, downloads the PDF and converts it using convert_doc.
	The download may take a few seconds and the output can be long.

	Args:
		paper_id:  arXiv paper ID (e.g. '1706.03762', '1706.03762v5',
		           'quant-ph/0201082'). Version suffix is optional.
		full_text: If True, return full PDF content instead of abstract only.
		save_to:   If given, write the markdown content to this file path and
		           omit 'markdown' from the return value. The directory is
		           created if it does not exist.

	Returns dict with paper metadata and either 'markdown' or 'saved_to'/'size_bytes'.
	"""
	search = _arxiv.Search(id_list=[paper_id])
	try:
		result = next(_client().results(search), None)
	except Exception as e:
		return {"error": str(e)}

	if result is None:
		return {"error": f"No paper found with id '{paper_id}'"}

	meta = _fmt_result(result)

	if not full_text:
		# Build a clean markdown summary from metadata
		authors_str = ", ".join(meta["authors"])
		cats = ", ".join(meta["categories"] or [])
		lines = [
			f"# {meta['title']}",
			f"",
			f"**Authors:** {authors_str}  ",
			f"**Published:** {meta['published']}  ",
			f"**Updated:** {meta['updated']}  ",
			f"**Categories:** {cats}  ",
		]
		if meta["doi"]:
			lines.append(f"**DOI:** {meta['doi']}  ")
		if meta["journal_ref"]:
			lines.append(f"**Journal ref:** {meta['journal_ref']}  ")
		if meta["comment"]:
			lines.append(f"**Comment:** {meta['comment']}  ")
		lines += [
			f"",
			f"**arXiv:** {meta['arxiv_url']}  ",
			f"**PDF:** {meta['pdf_url']}  ",
			f"",
			f"## Abstract",
			f"",
			meta["abstract"],
		]
		markdown = "\n".join(lines)
		if save_to:
			from pathlib import Path
			p = Path(save_to)
			p.parent.mkdir(parents=True, exist_ok=True)
			p.write_text(markdown, encoding="utf-8")
			return {**meta, "saved_to": str(p.resolve()), "size_bytes": p.stat().st_size}
		return {**meta, "markdown": markdown}

	# full_text=True: download PDF then convert via cait.document
	if not meta["pdf_url"]:
		return {"error": f"No PDF URL available for paper '{paper_id}'"}

	try:
		import urllib.request
		from cait.document import convert_doc

		save_dir = _DEFAULT_FILEDIR
		save_dir.mkdir(parents=True, exist_ok=True)
		local_pdf = save_dir / (paper_id.replace("/", "-") + ".pdf")
		req = urllib.request.Request(meta["pdf_url"], headers={"User-Agent": _USER_AGENT})
		with urllib.request.urlopen(req, timeout=60) as resp:
			local_pdf.write_bytes(resp.read())

		conv = convert_doc(str(local_pdf), save_to=save_to)
		if save_to:
			return {**meta, "pdf_path": str(local_pdf), "saved_to": conv["saved_to"], "size_bytes": conv["size_bytes"]}
		from cait.fs import cap_inline_text
		md_text, trunc_meta = cap_inline_text(conv.get("content") or "")
		out = {**meta, "pdf_path": str(local_pdf), "markdown": md_text}
		if trunc_meta:
			out["truncated"] = True
			out["original_bytes"] = trunc_meta["original_bytes"]
			out["max_bytes"] = trunc_meta["max_bytes"]
		return out
	except Exception as e:
		return {"error": f"PDF conversion failed: {e}"}
