"""Testes do handoff automático do arranque do michi (michi_handoff_auto)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import michi_handoff_auto as mha  # noqa: E402


class FakeBackend:
    interativo = True

    def __init__(self):
        self.fechados = []

    def fechar(self, id):
        self.fechados.append(id)
        return True


def test_decide_modelo_diferente_pede_handoff():
    assert mha.decide("claude-opus-5-5", "claude-sonnet-5-5")[0] == "handoff"


def test_decide_contexto_pede_handoff_mesmo_com_modelo_certo():
    assert mha.decide("claude-sonnet-5-5", "claude-sonnet-5-5", contexto=True)[0] == "handoff"


def test_decide_modelo_certo_sem_contexto_fica():
    assert mha.decide("claude-sonnet-5-5", "claude-sonnet-5-5")[0] == "ficar"


def test_decide_marca_handed_nunca_faz_ciclo():
    assert mha.decide("claude-opus-5-5", "claude-sonnet-5-5", contexto=True, handed=True)[0] == "ficar"


def test_decide_sem_modelo_esperado_degrada_para_ficar():
    estado, motivo = mha.decide("claude-opus-5-5", None)
    assert estado == "ficar" and "aviso" in motivo


def test_comando_leva_marca_e_auto():
    assert mha.comando("abc") == "/michi abc --handed"
    assert mha.comando("abc", auto=True) == "/michi --auto abc --handed"


def _go(spawn_falha=False, origem="7"):
    be = FakeBackend()
    chamadas = []

    def spawn(slug, auto):
        chamadas.append((slug, auto))
        if spawn_falha:
            raise mha.HandoffError("painel não ficou pronto")
        return "9"

    res = mha.go("abc", origem, be, spawn=spawn)
    return res, be, chamadas


def test_go_spawn_ok_fecha_o_painel_antigo():
    res, be, chamadas = _go()
    assert res["ok"] and res["painel"] == "9" and be.fechados == ["7"]
    assert chamadas == [("abc", False)]


def test_go_spawn_falha_mantem_o_painel_antigo():
    res, be, _ = _go(spawn_falha=True)
    assert not res["ok"] and "pronto" in res["erro"] and be.fechados == []


def test_go_sem_painel_de_origem_nao_fecha_nada():
    res, be, _ = _go(origem=None)
    assert res["ok"] and be.fechados == []


def test_motivos_imprimem_em_cp1252():
    for args in (("a", "b"), ("b", "b", True), ("a", None)):
        "".join(mha.decide(*args)).encode("cp1252")
