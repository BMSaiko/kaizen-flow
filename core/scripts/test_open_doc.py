"""Testes de open-doc.py: SPs Doing antes de TODO, resto por mtime, pastas ignoradas e --limit."""
import os
import sys
from pathlib import Path

from sp_carregar import carregar

od = carregar(Path(__file__).resolve().parent / "open-doc.py", "open_doc", fresco=True)


def _md(raiz, rel, mtime):
    p = raiz / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def _correr(monkeypatch, capsys, raiz, *argv):
    monkeypatch.setattr(od, "ROOT", str(raiz))
    monkeypatch.setattr(sys, "argv", ["open-doc.py", *argv])
    od.main()
    return [linha.split("\t") for linha in capsys.readouterr().out.splitlines()]


def test_ordem_e_filtros(tmp_path, monkeypatch, capsys):
    _md(tmp_path, "p/sp/TODO/t.md", 300)
    _md(tmp_path, "p/sp/Doing/d.md", 100)
    _md(tmp_path, "p/sp/Done/feito.md", 50)
    _md(tmp_path, "velho.md", 10)
    _md(tmp_path, "novo.md", 200)
    _md(tmp_path, "node_modules/x.md", 999)
    _md(tmp_path, "nota.txt", 999)
    linhas = _correr(monkeypatch, capsys, tmp_path)
    assert [r for r, _ in linhas] == ["SP Doing · d.md", "SP TODO · t.md", "novo.md", "p/sp/Done/feito.md", "velho.md"]
    assert linhas[0][1] == str(tmp_path / "p/sp/Doing/d.md")


def test_limit_so_corta_o_resto(tmp_path, monkeypatch, capsys):
    _md(tmp_path, "p/sp/TODO/t.md", 1)
    _md(tmp_path, "a.md", 2)
    _md(tmp_path, "b.md", 3)
    linhas = _correr(monkeypatch, capsys, tmp_path, "--limit", "1")
    assert [r for r, _ in linhas] == ["SP TODO · t.md", "b.md"]
