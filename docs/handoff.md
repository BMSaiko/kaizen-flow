# Handoff

`sp-handoff.py` moves a story to a fresh context without losing the thread. `kaizen init` installs the script and the `/sp-handoff` command (or prompt) for each harness.

```sh
python scripts/sp-handoff.py --resolve [SLUG]            # find the story in Doing
python scripts/sp-handoff.py --write PATH [--file BODY]  # log progress in the story
python scripts/sp-handoff.py --launch PATH               # clear context and resume
```

Extra options: `--harness claude|codex`, `--backend wezterm|tmux|clipboard`, `--pane ID`, `--dry-run` (print the commands, execute nothing), `--auto` (no questions; needs a story in Doing).

## Backends

The handoff reuses the terminal where the agent already runs and opens no new window.

| Where you run | Backend | What happens |
|---|---|---|
| CLI in WezTerm (`$WEZTERM_PANE`) | `wezterm` | clear-context and resume command injected into the pane |
| CLI in tmux (`$TMUX_PANE`) | `tmux` | same, via `tmux send-keys` |
| Desktop app, or no multiplexer | `clipboard` | the resume command is copied to the clipboard and printed |

Resume command per harness: `/clear` then `/michi <story path>` in Claude Code; the Codex equivalent (`/new`, assumed; verify on your version) then a text instruction to run michi on the story.

`kaizen doctor` prints the detected mode: `handoff: cli (wezterm|tmux)` or `handoff: app (clipboard)`.

## CLI vs desktop app

| | CLI | Desktop app |
|---|---|---|
| Install | `kaizen init` writes project files | same files; the apps read the project (`.claude/`, `AGENTS.md`, Codex config) |
| Handoff | injected into the current WezTerm/tmux pane | resume command copied to the clipboard and printed |
| `kaizen doctor` | `handoff: cli (wezterm\|tmux)` | `handoff: app (clipboard)` |
