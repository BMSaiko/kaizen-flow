"""Testes de doc-list.py (listar DRs/DPs por estado)."""
import importlib.util
import os
import sys
import time
from pathlib import Path

_spec = importlib.util.spec_from_file_location("doc_list", Path(__file__).with_name("doc-list.py"))
doc_list = importlib.util.module_from_spec(_spec)
sys.modules["doc_list"] = doc_list
_spec.loader.exec_module(doc_list)


def _doc(root, rel):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    return p


def test_collect_ordena_doing_antes_de_todo_e_omite_done(tmp_path):
    _doc(tmp_path, "p/dr/TODO/b.md")
    _doc(tmp_path, "p/dr/Doing/a.md")
    _doc(tmp_path, "p/dr/Done/c.md")
    rows = doc_list.collect(tmp_path, "dr")
    assert [(r[1], r[2]) for r in rows] == [("a", "Doing"), ("b", "TODO")]


def test_collect_all_inclui_done_e_ignora_arquivo_e_outro_tipo(tmp_path):
    _doc(tmp_path, "p/dr/Done/c.md")
    _doc(tmp_path, "p/dr/arquivo/TODO/z.md")
    _doc(tmp_path, "p/dp/TODO/d.md")
    rows = doc_list.collect(tmp_path, "dr", include_done=True)
    assert [r[1] for r in rows] == ["c"]


def test_main_imprime_idade_em_dias(tmp_path, capsys):
    p = _doc(tmp_path, "p/dp/TODO/velho.md")
    antigo = time.time() - 3 * 86400 - 60
    os.utime(p, (antigo, antigo))
    assert doc_list.main(["dp", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "# Estado Slug (idade)"
    assert out[1] == "1 TODO velho (3d)"
