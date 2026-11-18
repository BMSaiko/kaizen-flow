#!/usr/bin/env python3
"""Renomeia a tab (WezTerm, herdr ou tmux) do painel atual para o slug do SP ou do handoff (best-effort, rc 0 sempre).

Uso: python -I scripts/tab-title.py <slug> [--pane N]

Sem painel de herdr, WezTerm ou tmux (nem --pane) não faz nada. Imprime o `/rename <slug>` pronto
a copiar: o Claude Code não permite disparar `/rename` a partir de um script sem escrever no painel.
rc: 0 ok (best-effort, nunca falha)
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from painel_backend import painel_atual, run_hidden  # noqa: E402

MAX_LEN = 40


def sanitize(text):
    """Slug ascii (a-z, 0-9, hífen), sem data final YYYY-MM-DD, ≤40 caracteres."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower().replace(".md", "")).strip("-")
    slug = re.sub(r"-?\d{4}-\d{2}-\d{2}$", "", slug)
    return slug[:MAX_LEN].strip("-")


def set_title(slug, pane=None, env=None, run=run_hidden):
    """True se o título foi definido; False (sem exceção) em qualquer falha."""
    env = os.environ if env is None else env
    backend, atual = painel_atual(env)
    if pane and not backend:
        backend = "wezterm"  # --pane sem multiplexer detetado: comportamento antigo
    pane = pane or atual
    title = sanitize(slug)
    if not pane or not title:
        return False
    argv = {
        # --no-auto-start + timeout: sem GUI acessível, o wezterm cli arrancava um mux-server e pendurava.
        "wezterm": ["wezterm", "cli", "--no-auto-start", "set-tab-title", "--pane-id", str(pane), title],
        "herdr": ["herdr", "pane", "rename", str(pane), title],
        "tmux": ["tmux", "rename-window", "-t", str(pane), title],
    }[backend]
    try:
        run(argv, check=True, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slug")
    ap.add_argument("--pane")
    args = ap.parse_args(argv)
    set_title(args.slug, args.pane)
    title = sanitize(args.slug)
    if title:
        print(f"/rename {title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
