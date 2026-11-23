import importlib.util
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import kaizen_config

_spec = importlib.util.spec_from_file_location("sp_cobertura_diff", Path(__file__).with_name("sp-cobertura-diff.py"))
cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cd)

CODIGO = "def f(x):\n    a = x + 1\n    b = a * 2\n    return b\n"


def git(d, *a):
    subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)


def repo_com_diff(tmp_path, extra=None):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "base.py").write_text("x = 1\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text(CODIGO, encoding="utf-8")
    for nome, texto in (extra or {}).items():
        (tmp_path / nome).write_text(texto, encoding="utf-8")
    return tmp_path


def lcov(tmp_path, hits):
    linhas = ["SF:src/mod.py"] + [f"DA:{n},{h}" for n, h in hits.items()] + ["end_of_record"]
    p = tmp_path / "lcov.info"
    p.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return str(p)


def run(repo, rel, *extra):
    return cd.main(["--repo", str(repo), "--base", "HEAD", "--cobertura", rel, *extra])


def test_diff_totalmente_coberto_rc0(tmp_path, capsys):
    repo = repo_com_diff(tmp_path)
    assert run(repo, lcov(tmp_path, {1: 1, 2: 3, 3: 1, 4: 1})) == 0
    assert "100.0% (4/4)" in capsys.readouterr().out


def test_diff_parcialmente_coberto_rc1(tmp_path, capsys):
    repo = repo_com_diff(tmp_path)
    assert run(repo, lcov(tmp_path, {1: 1, 2: 0, 3: 0, 4: 1})) == 1
    out = capsys.readouterr().out
    assert "50.0% (2/4)" in out and "src/mod.py:2,3" in out


def test_sem_linhas_de_codigo_rc0(tmp_path, capsys):
    (tmp_path / "tests").mkdir()
    repo = repo_com_diff(tmp_path, {"README.md": "# x\n", "cfg.json": "{}\n", "tests/a.py": "def t():\n    assert 1\n"})
    (repo / "src" / "mod.py").unlink()
    assert run(repo, lcov(tmp_path, {1: 0})) == 0
    assert "sem linhas de código" in capsys.readouterr().out


def test_limiar_por_argumento_e_config(tmp_path):
    repo = repo_com_diff(tmp_path)
    rel = lcov(tmp_path, {1: 1, 2: 0, 3: 0, 4: 1})
    assert run(repo, rel, "--limiar", "50") == 0
    (repo / "kaizen.config.json").write_text('{"qualidade": {"coberturaDiff": 40}}', encoding="utf-8")
    assert run(repo, rel) == 0


def test_linhas_nao_executaveis_nao_contam(tmp_path, capsys):
    repo = repo_com_diff(tmp_path)
    assert run(repo, lcov(tmp_path, {2: 1, 3: 1})) == 0
    assert "(2/2)" in capsys.readouterr().out


def test_sem_relatorio_rc2(tmp_path, capsys):
    repo = repo_com_diff(tmp_path)
    assert cd.main(["--repo", str(repo)]) == 2
    assert "sem relatório" in capsys.readouterr().err


def test_relatorio_ilegivel_rc2(tmp_path):
    repo = repo_com_diff(tmp_path)
    mau = tmp_path / "mau.xml"
    mau.write_text("<coverage", encoding="utf-8")
    assert run(repo, str(mau)) == 2


def test_relatorio_por_defeito_em_coverage(tmp_path):
    repo = repo_com_diff(tmp_path)
    (repo / "coverage").mkdir()
    (repo / "coverage" / "lcov.info").write_text(Path(lcov(tmp_path, {1: 1, 2: 1, 3: 1, 4: 1})).read_text(), encoding="utf-8")
    assert cd.main(["--repo", str(repo), "--base", "HEAD"]) == 0


def test_json_do_coverage_py(tmp_path):
    repo = repo_com_diff(tmp_path)
    j = tmp_path / "c.json"
    j.write_text(json.dumps({"files": {"src/mod.py": {"executed_lines": [1, 2], "missing_lines": [3, 4]}}}), encoding="utf-8")
    assert run(repo, str(j)) == 1
    assert run(repo, str(j), "--limiar", "50") == 0


def test_cobertura_xml_com_source_absoluto(tmp_path):
    repo = repo_com_diff(tmp_path)
    x = tmp_path / "c.xml"
    x.write_text(f'<coverage><sources><source>{repo / "src"}</source></sources><packages><package><classes>'
                 '<class filename="mod.py"><lines><line number="1" hits="1"/><line number="2" hits="1"/>'
                 '<line number="3" hits="1"/><line number="4" hits="1"/></lines></class></classes></package></packages></coverage>', encoding="utf-8")
    assert run(repo, str(x)) == 0


def test_ficheiro_sem_dados_avisa_e_nao_conta(tmp_path, capsys):
    repo = repo_com_diff(tmp_path)
    assert run(repo, lcov(tmp_path, {1: 1})) == 0  # mod.py presente
    (tmp_path / "r2").mkdir()
    repo2 = repo_com_diff(tmp_path / "r2")
    (repo2 / "src" / "mod.py").rename(repo2 / "src" / "outro.py")
    capsys.readouterr()
    assert run(repo2, lcov(tmp_path, {1: 1})) == 0
    assert "sem dados de cobertura" in capsys.readouterr().out


def test_config_cobertura_diff_defeito_e_invalidos(tmp_path):
    assert kaizen_config.cobertura_diff(tmp_path) == 85
    for v in ('"x"', "true", "150", "-1", "null"):
        (tmp_path / "kaizen.config.json").write_text('{"qualidade": {"coberturaDiff": %s}}' % v, encoding="utf-8")
        assert kaizen_config.cobertura_diff(tmp_path) == 85
    (tmp_path / "kaizen.config.json").write_text('{"qualidade": {"coberturaDiff": 90}}', encoding="utf-8")
    assert kaizen_config.cobertura_diff(tmp_path) == 90
