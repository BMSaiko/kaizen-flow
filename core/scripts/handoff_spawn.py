"""`sp-handoff.py --spawn`: um painel e uma worktree por SP, a correr `/michi --auto <slug>`."""
import importlib.util
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handoff_pane import ENTER_GAP, HandoffError, _argvs, _copy, detect_backend, prompt_has_text, run_hidden  # noqa: E402

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
