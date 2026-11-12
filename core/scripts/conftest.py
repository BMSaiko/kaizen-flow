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
def _paineis_falsos(monkeypatch, tmp_path_factory):
    """Estado das filas de painéis numa pasta temporária e backend de painéis falso por defeito (nunca abre WezTerm real)."""
    monkeypatch.setenv("SP_FILA_ROOT", str(tmp_path_factory.mktemp("sp-fila")))
    try:
        import sp_fila_execucao
        from sp_fila_testlib import PainelFalso
    except ImportError:
        return
    monkeypatch.setattr(sp_fila_execucao, "_backend_defeito", lambda: PainelFalso(), raising=False)


@pytest.fixture(autouse=True)
def _sem_wezterm_real(monkeypatch):
    """Rede de segurança no ponto único (`subprocess.run`/`Popen`): lançar `wezterm` real num teste é erro; quem precisa troca-o."""
    import subprocess
    run, popen = subprocess.run, subprocess.Popen

    def _verificar(argv):
        primeiro = argv if isinstance(argv, (str, bytes)) else (list(argv) or [""])[0]
        if Path(str(primeiro)).stem.lower() == "wezterm":
            raise AssertionError(f"teste lançou o wezterm real: {argv}")

    def run_guardado(argv, *a, **kw):
        _verificar(argv)
        return run(argv, *a, **kw)

    class PopenGuardado(popen):
        def __init__(self, argv, *a, **kw):
            _verificar(argv)
            super().__init__(argv, *a, **kw)

    monkeypatch.setattr(subprocess, "run", run_guardado)
    monkeypatch.setattr(subprocess, "Popen", PopenGuardado)


@pytest.fixture(autouse=True)
def _cwd_isolado(monkeypatch, tmp_path_factory):
    """Fora de worktree de agente `sp-move` ignora claims: os testes nunca tocam em `.git/sb-claims` real."""
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))
