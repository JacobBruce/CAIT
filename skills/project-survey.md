---
name: project-survey
description: "Survey and orient in an unfamiliar codebase. Use when first opening a repo, after a major refactor, when SURVEY.md is missing or stale, or when the user asks to familiarize yourself with the project. Produces SURVEY.md — a structured map of what exists. Run before project-planning when the codebase is unknown."
argument-hint: "Optional: project name for codebase-memory index, or 'refresh' to re-survey"
---

# Project Survey

## When to Use

- First contact with a repo (no `SURVEY.md`, or agent is unfamiliar with the layout)
- User says "survey this project", "familiarize yourself", "what is this codebase"
- Returning after a long absence or a large refactor (survey may be stale)
- Before `project-planning` when `PLAN.md` does not exist and the codebase is not already understood

**Do not use** when `SURVEY.md` is recent and the task is narrowly scoped — read the survey and proceed.

## How This Differs from project-planning

| | **project-survey** | **project-planning** |
|--|-------------------|----------------------|
| Purpose | Understand what *exists* | Decide what to *build next* |
| Output | `SURVEY.md` | `PLAN.md` + `TASKS.md` |
| User involvement | Minimal — can run autonomously | Collaborative interview |
| Depth | Broad, shallow map | Narrow, deep plan |

---

## Procedure

### Step 0 — Check existing artifacts

- If `SURVEY.md` exists, read the frontmatter (`last_surveyed_commit`, date). If the repo has had large changes since then, re-survey.
- Read `PLAN.md`, `TASKS.md`, `NOTES.md` if present — summarize in the survey; do not duplicate them wholesale.

### Step 1 — Index and structure (codebase-memory-mcp)

1. `list_projects` / `index_status` — call `index_repository` if missing or clearly stale.
2. `get_architecture` — packages, services, dependencies, high-level layout.
3. `get_graph_schema` — only if edge types or node labels are unclear.
4. `search_graph` — locate entry points (`main`, `if __name__`, `FastMCP`, `IMPLEMENT_APP`, `wxIMPLEMENT_APP`, CLI `typer`, etc.).

**Note**: If the codebase-memory-mcp tools are unavailable you can proceed with the project survey using the available tools.

### Step 2 — Config and docs (CAIT fs)

5. `get_dir_info` on the project root — top-level layout only; no deep recursion (capped; junk dirs pruned). Use the host `glob_files` / `grep_files` tools to search a whole tree.
6. `read_file` — README and the primary build manifest (first ~200 lines):
   - Python: `pyproject.toml`, `setup.py`, `requirements.txt`
   - C/C++: `CMakeLists.txt`, `Makefile`, `meson.build`
   - Node: `package.json`
7. Note presence of `compile_commands.json` for C++ projects.

### Step 3 — Ground truth checks

8. `detect_changes` — if the tree is dirty, note uncommitted work in the survey.
9. `trace_path` on one or two entry-point symbols (outbound, depth 2) — confirm the graph matches reality.
10. If no codebase index: use CAIT `find_definitions` / `find_imports` for Python entry points.

### Step 4 — Write SURVEY.md

Write `SURVEY.md` at the project root using `write_file` (replace mode). Use this layout:

```markdown
---
last_surveyed: YYYY-MM-DD
last_surveyed_commit: <short git hash or unknown>
index_project: <codebase-memory project name or none>
---

# Project Survey

## One-liner

{What this project is — from README or inference}

## Tech stack

{Languages, frameworks, build system, runtime, key dependencies}

## Directory map

{Top-level directories with one-line purpose each — not a full tree dump}

## Entry points

{main(), app bootstrap, CLI commands, MCP server entry, test runners}

## Key modules

{3–8 central files or packages with one-line roles}

## Build and test

{Exact commands to build, run, and test — from README or config files}

## Conventions

{Rules files, coding style signals, hooks, env vars worth knowing}

## Active work

{Summary from PLAN.md / TASKS.md / NOTES.md if they exist; otherwise "none documented"}

## Risks and quirks

{Large files, generated code, submodules, platform-specific bits, missing or stale index}

## Open questions

{What could not be determined — ask the user only for blockers here}

## Suggested next steps

{What an agent should read or do before editing — e.g. "re-index after refactor", "read X before touching Y"}
```

### Step 5 — Hand off

- If `open_questions` blocks the user's task → ask only those questions.
- If no `PLAN.md` and the user wants to build something → suggest the `project-planning` skill.
- If `TASKS.md` exists and the user has a task → proceed to work, citing relevant survey sections.
- Present a brief summary to the user: one-liner, entry points, and suggested next steps.

---

## Rules

- **Do not** read entire large files — use `get_file_info`, targeted `read_file` slices, or `search_file`.
- **Do not** duplicate `PLAN.md` / `TASKS.md` content — link and summarize.
- **Do not** store the survey in CAIT `mem_*` — `SURVEY.md` is project-scoped and may be git-tracked.
- **Do** mark uncertain claims with `(unverified)` in the survey body.
- **Do** keep the survey concise: target 1–3 pages. It is a map, not a manual.
- **Do** update `last_surveyed_commit` when git is available (`git rev-parse --short HEAD` via shell if needed).
