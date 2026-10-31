#!/usr/bin/env python3
"""Guarda de contexto: mede o contexto da sessão e pede o handoff do /michi perto do limiar.

Só leitura sobre o transcript (lê apenas o fim do ficheiro). Nunca faz commit, nem move SPs.

Uso:
  python -I scripts/context-guard.py --transcript <caminho> [--limit N]   # imprime "<tokens> <ok|aviso|limite>"
  python -I scripts/context-guard.py                                      # modo hook: JSON no stdin

Modo hook (eventos UserPromptSubmit e PostToolUse): recebe `session_id`, `transcript_path` e
`hook_event_name`. Limiar em `CLAUDE_CONTEXT_LIMIT` (omissão 100000); aviso a 85%.
- `aviso`: uma `systemMessage` ao utilizador, uma vez por sessão.
- `limite`: `additionalContext` curto a mandar correr, em modo automático e uma vez por sessão,
  `/sp-handoff` se a sessão trabalha num SP (correu `/michi <SP>` nela e o SP está em Doing) ou
  `/handoff` (ficheiro efémero em `handoffs/`) se é conversa livre. Um SP em Doing noutra sessão não conta.
Chamadas de subagentes (payload com `agent_id`) são ignoradas: partilham o `session_id` do principal.
`/michi <caminho>.md` num `UserPromptSubmit` grava o SP em `<session_id>.sp`.
Os marcadores vivem em `%TEMP%/claude-context-guard/<session_id>.<nível>`. Qualquer erro no hook é
silencioso (exit 0): o guard nunca pode estragar um prompt.
"""
import json
import os
import sys
from pathlib import Path

# argparse, re e tempfile custam ~190 ms de import: carregados só quando precisos (hook a cada tool call).

DEFAULT_LIMIT = 100_000
WARN_RATIO = 0.85
TAIL_SIZES = (64 * 1024, 1024 * 1024, 16 * 1024 * 1024)
USAGE_FIELDS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def _tail_lines(path, size):
    with open(path, "rb") as fh:
        total = fh.seek(0, os.SEEK_END)
        start = max(0, total - size)
        fh.seek(start)
        data = fh.read()
    lines = data.split(b"\n")
    if start > 0:
        lines = lines[1:]  # primeira linha da janela pode estar cortada
    return lines, start == 0


def _last_usage(lines):
    for raw in reversed(lines):
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(d, dict) or d.get("type") != "assistant" or d.get("isSidechain"):
            continue
        msg = d.get("message")
        usage = msg.get("usage") if isinstance(msg, dict) else None
        if isinstance(usage, dict):
            return sum(int(usage.get(f) or 0) for f in USAGE_FIELDS)
    return None


def context_tokens(path):
    """Tokens de contexto do último pedido do assistente (input + cache lida + cache escrita)."""
    try:
        for size in TAIL_SIZES:
            lines, whole = _tail_lines(path, size)
            tokens = _last_usage(lines)
            if tokens is not None or whole:
                return tokens
    except OSError:
        pass
    return None


def state(tokens, limit):
    if tokens >= limit:
        return "limite"
    if tokens >= limit * WARN_RATIO:
        return "aviso"
    return "ok"


def limit_from_env(env=None):
    raw = (os.environ if env is None else env).get("CLAUDE_CONTEXT_LIMIT", "")
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_LIMIT
    return value if value > 0 else DEFAULT_LIMIT


def marker_path(marker_dir, session_id, level):
    import re

    safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(session_id))
    return Path(marker_dir) / f"{safe}.{level}"


def _claim(marker_dir, session_id, level):
    """True só na primeira chamada por sessão e nível."""
    path = marker_path(marker_dir, session_id, level)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "x"):
            return True
    except FileExistsError:
        return False


MICHI_PATTERN = r"^\s*/michi\s+(\S.*\.md)\s*$"


def bind_sp(marker_dir, session_id, prompt):
    """Liga a sessão ao SP quando o prompt é `/michi <caminho>.md` (marcador `<session_id>.sp`)."""
    if not isinstance(prompt, str) or "/michi" not in prompt.lower():
        return
    import re

    match = re.match(MICHI_PATTERN, prompt.strip().strip('"'), re.IGNORECASE)
    if not match:
        return
    path = marker_path(marker_dir, session_id, "sp")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(match.group(1).strip('"'), encoding="utf-8")


def _bound_sp_doing(marker_dir, session_id):
    """Caminho do SP desta sessão se o marcador existe e o SP continua em Doing; senão None."""
    try:
        sp = marker_path(marker_dir, session_id, "sp").read_text(encoding="utf-8").strip()
        head = Path(sp).read_text(encoding="utf-8")
    except OSError:
        return None
    status = ""
    for line in head.splitlines()[1:40]:
        if line.strip() == "---":
            break
        if line.startswith("status:"):
            status = line.split(":", 1)[1].strip().lower()
    return sp if status == "doing" else None


def _k(n):
    return f"{n // 1000}K"


def hook(payload, env=None, marker_dir=None):
    session_id = payload.get("session_id")
    transcript = payload.get("transcript_path")
    if not session_id or not transcript or payload.get("agent_id"):
        return None  # subagente: o aviso gastaria o marcador da sessão e não chegaria ao modelo principal
    if marker_dir is None:
        import tempfile

        marker_dir = Path(tempfile.gettempdir()) / "claude-context-guard"
    if payload.get("hook_event_name") == "UserPromptSubmit":
        bind_sp(marker_dir, session_id, payload.get("prompt"))
    tokens = context_tokens(transcript)
    if tokens is None:
        return None
    limit = limit_from_env(env)
    level = state(tokens, limit)
    if level == "ok":
        return None
    if level == "aviso":
        if not _claim(marker_dir, session_id, "aviso"):
            return None
        return {"systemMessage": f"[context-guard] contexto em {_k(tokens)} de {_k(limit)}: handoff perto."}
    if not _claim(marker_dir, session_id, "limite"):
        return None
    event = payload.get("hook_event_name") or "UserPromptSubmit"
    sp = _bound_sp_doing(marker_dir, session_id)
    if sp:
        action = f"corre /sp-handoff em modo automático:\nsem perguntar, com `sp-handoff.py --launch {sp} --auto`."
    else:
        action = ("corre /handoff em modo automático:\nsem perguntar, escreve o handoff e lança-o com "
                  "`handoff.py --launch <ficheiro> --auto`.")
    text = (f"[context-guard] Contexto {_k(tokens)} >= limite {_k(limit)}. Acaba o passo em curso (nunca a meio de "
            f"uma edição ou teste) e {action} Não repitas este aviso.")
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    args = None
    if argv:  # caminho quente (hook) não tem argumentos: sem argparse
        import argparse

        ap = argparse.ArgumentParser(description="Guarda de contexto do Claude Code")
        ap.add_argument("--transcript", help="transcript (.jsonl) a medir")
        ap.add_argument("--limit", type=int, help="limiar em tokens (omissão: CLAUDE_CONTEXT_LIMIT ou 100000)")
        args = ap.parse_args(argv)
    if args and args.transcript:
        tokens = context_tokens(args.transcript)
        if tokens is None:
            print("sem usage no transcript", file=sys.stderr)
            return 1
        limit = args.limit if args.limit and args.limit > 0 else limit_from_env()
        print(f"{tokens} {state(tokens, limit)}")
        return 0
    try:
        out = hook(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        return 0
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
