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


def socket_dir(env=None):
    env = os.environ if env is None else env
    home = env.get("USERPROFILE") or env.get("HOME") or str(Path.home())
    return Path(home) / ".local" / "share" / "wezterm"


def _lista(run, env):
    """Painéis do GUI a que `env` aponta; HandoffError se o GUI não responde."""
    kw = {"env": env} if env is not None else {}
    out = run(["wezterm", "cli", "list", "--format", "json"], check=True, capture_output=True, text=True,
              encoding="utf-8", **kw).stdout
    return json.loads(out)


def live_socket(env=None, run=run_hidden, sockets=None):
    """Socket do GUI do WezTerm vivo: o atual (`WEZTERM_UNIX_SOCKET`), senão o `gui-sock-*` vivo mais recente.

    "" = o ambiente responde sem socket definido; None = nenhum GUI vivo.
    """
    env = dict(os.environ if env is None else env)
    atual = env.get("WEZTERM_UNIX_SOCKET", "")
    if sockets is None:
        try:
            sockets = sorted(socket_dir(env).glob("gui-sock-*"), key=lambda f: f.stat().st_mtime, reverse=True)
        except OSError:
            sockets = []
    candidatos = [atual] if (atual or not sockets) else [""]
    candidatos += [str(s) for s in sockets if str(s) != atual]
    for sock in candidatos:
        teste = {k: v for k, v in env.items() if k != "WEZTERM_UNIX_SOCKET"}
        if sock:
            teste["WEZTERM_UNIX_SOCKET"] = sock
        try:
            _lista(run, teste)
            return sock
        except (HandoffError, OSError, ValueError):
            continue
    return None


def socket_env(sock, env=None):
    """Ambiente com `WEZTERM_UNIX_SOCKET` ajustado ao socket escolhido."""
    env = dict(os.environ if env is None else env)
    if sock:
        env["WEZTERM_UNIX_SOCKET"] = sock
    return env


def pane_exists(pane, run=run_hidden, env=None, retoma=None):
    """Confere que o painel existe no GUI de `env`; `retoma` (ficheiro) acrescenta a retoma manual à mensagem."""
    if not any(str(p.get("pane_id")) == str(pane) for p in _lista(run, env)):
        dica = (f': retoma à mão numa sessão nova com `python -I scripts/handoff.py --consume "{retoma}"`'
                if retoma else "")
        raise HandoffError(f"painel {pane} não existe no WezTerm (janela fechada?){dica}")


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
    """Envia `text` e Enter e lê o ecrã (`screen(pane)`); se o texto continuar no prompt (Enter perdido), repete o Enter.

    Antes do Enter confirma que o texto chegou ao prompt: logo a seguir a `/clear` o Claude Code reinicia a
    sessão (hooks SessionStart) e descarta o que for escrito entretanto; nesse caso espera e reescreve.
    """
    for _ in range(tries):
        run(text_argv(pane, text), check=True)
        sleep(enter_gap)
        if prompt_has_text(screen(pane)):
            break
        sleep(settle)
    else:
        raise HandoffError(f"painel {pane}: o texto {text!r} não chegou ao prompt")
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


def launch_detached(script, args, env=None):
    """Corre `script args...` num processo separado, sem janela, para o envio só chegar depois de o turno atual acabar."""
    argv = [sys.executable, "-I", str(Path(script).resolve()), *args]
    flags = NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)  # DETACHED_PROCESS faria cada filho abrir consola
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, close_fds=True, **({"env": env} if env is not None else {}))
    return argv
