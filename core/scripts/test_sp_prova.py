"""Testes de scripts/sp-prova.py."""
import importlib.util
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("sp_prova", Path(__file__).with_name("sp-prova.py"))
sp_prova = importlib.util.module_from_spec(_spec)
sys.modules["sp_prova"] = sp_prova
_spec.loader.exec_module(sp_prova)


def test_grava_bytes_com_dolar_e_crases(tmp_path):
    src = tmp_path / "x.txt"
    src.write_bytes(b"# p\r\ncusto $1 `cmd`\r\n")
    dst = sp_prova.gravar(tmp_path, "prova-a", src)
    assert dst == tmp_path / "knowledge/projects/kaizen/kaizenflow/sp/proofs/prova-a.md"
    assert dst.read_bytes() == b"# p\r\ncusto $1 `cmd`\r\n"


def test_recusa_nome_com_separador(tmp_path):
    src = tmp_path / "x.txt"
    src.write_text("a")
    for nome in ("../fora", "a/b", "..", ""):
        with pytest.raises(ValueError):
            sp_prova.gravar(tmp_path, nome, src)


def test_nao_sobrescreve_sem_forcar(tmp_path):
    src = tmp_path / "x.txt"
    src.write_text("a")
    sp_prova.gravar(tmp_path, "p", src)
    with pytest.raises(FileExistsError):
        sp_prova.gravar(tmp_path, "p", src)
    src.write_text("b")
    assert sp_prova.gravar(tmp_path, "p", src, forcar=True).read_text() == "b"


def test_main_origem_inexistente_rc1(tmp_path):
    assert sp_prova.main(["p", "--arquivo", str(tmp_path / "nao"), "--root", str(tmp_path)]) == 1
