# michi — Help e skills suplementares

## michi — full project workflow

## Help

If the user instruction is exactly `help`, `--help`, `-h`, or `?`, **stop
here and reply with the Usage block below — do NOT start the workflow.**

```
/michi                                # full workflow (dr → grill → dp → da → gates → report → reflect → commit) — DR before grill: informed questions
/michi <idea>                         # jump in: DR runs first, then grill is informed by repo context
/michi <idea>                         # jump in with a project idea (grill picks up)
/michi <SP>                           # `modo: auto|manual` no SP decide sem pergunta; sem o campo nem --auto, pergunta «com/sem auto» no arranque
/michi --auto <SP>                    # modo auto (sem pergunta): sem perguntas, tudo em references/michi-modo-auto.md
/michi help | --help | -h | ?         # this help
/michi skip grill                     # honour "skip phase X" requests
/michi skip reflect                   # honour "no time for reflection this cycle"
/michi skip harden                    # salta o gate /harden (segurança/robustez/guardas)
/michi go to DA                       # jump to implementation with the current plan
```

Phases: **dr → grill → dp → da → gates → report → reflect → commit-suggest** (DR before grill: read the repo first so grill questions are informed, not generic).
Each phase is a stop point — the user can `/stop` after any step
and resume with another `/michi …`. See `## Quick reference` below.

### Supplemental analysis skills

The following skills complement the michi flow and can be invoked at
specific phases:

- **`swot`** — In Phase 1 (Grill), to map the current
situation when the project involves a system, process, or capability
that needs improvement.

These are optional enhancements — michi works without them, but they
sharpen the output when the situation warrants it.

---
