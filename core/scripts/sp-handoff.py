#!/usr/bin/env python3
"""Apoio ao /sp-handoff: resolve o SP em Doing, regista o progresso e lança a sessão seguinte.

O SP nunca muda de pasta nem de `status` (para isso, `sp-move.py`). Nunca faz commit.

Uso:
  python -I scripts/sp-handoff.py --resolve [slug]        # slug de um programa (SP-mãe): devolve o filho em Doing
  python -I scripts/sp-handoff.py --write <caminho> --file <progresso.md>
  python -I scripts/sp-handoff.py --launch <caminho> [--dry-run] [--auto]
  python -I scripts/sp-handoff.py --spawn <slug>... [--max N] [--backend wezterm|tmux|clipboard]

`--launch` não abre janelas: em segundo plano, passados ~5 s (para o turno atual acabar), escreve
`/clear` e depois `/michi <caminho>` no painel do WezTerm onde o Claude Code já corre ($WEZTERM_PANE),
via `wezterm cli send-text`. Não faz nada fora desse painel. `--auto` (usado após o aviso do
context-guard) recusa lançar se o SP não estiver em Doing.

`--spawn` abre um painel novo por SP (worktree própria via `sb-worktree ensure`, `claude`, `/michi --auto <slug>`)
e regista-o em `sessoes` do estado do `sp-fila`; a falha de um SP não afeta os outros (rc 1 se algum falhou).

Se o SP tem `parent:`, `--write` atualiza o `state` desse filho no SP-mãe (cache; a pasta manda) e
imprime o próximo filho elegível (TODO com todas as dependências em Done). Dependências por cumprir só avisam.

`--file` tem só o corpo do progresso; o título `## Progresso (sessão <data>)` é posto pelo script.
Com a mesma data a secção é substituída; com data diferente é acrescentada ao fim.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402
from handoff_pane import (ENTER_GAP, NO_WINDOW, SEND_DELAY, SEND_GAP, HandoffError, _argvs, _copy, check_prompt,  # noqa: E402,F401
                          detect_backend, enter_argv, launch_detached, pane_exists, pane_id, prompt_has_text, run_hidden,
                          send_argv, send_lines, tmux_enter_argv, tmux_send_argv)
from handoff_spawn import MAX_SPAWN, spawn  # noqa: E402,F401
from sp_progresso import (MAX_BODY_LINES, SP_SECTION_RE, _agent_claims, check_delta, require_doing, resolve,  # noqa: E402,F401
                          sync_program, sync_program_ready, write)

sp_list = kaizen_engine.load("sp-list")

BACKENDS = ("wezterm", "tmux", "clipboard")
HARNESSES = {
    "claude": ("/clear ", "/michi {sp}"),  # espaço final fecha o menu de sugestões
    "codex": ("/new", "Follow .agents/skills/michi/SKILL.md on {sp}"),
}
BACKENDS = ("wezterm", "tmux", "clipboard")


def resume_commands(harness, sp_path):
    if harness not in HARNESSES:
        raise HandoffError(f"harness desconhecido '{harness}' (válidos: {', '.join(HARNESSES)})")
    clear, resume = HARNESSES[harness]
    return [clear, resume.format(sp=sp_path)]


def deliver_clipboard(harness, sp_path, copy=None):
    """Sem painel injetável (apps desktop): copia o comando de retoma e imprime-o. True se copiou."""
    resume = resume_commands(harness, sp_path)[1]
    try:
        (copy or _copy)(resume)
        copied = True
    except OSError:
        copied = False
    print(f"{'copiado: ' if copied else 'colar na sessão nova: '}{resume}")
    return copied


def send(sp_path, pane, delay=SEND_DELAY, gap=SEND_GAP, enter_gap=ENTER_GAP, run=run_hidden, sleep=time.sleep,
         inspect=None, backend="wezterm", harness="claude"):
    text_argv, key_argv = _argvs(backend, pane)
    send_lines(resume_commands(harness, sp_path), pane, text_argv, key_argv, delay, gap, enter_gap, run, sleep, inspect)


def launch(sp_path, pane=None, backend=None, harness="claude"):
    """Lança em segundo plano o `send`, para o /clear só chegar depois de o turno atual acabar."""
    resume = resume_commands(harness, sp_path)[1]
    if backend is None:
        backend, found = detect_backend()
        pane = pane or found
    if backend == "clipboard":
        deliver_clipboard(harness, sp_path)
        return None
    pane = pane or pane_id()
    _argvs(backend, pane)[0](pane, resume)
    if backend == "wezterm":
        pane_exists(pane)
    return launch_detached(__file__, ["--send", str(sp_path), "--pane", str(pane), "--backend", backend, "--harness", harness])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Apoio ao /sp-handoff")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--resolve", nargs="?", const="", metavar="SLUG")
    group.add_argument("--write", metavar="CAMINHO")
    group.add_argument("--launch", metavar="CAMINHO")
    group.add_argument("--send", metavar="CAMINHO", help=argparse.SUPPRESS)
    group.add_argument("--spawn", nargs="+", metavar="SLUG", help="painel novo + worktree por SP, a correr /michi --auto")
    ap.add_argument("--sem-registo", action="store_true", help="com --spawn: não escreve no estado (quem chama, o sp-fila, já o faz)")
    ap.add_argument("--max", type=int, default=MAX_SPAWN, help=f"com --spawn: painéis em simultâneo (default {MAX_SPAWN})")
    ap.add_argument("--file", help="ficheiro com o corpo do progresso (com --write)")
    ap.add_argument("--pane", help="painel do multiplexer (default: $WEZTERM_PANE ou $TMUX_PANE)")
    ap.add_argument("--backend", choices=BACKENDS, help="default: deteção automática; sem painel, clipboard")
    ap.add_argument("--harness", choices=tuple(HARNESSES), default="claude", help="comando de retoma (default: claude)")
    ap.add_argument("--dry-run", action="store_true", help="com --launch ou --spawn: só mostra, sem efeitos")
    ap.add_argument("--auto", action="store_true", help="com --launch: modo do context-guard, exige SP em Doing")
    ap.add_argument("--root", default=str(sp_list.DEFAULT_ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        if args.auto:
            if not args.launch:
                raise HandoffError("--auto só com --launch")
            require_doing(args.launch)
        if args.resolve is not None:
            print(resolve(args.root, args.resolve or None, _agent_claims()))
        elif args.write:
            if not args.file:
                raise HandoffError("--write exige --file")
            write(args.write, Path(args.file).read_text(encoding="utf-8"))
            print(f"progresso registado em {args.write}")
            nxt = sync_program(args.root, args.write)
            if nxt:
                print(nxt)
        elif args.spawn:
            falhou = False
            for r in spawn(args.spawn, args.backend, args.max, registar=not args.sem_registo, dry_run=args.dry_run):
                if r.get("dry_run"):
                    print(f"{r['slug']}: dry-run (sem worktree nem painel)")
                    continue
                print(f"{r['slug']}: " + (f"painel {r['painel'] or '-'} em {r['worktree']}" if r["ok"] else f"FALHOU ({r['erro']})"))
                falhou = falhou or not r["ok"]
            return 1 if falhou else 0
        elif args.send:
            backend = args.backend or "wezterm"
            send(args.send, args.pane or pane_id(), backend=backend, harness=args.harness,
                 inspect=check_prompt if backend == "wezterm" else None)
        elif args.dry_run:
            backend, found = (args.backend, None) if args.backend else detect_backend()
            pane = args.pane or found
            if backend == "clipboard":
                print(f"clipboard: {resume_commands(args.harness, args.launch)[1]}")
            else:
                pane = pane or pane_id()
                text_argv, key_argv = _argvs(backend, pane)
                for text in resume_commands(args.harness, args.launch):
                    print(subprocess.list2cmdline(text_argv(pane, text)))
                    print(subprocess.list2cmdline(key_argv(pane)))
        else:
            if launch(args.launch, args.pane, args.backend, args.harness):
                print(f"a continuar neste painel em {SEND_DELAY:.0f}s: {' e '.join(resume_commands(args.harness, args.launch))}")
    except (HandoffError, OSError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
