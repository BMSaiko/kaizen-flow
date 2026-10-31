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
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402

sp_list = kaizen_engine.load("sp-list")

SEND_DELAY = 5.0
SEND_GAP = 2.0
ENTER_GAP = 0.5
UPDATED_RE = re.compile(r"^updated:.*$")
MAX_BODY_LINES = 25
SP_SECTION_RE = re.compile(r"^#{1,6}\s*(?:\d+\.\s*)?(role|context|objective|success criteria|constraints|seams|steps|done-when)", re.I)


class HandoffError(Exception):
    pass


def _agent_claims():
    """Slugs reclamados pelo agente deste worktree; None fora de worktrees (comportamento original)."""
    if not Path(__file__).with_name("sb-agent.py").is_file():
        return None
    mod = kaizen_engine.load("sb-agent")
    try:
        agent = mod.current_agent(Path.cwd())
        return set(mod.claims_of(Path.cwd(), agent)) if agent else None
    except mod.SbAgentError:
        return None


def resolve(root, slug=None, mine=None):
    sps = sp_list.collect(root, include_done=True)
    if slug:
        kids = [sp for sp in sps if sp.parent == slug]
        if kids and not any(sp.slug == slug and sp.status == "Doing" for sp in sps):
            doing = [sp for sp in kids if sp.status == "Doing"]
            if not doing:
                raise HandoffError(f"programa '{slug}': nenhum filho em Doing")
            if len(doing) > 1:
                raise HandoffError("vários filhos em Doing, indicar o slug:\n" + "\n".join(f"  {sp.slug}" for sp in doing))
            return doing[0].path.resolve()
        matches = [sp for sp in sps if sp.slug == slug]
        if not matches:
            raise HandoffError(f"SP '{slug}' não encontrado")
        doing = [sp for sp in matches if sp.status == "Doing"]
        if not doing:
            raise HandoffError(f"SP '{slug}' não está em Doing (está em {matches[0].status})")
        if len(doing) > 1:
            raise HandoffError("slug em vários projetos: " + ", ".join(f"{sp.slug} ({sp.project})" for sp in doing))
        return doing[0].path.resolve()
    doing = [sp for sp in sps if sp.status == "Doing" and (mine is None or sp.slug in mine)]
    if not doing:
        raise HandoffError("nenhum SP em Doing" + (" reclamado por este agente" if mine is not None else ""))
    if len(doing) > 1:
        opts = "\n".join(f"  {sp.slug} ({sp.project})" for sp in doing)
        raise HandoffError(f"vários SPs em Doing, indicar o slug:\n{opts}")
    return doing[0].path.resolve()


def check_delta(body):
    """O handoff só leva o delta: ≤MAX_BODY_LINES linhas e sem repetir secções 1-8 do SP."""
    lines = body.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) > MAX_BODY_LINES:
        raise HandoffError(f"handoff com {len(lines)} linhas (máx {MAX_BODY_LINES}): só o delta (próximo passo, ficheiros, decisões novas)")
    dup = next((l for l in lines if SP_SECTION_RE.match(l)), None)
    if dup:
        raise HandoffError(f"handoff repete uma secção do SP ({dup.strip()!r}): apontar para o SP em vez de copiar")


def write(path, progress, today=None):
    check_delta(progress)
    path = Path(path)
    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise HandoffError("SP sem frontmatter")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise HandoffError("frontmatter sem fecho")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for i in range(1, end):
        if UPDATED_RE.match(lines[i]):
            lines[i] = f"updated: {stamp}{eol}"
            break
    else:
        raise HandoffError("frontmatter sem updated")

    heading = f"## Progresso (sessão {today or date.today().isoformat()})"
    body = progress.replace("\r\n", "\n").strip("\n").replace("\n", eol)
    section = [f"{heading}{eol}", eol, f"{body}{eol}"]

    start = next((i for i in range(end + 1, len(lines)) if lines[i].rstrip("\r\n") == heading), None)
    if start is None:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += eol
        tail = [] if lines[-1].strip() == "" else [eol]
        lines += tail + section
    else:
        stop = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
        keep_gap = [eol] if stop < len(lines) else []
        lines[start:stop] = section + keep_gap
    path.write_bytes("".join(lines).encode("utf-8"))


def sync_program(root, child_path):
    """Escreve o estado (pasta) do filho no SP-mãe e devolve a linha do próximo elegível; None se não há mãe."""
    result = sync_program_ready(root, child_path)
    return result[1] if result else None


