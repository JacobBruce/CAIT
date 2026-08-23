"""cait.utils.status snapshot."""

from cait.utils import status


def test_status_keys(tmp_path, monkeypatch):
	monkeypatch.setenv("CAIT_WORKSPACE", str(tmp_path))
	monkeypatch.delenv("CAIT_DISABLE", raising=False)
	snap = status()
	assert snap["name"] == "CAIT - Core AI Toolkit"
	assert snap["version"]
	assert snap["python"]
	assert snap["python_executable"]
	assert snap["workspace"] == str(tmp_path.resolve())
	assert snap["workspace_env_set"] is True
	assert "cwd" in snap
	assert "fs" in snap["modules"]["enabled"]
	assert snap["modules"]["disabled"] == []
	assert snap["memory_path"]
	assert snap["files_path"]
	assert snap["cache_path"].endswith("doc_cache")
	assert isinstance(snap["chromadb"], bool)
	from cait.fs import _DEFAULT_EXCLUDE
	assert snap["default_exclude"] == sorted(_DEFAULT_EXCLUDE)
	assert "fastmcp" in snap
	assert "mcp" in snap
	assert "mcp_protocol" in snap


def test_status_disabled_modules(tmp_path, monkeypatch):
	monkeypatch.setenv("CAIT_WORKSPACE", str(tmp_path))
	monkeypatch.setenv("CAIT_DISABLE", "wiki,arxiv")
	snap = status()
	assert snap["modules"]["disabled"] == ["wiki", "arxiv"]
	assert "wiki" not in snap["modules"]["enabled"]
	assert "fs" in snap["modules"]["enabled"]


def test_status_unset_workspace_uses_cwd(tmp_path, monkeypatch):
	monkeypatch.delenv("CAIT_WORKSPACE", raising=False)
	monkeypatch.chdir(tmp_path)
	snap = status()
	assert snap["workspace_env_set"] is False
	assert snap["workspace"] == str(tmp_path.resolve())
