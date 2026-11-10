"""`sp-handoff.py --spawn`: um painel e uma worktree por SP, a correr `/michi --auto <slug>`.

Uso: módulo importado por sp-handoff.py (`--spawn`); sem execução direta
rc: n/a
"""
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import painel_backend  # noqa: E402
from handoff_pane import (ENTER_SETTLE, ENTER_TRIES, HandoffError, _argvs, _copy, detect_backend, read_screen,  # noqa: E402
                          run_hidden, send_confirmed)

from sp_fila_estado import ESTADO, atualizar, guardar, registar_sessao  # noqa: E402
try:
    import modelos  # noqa: E402
except ImportError:  # kaizen-flow sem modelos.py: lança só `claude`
    modelos = None

MAX_SPAWN = 3
MODELOS = modelos.DEFAULT if modelos else None  # .claude/modelos.json; os testes trocam-no
PAPEL = "michi-exec"
SPAWN_READY_S = 40  # espera máxima pelo prompt do Claude Code num painel novo
SPAWN_ENTER_TRIES = ENTER_TRIES
SPAWN_SETTLE = ENTER_SETTLE


def _claude_cmd():
    """`claude` com o modelo/effort do papel `michi-exec`; sem config válida avisa e devolve só `claude`."""
    if modelos is None:
        print(f"aviso: modelos.py em falta; a lançar claude sem --model para '{PAPEL}'", file=sys.stderr)
        return ["claude"]
    try:
        return ["claude"] + modelos.cli_args(PAPEL, MODELOS)
    except (modelos.ModelosError, OSError, AttributeError, TypeError) as exc:
        print(f"aviso: sem modelo para '{PAPEL}' ({exc}); a lançar claude sem --model", file=sys.stderr)
        return ["claude"]


def _spawn_pane(backend, wt, run, cmd=("claude",)):
    """Abre um painel novo em `wt` a correr `cmd` pela interface de backends; devolve o id do painel."""
    return painel_backend.por_nome(backend, run).abrir(list(cmd), wt)


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
        screen = read_screen(backend, pane, run)
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
    send_confirmed(pane, text, text_argv, key_argv, lambda p: read_screen(backend, p, run), run, sleep,
                   tries=SPAWN_ENTER_TRIES, settle=SPAWN_SETTLE)


def spawn(slugs, backend=None, maximo=MAX_SPAWN, run=run_hidden, sleep=time.sleep, estado_path=None, copy=None, registar=True, dry_run=False):
    """Um painel e uma worktree por SP: `sb-worktree ensure`, painel novo, `/michi --auto <slug>`, registo no estado.

    Cada SP é independente: a falha de um fica em `erro` e não pára os outros. Acima de `maximo` os SPs ficam adiados.
    Sem multiplexer (clipboard) imprime, por SP, o `cd` e o comando de retoma.
    """
    backend = backend or detect_backend()[0]
    claude = _claude_cmd()
    if dry_run:  # sem efeitos: nem worktree, nem painel, nem estado
        return [{"slug": s, "ok": True, "painel": None, "worktree": None, "dry_run": True, "cmd": " ".join(claude)} for s in slugs[:maximo]] +                [{"slug": s, "ok": False, "painel": None, "worktree": None, "erro": f"adiado: máximo de {maximo} painéis em simultâneo"} for s in slugs[maximo:]]
    estado_path = Path(estado_path or ESTADO)
    estado_path.parent.mkdir(parents=True, exist_ok=True)
    if registar and not estado_path.exists():
        guardar(estado_path, {"sessoes": {}})
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
                print(f"{slug}: cd {wt} && {' '.join(claude)}  →  {cmd}")
            elif backend == "background":  # sem terminal: não há prompt a esperar, o comando corre direto em `claude -p`
                res["painel"] = _spawn_pane(backend, wt, run, (*claude, "-p", cmd))
            else:
                res["painel"] = _spawn_pane(backend, wt, run, claude)
                _wait_prompt(backend, res["painel"], run, sleep)
                _send_line(backend, res["painel"], cmd, run, sleep)
            res["ok"] = True
        except (subprocess.CalledProcessError, OSError, HandoffError, IndexError, painel_backend.BackendError) as exc:
            res["erro"] = (getattr(exc, "stderr", None) or str(exc)).strip() or type(exc).__name__
            continue
        if not registar:
            continue
        inicio = datetime.now(timezone.utc).isoformat(timespec="seconds")
        atualizar(estado_path, lambda e, s=slug, i=inicio: registar_sessao(e, s, i, worktree=wt, painel=res["painel"], estado="lancado"))
    if backend == "clipboard":
        ok = [r["slug"] for r in results if r["ok"]]
        if ok:
            try:
                (copy or _copy)(f"/michi --auto {ok[-1]}")
            except OSError:
                pass
    return results