def sync_program_ready(root, child_path):
    """Como `sync_program`, mas devolve (próximo elegível ou None, linha); None se não há mãe."""
    child_path = Path(child_path).resolve()
    sps = sp_list.collect(root, include_done=True)
    child = next((sp for sp in sps if sp.path.resolve() == child_path), None)
    if child is None or not child.parent:
        return None
    mother = next((sp for sp in sps if sp.project == child.project and sp.slug == child.parent), None)
    if mother is None:
        raise HandoffError(f"SP-mãe '{child.parent}' não encontrado em {child.project}")
    raw = mother.path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.splitlines(keepends=True)
    item = next((i for i, line in enumerate(lines) if line.rstrip("\r\n").strip() == f"- slug: {child.slug}"), None)
    if item is not None:
        for i in range(item + 1, len(lines)):
            if lines[i].lstrip().startswith("- ") or not lines[i].startswith(" "):
                break
            if lines[i].strip().startswith("state:"):
                lines[i] = f"{lines[i][:len(lines[i]) - len(lines[i].lstrip())]}state: {child.status}{eol}"
                break
        mother.path.write_bytes("".join(lines).encode("utf-8"))

    groups, _ = sp_list.build_tree(sps)
    kids = next(kids for m, kids in groups if m.slug == mother.slug and m.project == mother.project)
    if kids and all(sp.status == "Done" for sp, _ in kids) and mother.status != "Done":
        return None, (f"programa completo: {mother.slug}; fechar com: "
                      f"python -I scripts/sp-move.py --project {mother.project} {mother.slug} done")
    todo = [(sp, unmet) for sp, unmet in kids if sp.status == "TODO"]
    ready = next((sp for sp, unmet in todo if not unmet), None)
    if ready:
        return ready, f"próximo elegível: {ready.slug}"
    waiting = ", ".join(f"{sp.slug} aguarda: {', '.join(unmet)}" for sp, unmet in todo)
    return None, (f"próximo elegível: nenhum ({waiting})" if waiting else "próximo elegível: nenhum")


def require_doing(path):
    status = sp_list.parse_frontmatter(Path(path).read_text(encoding="utf-8")).get("status", "")
    if status.lower() != "doing":
        raise HandoffError(f"modo automático só com SP em Doing (este está em {status or 'estado desconhecido'})")


def pane_id(env=None):
    pane = (os.environ if env is None else env).get("WEZTERM_PANE")
    if not pane:
        raise HandoffError("WEZTERM_PANE não definido: o Claude Code não está a correr num painel do WezTerm")
    return pane


NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_hidden(*args, **kwargs):
    """subprocess.run sem abrir janela de consola no Windows (wezterm/clip são apps de consola)."""
    kwargs.setdefault("creationflags", NO_WINDOW)
    return subprocess.run(*args, **kwargs)


def send_argv(pane, text):
    if any(ch in text for ch in "\r\n\x1b"):
        raise HandoffError("texto com caracteres de controlo")
    return ["wezterm", "cli", "send-text", "--pane-id", str(pane), "--no-paste", text]


def enter_argv(pane):
    # O Enter vai num envio à parte: "texto\r" no mesmo bloco é tratado como colagem e dá nova linha.
    return ["wezterm", "cli", "send-text", "--pane-id", str(pane), "--no-paste", "\r"]


def pane_exists(pane, run=run_hidden):
    out = run(["wezterm", "cli", "list", "--format", "json"], check=True, capture_output=True, text=True, encoding="utf-8").stdout
    if not any(str(p.get("pane_id")) == str(pane) for p in json.loads(out)):
        raise HandoffError(f"painel {pane} não existe")


def prompt_has_text(screen):
    """True se o prompt do Claude Code (última linha `❯`) já tem texto escrito."""
    lines = [ln for ln in screen.splitlines() if ln.lstrip().startswith("❯")]
    return bool(lines) and bool(lines[-1].lstrip()[1:].strip())


def check_prompt(pane, run=run_hidden):
    screen = run(["wezterm", "cli", "get-text", "--pane-id", str(pane)], check=True,
                 capture_output=True, text=True, encoding="utf-8").stdout
    if prompt_has_text(screen):
        raise HandoffError(f"o prompt do painel {pane} tem texto por enviar: handoff abortado para não o corromper")


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


