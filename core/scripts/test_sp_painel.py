"""Testes de scripts/sp-painel.py (vista unificada das sessões paralelas do sp-fila)."""
import importlib.util
import json
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("sp_painel", Path(__file__).with_name("sp-painel.py"))
sp_painel = importlib.util.module_from_spec(_spec)
sys.modules["sp_painel"] = sp_painel
_spec.loader.exec_module(sp_painel)


def make_sp(root, slug, folder, extra=""):
    path = root / "p" / "sp" / folder / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nstatus: {folder}\nslug: {slug}\nproject: p\npriority: P2\n---\n# corpo\n{extra}", encoding="utf-8")


def estado(tmp_path, **over):
    base = {"feitos": [], "falhados": [], "sessoes": {
        "a": {"inicio": "2026-10-28T10:00:00", "requests": 50, "painel": "11", "worktree": "/wt/sb-a", "estado": "lancado"},
        "b": {"inicio": "2026-10-28T10:01:00", "requests": 50, "painel": "12", "worktree": "/wt/sb-b", "estado": "lancado"}}}
    base.update(over)
    f = tmp_path / "estado.json"
    f.write_text(json.dumps(base), encoding="utf-8")
    return f


def test_vista_duas_sessoes_mostra_colunas(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", "Doing")
    make_sp(root, "b", "Done")
    linhas = sp_painel.vista(estado(tmp_path), root).splitlines()
    assert linhas[0].split() == ["SP", "WORKTREE", "PAINEL", "FASE", "REQUESTS", "RESULTADO"]
    a = next(l for l in linhas if l.startswith("a "))
    b = next(l for l in linhas if l.startswith("b "))
    assert "/wt/sb-a" in a and "11" in a and "Doing" in a and "50" in a and "em curso" in a
    assert "/wt/sb-b" in b and "12" in b and "Done" in b and "em curso" in b


def test_vista_resultado_feito_e_falhado(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", "Done")
    make_sp(root, "c", "Doing")
    st = estado(tmp_path, feitos=["a"], falhados=["c"], sessoes={})
    texto = sp_painel.vista(st, root)
    assert "feito" in next(l for l in texto.splitlines() if l.startswith("a "))
    assert "falhado" in next(l for l in texto.splitlines() if l.startswith("c "))


def test_vista_sem_fila(tmp_path):
    assert "sem fila" in sp_painel.vista(tmp_path / "nao-existe.json", tmp_path)


def test_main_rc(tmp_path, capsys):
    root = tmp_path / "sps"
    make_sp(root, "a", "Doing")
    assert sp_painel.main(["--estado", str(estado(tmp_path)), "--root", str(root)]) == 0
    assert "a " in capsys.readouterr().out
