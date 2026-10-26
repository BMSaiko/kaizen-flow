#!/usr/bin/env python3
"""Apoio ao /sp-handoff: resolve o SP em Doing, regista o progresso e lança a sessão seguinte.

O SP nunca muda de pasta nem de `status` (para isso, `sp-move.py`). Nunca faz commit.

Uso:
  python -I scripts/sp-handoff.py --resolve [slug]        # slug de um programa (SP-mãe): devolve o filho em Doing
  python -I scripts/sp-handoff.py --write <caminho> --file <progresso.md>
  python -I scripts/sp-handoff.py --launch <caminho> [--dry-run] [--auto]

`--launch` não abre janelas: em segundo plano, passados ~5 s (para o turno atual acabar), escreve
`/clear` e depois `/michi <caminho>` no painel do WezTerm onde o Claude Code já corre ($WEZTERM_PANE),
via `wezterm cli send-text`. Não faz nada fora desse painel. `--auto` (usado após o aviso do
context-guard) recusa lançar se o SP não estiver em Doing.

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


class HandoffError(Exception):
    pass


def _agent_claims():
    """Slugs reclamados pelo agente deste worktree; None fora de worktrees (comportamento original)."""
    if not Path(__file__).with_name("sb-agent.py").is_file():
        return None
    spec = importlib.util.spec_from_file_location("sb_agent", Path(__file__).with_name("sb-agent.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sb_agent"] = mod
    spec.loader.exec_module(mod)
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


def write(path, progress, today=None):
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


def send_argv(pane, text):
    if any(ch in text for ch in "\r\n\x1b"):
        raise HandoffError("texto com caracteres de controlo")
    return ["wezterm", "cli", "send-text", "--pane-id", str(pane), "--no-paste", text]


def enter_argv(pane):
    # O Enter vai num envio à parte: "texto\r" no mesmo bloco é tratado como colagem e dá nova linha.
    return ["wezterm", "cli", "send-text", "--pane-id", str(pane), "--no-paste", "\r"]


def pane_exists(pane, run=subprocess.run):
    out = run(["wezterm", "cli", "list", "--format", "json"], check=True, capture_output=True, text=True, encoding="utf-8").stdout
    if not any(str(p.get("pane_id")) == str(pane) for p in json.loads(out)):
        raise HandoffError(f"painel {pane} não existe")


def prompt_has_text(screen):
    """True se o prompt do Claude Code (última linha `❯`) já tem texto escrito."""
    lines = [ln for ln in screen.splitlines() if ln.lstrip().startswith("❯")]
    return bool(lines) and bool(lines[-1].lstrip()[1:].strip())


def check_prompt(pane, run=subprocess.run):
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
            subprocess.run(argv, input=text.encode("utf-16-le" if argv[0] == "clip" else "utf-8"), check=True)
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


def send(sp_path, pane, delay=SEND_DELAY, gap=SEND_GAP, enter_gap=ENTER_GAP, run=subprocess.run, sleep=time.sleep,
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
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, close_fds=True)
    return argv


def main(argv=None):
    ap = argparse.ArgumentParser(description="Apoio ao /sp-handoff")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--resolve", nargs="?", const="", metavar="SLUG")
    group.add_argument("--write", metavar="CAMINHO")
    group.add_argument("--launch", metavar="CAMINHO")
    group.add_argument("--send", metavar="CAMINHO", help=argparse.SUPPRESS)
    ap.add_argument("--file", help="ficheiro com o corpo do progresso (com --write)")
    ap.add_argument("--pane", help="painel do multiplexer (default: $WEZTERM_PANE ou $TMUX_PANE)")
    ap.add_argument("--backend", choices=BACKENDS, help="default: deteção automática; sem painel, clipboard")
    ap.add_argument("--harness", choices=tuple(HARNESSES), default="claude", help="comando de retoma (default: claude)")
    ap.add_argument("--dry-run", action="store_true", help="com --launch: só mostra os comandos")
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
