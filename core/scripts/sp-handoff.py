#!/usr/bin/env python3
"""Apoio ao /sp-handoff: resolve o SP em Doing, regista o progresso e lança a sessão seguinte.

O SP nunca muda de pasta nem de `status` (para isso, `sp-move.py`). Nunca faz commit.

Uso:
  python -I scripts/sp-handoff.py --resolve [slug]        # slug de um programa (SP-mãe): devolve o filho em Doing
  python -I scripts/sp-handoff.py --write <caminho> --file <progresso.md>
  python -I scripts/sp-handoff.py --launch <caminho> [--dry-run] [--auto] [--nivel simples|default|complexo|critico]
  python -I scripts/sp-handoff.py --spawn <slug>... [--max N] [--backend herdr|wezterm|tmux|background|clipboard]

`--launch` não abre janelas: em segundo plano, passados ~5 s (para o turno atual acabar), escreve
`/clear` e depois `/michi <caminho>` no painel onde o Claude Code já corre (herdr $HERDR_PANE_ID, WezTerm
$WEZTERM_PANE ou tmux $TMUX_PANE), com o prompt vazio confirmado antes. Não faz nada fora desse painel.
Num painel de uma fila (`sp-fila`: o estado do SP regista este painel), o `/michi` enviado é o prompt
da fila (`/michi --auto <slug>` com a worktree, as proibições e o `sp-estado` no fim), para a sessão
nova continuar em auto e o vigia manter o SP `a-correr` (EC-059). `--auto` (usado após o aviso do
context-guard) recusa lançar se o SP estiver em Done; em TODO lança sem o mover (o michi da sessão nova faz `sp-move doing`).
`--nivel` (escalada de modelo, harness claude): entre o `/clear` e o `/michi` envia `/model <modelo do nível>` (modelos.json).

`--spawn` abre um painel novo por SP (worktree própria via `sb-worktree ensure`, `claude`, `/michi --auto <slug>`)
e regista-o em `sessoes` do estado do `sp-fila`; a falha de um SP não afeta os outros (rc 1 se algum falhou).

Se o SP tem `parent:`, `--write` atualiza o `state` desse filho no SP-mãe (cache; a pasta manda) e
imprime o próximo filho elegível (TODO com todas as dependências em Done). Dependências por cumprir só avisam.

`--file` tem só o corpo do progresso; o título `## Progresso (sessão <data>)` é posto pelo script.
Com a mesma data a secção é substituída; com data diferente é acrescentada ao fim.
rc: 0 ok, 1 falha
"""
import argparse
import json
import subprocess
from pathlib import Path as _P
import sys as _s
_s.path.insert(0, str(_P(__file__).resolve().parent))
import sys
import time
from pathlib import Path

import kaizen_engine  # noqa: E402
import painel_backend  # noqa: E402
from handoff_pane import (ENTER_GAP, SEND_DELAY, SEND_GAP, HandoffError, _argvs, _copy, check_prompt,  # noqa: E402,F401
                          detect_backend, enter_argv, launch_detached, pane_exists, pane_id, prompt_has_text, read_screen, run_hidden,
                          send_argv, send_comandos, send_lines, tmux_enter_argv, tmux_send_argv)
from handoff_spawn import MAX_SPAWN, spawn  # noqa: E402,F401
from sp_progresso import (MAX_BODY_LINES, SP_SECTION_RE, _agent_claims, check_delta, exigir_reflect, fase_corrente,  # noqa: E402,F401
                          registar_excecao_reflect, require_doing, resolve, sync_program, sync_program_ready,
                          tem_reflect, worktree_agent, write)

sp_list = kaizen_engine.load("sp-list")

BACKENDS = ("wezterm", "tmux", "herdr", "clipboard", "background")


def sp_root_for(agent, cwd=None, run=run_hidden):
    """Raiz dos SPs: numa worktree (`agent`), a da worktree do cwd, mesmo com o script do checkout principal."""
    if agent:
        res = run(["git", "rev-parse", "--show-toplevel"], cwd=cwd or Path.cwd(), capture_output=True, text=True)
        top = res.stdout.strip() if res.returncode == 0 else ""
        if top:
            return sp_list.default_root(Path(top))
    return sp_list.DEFAULT_ROOT


HARNESSES = {
    "claude": ("/clear ", "/michi {sp}"),  # espaço final fecha o menu de sugestões
    "codex": ("/new", "Follow .agents/skills/michi/SKILL.md on {sp}"),
}


def modelo_nivel(nivel):
    """ID do modelo do nível michi (modelos.json); HandoffError se não houver modelos.py ou o nível não existir."""
    try:
        import modelos
    except ImportError:
        raise HandoffError("--nivel exige scripts/modelos.py")
    data = modelos.load(modelos.DEFAULT)
    if nivel not in (data.get("michi_modelo") or modelos.MICHI_DEFAULT):
        raise HandoffError(f"nível desconhecido '{nivel}'")
    return modelos.michi(data, nivel)[0]["model"]


