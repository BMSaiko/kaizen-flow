"""Do checkout principal, corre o script do SP na worktree dele (`agent/<slug>`).

Os scripts `sp-move` e `sp-fechar` escrevem em `Path(__file__)/..`; chamados do checkout principal
sujavam `master`. `redirect` volta a lançar a cópia da worktree (raiz, gates, orçamento e COMMIT_*.md
ficam lá); sem worktree cria-a primeiro com `sb-worktree ensure`.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402


def _worktree_of(repo, slug):
    """(worktree, no_principal): worktree registada do SP (ou None) e se `repo` é o checkout principal."""
    if not Path(__file__).with_name("sb-worktree.py").is_file():
        return None, False
    sbwt = kaizen_engine.load("sb-worktree")
    try:
        if Path(sbwt.agent.main_root(repo)).resolve() != Path(repo).resolve():
            return None, False
        return sbwt._find(Path(repo), sbwt.name_of(slug)), True
    except sbwt.SbWorktreeError:
        return None, False


def _sp_existe(repo, slug):
    sp_list = kaizen_engine.load("sp-list")
    return any(s.slug == slug for s in sp_list.collect(sp_list.default_root(repo), include_done=True))


def redirect(script, slug, argv):
    """RC da cópia da worktree, ou None se o script já corre numa worktree ou o SP não existe (o chamador dá o erro).

    No checkout principal, um SP existente sem worktree cria-a (`ensure`); se falhar, aborta com RC 2 sem escrever em `master`.
    """
    here = Path(script).resolve()
    wt, principal = _worktree_of(here.parent.parent, slug)
    if wt is None and principal and _sp_existe(here.parent.parent, slug):
        sbwt = kaizen_engine.load("sb-worktree")
        try:
            wt = sbwt.ensure(here.parent.parent, slug)
        except sbwt.SbWorktreeError as e:
            print(f"erro: não foi possível criar a worktree de '{slug}': {e}", file=sys.stderr)
            return 2
    target = wt / "scripts" / here.name if wt else None
    if target is None or not target.is_file():
        return None
    return subprocess.run([sys.executable, "-I", str(target), *argv], cwd=wt).returncode
