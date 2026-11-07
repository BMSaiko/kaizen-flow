"""Testes de scripts/sp-fila.py: modo sequencial (--seguinte, falhas seguidas, worktree)."""
import json
from datetime import datetime
from pathlib import Path
from sp_fila_testlib import (
    sp_fila,
    make_sp,
    _runner,
    _estado,
    _arvore,
    _runner_worktree,
)


def test_seguinte_lanca_primeiro_move_para_doing_e_nao_faz_push(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a")
    calls = []
    st = _estado(tmp_path)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), datetime(2026, 10, 25, 12, 0))
    assert out["acao"] == "lancou" and out["slug"] == "a"
    flat = [" ".join(map(str, c)) for c in calls]
    assert any("sp-move.py" in c and "doing" in c for c in flat)
    assert any("sp-handoff.py" in c and "--launch" in c and "--auto" in c for c in flat)
    assert not any("push" in c for c in flat)
    assert list(json.loads(st.read_text(encoding="utf-8"))["sessoes"]) == ["a"]
    assert json.loads(st.read_text(encoding="utf-8"))["usados"] == sp_fila.REQ_POR_SP


def test_seguinte_regista_feito_e_falhado_e_nao_avanca_dependentes(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Done")
    make_sp(root, "b", folder="Doing")
    make_sp(root, "dep-b", depends_on=["b"])
    make_sp(root, "livre", priority="P3")
    calls = []
    st = _estado(tmp_path, sessoes={"b": {}}, feitos=["a"])
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), datetime(2026, 10, 25, 12, 0))
    estado = json.loads(st.read_text(encoding="utf-8")) if st.exists() else {}
    assert out["slug"] == "livre"
    assert estado["falhados"] == ["b"]
    assert list(estado["sessoes"]) == ["livre"]


def test_seguinte_fim_escreve_relatorio_e_apaga_estado(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Done")
    make_sp(root, "excl", modo="manual")
    calls = []
    st = _estado(tmp_path, sessoes={"a": {}})
    rel = tmp_path / "rel"
    out = sp_fila.seguinte(root, st, rel, _runner(calls), datetime(2026, 10, 25, 12, 0))
    assert out["acao"] == "fim"
    assert not st.exists()
    texto = Path(out["relatorio"]).read_text(encoding="utf-8")
    assert "a" in texto and "excl" in texto and "Próximos passos" in texto
    assert all(c[0] == "git" and c[3] == "log" for c in calls)


def test_seguinte_limite_para_e_reporta(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Done")
    make_sp(root, "b")
    calls = []
    st = _estado(tmp_path, sessoes={"a": {}}, max=1)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), datetime(2026, 10, 25, 12, 0))
    assert out["acao"] == "fim" and "máximo" in out["motivo"]
    assert all(c[0] == "git" and c[3] == "log" for c in calls)
    assert "b" in Path(out["relatorio"]).read_text(encoding="utf-8")


def test_e2e_para_no_limite_grava_progresso_e_retoma(tmp_path):
    root = tmp_path / "sps"
    _arvore(root, {"orcamento_requests": 100})
    st = _estado(tmp_path, max=9, orcamento=100, programa="mae", horas=None, usd=None)
    agora, calls = datetime(2026, 10, 25, 12, 0), []
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), agora)
    assert out["slug"] == "f1"
    make_sp(root, "f1", folder="Done", extra={"parent": "mae"})  # sessão f1 fechou
    (root / "p" / "sp" / "TODO" / "f1.md").unlink()
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), agora)
    assert out["slug"] == "f2"
    make_sp(root, "f2", folder="Done", extra={"parent": "mae"})
    (root / "p" / "sp" / "TODO" / "f2.md").unlink()
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), agora)  # 100 usados: sem espaço para f3
    assert out["acao"] == "fim" and "orçamento" in out["motivo"] and not st.exists()
    mae = (root / "p" / "sp" / "TODO" / "mae.md").read_text(encoding="utf-8")
    assert "## Progresso" in mae and "- f1" in mae and "- f2" in mae and "- f3" in mae
    assert "fora" not in mae
    # retoma: nova corrida, f1/f2 ficam Done, só f3 por correr
    st2 = _estado(tmp_path, max=9, orcamento=100, programa="mae", horas=None, usd=None)
    assert sp_fila.seguinte(root, st2, tmp_path / "rel", _runner(calls), agora)["slug"] == "f3"


def test_estado_antigo_com_lancado_migra_para_sessoes(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Done")
    make_sp(root, "b")
    antigo = {"max": 3, "ate": None, "orcamento": 200, "usados": 50, "feitos": [], "falhados": [], "lancado": "a",
              "projeto": None, "inicio": "2026-10-25T10:00:00"}
    st = tmp_path / "estado.json"
    st.write_text(json.dumps(antigo), encoding="utf-8")
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), datetime(2026, 10, 25, 12, 0))
    estado = json.loads(st.read_text(encoding="utf-8"))
    assert out["slug"] == "b" and estado["feitos"] == ["a"]
    assert "lancado" not in estado and list(estado["sessoes"]) == ["b"]


