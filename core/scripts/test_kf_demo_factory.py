"""Testes de kf_demo_factory: a demo da factory corre de ponta a ponta num repo temporário (gate vermelho, orçamento, release, publish)."""
import shutil
import subprocess
import sys
from pathlib import Path

import kf_demo_factory as demo

SCRIPTS = Path(__file__).resolve().parent


def _projeto(tmp_path):
    """Repo de exemplo com os scripts do motor; sem `sb-worktree.py` (só do vault), o `sp-move` não cria worktrees."""
    shutil.copytree(SCRIPTS, tmp_path / "scripts", ignore=shutil.ignore_patterns("__pycache__", "sb-worktree.py"))
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    return tmp_path


def test_demo_completa_rc0(tmp_path):
    dirp = _projeto(tmp_path)
    r = subprocess.run([sys.executable, "-I", str(dirp / "scripts" / "kf_demo_factory.py"), "--dir", str(dirp)],
                       capture_output=True, text=True, encoding="utf-8", timeout=300)
    out = r.stdout
    assert r.returncode == 0, r.stdout + r.stderr
    assert "factory demo concluída" in out
    assert "[gate-vermelho]" in out
    assert "paragem: orcamento" in out
    assert "rc 3: recusado sem --confirmo" in out
    assert any("correcao" in p.name for p in (dirp / "knowledge" / "projects" / "kaizen" / "mini" / "sp").rglob("*.md"))


def test_criar_correcao_poe_data_no_fim():
    chamadas = []
    demo.py = lambda dirp, script, *a: chamadas.append(a) or subprocess.CompletedProcess(a, 0)
    try:
        novo = demo.criar_correcao(Path("."), "mini-visao-m2-tema-2026-11-27")
    finally:
        import importlib
        importlib.reload(demo)
    assert novo == "mini-visao-m2-tema-correcao-2026-11-27"
    assert chamadas[0][chamadas[0].index("--slug") + 1] == novo


def test_sem_dir_e_erro_de_uso():
    r = subprocess.run([sys.executable, "-I", str(SCRIPTS / "kf_demo_factory.py")], capture_output=True, text=True)
    assert r.returncode == 2
