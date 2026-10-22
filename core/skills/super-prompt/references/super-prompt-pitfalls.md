# Super-prompt — common pitfalls

Movido de `SKILL.md` (## Common pitfalls); texto integral, 10 entradas.

## 1. Empty goal

1. **Empty goal.** User typed only `/super-prompt`. Write a blocker note,
   ask once, exit. Do not invent a goal.

## 2. Skipping phases "to save time"

2. **Skipping phases "to save time".** Each phase tightens the next. A
   90-second brainstorm saves a 30-min rework in DP.

## 3. Multi-choice `clarify` for already-stated facts

3. **Multi-choice `clarify` for already-stated facts.** If the user said
   "scope is the auth flow" in turn 1, do not ask "auth flow or
   payments?" in turn 4.

## 4. Incomplete sections 4 / 5 / 8

4. **Incomplete sections 4 / 5 / 8.** "Success criteria" without
   observable signals = not a success criterion. "Done-when" without a
   concrete check = not a done condition. Restart grill-me for the
   under-specified section.

## 5. Saving to the wrong path

5. **Saving to the wrong path.** The 3-tier resolution exists for a
   reason - always check current working dir first.

## 6. Auto-executing the Super Prompt in the same session

6. **Auto-executing the Super Prompt in the same session.** The point
   of the Super Prompt is to survive a session boundary. Stay out of
   DA in this skill. If the user insists, say so explicitly: "this
   skill builds prompts, not implementations - `/michi` is the
   executor."

## 7. User pivots mid-pipeline to an unrelated task

7. **User pivots mid-pipeline to an unrelated task.** Mid-pipeline
   (typically between Phase 1-3) the user may send a meta-instruction
   or switch topic entirely — e.g. "review this conversation and
   update skills", "forget the polish, do X", "actually never mind".
   The wrong move is to keep marching to Phase 4/5 to "finish" the
   Super Prompt. The right move is to abort the pipeline cleanly,
   note in one sentence that the Super Prompt was not saved (and
   why), and hand off to whatever the user actually asked for. Do NOT
   save a half-baked Super Prompt just to close the loop — the
   receiving session would be built on unvalidated scope. The user
   can re-invoke `/super-prompt` when they have a stable goal.

## 8. Multi-round grill-me when one round + defaults suffices

8. **Multi-round grill-me when one round + defaults suffices.** (2026-09-04
   lesson.) The first grill-me round should batch ALL open questions
   (scope, success, constraints, non-goals, tecto, browser, evidence) into
   one free-text ask offering "default" for any item the user wants to
   skip. After the first round, **if the user's response covers 3+ items
   with "default" / explicit picks, close grill-me** — do NOT open a
   second round to "clarify the remaining 1-2 things". Interpret
   unknowns (e.g. user says "I don't know what Lighthouse is") inline in the
   Spec appendix: pick a sensible default + one-line note "user
   unaware, executor treats as gate". One round of grill-me is the
   ceiling for well-scoped goals. A second round is only justified when
   the first response materially contradicts a section (e.g. says A then
   picks B in same turn).

   **The bake-defaults-into-question-text pattern** that makes one round
   work in practice: list every open decision in the question text with
   its recommended default prefixed ("Por defeito aplico: (1) confirms-danger
   FICAM modal; (2) 4 tabs pinadas; (3) ..."). The user replies with
   "confirmo todas" or names only the deviations. This collapses what
   would otherwise be a multi-round `clarify` into one turn because the
   cost of saying yes is zero — no per-option re-reading. Use this when
   the user is fluent, the defaults are defensible, and the question set
   is ≥4 items. Don't use it when the user is learning the domain — bake
   defaults and surface them as facts in the Spec, not as a checklist.

## 9. Saving the Super Prompt with shell-hostile content

9. **Saving the Super Prompt with shell-hostile content.** (2026-09-04/05 lesson.)
   The body of a Super Prompt routinely contains backticks (`npx lighthouse <url>`),
   `$`, `!`, unescaped quotes, or Windows paths with spaces. Three failure modes
   on Windows/MSYS, in order — all fix to the SAME recipe:

   - **`write_file` fails with `unexpected EOF while looking for matching "'`**
     even when the JSON string is valid — Hermes routes `write_file` through bash.
   - **`execute_code` + `body = """..."""` also fails** with
     `SyntaxError: unterminated triple-quoted string literal` (or f-string
     backslash trap) before the write ever runs.
   - **`A = body.append; A("...frag with `)` inside...")` ALSO fails** with
     `SyntaxError: unmatched ')'` — the kernel still parses the whole execute_code
     cell before running it, and an unbalanced `)` inside one fragment ends the
     statement early. The fragment is a string literal, but Python doesn't know
     that until it has matched the parens. Common trigger: Markdown like
     `"see step 6), \`dashboard.tsx\`.\n"` — the `, )` looks like end of args.

   **Recipe that works for ANY Super Prompt body** — build a LIST of plain string
   literals directly, then `join`. Do NOT alias `body.append` to `A(...)`; the
   `A("...")` form is the same trap, just one level deeper:
   ```python
   fragments = [
       "# Super Prompt - <slug> (<date>)\n",
       "\n## 1. Role\n",
       "You are ...\n",
       # ...etc, one literal per logical paragraph
   ]
   pathlib.Path(out).write_text("".join(fragments), encoding="utf-8")
   ```
   Two rules that make this bulletproof for any content:
   (a) **No triple-quoted strings** for content that may contain backticks,
       `<...>`, or shell metachars.
   (b) **No parenthesised calls wrapping the fragment** — bare list entries only,
       so unbalanced `)`, unmatched `"`, or stray `\\` cannot break the parser.
   The error messages point at the bash wrapper / Python parser, not at your
   content; trust the recipe, not the error.

## 10. `clarify` tool shape is fragile; failures are opaque

10. **`clarify` tool shape is fragile; failures are opaque.** (2026-09-05
    lesson.) The `clarify` tool's `questions` param must be an array of
    properly-shaped `{question, choices?, multi_select?}` objects. Three
    failure modes that cost tool calls:
    - Passing a flat array of plain strings: rejected with
      `"questions must be an array of question objects"` — looks like a
      schema mismatch but the message gives no clue about the expected shape.
    - Passing objects with a `choices` field as a single boolean/string
      instead of `string[]`: rejected with `"choices field requires array
      of plain strings"` — the same opaque error.
    - The free-text path is correct: `[{question: "..."}]` (no `choices`)
      always works. Adding `choices: null` or omitting the field entirely
      both render as a free-text question.

    **Recipe for free-text grill-me questions** (this is the one-round
    pattern from Pitfall #8):
    ```python
    clarify(questions=[{
        "question": "Atlas — modais viram tabs dragáveis. Por defeito: (1) confirms-danger ficam modal; (2) até 4 tabs pinadas; (3) layout persiste em localStorage. Confirma ou altera."
    }])
    ```
    One entry, no `choices`, the defaults are inside the question text.
    User replies in their own words (or "confirmo todas"). Don't try to
    split into multi-choice `choices` arrays — the user typing in PT-PT
    needs prose, not pickable rows, and the defaults-as-question-text
    pattern collapses multi-round clarify into one turn.

    **When multi-choice IS right:** the user has 2-3 mutually-exclusive
    options that genuinely need to be picked from a list, AND the list
    is short (≤4 items). Use `choices: ["Recommended (PT-PT ...)", ...]`
    — put the recommended option FIRST so the UI marks it
    `(Recommended)`. Don't put options inside the question text — choices
    written into the question are dead prose the user can't click.

    11. **`clarify` time-out is silent confirmation, not failure** (2026-09-05
     lesson). When `clarify` returns `{timed_out: true}` with empty
     `responses`, treat it as the user accepting every default baked into
     the question text — do NOT re-ask, do NOT open a second round. This
     is the silent path of the one-round rule from Pitfall #8: the
     user's "response" was silence, not refusal. Only re-ask if the goal
     itself was empty (Pitfall #1 — different signal: no question was
     even asked). The bake-defaults-into-question-text pattern from
     Pitfall #8 makes this safe: every default is on the record inside
     the question, so silent accept IS recorded accept.

    12. **Patching a published SP with anchor strings you've assumed, not copied.** (2026-09-05 lesson, atlas-mundo-workflow-michi.) When iterating an SP across multiple user turns, the file changes: phase numbers shift, sentences get rewritten, an early anchor like "no new dep" becomes a different phrase mid-document. **Recipe (mandatory):** before every `replace(old, new)` on a published SP, **read the exact target bytes from the file** (`read_file`, then `m.group(0)`), then use that literal in `replace`. Do NOT use a paraphrase from your memory of the file's first version. `txt.count(anchor) != 1` is the cheap pre-flight that catches this. If count==0, the assertion will fail loudly and you save 3-5 wasted cells. **Failure mode if you skip:** the `replace` silently no-ops, the SP file doesn't change, downstream assertions fail, and you re-issue the same code 3-4 times before you read the actual file. Cost observed: 10-20 min per missed anchor, 3 missed anchors per session.

    13. **DR mini must cite infra that is alive on the base branch, not infra from prior epics.** (2026-09-05 lesson, atlas-mundo-workflow-michi.) When assembling §6 Seams, do NOT list seams that reference symbols or files removed in a recent cycle — the receiving session will try to extend them and fail the typecheck. The canonical mistake: assuming `Card`, `kops`, `viewTerminal`, `w:kanban:*` routes still exist when the strip-kanban cycle (`58c30cb feat(atlas): strip kanban UI residue + chat cross-mundo workflow docs`) just removed them. **Recipe (mandatory):** for every seam name cited in §6, run `git -C <repo> ls-files --error-unmatch <name-or-path>` (or grep `src/` + `server/` for the symbol) before publishing. The base branch HEAD is the source of truth — what was true last session may not be true this one. Same applies to imports (`run-card.mjs` was deleted 2026-09-05; the previous SP still listed it as a reuse target). **Failure mode if you skip:** the executor builds an SP that won't compile in the worktree, hits typecheck rc=1, wastes an hour tracing the dead seam back to its SP source.
