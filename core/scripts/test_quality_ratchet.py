import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_spec = importlib.util.spec_from_file_location("quality_ratchet", Path(__file__).with_name("quality-ratchet.py"))
qr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qr)


def test_contar_ruff_agrupa_por_ficheiro_e_regra():
    saida = json.dumps([{"filename": "/r/a.py", "code": "C901"}, {"filename": "/r/a.py", "code": "C901"}, {"filename": "/r/b.py", "code": "PLR0913"}])
    assert qr.contar_ruff(saida, "/r") == {"a.py": {"C901": 2}, "b.py": {"PLR0913": 1}}


def test_contar_mypy_conta_erros_por_ficheiro():
    saida = "core/x.py:3: error: a  [assignment]\ncore/x.py:9: error: b  [arg-type]\ncore/x.py:9: note: n\nFound 2 errors\n"
    assert qr.contar_mypy(saida) == {"core/x.py": {"mypy": 2}}


def test_comparar_sobe_falha_desce_melhora():
    base = {"a.py": {"C901": 2}}
    pior, melhor = qr.comparar({"a.py": {"C901": 3}, "b.py": {"PLR0911": 1}}, base)
    assert sorted(pior) == ["a.py C901: 2 -> 3", "b.py PLR0911: 0 -> 1"] and melhor == []
    pior, melhor = qr.comparar({"a.py": {"C901": 1}}, base)
    assert pior == [] and melhor == ["a.py C901: 2 -> 1"]


def test_main_falha_se_sobe_e_atualiza_se_desce(tmp_path, monkeypatch):
    bl = tmp_path / "quality-baseline.json"
    bl.write_text(json.dumps({"a.py": {"C901": 1}}), encoding="utf-8")
    atual = {"v": {"a.py": {"C901": 2}}}
    monkeypatch.setattr(qr, "medir", lambda repo, ferramentas: atual["v"])
    assert qr.main(["--repo", str(tmp_path)]) == 1
    atual["v"] = {}
    assert qr.main(["--repo", str(tmp_path)]) == 0
    assert json.loads(bl.read_text(encoding="utf-8")) == {"a.py": {"C901": 1}}  # sem --atualizar não escreve
    assert qr.main(["--repo", str(tmp_path), "--atualizar"]) == 0
    assert json.loads(bl.read_text(encoding="utf-8")) == {}


def test_atualizar_nao_sobe_baseline(tmp_path, monkeypatch):
    bl = tmp_path / "quality-baseline.json"
    bl.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(qr, "medir", lambda repo, ferramentas: {"a.py": {"C901": 1}})
    assert qr.main(["--repo", str(tmp_path), "--atualizar"]) == 1
    assert json.loads(bl.read_text(encoding="utf-8")) == {}


def test_contar_eslint_e_tsc():
    esl = json.dumps([{"filePath": "/r/bin/a.js", "messages": [{"ruleId": "eqeqeq"}, {"ruleId": "eqeqeq"}, {"ruleId": None}]}])
    assert qr.contar_eslint(esl, "/r") == {"bin/a.js": {"eqeqeq": 2, "eslint-parse": 1}}
    tsc = "bin/a.js(3,5): error TS2339: x\nbin/a.js(9,1): error TS2810: y\n  detalhe\n"
    assert qr.contar_tsc(tsc) == {"bin/a.js": {"tsc": 2}}


def test_js_violacao_nova_falha_e_divida_baixa_atualiza(tmp_path, monkeypatch):
    bl = tmp_path / "quality-baseline.json"
    bl.write_text(json.dumps({"bin/a.js": {"eqeqeq": 2}, "x.py": {"mypy": 4}}), encoding="utf-8")
    atual = {"v": {"bin/a.js": {"eqeqeq": 2, "no-undef": 1}}}
    monkeypatch.setattr(qr, "medir", lambda repo, ferramentas: atual["v"])
    assert qr.main(["--repo", str(tmp_path), "--so", "eslint"]) == 1  # violação nova
    atual["v"] = {"bin/a.js": {"eqeqeq": 1}}
    assert qr.main(["--repo", str(tmp_path), "--so", "eslint", "--atualizar"]) == 0
    assert json.loads(bl.read_text(encoding="utf-8")) == {"bin/a.js": {"eqeqeq": 1}, "x.py": {"mypy": 4}}  # mypy intacto


def test_ferramenta_js_nova_e_semeada(tmp_path, monkeypatch):
    bl = tmp_path / "quality-baseline.json"
    bl.write_text(json.dumps({"x.py": {"mypy": 4}}), encoding="utf-8")
    monkeypatch.setattr(qr, "medir", lambda repo, ferramentas: {"bin/a.js": {"tsc": 3}})
    assert qr.main(["--repo", str(tmp_path), "--so", "tsc"]) == 1
    assert qr.main(["--repo", str(tmp_path), "--so", "tsc", "--atualizar"]) == 0
    assert json.loads(bl.read_text(encoding="utf-8"))["bin/a.js"] == {"tsc": 3}


def _git(repo, *a):
    import subprocess
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)


def _repo_diff(tmp_path, lista):
    (tmp_path / "core/scripts").mkdir(parents=True)
    (tmp_path / "core/scripts/strict_modules.txt").write_text("# c\n" + lista, encoding="utf-8")
    (tmp_path / "core/scripts/velho.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    _git(tmp_path, "checkout", "-qb", "feat")
    return tmp_path


def test_diff_modulo_novo_nao_strict_falha(tmp_path):
    repo = _repo_diff(tmp_path, "core/scripts/ok.py\n")
    (repo / "core/scripts/novo.py").write_text("y = 2\n", encoding="utf-8")
    (repo / "core/scripts/ok.py").write_text("z = 3\n", encoding="utf-8")
    (repo / "core/scripts" / ("test_" + "zz.py")).write_text("", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "feat")
    assert qr.nao_strict(str(repo), "main") == ["core/scripts/novo.py"]
    assert qr.main(["--repo", str(repo), "--diff", "main"]) == 1


def test_diff_tocado_estrito_passa(tmp_path):
    repo = _repo_diff(tmp_path, "core/scripts/velho.py\n")
    (repo / "core/scripts/velho.py").write_text("x = 2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "feat")
    assert qr.main(["--repo", str(repo), "--diff", "main"]) == 0


def test_ler_strict_ignora_comentarios_e_vazias(tmp_path):
    (tmp_path / "core/scripts").mkdir(parents=True)
    (tmp_path / "core/scripts/strict_modules.txt").write_text("# x\n\ncore\\scripts\\a.py\n", encoding="utf-8")
    assert qr.ler_strict(str(tmp_path)) == {"core/scripts/a.py"}


def test_ler_strict_separa_toleradas(tmp_path):
    (tmp_path / "core/scripts").mkdir(parents=True)
    (tmp_path / "core/scripts/strict_modules.txt").write_text("core/scripts/a.py\n~core/scripts/b.py\n", encoding="utf-8")
    assert qr.ler_strict(str(tmp_path)) == {"core/scripts/a.py"}
    assert qr.ler_toleradas(str(tmp_path)) == {"core/scripts/b.py"}
