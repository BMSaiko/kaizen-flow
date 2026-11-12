"""Testes do helper `sp_carregar.carregar` (carregamento de scripts por caminho).

Uso: python -m pytest scripts/test_sp_carregar.py -q
rc: n/a
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import sp_carregar  # noqa: E402


def _script(tmp_path, nome="meu-script.py", corpo="VALOR = 1\n"):
    p = tmp_path / nome
    p.write_text(corpo, encoding="utf-8")
    return p


def test_carrega_script_com_hifen_e_regista(tmp_path):
    p = _script(tmp_path)
    try:
        m = sp_carregar.carregar(p)
        assert m.VALOR == 1
        assert sys.modules["meu_script"] is m
    finally:
        sys.modules.pop("meu_script", None)


def test_segunda_chamada_devolve_o_mesmo_objeto(tmp_path):
    p = _script(tmp_path)
    try:
        assert sp_carregar.carregar(p) is sp_carregar.carregar(p)
    finally:
        sys.modules.pop("meu_script", None)


def test_nome_explicito(tmp_path):
    p = _script(tmp_path)
    try:
        m = sp_carregar.carregar(p, "outro_nome")
        assert sys.modules["outro_nome"] is m
    finally:
        sys.modules.pop("outro_nome", None)


def test_sem_registar_nao_toca_em_sys_modules(tmp_path):
    p = _script(tmp_path)
    m = sp_carregar.carregar(p, registar=False)
    assert m.VALOR == 1
    assert "meu_script" not in sys.modules


def test_fresco_reexecuta(tmp_path):
    p = _script(tmp_path)
    try:
        a = sp_carregar.carregar(p)
        b = sp_carregar.carregar(p, fresco=True)
        assert a is not b
        assert sys.modules["meu_script"] is b
    finally:
        sys.modules.pop("meu_script", None)


def test_caminho_inexistente_da_mensagem_clara(tmp_path):
    with pytest.raises(FileNotFoundError, match="nao-existe.py"):
        sp_carregar.carregar(tmp_path / "nao-existe.py")


def test_erro_no_modulo_nao_deixa_nome_registado(tmp_path):
    p = _script(tmp_path, "parte-se.py", "raise RuntimeError('x')\n")
    with pytest.raises(RuntimeError):
        sp_carregar.carregar(p)
    assert "parte_se" not in sys.modules
