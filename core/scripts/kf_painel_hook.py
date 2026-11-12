"""Hook do harness (Stop, Notification, UserPromptSubmit) que atualiza sozinho o estado do painel do SP.

Lê o JSON do hook no stdin, descobre o slug (`KAIZEN_SLUG` ou ramo `agent/<slug>`, por prefixo) e escreve em
`sp_painel_estado.transitar` só metadados: estado e `pergunta` (`notification`|`stop`|null). Nunca copia texto da
conversa. Falhas (sem fila, JSON corrompido, transição inválida) são ignoradas: o hook nunca bloqueia o painel.

Uso: python -I scripts/kf_painel_hook.py   (JSON do hook no stdin)
rc: 0 sempre
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_painel_estado as pe  # noqa: E402
from sp_estado_base import ErroEstado  # noqa: E402

EVENTOS = ("Stop", "Notification", "UserPromptSubmit")


def _ramo(cwd=None):
    try:
        r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def resolver_slug(env=None, ramo=None, root=None):
    """`KAIZEN_SLUG` ganha; senão o ramo `agent/<prefixo>` casa com o slug que o regista (o ramo vem truncado)."""
    env = os.environ if env is None else env
    if env.get("KAIZEN_SLUG"):
        return env["KAIZEN_SLUG"]
    if not ramo or not ramo.startswith("agent/"):
        return None
    prefixo = ramo[len("agent/"):]
    try:
        filas = pe.filas(root)
    except OSError:
        return None
    achados = sorted({sp["slug"] for f in filas for sp in f["sps"]
                      if isinstance(sp.get("slug"), str) and sp["slug"].startswith(prefixo)})
    return achados[-1] if achados else None


def _sp_feito(slug, cwd):
    return any(Path(cwd or ".").glob(f"knowledge/projects/*/*/sp/Done/{slug}.md"))


def aplicar(evento, slug=None, root=None, agora=None, sp_feito=False):
    """Aplica o evento ao SP; True se escreveu. Nunca levanta por estado em falta, ilegível ou transição inválida."""
    nome = evento.get("hook_event_name") if isinstance(evento, dict) else None
    if nome not in EVENTOS or not slug:
        return False
    try:
        if nome == "Notification":
            pe.transitar(slug, "pergunta", root=root, agora=agora, pergunta="notification")
        elif nome == "Stop":
            if sp_feito:
                pe.transitar(slug, "done", root=root, agora=agora, pergunta=None)
            else:
                pe.transitar(slug, "pergunta", root=root, agora=agora, pergunta="stop")
        else:
            pe.transitar(slug, "a-correr", root=root, agora=agora, pergunta=None)
    except (ErroEstado, pe.SemVaga, OSError, ValueError, KeyError, TypeError):
        return False
    return True


def main():
    try:
        evento = json.loads(sys.stdin.read() or "{}")
        cwd = evento.get("cwd") if isinstance(evento, dict) else None
        slug = resolver_slug(ramo=_ramo(cwd))
        aplicar(evento, slug=slug, sp_feito=bool(slug) and _sp_feito(slug, cwd))
    except Exception:  # noqa: BLE001 - o hook nunca pode bloquear o painel
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
