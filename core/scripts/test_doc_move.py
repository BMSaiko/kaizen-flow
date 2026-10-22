"""Testes de scripts/doc-move.py e doc-list.py (fixtures temporárias)."""
import importlib.util
import sys
from pathlib import Path

import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), Path(__file__).with_name(f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod.__name__] = mod
    spec.loader.exec_module(mod)
    return mod


doc_move, doc_list = load("doc-move"), load("doc-list")


def make(root, rel, slug, text):
    p = root / rel / f"{slug}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))
    return p


def test_move_acrescenta_updated_em_falta_e_atualiza_status(tmp_path):
    make(tmp_path, "kaizen/dp/TODO", "abc", "---\nstatus: DRAFT\nscope: Full\n---\n# Plano\r\ncorpo")
    msg = doc_move.move(tmp_path, "dp", "abc", "doing")
    text = (tmp_path / "kaizen/dp/Doing/abc.md").read_bytes().decode("utf-8")
    assert "status: Doing\n" in text and "updated: " in text and "scope: Full" in text
    assert text.endswith("# Plano\r\ncorpo")
    assert not (tmp_path / "kaizen/dp/TODO/abc.md").exists()
    assert msg.startswith("abc: TODO → Doing")


def test_move_sem_frontmatter_cria_e_preserva_corpo(tmp_path):
    make(tmp_path, "kaizen/dr/Doing", "x", "# DR\ntexto\n")
    doc_move.move(tmp_path, "dr", "x", "done")
    text = (tmp_path / "kaizen/dr/Done/x.md").read_text(encoding="utf-8")
    assert text.startswith("---\nstatus: Done\nupdated: ") and text.endswith("# DR\ntexto\n")


def test_move_ignora_sp_e_tipo_errado(tmp_path):
    make(tmp_path, "kaizen/sp/TODO", "abc", "---\nstatus: TODO\n---\n")
    with pytest.raises(doc_move.DocMoveError):
        doc_move.move(tmp_path, "dp", "abc", "doing")


def test_move_ambiguo_e_ja_no_destino(tmp_path):
    make(tmp_path, "a/dp/TODO", "abc", "x")
    make(tmp_path, "b/dp/Doing", "abc", "x")
    with pytest.raises(doc_move.DocMoveError, match="ambíguo"):
        doc_move.move(tmp_path, "dp", "abc", "done")
    make(tmp_path, "c/dr/Done", "y", "x")
    assert "já está em Done" in doc_move.move(tmp_path, "dr", "y", "done")


def test_list_ordena_doing_antes_de_todo_e_omite_done(tmp_path):
    make(tmp_path, "p/dp/TODO", "t", "x")
    make(tmp_path, "p/dp/Doing", "d", "x")
    make(tmp_path, "p/dp/Done", "z", "x")
    make(tmp_path, "p/dr/TODO", "outro-tipo", "x")
    assert [r[1] for r in doc_list.collect(tmp_path, "dp")] == ["d", "t"]
    assert [r[1] for r in doc_list.collect(tmp_path, "dp", True)] == ["d", "t", "z"]
