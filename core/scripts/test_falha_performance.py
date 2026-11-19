"""Performance medida em teste (testes-falha-90 §4.7): checkpoint <200 ms e pré-voo <2 s, mediana de 5 corridas.

Margem para CI: os limites são o SLA do programa, não o valor local. Local (Linux, SSD) mede-se ~1 ms por
checkpoint e ~0,1 s por pré-voo com 3 worktrees; o CI Windows (antivírus, runners partilhados) chega a 10×
isto e continua abaixo do limite. A mediana absorve picos isolados (indexador, GC) sem esconder regressões.

Uso: python -m pytest core/scripts/test_falha_performance.py -q
rc: o do pytest
"""
import shutil
import statistics
import subprocess
import time
from pathlib import Path

import pytest
from sp_carregar import carregar

import sp_journal

pf = carregar(Path(__file__).with_name("sp-preflight.py"), "sp_preflight", fresco=True)

CORRIDAS = 5
LIMITE_CHECKPOINT = 0.2
LIMITE_PREFLIGHT = 2.0
ID = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main"]


def _mediana(fn):
    tempos = []
    for i in range(CORRIDAS):
        t0 = time.perf_counter()
        fn(i)
        tempos.append(time.perf_counter() - t0)
    return statistics.median(tempos)


def _git(repo, *args):
    subprocess.run(["git", *ID, "-C", str(repo), *args], check=True, capture_output=True)


def test_checkpoint_mediana_de_5_abaixo_de_200ms(tmp_path):
    sp_journal.inicio(tmp_path, "perf", "da", "0")
    med = _mediana(lambda i: sp_journal.gravar_checkpoint(tmp_path, "perf", "da", str(i), extra={"i": i}))
    assert med < LIMITE_CHECKPOINT, f"checkpoint mediana {med * 1000:.1f} ms (limite {LIMITE_CHECKPOINT * 1000:.0f} ms)"
    assert sp_journal.estado(tmp_path, "perf").fase == "da"


@pytest.mark.skipif(shutil.which("git") is None, reason="git ausente")
def test_preflight_mediana_de_5_abaixo_de_2s(tmp_path):
    repo = tmp_path / "repo perf ção"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.txt").write_bytes(b"a\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "base")
    for s in ("a", "b", "c"):
        destino = tmp_path / f"wt-{s}"
        _git(repo, "worktree", "add", "-q", "-b", f"agent/{s}", str(destino))
        (destino / "x.txt").write_bytes(b"x\n")

    def corrida(_):
        pf.kf_git.invalidar()  # sem cache: cada corrida paga o custo real do git
        pf.diagnosticar("a", repo=tmp_path / "wt-a")

    med = _mediana(corrida)
    pf.kf_git.invalidar()
    assert med < LIMITE_PREFLIGHT, f"pré-voo mediana {med:.2f} s (limite {LIMITE_PREFLIGHT:.0f} s)"
