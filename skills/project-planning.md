---
name: project-planning
description: "Create or update PLAN.md and TASKS.md for a project. Use when starting a new project, planning a new feature, or reviewing the current implementation roadmap. Guides collaboration with the user to produce a structured plan with goals, architecture, and phased tasks."
argument-hint: "Optional: describe what you want to plan (e.g. 'new feature', 'full project', 'update roadmap')"
---

# Project Planning

## When to Use

- Starting a new project or significant feature
- Reviewing or updating the current implementation plan
- Breaking a broad goal into structured phases and tasks

## Procedure

### Step 1 — Gather Context

Before drafting anything, explore the workspace:

- Check if `PLAN.md` and `TASKS.md` already exist; if so, read them
- Scan the file structure to understand the current state of the project
- Look for any README, docs, or config files that reveal project goals or constraints

### Step 2 — Interview the User

Ask about any unclear or missing details. Focus only on gaps not already evident from the workspace. Typical questions:

- What is the primary goal of the project?
- What frameworks, languages, or libraries are involved?
- Are there architectural constraints or preferences?
- What is the intended scope (MVP vs. full-featured)?
- Are there known upcoming features or phases beyond the immediate goal?

### Step 3 — Draft PLAN.md

Write or update `PLAN.md` at the project root using this layout:

```markdown
# Project Plan

## Goal

One paragraph describing the project and its primary objectives.

## Framework

Languages, libraries, runtime environment, external services.

## Architecture

File structure, key modules, data flow, design decisions.

## Roadmap

Planned features with brief implementation descriptions, grouped by version or phase.
```

**Rules for PLAN.md:**

- Be specific about technical decisions (library choices, API design, etc.)
- The Roadmap describes *what* and *why*, not step-by-step tasks
- Mark completed roadmap items with ✓

### Step 4 — Draft TASKS.md

Write or update `TASKS.md` at the project root using this layout:

```markdown
# Tasks

This document breaks the project down into manageable steps and provides a way to track progress. The agent should keep this document updated with details about what they have done and what needs to be done next (don't remove this message).

## Current Tasks

**Phase N: Phase Name**

- [x] First step in phase N
- [ ] The current task

## Planned Tasks

- [ ] An upcoming task
- [ ] Phase N+1: brief description
```

**Rules for TASKS.md:**

- **Current Tasks** = the active phase with checkboxes tracking completion
- **Planned Tasks** = upcoming phases or tasks described at a higher level
- Each task should be actionable and specific enough to implement without further clarification

### Step 5 — Review with User

After drafting, present a brief summary:

- The project goal and key architectural decisions
- The phase breakdown and estimated scope
- Any assumptions made during planning

Ask the user to confirm or correct before writing the files. If significant corrections are needed, revise and confirm again before finalising.
