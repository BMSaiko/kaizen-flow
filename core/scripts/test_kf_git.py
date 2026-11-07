"""Testes de kf_git: helper único para chamadas git (cache em processo, invalidação)."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import kf_git  # noqa: E402


class Falso:
    def __init__(self, saidas):
        self.saidas = list(saidas)
        self.chamadas = []

    def __call__(self, argv, **kw):
        self.chamadas.append(argv)
        out = self.saidas.pop(0) if self.saidas else ""
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")


def setup_function(_):
    kf_git.invalidar()


def test_run_nunca_usa_shell_e_passa_lista():
    f = Falso(["x"])
    kf_git.run("/r", "status", run=f)
    assert f.chamadas == [["git", "-C", "/r", "status"]]


def test_run_cache_repete_so_uma_vez():
    f = Falso(["a", "b"])
    assert kf_git.run("/r", "rev-parse", "HEAD", run=f, cache=True).stdout == "a"
    assert kf_git.run("/r", "rev-parse", "HEAD", run=f, cache=True).stdout == "a"
    assert len(f.chamadas) == 1


def test_run_sem_cache_repete():
    f = Falso(["a", "b"])
    kf_git.run("/r", "status", run=f)
    kf_git.run("/r", "status", run=f)
    assert len(f.chamadas) == 2


def test_invalidar_limpa_cache():
    f = Falso(["a", "b"])
    kf_git.run("/r", "rev-parse", "HEAD", run=f, cache=True)
    kf_git.invalidar()
    assert kf_git.run("/r", "rev-parse", "HEAD", run=f, cache=True).stdout == "b"


def test_branch_atual_e_ficheiros_alterados():
    f = Falso(["master\n", " M a.md\n?? b.md\n"])
    assert kf_git.branch_atual("/r", run=f) == "master"
    assert kf_git.ficheiros_alterados("/r", run=f) == ["a.md", "b.md"]


def test_ficheiros_em_head_uma_chamada_por_diretorio():
    f = Falso(["a.md\nb.md\n"])
    assert kf_git.ficheiros_em_head("/d", run=f, cache=True) == {"a.md", "b.md"}
    assert kf_git.ficheiros_em_head("/d", run=f, cache=True) == {"a.md", "b.md"}
    assert len(f.chamadas) == 1
    assert f.chamadas[0][:4] == ["git", "-C", "/d", "ls-tree"]


def test_ficheiros_em_head_fora_de_repo_devolve_none():
    def mau(argv, **kw):
        return subprocess.CompletedProcess(argv, 128, stdout="", stderr="fatal")
    assert kf_git.ficheiros_em_head("/x", run=mau) is None
