"""Fixtures partilhadas dos testes de scripts/.

Uso: carregado pelo pytest (sem execução direta).
rc: n/a
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

# Testes de 30-40 s (análise de todas as sessões AMATA). O gate completo corre-os; `-m "not lento"` salta-os.
LENTOS = (
    ("test_amata_solver_primitivas", "test_fixtures_derivam_para_a_integranda"),
    ("test_amata_solver_cli", "test_subcomando_test_chega_a_100"),
    ("test_amata_solver_parser", "test_taxa_falhas_baixa"),
    ("test_amata_solver_parser", "test_taxa_expr_alta"),
)
_LENTOS_IDS = tuple(f"{modulo}.py::{nome}" for modulo, nome in LENTOS)


def pytest_configure(config):
    config.addinivalue_line("markers", "lento: teste de 30-40 s; `-m \"not lento\"` para uma corrida rápida")


def pytest_collection_modifyitems(items):
    for item in items:
        if item.nodeid.endswith(_LENTOS_IDS):
            item.add_marker(pytest.mark.lento)


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


CRIADO = "2026-10-01T10:00:00Z"


def criar_sp(root, rel, slug, status="TODO", project=None, body="# corpo\n", created=CRIADO, phase=None,
             priority=None, parent=None, depends_on=None, kind=None, extra=""):
    """Cria `root/rel/slug.md` com frontmatter de SP e devolve o caminho (escrita em bytes: preserva CRLF do `body`).

    Campos opcionais só entram se passados; `extra` é texto cru no fim do frontmatter (cada linha termina em LF).
    """
    path = Path(root) / rel / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    linhas = [f"status: {status}", f"created: {created}", f"updated: {created}"]
    if phase:
        linhas.append(f"phase: {phase}")
    linhas.append(f"slug: {slug}")
    for chave, valor in (("project", project), ("priority", priority), ("parent", parent), ("kind", kind)):
        if valor:
            linhas.append(f"{chave}: {valor}")
    if depends_on:
        linhas.append(f"depends_on: [{', '.join(depends_on)}]")
    head = "---\n" + "\n".join(linhas) + "\n" + extra + "---\n"
    path.write_bytes((head + body).encode("utf-8"))
    return path


@pytest.fixture
def make_sp():
    """Fábrica de SPs em diretório temporário: ver `criar_sp`."""
    return criar_sp


def processo_cli(script, *args, cwd=None, env=None, input=None, isolado=True):
    """Lança `script` com `sys.executable` (`-I` se `isolado`) e devolve o `CompletedProcess`; `env` junta-se ao ambiente atual."""
    import os
    import subprocess
    caminho = Path(script)
    if not caminho.is_absolute():
        caminho = Path(__file__).parent / caminho
    cmd = [sys.executable] + (["-I"] if isolado else []) + [str(caminho), *map(str, args)]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=cwd,
                          env={**os.environ, **env} if env else None, input=input)


def executar_cli(script, *args, **kw):
    """Como `processo_cli`, mas devolve `(rc, stdout, stderr)`; `script` relativo resolve-se a `scripts/`."""
    r = processo_cli(script, *args, **kw)
    return r.returncode, r.stdout, r.stderr


@pytest.fixture
def run_cli():
    """Fábrica `run_cli(script, *args, cwd=None, env=None)` -> `(rc, stdout, stderr)`: ver `executar_cli`."""
    return executar_cli


class Relogio:
    """Relógio controlado: `agora()` devolve o instante atual e `dormir(s)` avança-o sem esperar."""

    def __init__(self, inicio=0.0):
        self.t = float(inicio)
        self.dormidos = []

    def agora(self):
        return self.t

    def dormir(self, segundos):
        self.dormidos.append(segundos)
        self.t += segundos


@pytest.fixture
def relogio():
    """Relógio injetável (`agora`/`dormir`) no lugar de `time.time`/`time.sleep` reais."""
    return Relogio()
