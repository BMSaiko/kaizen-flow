"""E2E de sp-fechar.py: gate verde fecha e gera COMMIT; gate vermelho deixa o SP em Doing."""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
PROJECT = "demo"
FILL = "conteúdo de teste"


def run(script, *args, cwd=None):
    r = subprocess.run([sys.executable, "-I", str(SCRIPTS / script), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       cwd=cwd or tempfile.gettempdir())
    return r.returncode, r.stdout, r.stderr


@pytest.fixture
def root(tmp_path):
    (tmp_path / "vault" / PROJECT).mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(tmp_path / "repo")], check=True)
    (tmp_path / "repo" / "a.txt").write_text("x", encoding="utf-8")
    return tmp_path


def novo(root, slug, *extra):
    return run("sp-new.py", "--root", str(root / "vault"), "--project", PROJECT, "--slug", slug,
               "--priority", "P3", *extra)


def novo_doing(root, slug, gate_cmd):
    vault = root / "vault"
    assert novo(root, slug, "--gate", gate_cmd)[0] == 0
    f = next((vault / PROJECT / "sp" / "TODO").glob(f"{slug}-*.md"))
    text = re.sub(r"(## \d\. [^\n]*\n)\n+", rf"\1\n{FILL}\n\n", f.read_text(encoding="utf-8"))
    f.write_text(text, encoding="utf-8")
    assert run("sp-move.py", "--root", str(vault), "--project", PROJECT, slug, "doing")[0] == 0


def fechar(root, slug):
    return run("sp-fechar.py", "--root", str(root / "vault"), "--project", PROJECT, slug,
               "--sem-budget", "--commit-dir", str(root / "repo"))


def test_gate_verde_fecha_e_gera_commit(root):
    novo_doing(root, "verde", f'"{sys.executable}" -c "import sys; sys.exit(0)"')
    rc, out, err = fechar(root, "verde")
    assert rc == 0, out + err
    assert list((root / "vault" / PROJECT / "sp" / "Done").glob("verde-*.md"))
    commit = list((root / "repo").glob("COMMIT_*.md"))
    assert len(commit) == 1
    assert "git add a.txt" in commit[0].read_text(encoding="utf-8")


def test_gate_vermelho_nao_move(root):
    novo_doing(root, "vermelho", f'"{sys.executable}" -c "import sys; sys.exit(1)"')
    rc, out, err = fechar(root, "vermelho")
    assert rc == 1
    assert list((root / "vault" / PROJECT / "sp" / "Doing").glob("vermelho-*.md"))
    assert not list((root / "vault" / PROJECT / "sp" / "Done").glob("vermelho-*.md"))
    assert not list((root / "repo").glob("COMMIT_*.md"))


def test_sp_fora_de_doing_erro(root):
    assert novo(root, "todo")[0] == 0
    rc, _, err = fechar(root, "todo")
    assert rc == 2 and "não em Doing" in err


def test_worktree_hint_so_em_worktree(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("sp_fechar", SCRIPTS / "sp-fechar.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    repo = tmp_path / "r"
    g = lambda *a, c=repo: subprocess.run(["git", "-C", str(c), *a], check=True, capture_output=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "--allow-empty", "-m", "i")
    wt = tmp_path / "wt"
    g("worktree", "add", "-q", "-b", "agent/x", str(wt))
    assert mod.worktree_hint(repo, "x") is None
    assert "sb-worktree.py merge x" in mod.worktree_hint(wt, "x")
    assert mod.worktree_hint(tmp_path, "x") is None


def _mod():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sp_fechar", SCRIPTS / "sp-fechar.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["sp_fechar"] = m
    spec.loader.exec_module(m)
    return m


def test_avisos_sem_prova_nem_reflect():
    out = _mod().avisos("## Prova de done\n\n## Reflect\n\nmodelo sem linhas\n")
    assert len(out) == 2


def test_avisos_com_prova_e_reflect():
    txt = "## Prova de done\nfast 2 s\n\n## Reflect\nReflect final: sem patch\n"
    assert _mod().avisos(txt) == []
