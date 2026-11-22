"""Caixa de avisos entre painéis: quem avisa deposita uma linha; a sessão dona do painel recolhe-a por hook.

Teclas enviadas a um Claude Code ocupado (turno a correr ou diálogo aberto) perdem-se; a caixa não.
Um ficheiro JSONL por painel em `~/.claude/avisos/` (ou `AVISOS_DIR`). Nunca levanta em `recolher`.

Uso:
  python -I scripts/avisos_caixa.py   # módulo importado por sp-autor, avisos-hook e sp-fila
rc: 0 sempre (biblioteca; erros de escrita/leitura são engolidos)
"""
import contextlib
import json
import os
import time
from pathlib import Path

OCUPADO = ("esc to interrupt", "Enter to select", "Review your answers", "Esc to cancel")


def raiz():
    return Path(os.environ.get("AVISOS_DIR") or Path.home() / ".claude" / "avisos")


def _ficheiro(pane, root=None):
    nome = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(pane))
    return (root or raiz()) / f"{nome}.jsonl"


def depositar(pane, msg, root=None):
    f = _ficheiro(pane, root)
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"t": time.time(), "msg": " ".join(str(msg).split())}, ensure_ascii=False) + "\n")


def recolher(pane, root=None):
    """Devolve as mensagens pendentes do painel e esvazia a caixa (rename atómico antes de ler)."""
    if not pane:
        return []
    f = _ficheiro(pane, root)
    tmp = f.with_suffix(f".{os.getpid()}.lendo")
    try:
        f.replace(tmp)
    except OSError:
        return []
    msgs = []
    with contextlib.suppress(OSError):
        for ln in tmp.read_text(encoding="utf-8").splitlines():
            with contextlib.suppress(ValueError):
                msgs.append(json.loads(ln)["msg"])
        tmp.unlink()
    return msgs


def livre(ecra):
    """True se o ecrã mostra o Claude Code parado no prompt (sem turno a correr nem diálogo)."""
    return bool(ecra) and not any(m in ecra for m in OCUPADO)