def detect_backend(env=None):
    """(backend, painel): wezterm ou tmux se o agente corre num painel; senão clipboard (apps desktop)."""
    env = os.environ if env is None else env
    if env.get("WEZTERM_PANE"):
        return "wezterm", env["WEZTERM_PANE"]
    if env.get("TMUX_PANE"):
        return "tmux", env["TMUX_PANE"]
    return "clipboard", None


def tmux_send_argv(pane, text):
    if any(ch in text for ch in "\r\n\x1b"):
        raise HandoffError("texto com caracteres de controlo")
    return ["tmux", "send-keys", "-t", str(pane), "-l", text]


def tmux_enter_argv(pane):
    return ["tmux", "send-keys", "-t", str(pane), "Enter"]


def _argvs(backend, pane):
    if backend == "wezterm":
        return send_argv, enter_argv
    if backend == "tmux":
        return tmux_send_argv, tmux_enter_argv
    raise HandoffError(f"backend '{backend}' não envia para painéis")


def _copy(text):
    """Copia para a área de transferência com a ferramenta do sistema; OSError se não há nenhuma."""
    for argv in (["clip"], ["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
        try:
            run_hidden(argv, input=text.encode("utf-16-le" if argv[0] == "clip" else "utf-8"), check=True)
            return
        except (OSError, subprocess.CalledProcessError):
            continue
    raise OSError("nenhuma ferramenta de área de transferência")


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
    clear, resume = resume_commands(harness, sp_path)

    def line(text):
        run(text_argv(pane, text), check=True)
        sleep(enter_gap)
        run(key_argv(pane), check=True)

    sleep(delay)
    if inspect:
        inspect(pane)
    line(clear)
    sleep(gap)
    line(resume)


def launch(sp_path, pane=None, backend=None, harness="claude"):
    """Lança em segundo plano o `send`, para o /clear só chegar depois de o turno atual acabar."""
    resume_commands(harness, sp_path)
    if backend is None:
        backend, found = detect_backend()
        pane = pane or found
    if backend == "clipboard":
        deliver_clipboard(harness, sp_path)
        return None
    pane = pane or pane_id()
    _argvs(backend, pane)[0](pane, resume_commands(harness, sp_path)[1])
    if backend == "wezterm":
        pane_exists(pane)
    argv = [sys.executable, "-I", str(Path(__file__).resolve()), "--send", str(sp_path), "--pane", str(pane),
            "--backend", backend, "--harness", harness]
    flags = NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)  # DETACHED_PROCESS faria cada filho abrir consola
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, close_fds=True)
    return argv


MAX_SPAWN = 3
SPAWN_READY_S = 40  # espera máxima pelo prompt do Claude Code num painel novo
SPAWN_ENTER_TRIES = 3
SPAWN_SETTLE = 6.0  # o Claude Code demora a limpar o prompt (hooks UserPromptSubmit)


