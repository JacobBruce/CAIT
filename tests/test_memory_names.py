"""Memory collection naming, tags, list totals, search snippets."""

from cait.memory import (
	_collection_name,
	_decode_tags,
	_encode_tags,
	_matches_tags,
	_snippet,
	mem_list,
	mem_search,
)


def test_global_and_empty_scope():
	assert _collection_name("global") == "cait_memory"
	assert _collection_name("") == "cait_memory"
	assert _collection_name(None) == "cait_memory"


def test_memory_scope_does_not_collide_with_global():
	assert _collection_name("memory") == "cait_proj_memory"
	assert _collection_name("myproject") == "cait_myproject"


def test_encode_tags_accepts_string():
	assert _decode_tags(_encode_tags("research")) == ["research"]


def test_tags_roundtrip_with_spaces():
	raw = _encode_tags(["deep research", "ai"])
	assert "deep research" in _decode_tags(raw)
	assert _decode_tags(raw) == ["deep research", "ai"]
	assert _matches_tags({"tags": raw}, ["deep research"])
	assert not _matches_tags({"tags": raw}, ["deep"])


def test_decode_tags_legacy_space_padded():
	assert _decode_tags(" research ai ") == ["research", "ai"]
	assert _matches_tags({"tags": " research ai "}, ["research", "ai"])


def test_snippet_truncates():
	long = "word " * 200
	s = _snippet(long, n=40)
	assert s.endswith("…")
	assert len(s) < len(long)


class _FakeCol:
	def __init__(self):
		self.ids = ["a", "b", "c"]
		self.metas = [
			{"title": "A", "tags": _encode_tags(["deep research"]), "created_at": "2020",
			 "description": "", "source": "", "updated_at": "2020"},
			{"title": "B", "tags": _encode_tags(["other"]), "created_at": "2021",
			 "description": "", "source": "", "updated_at": "2021"},
			{"title": "C", "tags": _encode_tags(["deep research"]), "created_at": "2022",
			 "description": "to clear", "source": "manual", "updated_at": "2022"},
		]
		self.docs = ["alpha " * 80, "beta", "gamma"]

	def count(self):
		return len(self.ids)

	def get(self, ids=None, include=None):
		if ids is not None:
			want = ids if isinstance(ids, list) else [ids]
			idxs = [self.ids.index(i) for i in want]
			return {
				"ids": [self.ids[i] for i in idxs],
				"metadatas": [self.metas[i] for i in idxs],
				"documents": [self.docs[i] for i in idxs],
			}
		return {"ids": list(self.ids), "metadatas": list(self.metas), "documents": list(self.docs)}

	def query(self, query_texts=None, n_results=5, include=None, ids=None):
		pool = ids if ids is not None else self.ids
		chosen = pool[:n_results]
		idxs = [self.ids.index(i) for i in chosen]
		return {
			"ids":       [[self.ids[i] for i in idxs]],
			"documents": [[self.docs[i] for i in idxs]],
			"metadatas": [[self.metas[i] for i in idxs]],
			"distances": [[0.1] * len(idxs)],
		}

	def update(self, ids, documents=None, metadatas=None):
		idx = self.ids.index(ids[0])
		if metadatas:
			self.metas[idx] = metadatas[0]
		if documents:
			self.docs[idx] = documents[0]


def test_mem_list_count_vs_total(monkeypatch):
	col = _FakeCol()
	monkeypatch.setattr("cait.memory._get_collection", lambda scope="global": (col, None))
	out = mem_list(limit=2)
	assert out["count"] == 2
	assert out["total"] == 3
	assert out["truncated"] is True
	assert out["limit"] == 2


def test_mem_search_tag_filter_uses_ids_not_overfetch(monkeypatch):
	col = _FakeCol()
	seen = {}

	orig_query = col.query

	def query(**kwargs):
		seen["ids"] = kwargs.get("ids")
		seen["n_results"] = kwargs.get("n_results")
		return orig_query(**kwargs)

	col.query = query
	monkeypatch.setattr("cait.memory._get_collection", lambda scope="global": (col, None))
	out = mem_search("x", tags=["deep research"], limit=5)
	assert set(seen["ids"]) == {"a", "c"}
	assert seen["n_results"] == 2
	assert "content" not in out["results"][0]
	assert "snippet" in out["results"][0]
