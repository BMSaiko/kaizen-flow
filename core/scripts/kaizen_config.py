"""Lê `kaizen.config.json` na raiz do repo; sem ficheiro ou chave, devolve o defeito.

Chaves: `spRoot` (raiz dos SPs) e `docsRoot` (raiz dos DR/DP), relativas à raiz do repo.
"""
import json
from pathlib import Path

DEFAULT_SP_ROOT = "knowledge/projects/kaizen"
DEFAULT_DOCS_ROOT = "knowledge/projects"
CONFIG_NAME = "kaizen.config.json"
DEFAULT_USER = "user"


def _read(repo):
    try:
        data = json.loads((Path(repo) / CONFIG_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def sp_root(repo):
    return Path(repo) / _read(repo).get("spRoot", DEFAULT_SP_ROOT)


def user_name(repo):
    """Nome com que os avisos tratam o utilizador (`userName`; defeito «user»)."""
    v = _read(repo).get("userName")
    return v if isinstance(v, str) and v.strip() else DEFAULT_USER


def docs_root(repo):
    return Path(repo) / _read(repo).get("docsRoot", DEFAULT_DOCS_ROOT)


HOOKS_NAME = "kaizen-hooks.json"
EVENTS = ("sp.created", "sp.moved", "michi.phase.start", "michi.phase.end",
          "michi.gate.failed", "michi.commit", "michi.closed")


def hooks(repo):
    """Hooks válidos de `kaizen-hooks.json` (lista `hooks`); entradas inválidas são descartadas."""
    try:
        data = json.loads((Path(repo) / HOOKS_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    raw = data.get("hooks") if isinstance(data, dict) else None
    out = []
    for h in raw if isinstance(raw, list) else []:
        if not isinstance(h, dict) or h.get("event") not in EVENTS:
            continue
        cmd = h.get("cmd")
        if not isinstance(cmd, str) or not cmd.strip():
            continue
        modo = h.get("modo", "informativo")
        timeout = h.get("timeout", 10)
        cond = h.get("if", {})
        if modo not in ("bloqueante", "informativo") or isinstance(timeout, bool) \
                or not isinstance(timeout, (int, float)) or timeout <= 0 or not isinstance(cond, dict):
            continue
        if h.get("enabled", True) is not True:
            continue
        out.append({"event": h["event"], "cmd": cmd, "modo": modo, "timeout": timeout, "if": cond})
    return out
