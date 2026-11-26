import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import kf_quality as kq  # noqa: E402


NOME = "test_a" + ".py"


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": __import__("os").environ["PATH"], "HOME": str(repo)})


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / NOME).write_text("def test_a():\n    assert 1\n    assert 2\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    _git(tmp_path, "checkout", "-qb", "feat")
    return tmp_path


def test_lista_de_etapas_e_cli(capsys):
    assert kq.main(["--lista"]) == 0
    assert capsys.readouterr().out.split() == list(kq.ETAPAS)


def test_base_por_defeito_usa_ramo_principal(repo):
    assert kq.base_por_defeito(repo) == "main"


def test_base_por_defeito_sem_ramo_devolve_none(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "outro")
    assert kq.base_por_defeito(tmp_path) is None


def test_etapa_de_diff_e_saltada_sem_base(tmp_path, capsys):
    _git(tmp_path, "init", "-q", "-b", "outro")
    assert kq.main(["--repo", str(tmp_path), "--so", "protegidos"]) == 0
    assert "saltada" in capsys.readouterr().out


def test_protegidos_falha_se_teste_enfraquecido(repo, capsys):
    (repo / "tests" / NOME).write_text("def test_a():\n    assert 1\n")
    _git(repo, "commit", "-qam", "enfraquece")
    assert kq.main(["--repo", str(repo), "--so", "protegidos"]) == 1
    assert "FALHOU em protegidos" in capsys.readouterr().err


def test_protegidos_passa_se_teste_cresce(repo):
    (repo / "tests" / NOME).write_text("def test_a():\n    assert 1\n    assert 2\n    assert 3\n")
    _git(repo, "commit", "-qam", "reforca")
    assert kq.main(["--repo", str(repo), "--so", "protegidos"]) == 0


def test_base_explicita_invalida_falha(repo):
    assert kq.main(["--repo", str(repo), "--base", "nao-existe", "--so", "protegidos"]) == 1


def test_qualquer_etapa_vermelha_da_rc_1_e_corre_as_restantes(monkeypatch, repo, capsys):
    vistas = []

    def falso(etapa, _repo, _base):
        vistas.append(etapa)
        return 1 if etapa == "lint" else 0

    monkeypatch.setattr(kq, "correr", falso)
    assert kq.main(["--repo", str(repo)]) == 1
    assert vistas == list(kq.ETAPAS)
    assert "FALHOU em lint" in capsys.readouterr().err


def test_tudo_verde_da_rc_0(monkeypatch, repo, capsys):
    monkeypatch.setattr(kq, "correr", lambda *_: 0)
    assert kq.main(["--repo", str(repo)]) == 0
    assert "quality: ok" in capsys.readouterr().out


def test_ferramenta_em_falta_falha_a_etapa(monkeypatch, repo):
    def sem_ferramenta(*_a, **_k):
        raise FileNotFoundError("node")

    monkeypatch.setattr(kq.subprocess, "run", sem_ferramenta)
    assert kq.correr("testes", repo, "main") == 1


def test_comando_testes_liga_cobertura(repo):
    cmd, env = kq.comando("testes", repo, None)
    assert cmd[-1].endswith("run-tests.js") and env == {"KAIZEN_COVERAGE": "1"}
