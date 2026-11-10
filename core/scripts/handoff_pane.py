"""Primitivas partilhadas pelos dois handoffs (`sp-handoff.py` e `handoff.py`): painel, teclas, envio e lançamento.

Sem lógica de SP nem de ficheiros de handoff: só falar com o multiplexer (wezterm, tmux) ou a área de transferência.

Uso: módulo importado por handoff.py e sp-handoff.py; sem execução direta
rc: n/a
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SEND_DELAY = 5.0
SEND_GAP = 2.0
ENTER_GAP = 0.5
ENTER_TRIES = 3
ENTER_SETTLE = 6.0  # o Claude Code demora a limpar o prompt (hooks UserPromptSubmit)


class HandoffError(Exception):
    pass

def pane_id(env=None):
    pane = (os.environ if env is None else env).get("WEZTERM_PANE")
    if not pane:
        raise HandoffError("WEZTERM_PANE não definido: o Claude Code não está a correr num painel do WezTerm")
    return pane


NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CLI_TIMEOUT = 10


def run_hidden(*args, **kwargs):
    """subprocess.run sem abrir janela de consola no Windows (wezterm/clip são apps de consola)."""
    kwargs.setdefault("creationflags", NO_WINDOW)
    argv = list(args[0]) if args else list(kwargs.pop("args"))
    if argv[:2] == ["wezterm", "cli"] and "--no-auto-start" not in argv:
        # Sem GUI acessível, o wezterm cli arranca um mux-server que herda o pipe e deixa o run pendurado.
        argv.insert(2, "--no-auto-start")
    if argv[:1] in (["wezterm"], ["tmux"]):
        kwargs.setdefault("timeout", CLI_TIMEOUT)
    try:
        return subprocess.run(argv, *args[1:], **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise HandoffError(f"{' '.join(argv[:3])} não respondeu em {exc.timeout:.0f}s") from exc
    except subprocess.CalledProcessError as exc:
        if argv[:1] not in (["wezterm"], ["tmux"]):
            raise
        raise HandoffError(f"{argv[0]} inacessível ({' '.join(argv[:4])}, rc={exc.returncode}): "
                           "abre a sessão nova à mão com o /michi impresso") from exc


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


def read_screen(backend, pane, run=run_hidden):
    """Texto do ecrã do painel (`wezterm cli get-text` ou `tmux capture-pane`)."""
    argv = (["wezterm", "cli", "get-text", "--pane-id", str(pane)] if backend == "wezterm"
            else ["tmux", "capture-pane", "-p", "-t", str(pane)])
    return run(argv, check=True, capture_output=True, text=True, encoding="utf-8").stdout


def send_confirmed(pane, text, text_argv, key_argv, screen, run=run_hidden, sleep=time.sleep, enter_gap=ENTER_GAP,
                   tries=ENTER_TRIES, settle=ENTER_SETTLE):
    """Envia `text` e Enter e lê o ecrã (`screen(pane)`); se o texto continuar no prompt (Enter perdido), repete o Enter."""
    run(text_argv(pane, text), check=True)
    for _ in range(tries):
        sleep(enter_gap)
        run(key_argv(pane), check=True)
        sleep(settle)
        if not prompt_has_text(screen(pane)):
            return
    raise HandoffError(f"painel {pane}: o Enter não submeteu {text!r}")


def send_lines(lines, pane, text_argv, key_argv, delay=SEND_DELAY, gap=SEND_GAP, enter_gap=ENTER_GAP, run=run_hidden,
               sleep=time.sleep, inspect=None, screen=None):
    """Espera `delay`, confere o prompt (`inspect`) e envia cada linha de `lines` com Enter, com `gap` entre elas.

    Com `screen(pane)` cada linha passa por `send_confirmed` (Enter reenviado se o texto ficar no prompt).
    """
    def line(text):
        if screen:
            send_confirmed(pane, text, text_argv, key_argv, screen, run, sleep, enter_gap)
            return
        run(text_argv(pane, text), check=True)
        sleep(enter_gap)
        run(key_argv(pane), check=True)

    sleep(delay)
    if inspect:
        inspect(pane)
    for n, text in enumerate(lines):
        if n:
            sleep(gap)
        line(text)


def launch_detached(script, args):
    """Corre `script args...` num processo separado, sem janela, para o envio só chegar depois de o turno atual acabar."""
    argv = [sys.executable, "-I", str(Path(script).resolve()), *args]
    flags = NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)  # DETACHED_PROCESS faria cada filho abrir consola
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, close_fds=True)
    return argv
