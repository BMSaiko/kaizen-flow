"""Fixtures partilhadas dos testes de scripts/.

Uso: carregado pelo pytest (sem execução direta).
rc: n/a
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True)
def _sem_custos_reais(monkeypatch):
    """`sp_fila_execucao._custos` lê os transcripts reais (~13 s); nos testes devolve {} (quem precisa passa `custo_fn`)."""
    try:
        import sp_fila_execucao
    except ImportError:
        return
    monkeypatch.setattr(sp_fila_execucao, "_custos", lambda: {})


@pytest.fixture(autouse=True)
def _cwd_isolado(monkeypatch, tmp_path_factory):
    """Fora de worktree de agente `sp-move` ignora claims: os testes nunca tocam em `.git/sb-claims` real."""
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))
