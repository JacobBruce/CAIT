"""
cait.memory — Persistent semantic memory using ChromaDB.

Two scopes are supported:
  global  (default) — one shared collection across all projects.
  project — a per-project collection, isolated from the global one.
             Pass any short name string as the scope (e.g. scope="myproject").
             The collection is named "cait_<scope>".

Storage path defaults to ~/.cait/memory; override with the CAIT_MEMORY_PATH env var.

Requires: pip install chromadb
"""

import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
	import chromadb
	_CHROMADB_AVAILABLE = True
except ImportError:
	_CHROMADB_AVAILABLE = False

_UNAVAILABLE = {"error": "chromadb is not installed — run: pip install chromadb"}

_DB_PATH = Path(os.environ.get("CAIT_MEMORY_PATH", Path.home() / ".cait" / "memory"))

_client:      object       = None
_collections: dict         = {}  # name → chromadb.Collection


# ── Internal helpers ──────────────────────────────────────────────────────────

def _collection_name(scope: str) -> str:
	"""Map a scope string to a ChromaDB collection name."""
	if scope == "global":
		return "cait_memory"
	# Sanitize: keep only alphanumerics, hyphens, underscores
	slug = re.sub(r"[^a-zA-Z0-9_-]", "_", scope.strip()).strip("_-")
	if not slug:
		raise ValueError(f"Invalid scope: {scope!r}")
	return f"cait_{slug}"


def _get_collection(scope="global"):
	"""Return (collection, None) or (None, error_dict)."""
	global _client, _collections
	try:
		name = _collection_name(scope)
	except ValueError as e:
		return None, {"error": str(e)}

	if name in _collections:
		return _collections[name], None

	if not _CHROMADB_AVAILABLE:
		return None, _UNAVAILABLE
	try:
		_DB_PATH.mkdir(parents=True, exist_ok=True)
		if _client is None:
			_client = chromadb.PersistentClient(path=str(_DB_PATH))
		col = _client.get_or_create_collection(
			name=name,
			metadata={"hnsw:space": "cosine"},
		)
		_collections[name] = col
		return col, None
	except Exception as e:
		return None, {"error": f"Failed to open memory database: {e}"}


def _now():
	return datetime.now(timezone.utc).isoformat()


def _encode_tags(tags):
	"""Encode a tag list as a space-padded string for safe substring filtering.

	E.g. ["research", "ai"] → " research ai "
	Using space-padding ensures "$contains: ' research '" won't match "deep-research".
	"""
	if not tags:
		return " "
	return " " + " ".join(t.strip() for t in tags if t.strip()) + " "


def _decode_tags(tags_str):
	"""Decode a space-padded tag string back to a list."""
	return [t for t in (tags_str or "").split() if t]


def _matches_tags(metadata, tags):
	"""Return True if the entry's tag string contains all required tags."""
	tag_str = metadata.get("tags", "")
	return all(f" {t} " in tag_str for t in tags)


def _format_entry(entry_id, document, metadata, include_content=True):
	"""Build a standard result dict from ChromaDB fields."""
	result = {
		"id":          entry_id,
		"title":       metadata.get("title", ""),
		"description": metadata.get("description", ""),
		"tags":        _decode_tags(metadata.get("tags", "")),
		"source":      metadata.get("source", ""),
		"created_at":  metadata.get("created_at", ""),
		"updated_at":  metadata.get("updated_at", ""),
	}
	if include_content:
		result["content"] = document
	return result


# ── Public functions ──────────────────────────────────────────────────────────

_SCOPE_HINT = (
	"Memory scope: 'global' (default, shared across all projects) or a short project "
	"name string to use an isolated per-project collection (e.g. 'myproject')."
)


def mem_add(title, content, tags=None, description="", source="", entry_id=None, scope="global"):
	"""Add a new entry to memory.

	Args:
		title:       Short descriptive title (used for browsing and display).
		content:     Main text content — this is what gets embedded and searched.
		tags:        Optional list of tag strings for filtering (e.g. ["research", "ai"]).
		description: Optional one-line summary stored as metadata.
		source:      Optional origin URL, file path, or "manual".
		entry_id:    Optional custom ID. A UUID is generated if not provided.
		scope:       'global' (default) or a project name for an isolated collection.

	Returns dict with: id, title, added, scope.
	"""
	col, err = _get_collection(scope)
	if err:
		return err

	eid = entry_id or str(uuid.uuid4())
	metadata = {
		"title":       title,
		"description": description,
		"tags":        _encode_tags(tags or []),
		"source":      source,
		"created_at":  _now(),
		"updated_at":  _now(),
	}
	try:
		col.add(documents=[content], metadatas=[metadata], ids=[eid])
	except Exception as e:
		return {"error": str(e)}
	return {"id": eid, "title": title, "added": True, "scope": scope}


