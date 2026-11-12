"""E2E de sp-fechar.py: gate verde fecha e gera COMMIT; gate vermelho deixa o SP em Doing."""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from sp_carregar import carregar  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
PROJECT = "demo"
FILL = "conteúdo de teste"


def fs(nome):
    """Slug completo `<projeto>-<nome>-<data>` (sp-new não o altera)."""
    return f"{PROJECT}-{nome}-2026-11-01"


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
    f = next((vault / PROJECT / "sp" / "TODO").glob(f"{slug}.md"))
    text = re.sub(r"(## \d\. [^\n]*\n)\n+", rf"\1\n{FILL}\n\n", f.read_text(encoding="utf-8"))
    f.write_text(text, encoding="utf-8")
    assert run("sp-move.py", "--root", str(vault), "--project", PROJECT, slug, "doing")[0] == 0


def fechar(root, slug, *extra, dispensa=True):
    d = ("--sem-prova", "teste") if dispensa else ()
    return run("sp-fechar.py", "--root", str(root / "vault"), "--project", PROJECT, slug,
               "--sem-budget", "--commit-dir", str(root / "repo"), *d, *extra)


def test_sem_prova_nem_reflect_bloqueia(root):
    novo_doing(root, fs("semprova"), f'"{sys.executable}" -c "import sys; sys.exit(0)"')
    rc, out, err = fechar(root, fs("semprova"), dispensa=False)
    assert rc == 1, out + err
    assert list((root / "vault" / PROJECT / "sp" / "Doing").glob(f"{fs('semprova')}.md"))
    assert not list((root / "vault" / PROJECT / "sp" / "Done").glob(f"{fs('semprova')}.md"))
    assert not list((root / "repo").glob("COMMIT_*.md"))


def test_sem_prova_dispensa_regista_no_sp(root):
    novo_doing(root, fs("dispensa"), f'"{sys.executable}" -c "import sys; sys.exit(0)"')
    rc, out, err = fechar(root, fs("dispensa"))
    assert rc == 0, out + err
    sp = next((root / "vault" / PROJECT / "sp" / "Done").glob(f"{fs('dispensa')}.md"))
    assert "## Dispensa de prova/reflect" in sp.read_text(encoding="utf-8")


def test_sp_completo_fecha_sem_dispensa(root):
    novo_doing(root, fs("completo"), f'"{sys.executable}" -c "import sys; sys.exit(0)"')
    f = next((root / "vault" / PROJECT / "sp" / "Doing").glob(f"{fs('completo')}.md"))
    txt = f.read_text(encoding="utf-8")
    for sec in ("Prova de done", "Reflect"):
        txt = re.sub(rf"^## {sec}[^\n]*\n.*?(?=^## |\Z)", "", txt, flags=re.S | re.M)
    txt += "\n## Prova de done\n\nfast 2 s\n\n## Reflect\n\nReflect final: sem patch\n"
    f.write_text(txt, encoding="utf-8")
    rc, out, err = fechar(root, fs("completo"), dispensa=False)
    assert rc == 0, out + err
    done = next((root / "vault" / PROJECT / "sp" / "Done").glob(f"{fs('completo')}.md"))
    assert "## Dispensa" not in done.read_text(encoding="utf-8")


def test_gate_verde_fecha_e_gera_commit(root):
    novo_doing(root, fs("verde"), f'"{sys.executable}" -c "import sys; sys.exit(0)"')
    rc, out, err = fechar(root, fs("verde"))
    assert rc == 0, out + err
    assert list((root / "vault" / PROJECT / "sp" / "Done").glob(f"{fs('verde')}.md"))
    commit = list((root / "repo").glob("COMMIT_*.md"))
    assert len(commit) == 1
    assert "git add a.txt" in commit[0].read_text(encoding="utf-8")


def test_gate_vermelho_nao_move(root):
    novo_doing(root, fs("vermelho"), f'"{sys.executable}" -c "import sys; sys.exit(1)"')
    rc, out, err = fechar(root, fs("vermelho"))
    assert rc == 1
    assert list((root / "vault" / PROJECT / "sp" / "Doing").glob(f"{fs('vermelho')}.md"))
    assert not list((root / "vault" / PROJECT / "sp" / "Done").glob(f"{fs('vermelho')}.md"))
    assert not list((root / "repo").glob("COMMIT_*.md"))


