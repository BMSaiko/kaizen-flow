---
name: grill-me
description: Relentless interview to sharpen a plan or design
version: 1.3.0
author: Matt Pocock (adapted for Hermes)
license: MIT
platforms:
- linux
- macos
- windows
triggers:
- grill me
- grill-me
- grill this
- stress test this
- stress-test this
metadata:
  hermes:
    tags:
    - interview
    - design
    - plan
    - decision
    - productivity
    category: productivity
---
# Grill-me

Relentless interview protocol. Run it yourself, inline; there is no separate skill to load.

# Protocol

Interview the user relentlessly until you reach a shared understanding. Map this as a
**design tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are
already settled: the questions you can ask _now_ without guessing at answers you
haven't heard yet. Ask the whole frontier in one round: number each question and give
your recommended answer. Then wait for the user's answers before the next round.

Format a round like so:

```
? **Q1** - **<short topic>**: <question>?
> <your recommended answer with rationale>

---

? **Q2** - **<short topic>**: <question>?
> <your recommended answer with rationale>
```

Each round the user answers reshapes the tree: settled decisions push the frontier
outward and unblock questions that depended on them. Recompute the frontier and ask
the next round. A question whose answer depends on another question still open in this round
belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from
the environment (filesystem, tools, etc.), use `Bash`, `Read`, `Grep`/`Glob`,
or `WebSearch` to find it; don't ask the user for anything you could look up yourself.
Don't block on it: a running exploration is an unsettled prerequisite, so only the
questions downstream of it wait for the report; ask the rest of the frontier now. The
_decisions_ are the user's: put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited,
nothing left silently assumed. Do not act on it until the user confirms you have
reached a shared understanding.

# Modal/UI speculation trap (YAGNI, with user-override escape hatch)

In the grilling flow, do not propose **new** UI affordances (modals,
auto-popups, post-run wizards) unless the user has asked for them.
Specifically:

- **Do not** propose a "modal pré-run" for the user to type the plan/decision
  when the card description is **already an editable textarea** that the spawn
  injects into the prompt (e.g. Atlas kanban cards: the textarea is the
  `description` field, already wired to `cardDescription` in the spawn prompt).
  Ponytail rung 1: "Does this need to exist at all?" — the textarea is
  already there.
- **Do not** propose an "auto-open refine modal after run" when an existing
  reject flow already opens the same modal on user click (Atlas: the
  reject modal already has the refine textarea + submit). Auto-opening
  speculates a UX the user didn't request.
- **The rule:** when an existing field or flow already covers the case the
  user described, point to it and use it. If a feature request is missing,
  the absence is the answer.

