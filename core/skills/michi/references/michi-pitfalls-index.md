# michi — índice de pitfalls

## Pitfalls

Texto integral em `references/michi-pitfalls.md` (28 entradas, numeradas como abaixo). Ler só a entrada relevante.

1. Treating `/michi` as a single-shot: the user may want to pause at any
2. Re-asking the user a fact they already gave you
3. `/michi skip grill` + vague large-scope instruction
4. Interruption mid-DA leaves the on-disk state 80% done, 0% committed (michi 2026-09-04, atlas polish-A recovery
5. Banner-sectioned single-file split > N-file split when class-name families overlap heavily
6. `/michi` + "no questions, do all phases" is a bounded auto-pilot, not infinite licence (michi 2026-09-04, atla
7. "Bug report" ≠ "the thing to fix". Ask for the actual error string before DR/DA (Atlas michi cycle, 2026-09-03
8. When michi is loaded but the cycle is hijacked mid-stream by an ops request, Reflect still owes the user a fri
9. Reflect is a stop point, not a segue (atlas backend refactor, 2026-09-02)
10. Per-phase commit cadence in a multi-phase DA is a real workflow (atlas backend refactor, 2026-09-02)
11. Refactor clusters: commit EACH new file before moving to the next, not at end-of-DA (atlas wrapper-replacement
14. Post-child work (cleanup, merge, push) must be detached from the orchestrator's event loop (atlas wrapper-repl
15. "Faz um ajuste" to a signed-off plan means: respect the why, not just the what (atlas backend refactor, 2026-0
16. Post-DA correction list is a phase, not a restart (atlas main-chat michi, 2026-09-04)
17. Numbered-correction list is a contract, parse it as one (atlas main-chat michi, 2026-09-04)
20. Pre-DA state gate: snapshot `git status` + `git branch --show-current` + `git log -1` before any edit (hermes-
21. `git checkout <other-branch>` aborts on uncommitted changes
22. Junctions/symlinks do NOT auto-propagate from parent to worktree (atlas strip-kanban cycle, 2026-09-05)
23. Fast-forward merge when the WT is 1 commit ahead of dev and parent is clean (atlas strip-kanban cycle, 2026-09
25. Worktree → dev: pull first, merge INTO the worktree, resolve there, THEN merge to dev
26. Fecho com push + merge: fast-forward quando `origin/<ramo>` == base (portfolio-docs-audit, 2026-10-17)
27. Python em modo texto no Windows: CRLF e `\n` escapado (dev-workflow-escalar-programas, 2026-10-18)
28. "Duplicada" num SP de inventário: ler o corpo antes de remover (dev-workflow-refactorizar-inventario, 2026-10-18)
