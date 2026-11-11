"""Arranque do michi: handoff automático para uma sessão com o modelo `michi-exec`, só se preciso.

`decide` diz `handoff` se o modelo da sessão ≠ `michi-exec` ou se houve trabalho antes do michi; a sessão lançada
traz `--handed` e fica sempre (sem ciclo). `go` abre um painel novo (modelo `michi-exec`, `/michi <slug> --handed`)
e só depois de ele estar pronto fecha o painel de origem; se o spawn falhar, o antigo mantém-se.

Uso: python -I scripts/michi_handoff_auto.py decide --sessao <modelo> [--contexto] [--handed] [--painel] [--em-subagent]
     python -I scripts/michi_handoff_auto.py go <slug> [--auto]
rc: decide 0 (imprime `subagent|handoff|ficar <motivo>`); go 0 ok, 1 falhou (painel antigo intacto)
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import handoff_spawn  # noqa: E402
import painel_backend  # noqa: E402
from handoff_pane import HandoffError, detect_backend, run_hidden  # noqa: E402

try:
    import modelos  # noqa: E402
except ImportError:  # kaizen-flow sem modelos.py
    modelos = None

PAPEL = handoff_spawn.PAPEL


def esperado():
    """ID do modelo do papel `michi-exec`; None sem modelos.py ou config válida."""
    if modelos is None:
        return None
    try:
        return modelos.papel(modelos.load(handoff_spawn.MODELOS), PAPEL)["model"]
    except (modelos.ModelosError, OSError, AttributeError, TypeError, KeyError):
        return None


def decide(sessao, esperado_id, contexto=False, handed=False, painel=False, em_subagent=False):
    """(`handoff`|`ficar`, motivo). `--handed` ou dentro de outra sessão lançada = ficar (anti-ciclo); por defeito
    `ficar` (o michi corre na sessão principal, sem `Agent`); a lógica de painel só com `--painel` (sem modelo
    esperado só avisa)."""
    if handed:
        return "ficar", "sessão já veio de um handoff (--handed)"
    if em_subagent:
        return "ficar", "já dentro de um sub-agent: segue o ciclo sem relançar"
    if not painel:
        return "ficar", "sessão principal: o michi segue nesta sessão (painel só com --painel)"
    if not esperado_id:
        return "ficar", "aviso: sem modelo esperado para michi-exec; sem handoff"
    if sessao != esperado_id:
        return "handoff", f"modelo da sessão {sessao} difere de michi-exec {esperado_id}"
    if contexto:
        return "handoff", "sessão com contexto (o michi não é o 1.º pedido)"
    return "ficar", "modelo certo e sessão limpa"


def comando(slug, auto=False):
    return f"/michi {'--auto ' if auto else ''}{slug} --handed"


def _origem():
    return os.environ.get("WEZTERM_PANE") or os.environ.get("TMUX_PANE")


def _spawn_real(backend, run=run_hidden):
    """Spawn de um painel novo na worktree de `slug` (reutiliza o handoff_spawn); devolve o id."""
    def spawn(slug, auto):
        wt = run([sys.executable, "-I", str(Path(__file__).with_name("sb-worktree.py")), "ensure", slug],
                 check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip().splitlines()[-1]
        painel = handoff_spawn._spawn_pane(backend, wt, run, handoff_spawn._claude_cmd())
        handoff_spawn._wait_prompt(backend, painel, run, time.sleep)
        handoff_spawn._send_line(backend, painel, comando(slug, auto), run, time.sleep)
        return painel
    return spawn


def go(slug, origem, backend, spawn, auto=False):
    """Abre o painel novo e só depois de pronto fecha `origem`; falha do spawn deixa o antigo intacto."""
    try:
        painel = spawn(slug, auto)
    except (subprocess.CalledProcessError, OSError, HandoffError, IndexError, painel_backend.BackendError) as exc:
        return {"ok": False, "painel": None, "erro": (getattr(exc, "stderr", None) or str(exc)).strip() or type(exc).__name__}
    if origem:
        backend.fechar(origem)
    return {"ok": True, "painel": painel}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("decide")
    d.add_argument("--sessao", required=True, help="ID do modelo desta sessão")
    d.add_argument("--contexto", action="store_true")
    d.add_argument("--handed", action="store_true")
    d.add_argument("--painel", action="store_true", help="pedido explícito de painel WezTerm/tmux")
    d.add_argument("--em-subagent", action="store_true", help="o michi já corre num sub-agent")
    g = sub.add_parser("go")
    g.add_argument("slug")
    g.add_argument("--auto", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "decide":
        estado, motivo = decide(a.sessao, esperado(), a.contexto, a.handed, a.painel, a.em_subagent)
        print(f"{estado} {motivo}")
        return 0
    nome = detect_backend()[0]
    if nome not in ("wezterm", "tmux"):
        print(f"sem painel interativo ({nome}): ficar nesta sessão", file=sys.stderr)
        return 1
    backend = painel_backend.por_nome(nome, run_hidden)
    res = go(a.slug, _origem(), backend, _spawn_real(nome), a.auto)
    print(res["painel"] if res["ok"] else f"falhou: {res['erro']}", file=None if res["ok"] else sys.stderr)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
