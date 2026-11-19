"""Testes de scripts/sp-preflight.py (pré-voo git/worktree/ferramentas) com repos git temporários.

Uso: python -m pytest scripts/test_sp_preflight.py -q
rc: o do pytest
"""
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from sp_carregar import carregar

pf = carregar(Path(__file__).with_name("sp-preflight.py"), "sp_preflight", fresco=True)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git ausente")

ID = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main"]


def g(repo, *args, check=True):
    r = subprocess.run(["git", *ID, "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode != 0:
        raise AssertionError(r.stderr)
    return r


def ecs(probs):
    return [p.ec for p in probs]


@pytest.fixture
def repo(tmp_path):
    pf.kf_git.invalidar()
    r = tmp_path / "repo ção"  # espaços e acentos no caminho
    r.mkdir()
    g(r, "init", "-q")
    (r / "a.txt").write_text("a\n", encoding="utf-8")
    g(r, "add", "a.txt")
    g(r, "commit", "-q", "-m", "base")
    yield r
    pf.kf_git.invalidar()


def wt(repo, slug, branch=None):
    caminho = repo.parent / f"wt-{slug}"
    g(repo, "worktree", "add", "-q", "-b", branch or f"agent/{slug}", str(caminho))
    pf.kf_git.invalidar()
    return caminho


def diag(repo, slug=None, **kw):
    pf.kf_git.invalidar()
    return pf.diagnosticar(slug, repo=repo, **kw)


def test_repo_limpo_sem_problemas(repo):
    assert diag(repo) == []


def test_worktree_limpa_do_slug_sem_problemas(repo):
    w = wt(repo, "x")
    assert diag(w, "x") == []
    assert diag(repo, "x") == []  # do checkout principal encontra a worktree do SP


def test_arvore_suja_ec060_lista_ficheiros_sem_alterar(repo):
    w = wt(repo, "x")
    (w / "novo.txt").write_text("n", encoding="utf-8")
    (w / "a.txt").write_text("mudado\n", encoding="utf-8")
    antes = g(w, "status", "--porcelain").stdout
    (p,) = diag(w, "x")
    assert p.ec == "EC-060" and p.nivel == "aviso" and "novo.txt" in p.oque and "a.txt" in p.oque
    assert "stash push -u -m" in p.proximo
    assert g(w, "status", "--porcelain").stdout == antes


def test_estado_do_kf_nao_conta_como_arvore_suja(repo):
    w = wt(repo, "x")
    (w / ".kaizen" / "estado").mkdir(parents=True)
    (w / ".kaizen" / "estado" / "outro.journal.jsonl").write_text("{}", encoding="utf-8")
    assert diag(w, "x") == []


def test_ramo_errado_ec061(repo):
    w = wt(repo, "x", branch="outro")
    (p,) = diag(w, "x")
    assert p.ec == "EC-061" and p.nivel == "erro" and "outro" in p.oque and "agent/x" in p.proximo


def test_checkout_principal_fora_do_ramo_principal_ec031(repo):
    g(repo, "checkout", "-q", "-b", "feature")
    (p,) = diag(repo)
    assert p.ec == "EC-031" and p.nivel == "erro" and "checkout main" in p.proximo


def test_worktree_em_falta_ec062(repo):
    (p,) = diag(repo, "y")
    assert p.ec == "EC-062" and p.nivel == "erro" and "worktree add" in p.proximo and "agent/y" in p.proximo


def test_worktree_por_limpar_ec063(repo):
    w = wt(repo, "z")
    shutil.rmtree(w)
    probs = diag(repo)
    assert ecs(probs) == ["EC-063"] and probs[0].nivel == "aviso"
    assert probs[0].fix == ["git", "-C", str(repo), "worktree", "prune"]


def test_merge_a_meio_ec064_so_sugere(repo):
    g(repo, "checkout", "-q", "-b", "lado")
    (repo / "a.txt").write_text("lado\n", encoding="utf-8")
    g(repo, "commit", "-q", "-am", "lado")
    g(repo, "checkout", "-q", "main")
    (repo / "a.txt").write_text("main\n", encoding="utf-8")
    g(repo, "commit", "-q", "-am", "main")
    g(repo, "merge", "lado", check=False)
    probs = diag(repo)
    p = next(p for p in probs if p.ec == "EC-064")
    assert p.nivel == "erro" and "merge" in p.oque and p.fix is None and "--abort" in p.proximo


def test_rebase_a_meio_ec064(repo):
    g(repo, "checkout", "-q", "-b", "lado")
    (repo / "a.txt").write_text("lado\n", encoding="utf-8")
    g(repo, "commit", "-q", "-am", "lado")
    g(repo, "checkout", "-q", "main")
    (repo / "a.txt").write_text("main\n", encoding="utf-8")
    g(repo, "commit", "-q", "-am", "main")
    g(repo, "checkout", "-q", "lado")
    g(repo, "rebase", "main", check=False)
    p = next(p for p in diag(repo) if p.ec == "EC-064")
    assert "rebase" in p.oque


def test_atras_do_principal_ec025(repo):
    w = wt(repo, "x")
    (repo / "b.txt").write_text("b", encoding="utf-8")
    g(repo, "add", "b.txt")
    g(repo, "commit", "-q", "-m", "mais")
    (p,) = diag(w, "x")
    assert p.ec == "EC-025" and p.nivel == "aviso" and "1 commit" in p.oque and p.fix is None


def test_orfao_ec027_via_api_do_resume(repo):
    w = wt(repo, "x")
    est = w / ".kaizen" / "estado"
    est.mkdir(parents=True)
    (est / "x.json").write_text("{}", encoding="utf-8")
    (w / ".gitignore").write_text(".kaizen/\n", encoding="utf-8")
    g(w, "add", ".gitignore")
    g(w, "commit", "-q", "-m", "ign")
    (p,) = diag(w, "x")
    assert p.ec == "EC-027" and "kaizen resume x" in p.proximo
    assert diag(w, "x", ignorar_orfao=True) == []


def test_git_ausente_ec065(repo):
    probs = pf.diagnosticar(None, repo=repo, which=lambda n: None if n == "git" else "/usr/bin/" + n)
    assert ecs(probs) == ["EC-065"] and "git" in probs[0].oque


def test_python_ausente_ec065(repo):
    probs = diag(repo, which=lambda n: "/usr/bin/git" if n == "git" else None)
    assert ecs(probs) == ["EC-065"] and "Python" in probs[0].oque


def test_nao_e_repo_git_erro_de_uso(tmp_path):
    with pytest.raises(pf.ErroUso):
        pf.diagnosticar(None, repo=tmp_path)


def test_slug_invalido_erro_de_uso(repo):
    with pytest.raises(pf.ErroUso):
        pf.diagnosticar("../x", repo=repo)


def test_slug_invalido_cli_no_formato_ec067(repo, capsys):
    assert pf.main(["../x", "--repo", str(repo)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("EC-067 O quê: slug inválido") and "  Próximo: " in err


# --- correção -----------------------------------------------------------------

def test_corrigir_sem_confirmacao_nao_faz_nada(repo):
    w = wt(repo, "x")
    (w / "novo.txt").write_text("n", encoding="utf-8")
    (p,) = diag(w, "x")
    rc, _ = pf.corrigir(p, confirmar=lambda: False)
    assert rc == 1 and (w / "novo.txt").exists() and g(w, "stash", "list").stdout == ""


def test_corrigir_com_confirmacao_guarda_em_stash_sem_perder(repo):
    w = wt(repo, "x")
    (w / "novo.txt").write_text("n", encoding="utf-8")
    (p,) = diag(w, "x")
    rc, _ = pf.corrigir(p, confirmar=lambda: True)
    assert rc == 0 and "preflight-x" in g(w, "stash", "list").stdout
    assert g(w, "status", "--porcelain").stdout == ""
    g(w, "stash", "pop", "-q")
    assert (w / "novo.txt").read_text(encoding="utf-8") == "n"


def test_corrigir_sem_fix_so_sugere(repo):
    p = pf.Problema("EC-064", "erro", "merge a meio", "x", "git merge --abort", fix=None)
    rc, msg = pf.corrigir(p, confirmar=lambda: True)
    assert rc == 1 and "à mão" in msg


@pytest.mark.parametrize("fix", [["git", "push"], ["rm", "-rf", "x"], ["git", "-C", "r", "stash", "drop"], ["git"]])
def test_corrigir_recusa_comando_fora_da_lista_segura(fix):
    p = pf.Problema("EC-060", "aviso", "a", "b", "c", fix=fix)
    rc, msg = pf.corrigir(p, confirmar=lambda: True)
    assert rc == 2 and "recusada" in msg


def test_confirmacao_eof_vale_nao(monkeypatch):
    def eof(_):
        raise EOFError
    monkeypatch.setattr("builtins.input", eof)
    assert pf._perguntar("git x") is False


def test_anti_destrutivo_nenhum_comando_perigoso_no_codigo():
    fonte = Path(pf.__file__).read_text(encoding="utf-8")
    proibidos = [r"reset\W+--hard", r"clean\W+-[a-z]*f", r"branch\W+-D", r"remove\W+--force", r"\bunlink\(",
                 r"rmtree", r"os\.remove", r"stash\W+(drop|clear)", r"push\W+--force", r"checkout\W+--\W"]
    achados = [p for p in proibidos if re.search(p, fonte)]
    assert not achados, achados


def test_fixes_so_usam_subcomandos_seguros(repo):
    w = wt(repo, "x")
    (w / "n.txt").write_text("n", encoding="utf-8")
    shutil.rmtree(wt(repo, "z"))
    for p in diag(w, "x") + diag(repo):
        assert p.fix is None or pf._fix_seguro(p.fix), p.fix


# --- CLI e desempenho -----------------------------------------------------------

def test_cli_limpo_rc0(repo, capsys):
    assert pf.main(["--repo", str(repo)]) == 0
    assert "limpo" in capsys.readouterr().out


def test_cli_problemas_rc1_no_formato(repo, capsys):
    assert pf.main(["y", "--repo", str(repo)]) == 1
    out = capsys.readouterr().out
    assert re.search(r"^EC-062 O quê: ", out, re.M) and "  Porquê: " in out and "  Estado guardado: nada alterado" in out


def test_cli_json(repo, capsys):
    assert pf.main(["y", "--repo", str(repo), "--json"]) == 1
    d = json.loads(capsys.readouterr().out)
    assert d["problemas"][0]["ec"] == "EC-062" and d["problemas"][0]["nivel"] == "erro" and "ms" in d


def test_cli_nao_repo_rc2(tmp_path, capsys):
    assert pf.main(["--repo", str(tmp_path)]) == 2
    assert "EC-" in capsys.readouterr().err


def test_cli_fix_sem_tty_nao_altera(repo, monkeypatch, capsys):
    w = wt(repo, "x")
    (w / "novo.txt").write_text("n", encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(EOFError()))
    assert pf.main(["x", "--repo", str(w), "--fix"]) == 1
    assert (w / "novo.txt").exists() and g(w, "stash", "list").stdout == ""


def test_desempenho_menos_de_2s_com_worktrees_reais(repo):
    for s in ("a", "b", "c"):
        w = wt(repo, s)
        (w / "x.txt").write_text("x", encoding="utf-8")
    t = time.perf_counter()
    diag(repo / ".." / "wt-a", "a")
    assert time.perf_counter() - t < 2.0


def test_ec_055_worktree_com_caminho_longo_erro_claro_sem_criar(repo, monkeypatch):
    """EC-055: destino da worktree acima do limite → erro com o caminho; o pré-voo não cria nada."""
    monkeypatch.setattr(pf, "LIMITE_CAMINHO", 10)
    antes = sorted(p.name for p in repo.parent.iterdir())
    probs = diag(repo, "y")
    assert ecs(probs) == ["EC-062", "EC-055"]
    longo = probs[1]
    assert longo.nivel == "erro" and f"{repo.name}-y" in longo.oque and "core.longpaths" in longo.proximo
    assert sorted(p.name for p in repo.parent.iterdir()) == antes


def test_ec_055_caminho_curto_sem_aviso(repo, monkeypatch):
    monkeypatch.setattr(pf, "LIMITE_CAMINHO", 10_000)
    assert ecs(diag(repo, "y")) == ["EC-062"]
