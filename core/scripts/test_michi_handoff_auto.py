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


def test_esperado_devolve_o_modelo_do_papel(monkeypatch):
    monkeypatch.setattr(mha.modelos, "load", lambda _p: {})
    monkeypatch.setattr(mha.modelos, "papel", lambda _c, _n: {"model": "claude-sonnet-5-5"})
    assert mha.esperado() == "claude-sonnet-5-5"


def test_esperado_degrada_para_none_com_config_invalida(monkeypatch):
    def falha(_p):
        raise OSError("sem config")
    monkeypatch.setattr(mha.modelos, "load", falha)
    assert mha.esperado() is None


def test_esperado_sem_modulo_modelos_e_none(monkeypatch):
    monkeypatch.setattr(mha, "modelos", None)
    assert mha.esperado() is None


def test_origem_prefere_wezterm_e_cai_para_tmux(monkeypatch):
    monkeypatch.setenv("WEZTERM_PANE", "3")
    monkeypatch.setenv("TMUX_PANE", "%1")
    assert mha._origem() == "3"
    monkeypatch.delenv("WEZTERM_PANE")
    assert mha._origem() == "%1"


def test_main_decide_imprime_estado_e_motivo(monkeypatch, capsys):
    monkeypatch.setattr(mha, "esperado", lambda: "claude-sonnet-5-5")
    assert mha.main(["decide", "--sessao", "claude-opus-5-5"]) == 0
    assert capsys.readouterr().out.startswith("handoff ")


def test_main_go_sem_painel_interativo_avisa_e_sai_1(monkeypatch, capsys):
    monkeypatch.setattr(mha, "detect_backend", lambda: ("nenhum",))
    assert mha.main(["go", "abc"]) == 1
    assert "sem painel interativo" in capsys.readouterr().err


def _main_go(monkeypatch, ok):
    be = FakeBackend()
    monkeypatch.setattr(mha, "detect_backend", lambda: ("wezterm",))
    monkeypatch.setattr(mha.painel_backend, "por_nome", lambda _n, _r: be)
    monkeypatch.setattr(mha, "_spawn_real", lambda _n: (lambda slug, auto: "9") if ok else _falha)
    monkeypatch.setenv("WEZTERM_PANE", "7")
    return be


def _falha(slug, auto):
    raise mha.HandoffError("painel não ficou pronto")


def test_main_go_ok_imprime_painel_e_fecha_origem(monkeypatch, capsys):
    be = _main_go(monkeypatch, ok=True)
    assert mha.main(["go", "abc", "--auto"]) == 0
    assert capsys.readouterr().out.strip() == "9" and be.fechados == ["7"]


def test_main_go_falha_sai_1_e_mantem_origem(monkeypatch, capsys):
    be = _main_go(monkeypatch, ok=False)
    assert mha.main(["go", "abc"]) == 1
    assert "falhou:" in capsys.readouterr().err and be.fechados == []


def test_spawn_real_encadeia_ensure_painel_prompt_e_comando(monkeypatch):
    passos = []
    monkeypatch.setattr(mha.handoff_spawn, "_claude_cmd", lambda: "claude")
    monkeypatch.setattr(mha.handoff_spawn, "_spawn_pane", lambda be, wt, run, cmd: passos.append(("pane", wt)) or "9")
    monkeypatch.setattr(mha.handoff_spawn, "_wait_prompt", lambda be, p, run, sl: passos.append(("wait", p)))
    monkeypatch.setattr(mha.handoff_spawn, "_send_line", lambda be, p, linha, run, sl: passos.append(("send", linha)))

    class R:
        stdout = "ruido\nC:/wt/abc\n"

    def run(cmd, **kw):
        assert cmd[-2:] == ["ensure", "abc"]
        return R()

    assert mha._spawn_real("wezterm", run=run)("abc", True) == "9"
    assert passos == [("pane", "C:/wt/abc"), ("wait", "9"), ("send", "/michi --auto abc --handed")]