def prompt_da_fila(sp_path, pane, root=None):
    """Prompt da fila se `pane` é o painel registado do SP numa fila por acabar; senão None (nunca levanta)."""
    if not pane:
        return None
    try:
        import sp_painel_estado as pe
        slug = Path(sp_path).stem
        sp = pe.ler(pe.procurar(slug, root), slug, root)
        if sp.get("estado") in pe.FINAIS or str(sp.get("pane") or "") != str(pane):
            return None
        import sp_fila_paineis
        return sp_fila_paineis.prompt_painel(slug, sp.get("worktree") or str(Path.cwd()))
    except Exception:  # noqa: BLE001 — sem fila (ou estado ilegível): handoff normal
        return None


def resume_commands(harness, sp_path, nivel=None, pane=None):
    if harness not in HARNESSES:
        raise HandoffError(f"harness desconhecido '{harness}' (válidos: {', '.join(HARNESSES)})")
    clear, resume = HARNESSES[harness]
    if nivel and harness != "claude":
        raise HandoffError("--nivel só com o harness claude")
    fila = prompt_da_fila(sp_path, pane) if harness == "claude" else None
    return [clear, *([f"/model {modelo_nivel(nivel)}"] if nivel else []), fila or resume.format(sp=sp_path)]


def _inspect(backend, limpar=False):
    """Confere o prompt vazio antes de escrever, em qualquer backend com ecrã legível (`limpar`: painel de fila, Ctrl+U se sobra texto)."""
    if backend in ("wezterm", "tmux", "herdr"):
        return lambda p: check_prompt(p, backend=backend, limpar=limpar)
    return None


def deliver_clipboard(harness, sp_path, copy=None):
    """Sem painel injetável (apps desktop): copia o comando de retoma e imprime-o. True se copiou."""
    resume = resume_commands(harness, sp_path)[-1]
    try:
        (copy or _copy)(resume)
        copied = True
    except OSError:
        copied = False
    print(f"{'copiado: ' if copied else 'colar na sessão nova: '}{resume}")
    return copied


def send(sp_path, pane, delay=SEND_DELAY, gap=SEND_GAP, enter_gap=ENTER_GAP, run=run_hidden, sleep=time.sleep,
         inspect=None, backend="wezterm", harness="claude", confirm=False, nivel=None):
    send_comandos(resume_commands(harness, sp_path, nivel, pane), pane, backend, delay, gap, enter_gap, run, sleep, inspect, confirm)


def launch(sp_path, pane=None, backend=None, harness="claude", nivel=None):
    """Lança em segundo plano o `send`, para o /clear só chegar depois de o turno atual acabar."""
    if backend is None:
        backend, found = detect_backend()
        pane = pane or found
    if backend == "clipboard":
        deliver_clipboard(harness, sp_path)
        return None
    pane = pane or pane_id(backend=backend)
    resume = resume_commands(harness, sp_path, nivel, pane)[-1]
    _argvs(backend, pane)[0](pane, resume)
    if backend == "wezterm":
        pane_exists(pane)
    return launch_detached(__file__, ["--send", str(sp_path), "--pane", str(pane), "--backend", backend, "--harness", harness,
                                      *(["--nivel", nivel] if nivel else [])])


def _parser():
    ap = argparse.ArgumentParser(description="Apoio ao /sp-handoff")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--resolve", nargs="?", const="", metavar="SLUG")
    group.add_argument("--write", metavar="CAMINHO")
    group.add_argument("--launch", metavar="CAMINHO")
    group.add_argument("--send", metavar="CAMINHO", help=argparse.SUPPRESS)
    group.add_argument("--spawn", nargs="+", metavar="SLUG", help="painel novo + worktree por SP, a correr /michi --auto")
    ap.add_argument("--sem-registo", action="store_true", help="com --spawn: não escreve no estado (quem chama, o sp-fila, já o faz)")
    ap.add_argument("--json", action="store_true", help="com --spawn: imprime o resultado como JSON (uma lista de {slug, ok, painel, worktree}) para o sp-fila")
    ap.add_argument("--max", type=int, default=MAX_SPAWN, help=f"com --spawn: painéis em simultâneo (default {MAX_SPAWN})")
    ap.add_argument("--file", help="ficheiro com o corpo do progresso (com --write)")
    ap.add_argument("--pane", help="painel do multiplexer (default: $HERDR_PANE_ID, $WEZTERM_PANE ou $TMUX_PANE)")
    ap.add_argument("--backend", choices=BACKENDS, help="default: deteção automática; sem painel, clipboard")
    ap.add_argument("--harness", choices=tuple(HARNESSES), default="claude", help="comando de retoma (default: claude)")
    ap.add_argument("--dry-run", action="store_true", help="com --launch ou --spawn: só mostra, sem efeitos")
    ap.add_argument("--auto", action="store_true", help="com --launch: modo do context-guard, exige SP em TODO ou Doing")
    ap.add_argument("--nivel", help="com --launch: escalada de modelo, `/model` do nível (simples|default|complexo|critico) antes do /michi")
    ap.add_argument("--fase", help="com --write/--launch: fase michi corrente (default: última linha `Fase:` do progresso)")
    ap.add_argument("--sem-reflect", action="store_true", help="só o user: avança sem `Reflect <fase>` e regista a exceção em ## Progresso")
    ap.add_argument("--root", help=argparse.SUPPRESS)
    return ap