def test_sp_fora_de_doing_erro(root):
    assert novo(root, fs("todo"))[0] == 0
    rc, _, err = fechar(root, fs("todo"))
    assert rc == 2 and "não em Doing" in err


def test_worktree_hint_so_em_worktree(tmp_path):
    mod = carregar(SCRIPTS / "sp-fechar.py", "sp_fechar", registar=False, fresco=True)
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
    m = carregar(SCRIPTS / "sp-fechar.py", "sp_fechar", fresco=True)
    return m


def test_avisos_sem_prova_nem_reflect():
    out = _mod().avisos("## Prova de done\n\n## Reflect\n\nmodelo sem linhas\n")
    assert len(out) == 2


def test_avisos_com_prova_e_reflect():
    txt = "## Prova de done\nfast 2 s\n\n## Reflect\nReflect final: sem patch\n"
    assert _mod().avisos(txt) == []


def test_erro_nao_encontrado_sugere_sp_list(root):
    rc, _, err = fechar(root, "inexistente")
    assert rc == 2 and "sp-list.py" in err


def test_erro_fora_de_doing_sugere_sp_move(root):
    assert novo(root, fs("todo2"))[0] == 0
    rc, _, err = fechar(root, fs("todo2"))
    assert rc == 2 and f"sp-move.py {fs('todo2')} doing" in err


def test_alias_slug_flag(root):
    rc, _, err = run("sp-fechar.py", "--root", str(root / "vault"), "--project", PROJECT,
                     "--slug", "inexistente", "--sem-budget", "--commit-dir", str(root / "repo"))
    assert rc == 2 and "sp-list.py" in err


def _prog(tmp_path, estados):
    """Mãe 'mae' + filhos a,b,c com o estado dado (pasta TODO/Doing/Done); b depende de a."""
    for slug, st in estados.items():
        d = tmp_path / PROJECT / "sp" / st
        d.mkdir(parents=True, exist_ok=True)
        extra = "kind: program\n" if slug == "mae" else "parent: mae\n" + ("depends_on: [a]\n" if slug == "b" else "")
        (d / f"{slug}-2026-11-01.md").write_text(
            f"---\nstatus: {st}\nupdated: 2026-11-01T00:00:00Z\nslug: {slug}\nproject: {PROJECT}\npriority: P3\nmodo: manual\n{extra}---\n# SP\n",
            encoding="utf-8")


def test_seguinte_proximo_filho(tmp_path):
    _prog(tmp_path, {"mae": "TODO", "a": "Done", "b": "TODO", "c": "TODO"})
    out = _mod().seguinte(tmp_path, "a", PROJECT)
    assert out.startswith("PRÓXIMO FILHO:") and "b" in out


def test_seguinte_ultimo_filho_fecha_mae(tmp_path):
    _prog(tmp_path, {"mae": "TODO", "a": "Done", "b": "Done", "c": "Done"})
    out = _mod().seguinte(tmp_path, "c", PROJECT)
    assert out.startswith("ÚLTIMO FILHO:") and "mae" in out
    # o fecho da mãe passa por worktree + commit + merge, nunca pelo checkout principal
    assert "sb-worktree.py ensure mae" in out and "merge" in out and "checkout principal" in out


def test_seguinte_ultimo_filho_nao_com_irmaos_invisiveis(tmp_path):
    """Regressão: a mãe lista a,b,c mas só a e b existem neste ramo; c (TODO em master) conta como irmão por fechar."""
    _prog(tmp_path, {"mae": "TODO", "a": "Done", "b": "Done"})
    mae = next((tmp_path / PROJECT / "sp" / "TODO").glob("mae-*.md"))
    txt = mae.read_text(encoding="utf-8").replace(
        "kind: program\n", "kind: program\nchildren:\n  - slug: a\n  - slug: b\n  - slug: c\n")
    mae.write_text(txt, encoding="utf-8")
    out = _mod().seguinte(tmp_path, "b", PROJECT)
    assert not out.startswith("ÚLTIMO FILHO") and "c" in out