**Exception (learned 2026-09-01):** the user *explicitly* asked for the
modal. In that case build it — but build it on the *existing* `openModal`
helper, not a new framework. The trap fires most often on the Q-round
*after* the grilling flow starts working ("wouldn't it be nicer if there
was a modal for X?"). When the user says "I want a modal that...", the
absence of an existing field is no longer the answer — build it small,
reuse `openModal`, ship. Same rule: never invent a new modal framework
to solve this; `openModal` already does the job.

When invoked from chat (not Atlas), grilling still happens inline. The
distinction matters: Atlas = worker handles rounds in wezterm; chat = agent
handles rounds in the same conversation.

# Input validation — BEFORE the first round (load-bearing)

The plan/decision seed (Atlas card description, user message, or `<descreve o plano>`
block) is the prerequisite for every round. If the seed is **missing, empty, or
a literal placeholder**, no frontier can be built a frontier — there is nothing
to stress-test. Do NOT improvise a frontier by guessing what the user meant.
Do NOT open rounds against assumed intent. Do NOT even start typing a frontier
block — typing the questions IS the failure mode.

Treat these as **invalid seeds** (same handling for all):

- Empty string / whitespace only
- Literal placeholders: `<descreve o plano>`, `<descreve a decisao>`,
  `<descreve o design>`, `TODO`, `TBD`, `???`, `...`, any `<...>`-wrapped text
  that looks like a template slot
- Only the prompt template scaffolding with no actual content (e.g. just the
  world name + slug + a one-line "describe the decision" prompt)
- The user said "grill this" but pointed at an Atlas card whose description
  is the template above (this is the silent-failure case — see "Atlas
  auto-load pitfall" below)

**Required action when seed is invalid (FIRST response, no other output):**

1. STOP. Do not run a "round 1" against assumed
   intent. Do not type a Q1/Q2/Q3 frontier block.
2. One-line report naming the exact blocker: which placeholder/empty slot,
   and what valid input looks like (concrete length: "2-5 linhas").
3. Concrete next action for the user: where to paste (chat or card
   description), and what the next session will do once they do
   ("DR → grill-me → DP → DA, com notas no fim").
4. If running inside an Atlas world, create a note with tags
   `grilled, decision, blocked, needs-input` and move the card to `review`
   with `result=BLOCKER` (see `atlas-wrapper-python` skill for the run
   protocol and how to write the note). Do NOT archive the card — the user
   still needs to act on it.
5. Exit. Do not poll, do not check again later.

# When the user loads the skill themselves (out-of-band)

Sometimes the user types `grill me` or `grill this` in chat without an
Atlas card. In that case:

- If they describe the plan in the same message, proceed (real seed).
- If they do NOT, ask once: "cola o plano/decisao em 2-5 linhas aqui, ou
  aponta-me o card Atlas com description preenchida." Then stop. Same
  refusal — the chat is not different from the Atlas world, the seed rule
  is the same.

# Anti-pattern (which this skill existed to prevent)

A previous version of this skill was loaded against a card with a literal
`<descreve a decisao>` placeholder. The skill started a round and
built a frontier against **assumed** intent — i.e. the
agent invented a plan and stress-tested its own invention. That is not
grilling; that is hallucination dressed as Socratic method. The rule above
exists to refuse the round until the seed is real.

# Bulk-rename / wholesale-change scope frontier (learned 2026-09-02)

When the topic is a **wholesale rename, refactor, or rebrand** ("rename X to
Y", "rewrite all Z", "deprecate W everywhere"), the design tree has a hidden
root that the usual frontier misses: **scope**. Three sub-questions
that almost always need an early round before any design Qs:

1. **What counts as "the codebase"?** A literal `grep -r` may return 745
   hits where only 30-50 are files the user actually opens. The rest are
   snapshots, backups, worktrees, history artifacts. The answer determines
   the diff size and the risk.
2. **What's sacred vs cosmetic?** Historical artifacts (CHANGELOG.md
   entries, git log, named versions, vendor names in package metadata)
   are **append-only by social contract**. Rewriting them lies about what
   happened. User-facing strings are mutable.
3. **Frontend-only or full?** User said "no UI tudo q é kanban passa para
   michi e futuramente mudamos o codigo e backend, par ajá só o que é
   mostrado ao cliente final" — that is the **canonical** answer: rename
   what the user sees first, leave the backend alone for a later pass.
   This is the default. Re-ask only if the user wants more.

**The vault-rename trap (user's Second Brain, 2026-09-02):** when
`grep -ri '<term>'` returns hundreds of hits, the breakdown is usually
~5% active code/docs and ~95% of these categories — each non-obvious until
you see it once:

- `.wt/<branch>/` — git worktrees, one subdir per worktree. Lots of
  near-duplicate copies of the same code. Renaming them all suja git
  history, doesn't change what the user sees, and breaks future
  `git log`/bisect that wants to find "kanban v3 from 27-Aug".
- `data/.wt/`, `live-data/`, `data/.backup/` — runtime state, board
  JSON snapshots, dated `.backup/<name>-<iso>.json` files. Mutable data
  files, not source.
- `<project>/.backup/` — note/board backups with timestamps in the
  filename. Mutable in principle, but mass-rewriting timestamps to
  match the rename is just busywork.
- `knowledge/projects/<X>/plans/<date>-<topic>-{DR,DP,DA}.md` — design
  notes. Historical. Renaming the term inside them rewrites what the
  designer was thinking about at the time. Leave them.
- `CHANGELOG.md` — append-only log of what shipped. Rewriting an entry
  from "added kanban terminal control" to "added michi terminal control"
  is a lie about the past. **Never.**
- Drafts `.dp_*.md`, `.dp_<id>.md`, `_draft/` dirs — work in progress.
  Safe to leave (the user hasn't read them) but not worth touching
  because they may be overwritten tomorrow.

**Rule of thumb:** count the hits. If `grep -ri` returns > 100 and the
active codebase you actually edit is < 50 files, **stop and ask the
scope question first** ("active codebase only, or every hit including
worktrees/backups/history?"). The diff size and the answer to "should
this also rewrite CHANGELOG" both depend on the answer.

This is a scope chair, not a design chair. It usually belongs in **Round 1**
of a wholesale-change grill, before any "what does the new name mean"
questions.

# See also — for vault rename/refactor recipes

`references/vault-bulk-rename.md` — the concrete shell recipe (Python
walk via `os.walk`, exclusion sets for `.wt/`, `.backup/`, `data/`,
`live-data/`, `CHANGELOG.md`, etc.) and the verification pattern
(re-grep for stale hits, `git diff --stat` for diff size sanity check).

# Atlas invocation (async ping-pong)

When invoked from an Atlas card (workdir context), the prompt template already includes
the world's name, slug, and description. **The grilling session is an async
ping-pong between the worker and the Atlas UI. The wezterm pane is NOT the
channel.** A "wait for the user to answer" loop blocks forever in headless
context. Pattern:

1. **Read the description carefully.** If it contains a placeholder (e.g.
   `<descreve a decisao>`, `TBD`, `<descreve...>`, an empty "O que quero grillar"
   section), do NOT shotgun. Detect this and abort into a note.
2. **Write Round 1's questions to a note** via the kanban API (URL is in the prompt
   template). Tags: `grilled, decision, awaiting-user, card-<cardId>` (note: user's
   notes use **`card-` with hyphen**, not `card:` with colon — matchers must accept
   both). The note title = card title. The note body = the full Round 1 with your
   recommended answers.
3. **Move the card to `review`** and write a `result` field on the card with a one-liner
   ("Round 1 gravado como nota n<id>; à espera de resposta via reply no card").
4. **Exit cleanly** (rc=0). The user will reply via the Atlas UI.

## Reply flow (Atlas UI ↔ worker, 2026-09-01)

The Atlas UI has a `reply` button on grilled notes (`src/views/notes.ts::replyGrill`)
and a `Reply` button in the terminal modal (`src/views/kanban.ts::openReplyModal`,
`data-act="reply-from-term"`). Both open a split-layout modal: card markdown on the
left, textarea on the right.

- **In the note button:** submitting creates a **NEW** card of grilling (clones the
  source, appends the reply to description, puts it in `doing` with
  `skills: ['grill-me']`, calls `launchRun`, navigates to the new card).
  This preserves the original card's state and gives the user a clean Round 2.
- **In the terminal modal:** submitting does a **re-spawn** of the same card
  (appends reply to description, calls `runCard`). Used when the worker is alive in
  the pane and the user wants to keep that session.

The note has the tag `card-<id>` of the **source** card. The reply button reads this
tag, finds the source card, and either clones it (note button) or re-spawns it
(terminal button). When the new round is invoked, **read the previous note FIRST**
to get the context. The note title is the same as the card title; the note body has
your previous round's questions and the user's replies will be in the new card's
description under `## Reply do user (<timestamp>)`.

**Why this shape:** the user is in the Atlas UI, not the terminal. A "wait for the
user's answers" loop blocks forever in headless context. The note-based pattern
turns the grilling into an async ping-pong that survives worker death. Without it, the
skill aborts in 3 seconds and silently moves the card to review with no question ever
asked (BUG 3h in `atlas-wrapper-python`).

## Auto-detect questions in the worker log (optional, 2026-09-01)

The Atlas `viewTerminal` polls the worker's `.log` for `? **Q\d+**` regex
(the agent's format). When a new question is detected, a reply modal opens
automatically with the question hint pre-filled. Format coupling: if the agent changes
the question format, this regex must be updated. Cheap and useful; not required for
the skill to function — it's a UI nicety.

# Pitfalls

1. **Empty plan = immediate blocker (BUG 3h, 2026-09-01).** If the card description has
   no real decision (placeholder, "TBD", `<descreve...>`, or the "O que quero grillar"
   section is empty), do NOT spend a turn trying to infer. Create a note with title
   "Grilling bloqueado: <card-id> — description vazia", tags
   `grilled, decision, blocked, needs-input`, body = "Card <id> sem decisão. Worker
   abortou sem rounds. Ação: user cola plano/decision na description e clica Reply."
   Move the card to `review`. Do not invent questions.
2. **Don't shotgun.** If you can't open a clean frontier (e.g. only 1 fact available
   and 3 things depend on it), ask the 1 question that unblocks the most. Better 1 Q
   than 5 speculative ones.
3. **Recommended answer is mandatory.** Each question carries your best guess. The
   user accepts/rejects — this is the contract. Never ask "what do you think?" without
   a recommended answer.
4. **Fact-finding is your job, not the user's.** Don't ask the user to run a command
   you can run. The exception is when the fact is about user preference or context you
   cannot observe (e.g. "do you have access to X?").
5. **Recursion guard.** If the same question appears in your frontier twice (you
   already asked it, or it was already settled in a prior note), drop it. If the
   frontier is empty after dedup, write a "0 rounds" note and exit.
6. **Skill is one-shot.** Don't promise "I'll wait for your answer then ask Round 2" —
   you won't be alive when the user replies. Each invocation is ONE round. Document
   the round in a note; the next invocation reads it and continues.
