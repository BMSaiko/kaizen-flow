# michi — Worktree → dev merge protocol

   **Worktree → dev merge protocol** (michi 2026-09-05, atlas cycle):
   when the worktree's commit+push is accepted and the next step is
   merging back to `dev`, never merge straight to dev and resolve there
   — dev may have moved since the worktree was cut, and conflict
   markers on dev are a 3am page. Protocol:
   1. `git -C <parent> fetch origin dev` — see what's new on dev.
   2. If origin/dev is ahead of the worktree's merge-base: `git -C <wt>
      merge origin/dev` (or local `dev` if local is current).
   3. Resolve conflicts IN THE WORKTREE — you have the full context of
      your changes + tests + gate output; on dev you'd be debugging
      against stale state from other features.
   4. Re-run the gates in the worktree (the merged state is what ships).
   5. ONLY then `git -C <parent> merge <wt-branch>` → push origin dev
      (fast-forward if possible, else `--no-ff` for the merge-commit
      audit trail).