def mem_set(entry_id, title=None, content=None, tags=None, description=None, source=None, scope="global"):
	"""Update fields of an existing memory entry. Only provided fields are changed.

	Args:
		entry_id:    ID of the entry to update.
		title:       New title, or None to leave unchanged.
		content:     New content (re-embeds the entry), or None to leave unchanged.
		tags:        New tag list (replaces existing tags), or None to leave unchanged.
		description: New description, or None to leave unchanged.
		source:      New source, or None to leave unchanged.
		scope:       'global' (default) or a project name for an isolated collection.

	Returns dict with: id, updated.
	"""
	col, err = _get_collection(scope)
	if err:
		return err

	existing = col.get(ids=[entry_id], include=["documents", "metadatas"])
	if not existing["ids"]:
		return {"error": f"No memory entry with id {entry_id!r}"}

	old_meta = existing["metadatas"][0]
	old_doc  = existing["documents"][0]

	new_meta = dict(old_meta)
	if title       is not None: new_meta["title"]       = title
	if description is not None: new_meta["description"] = description
	if tags        is not None: new_meta["tags"]        = _encode_tags(tags)
	if source      is not None: new_meta["source"]      = source
	new_meta["updated_at"] = _now()

	new_doc = content if content is not None else old_doc

	try:
		col.update(ids=[entry_id], documents=[new_doc], metadatas=[new_meta])
	except Exception as e:
		return {"error": str(e)}
	return {"id": entry_id, "updated": True}


def mem_edit(entry_id, pattern=None, text="", scope="global"):
	"""Edit the content of a memory entry in-place.

	Two modes:
	  - Regex replace: provide pattern (no replacement text = delete matches).
	    Applies re.sub(pattern, text, content) and re-embeds the result.
	  - Append: provide text with no pattern. Appends to the existing
	    content with a newline separator if needed.

	Args:
		entry_id:    ID of the entry to edit.
		pattern:     Regex pattern to match within the content. Required for replace mode.
		text:        Replacement string for regex mode, appends text when pattern is None.
		scope:       'global' (default) or a project name for an isolated collection.

	Returns dict with: id, updated, old_length, new_length.
	"""
	col, err = _get_collection(scope)
	if err:
		return err

	existing = col.get(ids=[entry_id], include=["documents", "metadatas"])
	if not existing["ids"]:
		return {"error": f"No memory entry with id {entry_id!r}"}

	old_content = existing["documents"][0]
	meta        = existing["metadatas"][0]

	if pattern is not None:
		try:
			new_content = re.sub(pattern, text, old_content)
		except re.error as e:
			return {"error": f"Invalid regex pattern: {e}"}
	elif text:
		sep         = "" if old_content.endswith("\n") else "\n"
		new_content = old_content + sep + text
	else:
		return {"error": "Provide either 'pattern' and/or 'text' arguments"}

	if new_content == old_content:
		return {"id": entry_id, "updated": False, "note": "Content unchanged"}

	meta["updated_at"] = _now()
	try:
		col.update(ids=[entry_id], documents=[new_content], metadatas=[meta])
	except Exception as e:
		return {"error": str(e)}

	return {
		"id":         entry_id,
		"updated":    True,
		"old_length": len(old_content),
		"new_length": len(new_content),
	}


def mem_search(query, limit=5, tags=None, scope="global"):
	"""Search memory by semantic similarity to a query string.

	Args:
		query: Natural language query — finds entries whose content is semantically similar.
		limit: Maximum number of results (default 5).
		tags:  Optional list of tags to filter by (AND logic — entry must have all given tags).
		scope: 'global' (default) or a project name for an isolated collection.

	Returns dict with: query, results list.
	Each result includes: id, title, description, tags, source, created_at, updated_at, content, score.
	Score is cosine similarity (0–1, higher is more similar).
	"""
	col, err = _get_collection(scope)
	if err:
		return err

	count = col.count()
	if count == 0:
		return {"query": query, "results": []}

	# Overfetch when tag filtering so we can reach the requested limit after filtering
	n_fetch = min(count, limit * 4 if tags else limit)
	kwargs = {
		"query_texts": [query],
		"n_results":   n_fetch,
		"include":     ["documents", "metadatas", "distances"],
	}

	try:
		results = col.query(**kwargs)
	except Exception as e:
		return {"error": str(e)}

	entries = []
	for eid, doc, meta, dist in zip(
		results["ids"][0],
		results["documents"][0],
		results["metadatas"][0],
		results["distances"][0],
	):
		if tags and not _matches_tags(meta, tags):
			continue
		entry = _format_entry(eid, doc, meta, include_content=True)
		entry["score"] = round(1 - dist, 4)
		entries.append(entry)
		if len(entries) >= limit:
			break

	return {"query": query, "results": entries}


