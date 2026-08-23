"""CAIT — Core AI Toolkit.

Library helpers live in submodules (`cait.fs`, `cait.code`, …). Run the MCP
server with ``python -m cait.server``.

The names below are the filesystem helpers most often imported directly.
"""

from cait.fs import (
	dir_info,
	fetch_url,
	file_download,
	file_info,
	file_read,
	file_search,
	file_write,
	resolve_path,
	workspace_root,
)

__version__ = "1.0.4"
__all__ = [
	"__version__",
	"dir_info",
	"fetch_url",
	"file_download",
	"file_info",
	"file_read",
	"file_search",
	"file_write",
	"resolve_path",
	"workspace_root",
]
