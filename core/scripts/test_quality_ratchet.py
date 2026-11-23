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
