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

- **`five-whys`** — In Phase 1 (Grill) or Phase 2 (DR), before committing
to a problem definition. If the symptom is unclear, run Five Whys to find
the root cause before the grill even starts.
- **`swot`** — In Phase 1 (Grill), to map the current
situation when the project involves a system, process, or capability
that needs improvement.
- **`ooda-loop`** — During any phase when the environment is changing
faster than the plan can hold. The OODA loop keeps you aligned with
reality — use it alongside michi when the situation is volatile.
- **`eisenhower-matrix`** — After Phase 6 (Report) and before commit,
to prioritize the actions from Reflect into a concrete execution order.
  Or during Phase 3 (DP) to scope the phase breakdown.

These are optional enhancements — michi works without them, but they
sharpen the output when the situation warrants it.

---