def test_move_filho_atualiza_state_na_mae(tmp_path):
    _prog(tmp_path, {"mae": "TODO", "a": "Doing", "b": "TODO"})
    mae = next((tmp_path / PROJECT / "sp" / "TODO").glob("mae-*.md"))
    mae.write_text(mae.read_text(encoding="utf-8").replace(
        "kind: program\n", "kind: program\nchildren:\n  - slug: a\n    state: Doing\n  - slug: b\n    state: TODO\n"),
        encoding="utf-8")
    rc, out, err = run("sp-move.py", "--root", str(tmp_path), "--project", PROJECT, "a", "done")
    assert rc == 0, out + err
    assert "  - slug: a\n    state: Done\n" in mae.read_text(encoding="utf-8")


def test_seguinte_sem_parent_nada(tmp_path):
    _prog(tmp_path, {"mae": "TODO", "a": "Done"})
    assert _mod().seguinte(tmp_path, "mae", PROJECT) == ""


def test_guarda_fecho_filho_anuncia_seguinte(tmp_path):
    """Guarda: fechar um filho (sem --next) nunca omite PRÓXIMO FILHO / ÚLTIMO FILHO."""
    _prog(tmp_path, {"mae": "TODO", "a": "Doing", "b": "TODO", "c": "TODO"})
    sp = tmp_path / PROJECT / "sp" / "Doing" / "a-2026-11-01.md"
    sp.write_text(sp.read_text(encoding="utf-8") + "\n## Prova de done\nok\n\n## Reflect\nReflect final: sem patch\n", encoding="utf-8")
    rc, out, err = run("sp-fechar.py", "--root", str(tmp_path), "--project", PROJECT, "a",
                       "--sem-budget", "--sem-testes", "--sem-commit")
    assert rc == 0, err
    assert "PRÓXIMO FILHO:" in out


def test_guarda_skill_michi_regista_regra():
    """Guarda: o SKILL.md do michi mantém a regra do passo seguinte ao fechar um filho."""
    caminhos = [SCRIPTS.parent / ".claude" / "skills" / "michi" / "SKILL.md", SCRIPTS.parent / "skills" / "michi" / "SKILL.md"]
    existente = next((c for c in caminhos if c.is_file()), None)
    if existente is None:
        pytest.skip("SKILL.md do michi não existe neste layout")
    skill = existente.read_text(encoding="utf-8")
    assert "PRÓXIMO FILHO" in skill and "ÚLTIMO FILHO" in skill and "Nunca omitir" in skill

def test_changed_paths_ignora_apagamento_em_stage(tmp_path):
    """Rename TODO->Done: o stage não lista a origem já apagada (git add falhava)."""
    sys.path.insert(0, str(SCRIPTS))
    mod = carregar(SCRIPTS / "sp-fechar.py", "sp_fechar_mod", registar=False, fresco=True)
    g = lambda *a: subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=a@b", "-c", "user.name=a", *a],
                                  check=True, capture_output=True)
    g("init", "-q")
    (tmp_path / "TODO").mkdir()
    (tmp_path / "Done").mkdir()
    (tmp_path / "TODO" / "x.md").write_text("a", encoding="utf-8")
    g("add", ".")
    g("commit", "-qm", "i")
    (tmp_path / "TODO" / "x.md").rename(tmp_path / "Done" / "x.md")
    g("rm", "--cached", "-q", "TODO/x.md")
    assert mod.changed_paths(tmp_path) == ["Done/x.md"]


def test_em_fila_so_com_sessao_registada(tmp_path):
    f = tmp_path / "estado.json"
    f.write_text('{"sessoes": {"a": {}}}', encoding="utf-8")
    assert _mod().em_fila("a", f) and not _mod().em_fila("b", f)
    assert not _mod().em_fila("a", tmp_path / "nao-existe.json")


def test_seguinte_em_fila_so_reporta_sem_proximo_filho(tmp_path):
    _prog(tmp_path, {"mae": "TODO", "a": "Done", "b": "TODO"})
    out = _mod().seguinte(tmp_path, "a", PROJECT, fila=True)
    assert out.startswith("FILA:") and "PRÓXIMO FILHO" not in out and "sp-handoff" not in out
