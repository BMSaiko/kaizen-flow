"""Do checkout principal, corre o script do SP na worktree dele (`agent/<slug>`).

Os scripts `sp-move` e `sp-fechar` escrevem em `Path(__file__)/..`; chamados do checkout principal
sujavam `master`. Com worktree registada, `redirect` volta a lançar a cópia da worktree (raiz, gates,
orçamento e COMMIT_*.md ficam lá). Sem worktree devolve None e o chamador segue como antes.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402


def _worktree_of(repo, slug):
    if not Path(__file__).with_name("sb-worktree.py").is_file():
        return None
    sbwt = kaizen_engine.load("sb-worktree")
    try:
        if Path(sbwt.agent.main_root(repo)).resolve() != Path(repo).resolve():
            return None
        return sbwt._find(Path(repo), sbwt.name_of(slug))
    except sbwt.SbWorktreeError:
        return None


def redirect(script, slug, argv):
    """RC da cópia da worktree, ou None se o script já corre numa worktree ou o SP não tem uma."""
    here = Path(script).resolve()
    wt = _worktree_of(here.parent.parent, slug)
    target = wt / "scripts" / here.name if wt else None
    if target is None or not target.is_file():
        return None
    return subprocess.run([sys.executable, "-I", str(target), *argv], cwd=wt).returncode