def test_seguinte_com_slug_so_fecha_essa_sessao_e_espera_pelas_outras(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Done")
    make_sp(root, "b", folder="Doing")
    make_sp(root, "c")
    st = _estado(tmp_path, sessoes={"a": {}, "b": {}})
    calls = []
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), datetime(2026, 10, 25, 12, 0), slug="a")
    estado = json.loads(st.read_text(encoding="utf-8"))
    assert out["acao"] == "espera" and estado["feitos"] == ["a"] and list(estado["sessoes"]) == ["b"]
    assert calls == [] and st.exists()


def test_limite_falhas_seguidas_para_com_motivo():
    estado = {"max": 9, "ate": None, "orcamento": None, "usados": 0, "feitos": [], "falhados": ["a", "b"], "seguidas": 2, "max_falhas": 2}
    assert "falhas seguidas" in sp_fila.limite(estado, datetime(2026, 10, 25, 12, 0))
    estado["seguidas"] = 1
    assert sp_fila.limite(estado, datetime(2026, 10, 25, 12, 0)) is None


def test_seguidas_conta_falhas_e_um_feito_repoe_a_zero(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "mau", folder="Doing")
    make_sp(root, "bom", folder="Done")
    make_sp(root, "livre")
    st = _estado(tmp_path, sessoes={"mau": {}}, max=9, max_falhas=3, seguidas=0)
    sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), datetime(2026, 10, 25, 12, 0), slug="mau")
    assert json.loads(st.read_text(encoding="utf-8"))["seguidas"] == 1
    estado = json.loads(st.read_text(encoding="utf-8"))
    estado["sessoes"] = {"bom": {}}
    st.write_text(json.dumps(estado), encoding="utf-8")
    sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), datetime(2026, 10, 25, 12, 0), slug="bom")
    assert json.loads(st.read_text(encoding="utf-8"))["seguidas"] == 0


def test_falhas_seguidas_param_a_fila_e_nao_lancam(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "mau", folder="Doing")
    make_sp(root, "livre")
    calls = []
    st = _estado(tmp_path, sessoes={"mau": {}}, max=9, max_falhas=1, seguidas=0)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), datetime(2026, 10, 25, 12, 0))
    assert out["acao"] == "fim" and "falhas seguidas" in out["motivo"]
    assert all(c[0] == "git" for c in calls)


def test_paralelo_tambem_para_nas_falhas_seguidas(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "mau", folder="Doing")
    make_sp(root, "livre")
    calls = []
    st = _estado(tmp_path, sessoes={"mau": {}}, concorrencia=2, max_falhas=1, seguidas=0)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), datetime(2026, 10, 25, 12, 0), slug="mau")
    assert out["acao"] == "fim" and "falhas seguidas" in out["motivo"]


def test_seguinte_recusa_fechar_sp_done_so_na_worktree(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Doing")
    wt = tmp_path / "a"
    make_sp(wt, "a", folder="Done")
    calls = []
    st = _estado(tmp_path, sessoes={"a": {}})
    antes = st.read_text(encoding="utf-8")
    try:
        sp_fila.seguinte(root, st, tmp_path / "rel", _runner_worktree(calls, wt), datetime(2026, 10, 25, 12, 0), slug="a")
    except sp_fila.IntegracaoPendente as e:
        assert "sb-worktree.py merge a" in str(e)
    else:
        raise AssertionError("devia recusar: Done só na worktree")
    assert st.read_text(encoding="utf-8") == antes
    assert not any("handoff" in " ".join(map(str, c)) for c in calls)


def test_seguinte_sp_ja_integrado_continua_a_avancar(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Done")
    make_sp(root, "b")
    wt = tmp_path / "a"
    make_sp(wt, "a", folder="Done")
    st = _estado(tmp_path, sessoes={"a": {}})
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner_worktree([], wt), datetime(2026, 10, 25, 12, 0), slug="a")
    assert out["acao"] == "lancou" and out["slug"] == "b"


def test_seguinte_nunca_relanca_sp_ja_doing_nem_ja_lancado(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Doing")
    make_sp(root, "b")
    calls = []
    st = _estado(tmp_path, feitos=["b"])
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), datetime(2026, 10, 25, 12, 0))
    assert out["acao"] == "fim"
    assert not any("sp-handoff.py" in " ".join(map(str, c)) for c in calls)


# --- relatório integrado com a vigia (fila-relatorio-integrado) ---
