import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import avisos_caixa as ac  # noqa: E402


def test_depositar_e_recolher_esvazia(tmp_path):
    ac.depositar("wB:p1", "um\naviso", root=tmp_path)
    ac.depositar("wB:p1", "dois", root=tmp_path)
    assert ac.recolher("wB:p1", root=tmp_path) == ["um aviso", "dois"]
    assert ac.recolher("wB:p1", root=tmp_path) == []


def test_recolher_sem_painel_ou_caixa_devolve_vazio(tmp_path):
    assert ac.recolher(None, root=tmp_path) == [] and ac.recolher("x", root=tmp_path) == []


def test_livre_so_com_prompt_parado():
    assert ac.livre("❯ \n Opus · ctx") and not ac.livre("esc to interrupt") and not ac.livre("")