def _cmd_write(args, excecao):
    if not args.file:
        raise HandoffError("--write exige --file")
    write(args.write, Path(args.file).read_text(encoding="utf-8"))
    if excecao:
        registar_excecao_reflect(args.write)
    print(f"progresso registado em {args.write}")
    nxt = sync_program(args.root, args.write)
    if nxt:
        print(nxt)


def _cmd_spawn(args):
    nome = args.backend
    if nome is None:  # sem --backend: `painelBackend` da config manda; sem backend utilizável, a deteção antiga
        kc = kaizen_engine.load("kaizen_config")
        esc = painel_backend.escolher(kc.painel_backend(Path.cwd()), herdr=kc.herdr(Path.cwd()))
        nome = esc.nome if esc else None
    resultados = spawn(args.spawn, nome, args.max, registar=not args.sem_registo, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(resultados, ensure_ascii=False))
        return 1 if any(not r["ok"] for r in resultados) else 0
    falhou = False
    for r in resultados:
        if r.get("dry_run"):
            print(f"{r['slug']}: dry-run (sem worktree nem painel) · {r['cmd']}  →  /michi --auto {r['slug']}")
            continue
        print(f"{r['slug']}: " + (f"painel {r['painel'] or '-'} em {r['worktree']}" if r["ok"] else f"FALHOU ({r['erro']})"))
        falhou = falhou or not r["ok"]
    return 1 if falhou else 0


def _cmd_dry_run(args):
    backend, found = (args.backend, None) if args.backend else detect_backend()
    pane = args.pane or found
    if backend == "clipboard":
        print(f"clipboard: {resume_commands(args.harness, args.launch, args.nivel)[-1]}")
        return
    pane = pane or pane_id(backend=backend)
    text_argv, key_argv = _argvs(backend, pane)
    for text in resume_commands(args.harness, args.launch, args.nivel, pane):
        print(subprocess.list2cmdline(text_argv(pane, text)))
        print(subprocess.list2cmdline(key_argv(pane)))


def _cmd_launch(args):
    argv_send = launch(args.launch, args.pane, args.backend, args.harness, args.nivel)
    if argv_send:
        pane = argv_send[argv_send.index("--pane") + 1]
        print(f"a continuar neste painel em {SEND_DELAY:.0f}s: {' e '.join(resume_commands(args.harness, args.launch, args.nivel, pane))}")


def _verificar_reflect(args):
    """Exige o Reflect da fase; com --sem-reflect regista a exceção. Devolve True se houve exceção."""
    alvo = args.write or args.launch
    if not alvo:
        return False
    extra = Path(args.file).read_text(encoding="utf-8") if args.write and args.file else ""
    try:
        exigir_reflect(alvo, args.fase, extra)
    except HandoffError:
        if not args.sem_reflect:
            raise
        excecao = not args.dry_run
        if excecao and args.launch:
            registar_excecao_reflect(alvo)
        return excecao
    return False


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        args.root = args.root or str(sp_root_for(worktree_agent()))
        if args.auto:
            if not args.launch:
                raise HandoffError("--auto só com --launch")
            require_doing(args.launch)
        excecao = _verificar_reflect(args)
        if args.resolve is not None:
            agent = worktree_agent()
            print(resolve(args.root, args.resolve or None, _agent_claims(agent), agent))
        elif args.write:
            _cmd_write(args, excecao)
        elif args.spawn:
            return _cmd_spawn(args)
        elif args.send:
            backend = args.backend or "wezterm"
            send(args.send, args.pane or pane_id(backend=backend), backend=backend, harness=args.harness,
                 inspect=_inspect(backend, limpar=prompt_da_fila(args.send, args.pane) is not None), confirm=True, nivel=args.nivel)
        elif args.dry_run:
            _cmd_dry_run(args)
        else:
            _cmd_launch(args)
    except (HandoffError, OSError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-handoff", main))
