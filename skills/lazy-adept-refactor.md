---
name: lazy-adept-refactor
description: "Simplify over-engineered code and clean up poor design like an adept but lazy engineer - minimize unnecessary complexity and repetition without sacrificing behavior or flexibility. Use when code feels bloated, novice, repetitive, or harder than it needs to be; not for code-golf or rewriting clear code."
argument-hint: "Optional: path, module, or PR/diff scope (default: recent changes or current focus area)"
---

# Lazy Adept Refactor

## Mindset

Think like an **adept but lazy** software engineer.

- **Lazy** does **not** mean the easiest shortcut, half-finished work, or "ship the hack."
- **Lazy** means: spend effort once so you and others spend less effort forever. Prefer the solution that is efficient to write *and* efficient to read, change, and debug later.
- Adept laziness deletes work: fewer concepts, fewer branches, fewer wrappers, fewer places that must stay in sync.
- If the code is already clear and concise, **leave it alone**. This is not code golf. Shorter is not better when it obscures intent.

Sister skill: `thermo-nuclear-code-quality-review` is a harsh review bar. This skill is an **execution** pass: find and apply simplifications that earn their keep.

## When to Use

- After a feature landed and the design got heavier than the problem
- When the same idea is expressed three different ways
- When novice patterns, brittle stringly logic, or outdated APIs show up
- When the user asks to simplify, clean up, declutter, or "make this less over-engineered"
- Before calling something "done" if the implementation feels tiring to explain

**Do not use** to:

- Rewrite working, clear code for style points
- Compress everything into clever one-liners
- Invent new frameworks or "architecture" where a straight-line function would do
- Expand scope into unrelated refactors

## Goals

1. **Minimize unnecessary complexity** - remove layers, flags, and ceremony that do not buy flexibility you actually need.
2. **Minimize repetition** - one clear home for a rule; call it from the rest.
3. **Preserve behavior and needed flexibility** - do not "simplify" by deleting edge cases, error handling, or extension points the product still needs.
4. **Upgrade novice code** - replace fragile patterns with reliable, boring, modern equivalents.
5. **Surface obvious debt** - while you are there, note (and fix when cheap) clear bugs, footguns, and modernization opportunities.

## Procedure

### Step 1 - Scope

- Prefer a bounded scope: recent diff, named module, or the feature just built.
- Read surrounding code before changing it. Match project conventions (indentation, naming, module layout).
- If `SURVEY.md` / `NOTES.md` / `TASKS.md` exist, skim them so you do not fight known design choices.

### Step 2 - Diagnose (read before you cut)

Ask for each hotspot:

- What is the *intent* in one sentence?
- How many concepts must a reader hold to follow this?
- Which branches, helpers, or files exist only to paper over an awkward model?
- Is there duplication that will drift?
- Is there a novice pattern (copy-paste, deep nesting, magic strings, ignored errors, outdated APIs)?
- Is something obviously wrong, racy, or one bad edit away from breaking?

If the answer is "this is already the straightforward shape," skip it.

### Step 3 - Apply simplifications

Prefer changes in this order:

1. **Delete** dead code, unused params, empty wrappers, unreachable branches.
2. **Collapse** duplicate paths into one helper or one data-driven table.
3. **Flatten** nesting; invert conditions; early return.
4. **Relocate** logic to the module that already owns the concept (do not create a new package for a 10-line helper).
5. **Modernize** only where the new form is clearly clearer or safer (current language/stdlib idioms, explicit errors, less stringly typing).
6. **Fix** obvious bugs and footguns you touch; do not ignore a landmine next to your edit.

Rules of thumb:

- One function, one job. If a name needs "and," split or rename.
- Configuration and policy beat sprawling `if` forests when the cases are data.
- Comments explain *why*, not narrate *what*. Delete comments that only restate the code.
- Keep public APIs stable unless the user asked for a break or nothing external depends on them.
- Prefer the standard library / existing project utilities over new dependencies.

### Step 4 - Anti-patterns to hunt

Flag and usually fix:

- Pass-through wrappers that add no meaning
- Parallel fields or flags that must stay synchronized
- Speculative generality ("in case we need plugins someday")
- Deep callback / promise pyramids that could be straight-line `async`/`await`
- Giant functions that mix I/O, policy, and formatting
- Copy-pasted blocks with one-token differences
- Swallowing errors or using bare `except` / empty `catch`
- Magic numbers and unexplained string protocols where a named constant or small helper would clarify
- Deprecated APIs with an obvious modern replacement already used elsewhere in the repo
- UI / user-facing strings with characters that break on some systems (e.g. prefer ASCII `-` over Unicode em dashes in labels and titles)

### Step 5 - Validate

- Keep behavior the same unless you are fixing a clear bug (call that out).
- Run the lightest meaningful check: existing tests, a focused smoke path, or a quick manual sanity check.
- Update `NOTES.md` / `TASKS.md` only when the project expects it and you learned something durable.

### Step 6 - Report

Summarize for the user:

1. What complexity you removed (concepts, branches, files, duplication)
2. Novice / reliability / modernization fixes
3. Obvious issues you noticed but did **not** change (and why)
4. Anything that still deserves a larger redesign later

Keep the report short. Show intent, not a tour of every diff hunk.

## Tone While Working

- Direct and practical.
- Do not moralize. Do not bike-shed renames when structure is fine.
- If a dramatic simplification exists, take it. If it does not, stop.
- Proudly leave clear code untouched.

## Approval Bar (for your own edits)

You are done only when:

- The scoped code is easier to explain out loud
- Repetition and ceremony went down, or you justified why not
- Behavior (and needed flexibility) remain intact
- Obvious footguns you touched are fixed
- You did not golf already-clear code into clever soup
