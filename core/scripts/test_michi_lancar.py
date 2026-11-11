"""Testes de michi-lancar.py: plano de lançamento do michi num sub-agent `Agent`."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

_spec = importlib.util.spec_from_file_location("michi_lancar", Path(__file__).resolve().parent / "michi-lancar.py")
ml = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ml)


def _sp(root, slug, pasta="TODO", nivel=None):
    d = root / "knowledge" / "projects" / "x" / "y" / "sp" / pasta
    d.mkdir(parents=True, exist_ok=True)
    extra = f"michi_modelo: {nivel}\n" if nivel else ""
    (d / f"{slug}.md").write_text(f"---\nslug: {slug}\n{extra}---\n# t\n", encoding="utf-8")


def _run(chamadas):
    def run(argv, **kw):
        chamadas.append([str(a) for a in argv])
        out = "C:/wt/sb-x\n" if "ensure" in argv else "ok\n"
        return SimpleNamespace(returncode=0, stdout=out, stderr="")
    return run


def test_plano_tem_campos_e_effort_low(tmp_path, monkeypatch):
    _sp(tmp_path, "s-1", nivel="simples")
    monkeypatch.setattr(ml.sfs, "modelo_agent", lambda nivel=None: {"simples": "m-s"}.get(nivel, "m-d"))
    ch = []
    item = ml.plano_sp("s-1", tmp_path, run=_run(ch))
    for k in ("slug", "worktree", "prompt", "description", "model"):
        assert k in item
    assert item["model"] == "m-s" and item["effort"] == "low" and item["run_in_background"] is True
    assert item["worktree"] == "C:/wt/sb-x" and item["description"] == "s-1"
    assert any("sp-move.py" in " ".join(c) and "--start" in c for c in ch)
    assert any("ensure" in c for c in ch)


def test_sp_sem_campo_usa_default(tmp_path, monkeypatch):
    _sp(tmp_path, "s-2")
    monkeypatch.setattr(ml.sfs, "modelo_agent", lambda nivel=None: {"default": "m-d"}.get(nivel or "default"))
    assert ml.plano_sp("s-2", tmp_path, run=_run([]))["model"] == "m-d"


def test_sp_inexistente_rc1(tmp_path, capsys):
    assert ml.main(["nao-existe", "--root", str(tmp_path)]) == 1
    assert "não encontrado" in capsys.readouterr().err


def test_main_imprime_uma_linha_json(tmp_path, monkeypatch, capsys):
    _sp(tmp_path, "s-3", nivel="complexo")
    monkeypatch.setattr(ml, "_RUN", _run([]))
    monkeypatch.setattr(ml.sfs, "modelo_agent", lambda nivel=None: "m-c")
    assert ml.main(["s-3", "--root", str(tmp_path)]) == 0
    linhas = capsys.readouterr().out.strip().splitlines()
    assert len(linhas) == 1 and json.loads(linhas[0])["effort"] == "low"


def test_main_saida_e_ascii(tmp_path, monkeypatch, capsys):
    _sp(tmp_path, "s-4")
    monkeypatch.setattr(ml, "_RUN", _run([]))
    monkeypatch.setattr(ml.sfs, "modelo_agent", lambda nivel=None: "m")
    assert ml.main(["s-4", "--root", str(tmp_path)]) == 0
    capsys.readouterr().out.encode("ascii")
