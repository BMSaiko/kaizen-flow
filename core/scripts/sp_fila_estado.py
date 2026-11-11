"""Sp-fila: configuração, execução sem janela e estado partilhado (bloqueio, leitura e escrita atómica).

O bloqueio, a escrita atómica e o `pid_vivo` vivem em `sp_painel_estado.py` (estado por fila e por SP);
este módulo delega neles e mantém o estado único `~/.claude/sp-fila-estado.json` da série.

Uso: módulo importado por sp-fila.py; sem execução direta
rc: n/a
"""
import json
import os  # noqa: F401  (os testes instrumentam `sp_fila_estado.os`)
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402
import sp_painel_estado  # noqa: E402
from sp_painel_estado import LOCK_VELHO_S, _lock_obsoleto, bloqueio, guardar, pid_vivo  # noqa: E402,F401

_cfg = kaizen_engine.load("kaizen_config")
REPO = Path(__file__).resolve().parent.parent
USER = _cfg.user_name(REPO)
SCRIPTS = Path(__file__).resolve().parent
ESTADO = Path.home() / ".claude" / "sp-fila-estado.json"
RELATORIOS = REPO / "knowledge" / "infra" / "reports" / "sp-fila"
REQ_POR_SP = 50  # unidade de contagem do teto opt-in (--orcamento / orcamento_requests); por defeito sem limite
ORCAMENTO = None  # sem limite de requests
MAX_FALHAS_DEFEITO = 2  # falhas seguidas até parar a fila
MAX_DEFEITO = 5


NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_hidden(*args, **kwargs):
    """subprocess.run sem janela de consola no Windows: o vigia chama wezterm/git a cada ciclo e as janelas piscavam."""
    kwargs.setdefault("creationflags", NO_WINDOW)
    return subprocess.run(*args, **kwargs)


def registar_sessao(dados, slug, inicio, **campos):
    """Único sítio que escreve `estado["sessoes"][slug]`: `inicio` mais os campos dados (painel, worktree, requests, ...)."""
    dados["sessoes"][slug] = {"inicio": inicio, **campos}


def migrar_para_filas(path=None, root=None):
    """Converte o estado único (`ESTADO`) numa fila do estado por fila; devolve o fila-id ou None se não há ficheiro.

    O ficheiro antigo fica onde está: a série (`sp-handoff --launch`) continua a usá-lo."""
    return sp_painel_estado.migrar_antigo(path or ESTADO, root=root)


def migrar(estado):
    """Formato antigo (`lancado`: um slug) → `sessoes`: {slug: {inicio, ...}} (uma entrada por SP em curso)."""
    antigo = estado.pop("lancado", None)
    estado.setdefault("sessoes", {})
    estado.setdefault("feitos", [])  # estado só com sessoes+vigia (sem chaves de fila): tolerar a ausência
    estado.setdefault("falhados", [])
    if antigo:
        estado["sessoes"].setdefault(antigo, {})
    return estado


def ler(path):
    return migrar(json.loads(Path(path).read_text(encoding="utf-8")))


def atualizar(path, fn):
    """Ler-alterar-escrever o estado sob bloqueio; `fn(estado)` altera-o no sítio."""
    with bloqueio(path):
        estado = ler(path)
        fn(estado)
        guardar(path, estado)
        return estado


