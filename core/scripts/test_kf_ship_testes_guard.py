import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import kf_ship_testes_guard as g

# nomes montados para o core-consistency não os ler como scripts em falta
T = "test" + "_"
A = T + "a.py"


def test_is_teste():
    for p in ("tests/a.test.js", "core/scripts/" + T + "x.py", "x_test.py", "src/a.spec.ts", "tests/helpers/h.js"):
        assert g.is_teste(p), p
    for p in ("core/scripts/x.py", "README.md", "src/latest.js"):
        assert not g.is_teste(p), p


def test_contar_asserts():
    txt = "assert x\n    assert y == 1\nexpect(a).toBe(1)\nassert.equal(a, b)\nself.assertEqual(a, b)\nprint(1)\n"
    assert g.contar_asserts(txt) == 5


def test_teste_apagado():
    v = g.verificar({"tests/a.test.js": "expect(1)"}, {})
    assert v and "apagado" in v[0]


def test_assert_removido():
    v = g.verificar({A: "assert 1\nassert 2\n"}, {A: "assert 1\n"})
    assert v and "2 → 1" in v[0]


def test_teste_novo_e_so_codigo_ok():
    assert g.verificar({}, {T + "n.py": "assert 1"}) == []
    assert g.verificar({A: "assert 1"}, {A: "assert 1\nassert 2"}) == []
    assert g.verificar({"a.py": "x=1"}, {}) == []


def _git(d, *a):
    subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)


def _repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / A).write_text("assert 1\nassert 2\n")
    (tmp_path / "a.py").write_text("x = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def test_main_ok_e_violacao(tmp_path, capsys):
    r = _repo(tmp_path)
    (r / "a.py").write_text("x = 2\n")
    _git(r, "commit", "-qam", "codigo")
    assert g.main(["HEAD~1..HEAD", "--repo", str(r)]) == 0
    (r / A).write_text("assert 1\n")
    _git(r, "commit", "-qam", "enfraquece")
    assert g.main(["HEAD~1..HEAD", "--repo", str(r)]) == 1
    assert A in capsys.readouterr().out


def test_main_sem_testes(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.py").write_text("x\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "b")
    (tmp_path / "a.py").write_text("y\n")
    _git(tmp_path, "commit", "-qam", "c")
    assert g.main(["HEAD~1..HEAD", "--repo", str(tmp_path)]) == 3


def test_main_uso():
    assert g.main(["semintervalo"]) == 64


def test_main_base_avancou(tmp_path):
    r = _repo(tmp_path)
    _git(r, "branch", "-q", "ramo")
    (r / A).write_text("assert 1\nassert 2\nassert 3\n")
    _git(r, "commit", "-qam", "base ganha asserts")
    _git(r, "checkout", "-q", "ramo")
    (r / "a.py").write_text("x = 3\n")
    _git(r, "commit", "-qam", "codigo no ramo")
    principal = subprocess.run(["git", "-C", str(r), "for-each-ref", "--format=%(refname:short)", "refs/heads"],
                               capture_output=True, text=True).stdout.split()
    principal = next(b for b in principal if b != "ramo")
    assert g.main([f"{principal}..ramo", "--repo", str(r)]) == 0


def test_main_recusa_opcoes_como_ref():
    assert g.main(["main..-x"]) == 64