def _sp_fila():
    spec = importlib.util.spec_from_file_location("sp_fila_spawn", Path(__file__).with_name("sp-fila.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_fila_spawn"] = mod
    spec.loader.exec_module(mod)
    return mod


def _spawn_pane(backend, wt, run):
    """Abre um painel novo em `wt` a correr o Claude Code; devolve o id do painel."""
    if backend == "wezterm":
        argv = ["wezterm", "cli", "spawn", "--cwd", wt, "--", "claude"]
        pane = run(argv, check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()
        origem = os.environ.get("WEZTERM_PANE")
        if origem:  # o spawn foca o painel novo; devolver o foco ao painel que lançou a fila
            run(["wezterm", "cli", "activate-pane", "--pane-id", origem], capture_output=True, text=True, encoding="utf-8")
        return pane
    else:
        argv = ["tmux", "split-window", "-P", "-F", "#{pane_id}", "-c", wt, "claude"]
    return run(argv, check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def _screen(backend, pane, run):
    argv = (["wezterm", "cli", "get-text", "--pane-id", str(pane)] if backend == "wezterm"
            else ["tmux", "capture-pane", "-p", "-t", str(pane)])
    return run(argv, check=True, capture_output=True, text=True, encoding="utf-8").stdout


_KEYS = {"wezterm": {"Down": chr(27) + "[B", "Space": " ", "Enter": chr(13)}}


def _press(backend, pane, key, run):
    if backend == "wezterm":
        run(["wezterm", "cli", "send-text", "--pane-id", str(pane), "--no-paste", _KEYS["wezterm"][key]], check=True)
    else:
        run(["tmux", "send-keys", "-t", str(pane), key], check=True)


def _aviso_mcp(screen):
    """True no aviso «new MCP servers found» (o `❯` dele não é o prompt)."""
    return "new MCP server" in screen


def _aprovar_mcp(backend, pane, run, sleep):
    """Aprova só o `vault`: desmarca o `roblox` (2.ª linha) e confirma «Enable selected»."""
    for key in ("Down", "Space", "Down", "Enter"):
        _press(backend, pane, key, run)
        sleep(0.5)


def _wait_prompt(backend, pane, run, sleep):
    """Espera que o prompt `❯` apareça (o Claude Code descarta teclas enviadas durante o arranque)."""
    for _ in range(SPAWN_READY_S):
        screen = _screen(backend, pane, run)
        if _aviso_mcp(screen):
            _aprovar_mcp(backend, pane, run, sleep)
            sleep(2)
            continue
        if any(ln.lstrip().startswith("❯") for ln in screen.splitlines()):
            sleep(1)
            return
        sleep(1)
    raise HandoffError(f"painel {pane}: o Claude Code não ficou pronto em {SPAWN_READY_S}s")


def _send_line(backend, pane, text, run, sleep):
    """Envia `text` e Enter; se o texto continuar no prompt (Enter perdido), repete o Enter."""
    text_argv, key_argv = _argvs(backend, pane)
    run(text_argv(pane, text), check=True)
    for _ in range(SPAWN_ENTER_TRIES):
        sleep(ENTER_GAP)
        run(key_argv(pane), check=True)
        sleep(SPAWN_SETTLE)
        if not prompt_has_text(_screen(backend, pane, run)):
            return
    raise HandoffError(f"painel {pane}: o Enter não submeteu {text!r}")


def spawn(slugs, backend=None, maximo=MAX_SPAWN, run=run_hidden, sleep=time.sleep, estado_path=None, copy=None, registar=True, dry_run=False):
    """Um painel e uma worktree por SP: `sb-worktree ensure`, painel novo, `/michi --auto <slug>`, registo no estado.

    Cada SP é independente: a falha de um fica em `erro` e não pára os outros. Acima de `maximo` os SPs ficam adiados.
    Sem multiplexer (clipboard) imprime, por SP, o `cd` e o comando de retoma.
    """
    backend = backend or detect_backend()[0]
    if dry_run:  # sem efeitos: nem worktree, nem painel, nem estado
        return [{"slug": s, "ok": True, "painel": None, "worktree": None, "dry_run": True} for s in slugs[:maximo]] +                [{"slug": s, "ok": False, "painel": None, "worktree": None, "erro": f"adiado: máximo de {maximo} painéis em simultâneo"} for s in slugs[maximo:]]
    fila = _sp_fila()
    estado_path = Path(estado_path or fila.ESTADO)
    estado_path.parent.mkdir(parents=True, exist_ok=True)
    if registar and not estado_path.exists():
        fila.guardar(estado_path, {"sessoes": {}})
    results = []
    for n, slug in enumerate(slugs):
        res = {"slug": slug, "ok": False, "painel": None, "worktree": None}
        results.append(res)
        if n >= maximo:
            res["erro"] = f"adiado: máximo de {maximo} painéis em simultâneo"
            continue
        try:
            wt = run([sys.executable, "-I", str(Path(__file__).with_name("sb-worktree.py")), "ensure", slug],
                     check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip().splitlines()[-1]
            res["worktree"] = wt
            cmd = f"/michi --auto {slug}"
            if backend == "clipboard":
                print(f"{slug}: cd {wt} && claude  →  {cmd}")
            else:
                res["painel"] = _spawn_pane(backend, wt, run)
                _wait_prompt(backend, res["painel"], run, sleep)
                _send_line(backend, res["painel"], cmd, run, sleep)
            res["ok"] = True
        except (subprocess.CalledProcessError, OSError, HandoffError, IndexError) as exc:
            res["erro"] = (getattr(exc, "stderr", None) or str(exc)).strip() or type(exc).__name__
            continue
        if not registar:
            continue
        entrada = {"worktree": wt, "painel": res["painel"], "estado": "lancado",
                   "inicio": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        fila.atualizar(estado_path, lambda e, s=slug, v=entrada: e["sessoes"].__setitem__(s, v))
    if backend == "clipboard":
        ok = [r["slug"] for r in results if r["ok"]]
        if ok:
            try:
                (copy or _copy)(f"/michi --auto {ok[-1]}")
            except OSError:
                pass
    return results


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