def mem_get(entry_id, scope="global"):
	"""Retrieve a specific memory entry by ID, including full content.

	Args:
		entry_id: ID of the entry to retrieve.
		scope:    'global' (default) or a project name for an isolated collection.

	Returns the entry dict with: id, title, description, tags, source, created_at, updated_at, content.
	"""
	col, err = _get_collection(scope)
	if err:
		return err

	result = col.get(ids=[entry_id], include=["documents", "metadatas"])
	if not result["ids"]:
		return {"error": f"No memory entry with id {entry_id!r}"}

	return _format_entry(result["ids"][0], result["documents"][0], result["metadatas"][0])


def mem_list(tags=None, limit=20, sort_by="created_at", ascending=False, scope="global"):
	"""List memory entries sorted by date (most recent first by default).

	Content is omitted for brevity — use mem_get(id) to fetch the full content of an entry.

	Args:
		tags:      Optional list of tags to filter by (AND logic).
		limit:     Maximum number of entries to return (default 20).
		sort_by:   Field to sort by — 'created_at' or 'updated_at' (default 'created_at').
		ascending: If True, return oldest first. Default False (newest first).
		scope:     'global' (default) or a project name for an isolated collection.

	Returns dict with: count (number of entries returned, up to limit), entries list.
	Each entry includes: id, title, description, tags, source, created_at, updated_at.
	"""
	col, err = _get_collection(scope)
	if err:
		return err

	if sort_by not in ("created_at", "updated_at"):
		return {"error": f"sort_by must be 'created_at' or 'updated_at', got '{sort_by}'"}

	# ChromaDB has no ORDER BY, so we must fetch all metadata and sort in Python.
	# We fetch metadata-only (no document bodies) to keep this as lean as possible.
	# Note: ChromaDB 1.5.8's $contains operator is broken; server-side tag filtering
	# would require storing tags as individual boolean fields (schema change).
	try:
		result = col.get(include=["metadatas"])
	except Exception as e:
		return {"error": str(e)}

	entries = [
		_format_entry(eid, None, meta, include_content=False)
		for eid, meta in zip(result["ids"], result["metadatas"])
		if not tags or _matches_tags(meta, tags)
	]
	entries.sort(key=lambda e: e.get(sort_by, ""), reverse=not ascending)
	returned = entries[:limit]
	return {"count": len(returned), "entries": returned}


def mem_delete(entry_id, scope="global"):
	"""Delete a memory entry by ID.

	Args:
		entry_id: ID of the entry to delete.
		scope:    'global' (default) or a project name for an isolated collection.

	Returns dict with: id, deleted.
	"""
	col, err = _get_collection(scope)
	if err:
		return err

	existing = col.get(ids=[entry_id])
	if not existing["ids"]:
		return {"error": f"No memory entry with id {entry_id!r}"}

	try:
		col.delete(ids=[entry_id])
	except Exception as e:
		return {"error": str(e)}
	return {"id": entry_id, "deleted": True}


def mem_find(title=None, source=None, tags=None, limit=20, scope="global"):
	"""Fast metadata-only lookup without semantic embedding.

	Scans entry metadata and returns entries matching all provided criteria.
	At least one of title, source, or tags must be given.

	Unlike mem_search, this uses exact/substring matching and no embedding,
	making it suitable for deduplication checks before mem_add.

	Args:
		title:  Case-insensitive substring to match against entry titles.
		source: Exact source string to match (URL, file path, or 'manual').
		tags:   List of tags — entry must have ALL given tags (AND logic).
		limit:  Maximum number of entries to return (default 20).
		scope:  'global' (default) or a project name for an isolated collection.

	Returns dict with: count, entries list (no content — use mem_get for full entry).
	"""
	if title is None and source is None and tags is None:
		return {"error": "Provide at least one of: title, source, tags"}

	col, err = _get_collection(scope)
	if err:
		return err

	try:
		result = col.get(include=["metadatas"])
	except Exception as e:
		return {"error": str(e)}

	title_lower = title.lower() if title else None

	entries = []
	for eid, meta in zip(result["ids"], result["metadatas"]):
		if title_lower and title_lower not in meta.get("title", "").lower():
			continue
		if source and meta.get("source", "") != source:
			continue
		if tags and not _matches_tags(meta, tags):
			continue
		entries.append(_format_entry(eid, None, meta, include_content=False))
		if len(entries) >= limit:
			break

	return {"count": len(entries), "entries": entries}
