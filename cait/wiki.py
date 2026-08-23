"""
cait.wiki — Wikipedia tools using the wikipedia-api library.

All functions return plain dicts and use the synchronous Wikipedia client.
A cached client instance is shared per language to avoid redundant initialisation.
"""

import re
import platform
from functools import lru_cache

import wikipediaapi

from cait.errors import tool_error

_USER_AGENT = f"CAIT/1.0 (FastMCP; {platform.system()}; {platform.release()})"


# ── Internal helpers ──────────────────────────────────────────────────────────

@lru_cache(maxsize=16)
def _client(language="en"):
	"""Return a cached Wikipedia client for *language*."""
	return wikipediaapi.Wikipedia(user_agent=_USER_AGENT, language=language)


def _get_page(title, language):
	"""Return (page, None) or (None, error_dict)."""
	wiki = _client(language)
	try:
		page = wiki.page(title)
	except wikipediaapi.WikipediaException as e:
		return None, tool_error(str(e), hint="Retry, or check the title and language code.", title=title)
	if not page.exists():
		return None, tool_error(
			f"Page not found: {title!r}",
			hint="Use wiki_search to find the canonical title.",
			title=title,
			language=language,
		)
	return page, None


def _strip_html(text):
	"""Remove HTML tags from a snippet string."""
	return re.sub(r"<[^>]+>", "", text or "").strip()


def _page_url(title, language):
	"""Construct a Wikipedia URL without an extra API call."""
	slug = title.replace(" ", "_")
	return f"https://{language}.wikipedia.org/wiki/{slug}"


def _iter_sections(sections):
	"""Yield every section in *sections* recursively (depth-first)."""
	for s in sections:
		yield s
		yield from _iter_sections(s.sections)


def _sections_toc(sections):
	"""Recursively build a table-of-contents list (no text content)."""
	return [
		{
			"title": s.title,
			"subsections": _sections_toc(s.sections),
		}
		for s in sections
	]


# ── Public functions ──────────────────────────────────────────────────────────

def wiki_search(query, limit=5, language="en"):
	"""Search Wikipedia and return matching pages with snippets.

	Args:
		query:    Search query.
		limit:    Maximum number of results (default 5).
		language: Wikipedia language code (default "en").

	Returns dict with: query, total_hits, suggestion, results list.
	Each result has: title, snippet, wordcount, url.
	"""
	wiki = _client(language)
	try:
		results = wiki.search(query, limit=limit)
	except wikipediaapi.WikipediaException as e:
		return tool_error(str(e), hint="Retry the search, or simplify the query.")

	pages = []
	for title, page in results.pages.items():
		meta = page.search_meta
		pages.append({
			"title":     title,
			"snippet":   _strip_html(meta.snippet) if meta else "",
			"wordcount": meta.wordcount if meta else None,
			"url":       _page_url(title, language),
		})

	return {
		"query":      query,
		"language":   language,
		"total_hits": results.totalhits,
		"suggestion": results.suggestion or None,
		"results":    pages,
	}


def wiki_sections(title, language="en"):
	"""List all sections of a Wikipedia page as a table of contents.

	Returns section titles and their nesting structure without any text content.
	Use wiki_section() to fetch the text of a specific section.

	Args:
		title:    Wikipedia page title.
		language: Wikipedia language code (default "en").

	Returns dict with: title, url, sections (nested list of title/subsections).
	"""
	page, err = _get_page(title, language)
	if err:
		return err
	return {
		"title":    page.title,
		"url":      page.fullurl,
		"language": language,
		"sections": _sections_toc(page.sections),
	}


def wiki_section(title, section_title, language="en"):
	"""Get the text content of a specific section of a Wikipedia page.

	Performs a case-insensitive search if the exact title isn't found.

	Args:
		title:         Wikipedia page title.
		section_title: Section heading to retrieve (e.g. "History").
		language:      Wikipedia language code (default "en").

	Returns dict with: title, section, text, subsections (list of title/text), url.
	"""
	page, err = _get_page(title, language)
	if err:
		return err

	section = page.section_by_title(section_title)

	# Fall back to case-insensitive match
	if section is None:
		lower = section_title.lower()
		section = next(
			(s for s in _iter_sections(page.sections) if s.title.lower() == lower),
			None,
		)

	if section is None:
		available = [s.title for s in _iter_sections(page.sections)]
		return tool_error(
			f"Section {section_title!r} not found",
			hint="Call wiki_sections first and use an exact section title from that list.",
			title=page.title,
			available=available,
		)

	from cait.fs import cap_inline_text
	text, trunc_meta = cap_inline_text(section.text or "")
	subs = []
	for s in section.sections:
		st, _ = cap_inline_text(s.text or "", max_bytes=min(20_000, 100_000))
		subs.append({"title": s.title, "text": st})
	out = {
		"title":       page.title,
		"section":     section.title,
		"text":        text,
		"subsections": subs,
		"url":         page.fullurl,
		"language":    language,
	}
	if trunc_meta:
		out["truncated"] = True
		out["original_bytes"] = trunc_meta["original_bytes"]
		out["max_bytes"] = trunc_meta["max_bytes"]
	return out


def wiki_page(title, language="en", summary_only=False):
	"""Get content from a Wikipedia page.

	Args:
		title:        Wikipedia page title.
		language:     Wikipedia language code (default "en").
		summary_only: If True, return only the summary paragraph (token-efficient).
		              If False (default), return the full page text.

	Returns dict with: title, summary, url, language.
	When summary_only is False, also includes: text (full concatenated content).
	"""
	page, err = _get_page(title, language)
	if err:
		return err
	result = {
		"title":    page.title,
		"summary":  page.summary,
		"url":      page.fullurl,
		"language": language,
	}
	if not summary_only:
		from cait.fs import cap_inline_text
		text, trunc_meta = cap_inline_text(page.text or "")
		result["text"] = text
		if trunc_meta:
			result["truncated"] = True
			result["original_bytes"] = trunc_meta["original_bytes"]
			result["max_bytes"] = trunc_meta["max_bytes"]
	return result
