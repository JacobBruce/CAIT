---
name: new-roleplay-world
description: >-
  Sets up a new file-based roleplay world by interviewing the player about their
  character, the setting, and the game rules, then scaffolding the world folder. Use
  when the user wants to start, create, or set up a new roleplay world, campaign, or
  text adventure.
---

# New Roleplay World

Create a new roleplay world: interview the player, then scaffold the world folder the
Game Master will run.

This skill owns only the **interview** and **what to seed**. The folder layout
and file formats are defined by the Game Master Protocols — follow §2 and §3
there for structure and formatting rather than reinventing them.

## Workflow

```
- [ ] Step 1: Offer a starting point (preset or custom)
- [ ] Step 2: Interview — setting, character, rules, visuals
- [ ] Step 3: Confirm the assembled world back to the player
- [ ] Step 4: Scaffold worlds/<slug>/
- [ ] Step 5: Introduce the world and open the scene
```

Guiding rules for the interview:
- Use the **AskQuestion** tool (if available) for each interview section — structured
  choices keep setup fast and clear. Offer a **"You decide"** option on every question
  so the player can defer; fill gaps consistently with the established genre and tone.
- One section per AskQuestion round, not one field at a time.
- Don't interrogate. Include presets and examples in the options where helpful.

## Step 1: Starting point

Offer the genre quick-starts in [presets.md](presets.md), or a fully custom world. A
preset pre-fills sensible defaults (tone, content rating, mechanics, death model, a
sample premise and starting location) that the player can accept or tweak. Read
`presets.md` only when the player wants to browse presets.

## Step 2: Interview

Cover three sections. Adapt depth to the player's appetite.

**Setting & premise**
- Genre and tone (e.g. heroic high fantasy, grimdark survival, hopeful sci-fi).
- Time period / tech level.
- Premise and backstory — the situation the world is in as play begins.
- Starting situation and location.
- **Content rating and hard limits** — how dark/mature the story may go, and any
  off-limits content. Always ask; record it in `WORLD.md`.

**Player character**
- Name, age, appearance.
- Background / who they are.
- Skills and strengths; weaknesses and flaws.
- Starting inventory and equipment.

**Rules & mechanics**
- Difficulty.
- How death works (e.g. permadeath, narrative consequence, downed-not-dead).
- Mechanics tier:
  - *Freeform* — pure narrative, no tracked stats beyond vitals.
  - *Light stats* — a few tracked attributes, outcomes adjudicated by the GM.
  - *Full stats + checks* — attributes plus resolved checks/rolls.
- **Resolution mode (only if checks are used):** real rolls via `repl_exec`, or the GM
  adjudicates outcomes fairly. Record the choice.
- Progression (leveling, skill growth) and core resources (health, currency, etc.).

**Visuals (optional)**
- Enable image generation? Assume the environment provides an image tool, but let the
  player opt out. If enabled:
  - Auto-generate **scene images** on entering new locations? Default **off** — scenes
    are visualized on demand via the `look scene` command instead.
  - Auto-generate **portraits** when first meeting important characters? Default **on**.
  - Pick a global **art style** for all images (e.g. painterly fantasy, gritty comic,
    anime, photoreal).
- If disabled, the game simply runs without images.

## Step 3: Confirm

Summarize the assembled world — character, setting, and rules — and get a quick
confirmation or corrections before writing files.

## Step 4: Scaffold

Create the world under `worlds/<slug>/` using the structure specified in
§2 of the Game Master Protocols, with formats from §3. Seed:

- `WORLD.md` — premise, setting, genre, tone, **content rating + hard limits**, the
  **mechanics tier, resolution mode, and death model**, and the **visual settings**
  chosen above. This is the canon the GM adjudicates by.
- `HISTORY.md` — the agreed backstory under `## Summary`, with an empty `## Log`.
- `STATE.md` — starting date/time, the starting location, and who is present.
- `PLACES.md` and `CAST.md` — seeded with the starting location and any opening NPCs.
- `characters/player/` — `PROFILE.md`, `STATE.md`, and `INVENTORY.md`.
- `locations/<starting_id>/` — `SUMMARY.md`, `STATE.md`, `CHARACTERS.md`, and an
  initialized `HISTORY.md`.

Record every meaningful detail from the interview into the right file — character
backstory into the player's `PROFILE.md`, world backstory into `HISTORY.md`/`WORLD.md`,
named NPCs into `CAST.md` and their own folders — so nothing established in setup is
lost. Create only what exists at the start; everything else is created lazily in play.

## Step 5: Introduce the world and open the scene

You are the Game Master from here on. Open with an introduction monologue, in the
established tone and within the content rating, that:

- **Sets the scene** — reiterate the world's setting, premise, and the backstory the
  player gave, so the world feels established.
- **Reflects the character** — weave in who the player character is (their background
  and notable traits) so they recognise themselves in the world.
- **Hooks** — end on a compelling situation, tension, or call to action that pulls the
  player into the starting location and invites their first move.

Write the player into the opening scene, then hand them control and play on, following
the Game Master Protocols (refer to the turn loop and reading/writing rules in §5 and §6).
