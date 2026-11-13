"""Commit + push automáticos e seguros para hooks de arranque (notas periódicas, envelhecer SPs).

Só no ramo master; só os caminhos pedidos (git commit -- paths, não toca no resto do stage);
push sem force; nunca levanta: devolve uma linha de estado.
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _git(*args, timeout=60):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", timeout=timeout)


def alterados(prefixos):
    """Caminhos (relativos ao repo) modificados/novos sob os prefixos dados."""
    r = _git("status", "--porcelain", "-uall", "--", *prefixos)
    out = []
    for ln in r.stdout.splitlines():
        p = ln[3:].strip().strip('"')
        if " -> " in p:
            p = p.split(" -> ")[-1]
        if p:
            out.append(p)
    return out


def commit_push(paths, mensagem, git=_git):
    """git add + commit -- paths + push. Devolve texto de estado (nunca levanta)."""
    try:
        paths = list(paths)
        if not paths:
            return ""
        if git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() != "master":
            return "auto-commit: fora de master, ignorado"
        git("add", "--", *paths)
        c = git("commit", "-q", "-m", mensagem, "--", *paths)
        if c.returncode != 0:
            return "auto-commit: commit falhou: %s" % (c.stderr or c.stdout).strip()[:200]
        p = git("push", timeout=120)
        if p.returncode != 0:
            return "auto-commit: commit feito, push falhou: %s" % (p.stderr or p.stdout).strip()[:200]
        return "auto-commit: %d ficheiro(s) commitados e enviados" % len(paths)
    except Exception as e:
        return "auto-commit: %s: %s" % (type(e).__name__, e)
