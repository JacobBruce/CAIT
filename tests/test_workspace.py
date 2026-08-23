"""CAIT_WORKSPACE relative-path resolution."""

import os
from pathlib import Path

from cait.fs import resolve_path, workspace_root, file_info, file_read
from cait.code import find_definitions


def test_relative_joins_env(tmp_path, monkeypatch):
	readme = tmp_path / "README.md"
	readme.write_text("hello\n", encoding="utf-8")
	monkeypatch.setenv("CAIT_WORKSPACE", str(tmp_path))
	got = resolve_path("README.md")
	assert got == readme.resolve()
	info = file_info("README.md")
	assert info["name"] == "README.md"
	data = file_read("README.md")
	assert "hello" in data.get("content", "")
	assert data.get("total_lines") == 1
	assert data.get("truncated") is False


def test_absolute_ignores_workspace(tmp_path, monkeypatch):
	other = tmp_path / "other"
	other.mkdir()
	target = tmp_path / "target.txt"
	target.write_text("x\n", encoding="utf-8")
	monkeypatch.setenv("CAIT_WORKSPACE", str(other))
	assert resolve_path(str(target)) == target.resolve()


def test_tilde(monkeypatch):
	home = Path.home()
	monkeypatch.setenv("CAIT_WORKSPACE", str(home / "nope"))
	got = resolve_path("~/.")
	assert got == home.resolve()


def test_unset_env_uses_cwd(tmp_path, monkeypatch):
	monkeypatch.delenv("CAIT_WORKSPACE", raising=False)
	monkeypatch.chdir(tmp_path)
	assert workspace_root() == tmp_path.resolve()
	(tmp_path / "a.txt").write_text("ok\n", encoding="utf-8")
	assert resolve_path("a.txt") == (tmp_path / "a.txt").resolve()


def test_code_default_path_is_workspace(tmp_path, monkeypatch):
	src = tmp_path / "mod.py"
	src.write_text("def ping():\n\treturn 1\n", encoding="utf-8")
	monkeypatch.setenv("CAIT_WORKSPACE", str(tmp_path))
	hits = find_definitions("ping")
	assert any(h["file"].endswith("mod.py") for h in hits["results"])
