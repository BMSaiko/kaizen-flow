"""Testes de scripts/sp-execucao.py (grava/lê execucao: da mãe, em bytes)."""
import importlib.util
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("sp_execucao", Path(__file__).with_name("sp-execucao.py"))
sp_execucao = importlib.util.module_from_spec(_spec)
sys.modules["sp_execucao"] = sp_execucao
_spec.loader.exec_module(sp_execucao)

MAE = "---\nstatus: TODO\nupdated: 2026-01-01T00:00:00Z\nslug: mae\nproject: demo\npriority: P2\nkind: program\nexecucao:\n---\n# SP\n"


def make(tmp_path, text, name="mae"):
    d = tmp_path / "demo" / "sp" / "TODO"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{name}.md"
    f.write_bytes(text.encode("utf-8"))
    return f


def test_sem_valor_por_escolher_e_depois_grava(tmp_path):
    f = make(tmp_path, MAE)
    assert sp_execucao.main(["mae", "--root", str(tmp_path)]) == 0
    assert sp_execucao.ler(tmp_path, "mae") == "por escolher"
    assert "execucao = paralelo" in sp_execucao.gravar(tmp_path, "mae", "paralelo")
    text = f.read_text(encoding="utf-8")
    assert "execucao: paralelo\n" in text and "updated: 2026-01-01" not in text
    assert sp_execucao.ler(tmp_path, "mae") == "paralelo"


def test_idempotente_nao_reescreve(tmp_path):
    f = make(tmp_path, MAE.replace("execucao:", "execucao: sequencial"))
    antes = f.read_bytes()
    assert "já é sequencial" in sp_execucao.gravar(tmp_path, "mae", "sequencial")
    assert f.read_bytes() == antes


def test_recusa_nao_mae_e_valor_invalido(tmp_path):
    make(tmp_path, MAE.replace("kind: program\n", ""), "filho")
    make(tmp_path, MAE)
    assert sp_execucao.main(["filho", "paralelo", "--root", str(tmp_path)]) == 1
    assert sp_execucao.main(["mae", "aos-saltos", "--root", str(tmp_path)]) == 1
    with pytest.raises(sp_execucao.SpExecucaoError):
        sp_execucao.gravar(tmp_path, "nada", "paralelo")


def test_preserva_crlf_e_acrescenta_campo_em_falta(tmp_path):
    f = make(tmp_path, MAE.replace("execucao:\n", "").replace("\n", "\r\n"))
    sp_execucao.gravar(tmp_path, "mae", "sequencial")
    raw = f.read_bytes()
    assert b"execucao: sequencial\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
