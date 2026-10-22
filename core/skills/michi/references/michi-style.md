# michi — Style (casos e regras de estilo)

Movido de `SKILL.md` (## Style); texto integral, 16 entradas.

## 1. DEFAULT to a free-text question, not multi-choice `clarify`

- **DEFAULT to a free-text question, not multi-choice `clarify`.** A 4-option
  list is overhead when the next phase is mechanical (advance to DR, advance
  to DP). One free-text "go for X, or adjust?" replaces 3 multi-choice rounds.
  multi-choice is reserved for genuine forks where each option is a
  meaningfully different shape — and even then, add "Other" so the user can
  answer freely. **Pitfall in practice (Atlas michi cycle, 2026-09-03):**
  during grill I fired 3 sequential `clarify` rounds (wrapper symptom shape,
  workflow chip shape, column transitions) — 9 options total when each round
  was a real fork but the user could have answered all 3 in a single free-text
  message ("1+2+3, ambos, flow X"). Cost: 3 turns of latency for what was one
  decision block. Rule of thumb: if the next 2-3 questions are all in the
  same domain (grill-me shape, workflow shape, etc.), batch them in one
  free-text question with bullet list, NOT a chain of `clarify` calls.
  - **User responds with item-list ("1+2+3, quero …") — that IS the answer, not a request to clarify more (Atlas wrapper cycle, 2026-09-03).** When the user compresses 3 of your previous questions into "1+2+3" + a free-form
    directive, **stop clarifying**. The list IS the alignment. Honour each
    item implicitly as accepted, then proceed to DP. Re-asking the items as
    multi-choice clarify = re-asking facts the user already gave you (Style
    rule above). The first response after "1+2+3, quero X" should be DR
    evidence + DP draft, NOT another clarify round.

## 2. One user-visible turn per phase transition: short summary of what was

- One user-visible turn per phase transition: short summary of what was
  decided, what the next phase will do, ask for go/no-go.

## 3. Do not re-ask facts the user already stated

- **Do not re-ask facts the user already stated.** If they said
  "branch dev" in turn 1, do not put "master vs dev" in a clarify at
  turn 5. Confirmation of a stated fact is not a question; it is
  acknowledgement, then act.

## 4. `clarify` answers change the running code/skills in the same turn, not later

- **`clarify` answers change the running code/skills in the same turn, not later.**
  If you used `clarify` to settle a default — "where should this go?",
  "what slug?", "which branch?" — the answer updates the artefact NOW, in
  the same response that processes the result. Not in a follow-up patch.
  Not in the report. Not "for the next session". The user picks once, the
  default follows. (`requirements-pdf-interpreter` shipped with `~/.hermes/...`
  as default despite the user picking `<SB>/knowledge/projects/<slug>/` in
  the same `clarify` — had to be corrected in a later turn. Don't repeat.)

## 5. Um «go» responde ao que a pergunta nomeou (atlas-inbox-e-painel-sps, 2026-10-18)

- Never auto-commit, never auto-push. The michi skill is opinionated about
  *flow*; the user owns git operations.
  - **Um «go» responde ao que a pergunta nomeou (atlas-inbox-e-painel-sps, 2026-10-18).** Se o pedido de ok já lista as ações (commit, push, PR), um único «go» aprova todas; não voltar a pedir ok por ação. Se a lista for vaga («avanço?»), nomear cada ação na pergunta. Continua a valer: merge e ações destrutivas pedem ok próprio.
  - **A pergunta de ok de cada fase nomeia as ações (atlas-calendario-e-pomodoro, 2026-10-18).** «Segues com a 7?» não autoriza escrever nem commitar: dizer «escrevo, commito e passo à fase seguinte?». Um commit feito sobre um «go» que a pergunta não associou a commit é um deslize, mesmo com o plano aprovado. Antes de tentar o commit, confirmar que o assunto tem ≤72 caracteres (o hook do repo recusa).
  - **Factos herdados do SP verificam-se à hora do DP (atlas-calendario-e-pomodoro, 2026-10-18).** Número da próxima decisão e frases do tipo «validado em X» resolvem-se com `Grep` em `DECISIONS.md` e no código; o SP dizia «decisão 24» (era 26) e «validado em `write_board`» (quem rejeitava era o serde). Alinha com o ponto «SP vs repo state may still fork».
  - **Script de runtime que envia teclas: conferir cada atalho em `shortcuts.ts` antes de o escrever (atlas-calendario-e-pomodoro, 2026-10-18).** Copiar de outro script não chega: `^1` escolhe o mundo, a vista Todo é `Alt+3`. Um screenshot da primeira falha mostra logo a vista errada; vê-lo antes de reescrever o teste.

## 6. Never auto-patch skills, never auto-create skills. Reflect proposes; the

- Never auto-patch skills, never auto-create skills. Reflect proposes; the
  user approves. Self-edit is a proposal, not an execution.

## 7. "fix it" + destructive fix = clarify, never guess (hermes-agent 2026-09-04, michi cycle)

- **"fix it" + destructive fix = clarify, never guess (hermes-agent 2026-09-04, michi cycle).** When the user says "fix it" without context and the obvious fix is destructive (kill 6 user processes, drop a table, force-push), do NOT act on the verb alone. "fix it" is granting execution autonomy for the *non-destructive* path. The destructive path needs an explicit "yes, kill them" with the cost visible. **Recipe:** (1) list the 6 PIDs, (2) name the cost ("you'll lose 6 sessions of work in progress"), (3) propose a narrower default (kill 1 + retry; or wait for the user to close them and re-run), (4) ask. **Anti-pattern:** "fix it" → broad-kill → user loses 6 hours of unrelated work. The user asked for a fix, not for you to gamble their session state. **Companion rule:** if a destructive fix has ≥ 2 outcomes (e.g. "kill the holder" vs "wait for clean state") and the user is on the box, list the PIDs, list the cost, ask. The michi flow already says "ask before destructive ops" — this just makes the trigger phrase explicit so the agent doesn't pattern-match "fix it" as a green light.

## 8. If the user says "skip phase X" or "go to DA", honour it. The phases are

- If the user says "skip phase X" or "go to DA", honour it. The phases are
  a default ordering, not a cage. `/michi skip reflect` skips Reflect and
  goes straight to commit-suggest.

## 9. Skill-fit check before loading (atlas main-chat michi, 2026-09-04)

- **Skill-fit check before loading (atlas main-chat michi, 2026-09-04).**
  When a user asks for "design, frontend, taste, UX/UI" coverage, the
  reflex is to load `ui-styling` + `ui-ux-pro-max` + `design-system` + ...
  Don't load blindly. Stack-fit first: `ui-styling` is **shadcn/Tailwind/React**
  — useless in a vanilla-TS Vite project (Atlas, etc.). The right move is
  `ui-ux-pro-max` (the rules are stack-agnostic: contrast, focus, touch
  targets, line length, motion) + `design-system` (token architecture, even
  if not exported as Tailwind) **but** scoped to the project's existing
  primitives (Atlas has `tokens.css` with 3-layer night/day/dusk + 4
  seasons; re-use, do not re-invent). Rule: before `skill_view(name)`, ask
  "does this skill's primary technology match the project?" If not, skip
  and document the skip in the DP — the user values explicit non-loads
  over cargo-culted ones.

## 10. Scope

- **DP must absorb user preferences as design decisions, not as open
  questions (atlas main-chat michi, 2026-09-04).** When the user says
  "no chat vou sempre referir o mundo" mid-DP, the response is NOT
  "OK, want me to ask per-message?" — it's "removed. DP updated:
  agent has no slug default, prompts user 'Em que mundo?' when no slug
  is detected, and the UI removes any default-action inference." The
  user's plain statement IS the design decision; embed it, don't queue
  it for a later round. Same pattern for "should the chat remember
  history?" → decide (200 cap FIFO), don't ask. **Scope:** the rule is
  for *plain* preferences. Genuine forks (which shape? what stack? where
  does it live?) still go through free-text batch.

## 11. **Test tautology skip is a valid TDD decision, document it (atlas main-chat

- **Test tautology skip is a valid TDD decision, document it (atlas main-chat
  michi, 2026-09-04).** If the new code is byte-by-byte copy-modify of an
  existing handler (only paths/IDs differ), the existing test for the
  *class* already covers the new instance. Writing a parallel test
  (e.g. `chat-output.test.mjs` mirroring `output-stream.test.mjs`) is
  tautology — both tests would catch the same bug class, and a future
  refactor that breaks the new one breaks the old one too. **Skip the
  parallel test** and call it out in the report: "skipped <name>.test.mjs
  — clone of <existing>.test.mjs, same logic, different paths." Don't
  ship redundant coverage. The bar for a new test is "fails for a reason
  the existing test would NOT catch."

## 12. **Default to "run the gate" over "probe the dependency" (atlas polish-A

- **Default to "run the gate" over "probe the dependency" (atlas polish-A
  michi, 2026-09-04).** When a gate depends on a running service (preview
  server, DB, daemon), the question "is X up?" is best answered by running
  the gate itself and letting it report connection state — NOT by a separate
  curl/fetch/probe call. Three reasons: (1) the gate tool is going to run
  anyway, so the probe is duplicate work; (2) the probe's success does not
  prove the gate will succeed (port open ≠ endpoint responsive); (3) the
  user has explicitly blocked diagnostic probes (`curl http://...`, `node -e
  fetch(...)`) in this profile. The only case where a separate probe wins is
  when the gate's failure mode is opaque and you genuinely need early signal
  — and even then, probe via the same transport the gate will use (e.g.
  `lighthouse http://...` twice is fine; a `curl` probe followed by a
  `lighthouse` is wasteful).

## 13. If the workflow reveals the plan is wrong mid-DA, restart at the relevant

- If the workflow reveals the plan is wrong mid-DA, restart at the relevant
  earlier phase. Do not silently backtrack.

## 14. Keep responses short. Code and outputs first, prose only where asked

- Keep responses short. Code and outputs first, prose only where asked.

## 15. DP supersession by rename, not overwrite (michi 2026-09-04, atlas polish-A recovery cycle)

- **DP supersession by rename, not overwrite (michi 2026-09-04, atlas polish-A recovery cycle).** When a DP evolves because on-disk state changed between the original sign-off and the new attempt (e.g. the previous session shipped A1+A3+A4 but never committed; the v2 DP is a recovery plan), the previous DP is audit-relevant — it documents what was designed and why the current state is what it is. **Recipe:** `git mv plans/<slug>-DP plans/<slug>-DP-v1` (or in untracked state, just `Path.rename`) BEFORE writing v2 at the canonical `plans/<slug>-DP/DP.md` path. Add a `supersedes: plans/<slug>-DP-v1/DP.md` line in v2's frontmatter so the lineage is grep-able. Anti-pattern: overwriting v1's DP.md with v2 — loses the audit trail. Anti-pattern: writing v2 to a parallel `<slug>-DP-v2/` directory — splits context, makes "where is the live plan" ambiguous. The rename-to-`-v1` pattern keeps the canonical path stable (every agent looks for `<slug>-DP/DP.md`) while preserving the lineage.

## 16. User did not answer the free-text ask within the window → ponytail defaults applied (michi 2026-09-04)

- **User did not answer the free-text ask within the window → ponytail defaults applied (michi 2026-09-04).** When the michi flow asks a free-text question (`clarify` with no choices) and the user does not respond, the ponytail rule "ship the lazy version, question in the same response" applies, BUT the gate is: every default you apply MUST be the most conservative one that preserves the SP contract. Three concrete defaults used in the atlas polish-A cycle: (1) worktree state = **recover+finish** (don't wipe the previous session's uncommitted work — re-doing it is wasted time and a $30min mistake); (2) a leftover `stash@{0}` on `dev` from a prior session = **leave stashed, never touch** (preserves the user's option to deal with it separately; popping it into the new epic would conflate scopes and likely break the SP's hard-invariants like `server/**` byte-identical); (3) a previous gate run that failed a bar (e.g. Lighthouse perf 91 vs SP ≥95) = **re-run once and trust the new number** (cheap, may have been a preview-server artifact). **Document every applied default in the DP's "What you should know before signing off" section** so the user can override on review. Never silently assume — surface the default, name the conservative choice, link the rule it falls back to.
