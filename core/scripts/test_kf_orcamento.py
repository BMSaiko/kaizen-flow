"""Testes de kf_orcamento: decisão ok|aviso|parar e retoma da fila por orçamento."""
import json
from datetime import datetime
from pathlib import Path

import kaizen_config
import kf_orcamento as orc
from sp_fila_testlib import PainelFalso, _estado, _runner, make_sp, sp_fila

AGORA = datetime(2026, 11, 23, 12, 0)
CFG = {"spUsd": 10.0, "diaUsd": 50.0, "falhasSeguidas": 3}


def test_config_sem_chave_e_none(tmp_path):
    assert kaizen_config.orcamento(tmp_path) is None


def test_config_valida_defeitos_e_descarta_invalidos(tmp_path):
    (tmp_path / "kaizen.config.json").write_text(json.dumps({"orcamento": {"diaUsd": 20, "spUsd": -1, "falhasSeguidas": True}}), encoding="utf-8")
    assert kaizen_config.orcamento(tmp_path) == {"spUsd": None, "diaUsd": 20.0, "falhasSeguidas": 3}


def test_ok_abaixo_de_80_por_cento():
    assert orc.decidir(CFG, sp_usd=7.9, dia_usd=39.9, seguidas=2) == {"estado": "ok", "razao": "", "avisos": []}


def test_aviso_a_80_por_cento():
    r = orc.decidir(CFG, sp_usd=8.0, dia_usd=10.0, seguidas=0)
    assert r["estado"] == "aviso" and "spUsd" in r["avisos"][0]


def test_parar_por_dia_sp_e_falhas():
    assert orc.decidir(CFG, dia_usd=50.0)["estado"] == "parar" and "diaUsd" in orc.decidir(CFG, dia_usd=50.0)["razao"]
    assert "spUsd" in orc.decidir(CFG, sp_usd=10.0)["razao"]
    assert "falhasSeguidas" in orc.decidir(CFG, seguidas=3)["razao"]


def test_sem_config_ou_campo_ausente_nunca_para():
    assert orc.decidir(None, sp_usd=999, dia_usd=999, seguidas=99)["estado"] == "ok"
    assert orc.decidir({"spUsd": None, "diaUsd": None, "falhasSeguidas": None}, dia_usd=999)["estado"] == "ok"


def _fila(tmp_path, **over):
    root = tmp_path / "sps"
    make_sp(root, "a")
    return root, _estado(tmp_path, concorrencia=1, **over)


def test_fila_pausa_com_dia_acima_do_teto_e_regista_razao(tmp_path):
    root, st = _fila(tmp_path, orcamento_cfg={"spUsd": None, "diaUsd": 5.0, "falhasSeguidas": 3})
    painel = PainelFalso()
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), AGORA, backend=painel, gasto_dia_fn=lambda _a: 9.0)
    estado = json.loads(st.read_text(encoding="utf-8"))
    assert out["acao"] == "pausa" and "diaUsd" in out["razao"]
    assert estado["pausa"]["estado"] == "orcamento" and not painel.abertos and not estado["sessoes"]


def test_fila_pausada_nao_lanca_e_retomar_apos_subir_teto(tmp_path):
    root, st = _fila(tmp_path, orcamento_cfg={"spUsd": None, "diaUsd": 5.0, "falhasSeguidas": 3})
    kw = {"backend": PainelFalso(), "gasto_dia_fn": lambda _a: 9.0}
    sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), AGORA, **kw)
    assert sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), AGORA, **kw)["acao"] == "pausa"
    kw["retomar"] = True  # teto ainda baixo: continua pausada
    assert sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), AGORA, **kw)["acao"] == "pausa"
    estado = json.loads(st.read_text(encoding="utf-8"))
    estado["orcamento_cfg"]["diaUsd"] = 100.0  # o humano sobe o teto
    st.write_text(json.dumps(estado), encoding="utf-8")
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), AGORA, **kw)
    assert out["acao"] == "lancou" and "pausa" not in json.loads(st.read_text(encoding="utf-8"))


def test_falhas_seguidas_do_orcamento_pausam_em_vez_de_fechar(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "b", folder="Doing")
    make_sp(root, "c")
    st = _estado(tmp_path, concorrencia=2, sessoes={"b": {}}, seguidas=2, orcamento_cfg={"spUsd": None, "diaUsd": None, "falhasSeguidas": 3})
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), AGORA, slug="b", backend=PainelFalso(), gasto_dia_fn=lambda _a: 0.0)
    assert out["acao"] == "pausa" and "falhasSeguidas" in out["razao"]
    assert json.loads(st.read_text(encoding="utf-8"))["falhados"] == ["b"]


def test_sem_orcamento_cfg_comportamento_atual(tmp_path):
    root, st = _fila(tmp_path)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), AGORA, backend=PainelFalso(), gasto_dia_fn=lambda _a: 1e9)
    assert out["acao"] == "lancou"


def test_gasto_dia_sem_kaizen_usage_e_zero(tmp_path):
    assert orc.gasto_dia(AGORA, usage_dir=tmp_path / "inexistente") == 0.0


def test_gasto_dia_soma_so_o_dia_de_hoje(tmp_path):
    usage = tmp_path / "usage"
    usage.mkdir()
    (usage / "kaizen_usage.py").write_text(Path(__file__).resolve().parents[2].joinpath("usage", "kaizen_usage.py").read_text(encoding="utf-8"), encoding="utf-8")
    (usage / "prices.json").write_text(json.dumps({"models": {"m": {"in": 1000000, "out": 0}}}), encoding="utf-8")
    proj = tmp_path / "proj" / "p"
    proj.mkdir(parents=True)
    linha = lambda ts, n: json.dumps({"type": "assistant", "timestamp": ts, "message": {"model": "m", "id": f"i{n}", "usage": {"input_tokens": 1, "output_tokens": 0}}})  # noqa: E731
    (proj / "s1.jsonl").write_text("\n".join([linha("2026-11-23T10:00:00Z", 1), linha("2026-11-22T10:00:00Z", 2)]), encoding="utf-8")
    assert orc.gasto_dia(AGORA, usage_dir=usage, claude_root=str(tmp_path / "proj")) == 1.0


def test_fila_pausa_apos_fecho_de_sp_acima_do_spusd(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "b", folder="Done")
    make_sp(root, "c")
    st = _estado(tmp_path, concorrencia=2, sessoes={"b": {}}, orcamento_cfg={"spUsd": 10.0, "diaUsd": None, "falhasSeguidas": 3})
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), AGORA, slug="b", backend=PainelFalso(), custo_fn=lambda: {"b": 12.0})
    assert out["acao"] == "pausa" and "spUsd" in out["razao"]
    assert json.loads(st.read_text(encoding="utf-8"))["feitos"] == ["b"]
