"""Testes de scripts/sp-escalao.py."""
import importlib.util
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("sp_escalao", Path(__file__).parent / "sp-escalao.py")
sp_escalao = importlib.util.module_from_spec(_spec)
sys.modules["sp_escalao"] = sp_escalao
_spec.loader.exec_module(sp_escalao)


@pytest.mark.parametrize("f,r,h,esperado", [
    (1, "baixo", 1, "pequena"),
    (3, "medio", 2, "pequena"),
    (4, "baixo", 1, "media"),
    (1, "baixo", 3, "media"),
    (2, "alto", 1, "media"),
    (16, "baixo", 1, "grande"),
    (2, "baixo", 9, "grande"),
    (6, "alto", 1, "grande"),
])
def test_classificar(f, r, h, esperado):
    assert sp_escalao.classificar(f, r, h) == esperado


def test_comando_cada_escalao():
    assert "--slug x" in sp_escalao.comando("pequena", "p", "x", "P2")
    assert "--program x" in sp_escalao.comando("media", "p", "x", "P2")
    assert "x-c:x-a+x-b" in sp_escalao.comando("grande", "p", "x", "P2")


def test_override(capsys):
    sp_escalao.main(["--project", "p", "--slug", "x", "--ficheiros", "1", "--horas", "1", "--escalao", "grande"])
    out = capsys.readouterr().out
    assert "escalão: grande (override; proposto: pequena)" in out
    assert "x-c:x-a+x-b" in out


def test_sem_override(capsys):
    sp_escalao.main(["--project", "p", "--slug", "x", "--ficheiros", "5", "--horas", "1"])
    assert "escalão: media\n" in capsys.readouterr().out
