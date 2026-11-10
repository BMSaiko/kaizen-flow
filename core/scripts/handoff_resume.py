#!/usr/bin/env python3
"""Hook SessionStart: depois de /clear (ou arranque), aponta a sessão nova ao handoff pendente.

Não apaga nada: só injeta `additionalContext` a mandar correr `handoff.py --consume`.
Ignora `*-pendentes.md` (gerados no fim de sessão) e handoffs com mais de `MAX_AGE_H` horas.
Qualquer erro: rc 0 sem saída (nunca falha o arranque).

Uso (settings.json): python -I scripts/handoff_resume.py   (JSON do hook no stdin)
"""
import json
import sys
import time
from pathlib import Path

MAX_AGE_H = 12
SOURCES = {"clear", "startup"}


def pending(folder, now=None, max_age_h=MAX_AGE_H):
    """Handoffs de trabalho recentes, do mais recente para o mais antigo."""
    cutoff = (now or time.time()) - max_age_h * 3600
    found = []
    for f in Path(folder).glob("*.md"):
        if f.name.endswith("-pendentes.md") or not f.is_file():
            continue
        mtime = f.stat().st_mtime
        if mtime >= cutoff:
            found.append((mtime, f))
    return [f for _, f in sorted(found, key=lambda t: t[0], reverse=True)]


def build_context(files):
    if not files:
        return ""
    first = files[0].as_posix()
    text = (f'[handoff] Há um handoff por retomar. Antes de tudo, corre `python -I scripts/handoff.py --consume "{first}"` '
            "(lê o handoff e só depois o apaga) e segue o Próximo passo.")
    if files[1:]:
        text += " Outros pendentes: " + ", ".join(f.name for f in files[1:]) + "."
    return text


def hook(stdin_text, folder, now=None):
    try:
        data = json.loads(stdin_text or "{}")
    except ValueError:
        data = {}
    if data.get("source", "startup") not in SOURCES:
        return ""
    ctx = build_context(pending(folder, now))
    if not ctx:
        return ""
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}},
                      ensure_ascii=False)


def _default_dir():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import kaizen_engine  # noqa: E402
    return kaizen_engine.load("kaizen_config").sp_root(Path(__file__).resolve().parent.parent) / "handoffs"


def main():
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        folder = sys.argv[1] if len(sys.argv) > 1 else _default_dir()
        out = hook(sys.stdin.read(), folder)
        if out:
            print(out)
    except Exception:  # noqa: BLE001 — o arranque nunca pode falhar
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
