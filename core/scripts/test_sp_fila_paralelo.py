"""Testes de scripts/sp-fila.py: modo --concorrencia (teto, lançamento por subagent, retoma, sessões mortas)."""
import json
import sys
from datetime import datetime
from pathlib import Path
from sp_fila_testlib import (
    sp_fila,
    make_sp,
    slugs,
    _runner,
    _estado,
)


def test_concorrencia_so_lanca_ate_ao_teto(tmp_path):
    root = tmp_path / "sps"
    for s in ("a", "b", "c"):
        make_sp(root, s)
    calls = []
    st = _estado(tmp_path, concorrencia=2, max=5)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), datetime(2026, 10, 25, 12, 0))
    estado = json.loads(st.read_text(encoding="utf-8"))
    assert out["acao"] == "lancou" and out["slugs"] == ["a", "b"]
    assert list(estado["sessoes"]) == ["a", "b"] and estado["usados"] == 2 * sp_fila.REQ_POR_SP
    flat = [" ".join(map(str, c)) for c in calls]
    assert sum("ensure" in c for c in flat) == 2 and not any("--spawn" in c for c in flat)
    assert not any("--launch" in c or "push" in c for c in flat)
    assert [i["slug"] for i in out["itens"]] == ["a", "b"] and out["itens"][0]["worktree"] == "/wt/sb-a"
    assert estado["sessoes"]["a"]["subagent"] is True and estado["sessoes"]["b"]["worktree"] == "/wt/sb-b"


def test_main_imprime_o_plano_dos_subagents(tmp_path, monkeypatch, capsys):
    st = _estado(tmp_path, concorrencia=2, max=None)
    item = {"slug": "a", "worktree": "/wt/sb-a"}
    monkeypatch.setattr(sp_fila, "seguinte", lambda *a, **k: {"acao": "lancou", "slugs": ["a"], "itens": [item]})
    rc = sp_fila.main(["--seguinte", "--estado", str(st), "--root", str(tmp_path / "sps"), "--relatorios", str(tmp_path / "rel")])
    out = capsys.readouterr().out
    assert rc == 0 and "lançar como subagents · a" in out and "/wt/sb-a" in out


def test_concorrencia_1_e_paralelo_subagent_e_cwd_neutro(tmp_path, monkeypatch):
    root = tmp_path / "sps"
    make_sp(root, "a")
    make_sp(root, "b")
    neutro = tmp_path / "main"
    monkeypatch.setattr(sys.modules["sp_fila_execucao"], "_cwd_neutro", lambda _root: neutro)
    calls = []

    def run(argv, **kw):
        calls.append((argv, kw.get("cwd")))
        return _runner([])(argv)
    st = _estado(tmp_path, concorrencia=1, max=None)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", run, datetime(2026, 10, 25, 12, 0))
    assert out["acao"] == "lancou" and out["slugs"] == ["a"]
    flat = [" ".join(map(str, c[0])) for c in calls]
    assert sum("ensure" in c for c in flat) == 1 and not any("--launch" in c for c in flat)
    assert [c[1] for c in calls if "sp-move.py" in " ".join(map(str, c[0]))] == [neutro]


def test_concorrencia_cheia_espera_e_vaga_lanca_so_uma(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Done")
    make_sp(root, "b", folder="Doing")
    make_sp(root, "c")
    make_sp(root, "d")
    st = _estado(tmp_path, concorrencia=2, max=9, sessoes={"a": {}, "b": {}})
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), datetime(2026, 10, 25, 12, 0), slug="a")
    estado = json.loads(st.read_text(encoding="utf-8"))
    assert out["acao"] == "lancou" and out["slugs"] == ["c"] and list(estado["sessoes"]) == ["b", "c"]
    cheia = _estado(tmp_path, concorrencia=2, max=9, sessoes={"b": {}, "c": {}})
    assert sp_fila.seguinte(root, cheia, tmp_path / "rel", _runner([]), datetime(2026, 10, 25, 12, 0), slug="zz")["acao"] == "espera"


def test_paralelo_ignora_max_e_orcamento(tmp_path):
    root = tmp_path / "sps"
    for s in ("a", "b", "c"):
        make_sp(root, s)
    st = _estado(tmp_path, concorrencia=3, max=None, orcamento=1, usd=0.01, horas=0.0001)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), datetime(2026, 10, 25, 23, 0), custo_fn=lambda: {"a": 99.0})
    assert out["slugs"] == ["a", "b", "c"]


def test_paralelo_respeita_max_explicito(tmp_path):
    root = tmp_path / "sps"
    for s in ("a", "b", "c"):
        make_sp(root, s)
    st = _estado(tmp_path, concorrencia=3, max=2)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), datetime(2026, 10, 25, 12, 0))
    assert out["slugs"] == ["a", "b"]


def test_paralelo_respeita_ate(tmp_path):
    root = tmp_path / "sps"
    for s in ("a", "b"):
        make_sp(root, s)
    calls = []
    st = _estado(tmp_path, concorrencia=2, max=None, ate="10:00")
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), datetime(2026, 10, 25, 12, 0))
    assert out["acao"] == "fim" and "hora limite" in out["motivo"]
    assert not any("sp-move.py" in " ".join(map(str, c)) for c in calls)


def test_lock_livre_durante_o_lancamento(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a")
    st = _estado(tmp_path, concorrencia=1, max=None)
    obtido = []

    def run(argv, **_):
        if "ensure" in argv:
            try:
                with sp_fila.bloqueio(st, espera=0.3):
                    obtido.append(json.loads(st.read_text(encoding="utf-8"))["sessoes"])
            except TimeoutError:
                obtido.append("preso")
        return _runner([])(argv)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", run, datetime(2026, 10, 25, 12, 0))
    assert out["acao"] == "lancou" and obtido and obtido[0] != "preso" and list(obtido[0]) == ["a"]  # slug reservado antes de soltar
    assert list(json.loads(st.read_text(encoding="utf-8"))["sessoes"]) == ["a"]
    assert not Path(f"{st}.lock").exists()


def test_seguinte_durante_o_lancamento_nao_relanca_o_mesmo_sp(tmp_path):
    root = tmp_path / "sps"
    for s in ("a", "b"):
        make_sp(root, s)
    st = _estado(tmp_path, concorrencia=2, max=None)
    calls, internas = [], []

    def run(argv, **_):
        calls.append(argv)
        if "ensure" in argv and "a" in argv and not internas:
            internas.append(sp_fila.seguinte(root, st, tmp_path / "rel", run, datetime(2026, 10, 25, 12, 0), slug="zz"))
        return _runner([])(argv)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", run, datetime(2026, 10, 25, 12, 0))
    spawns = [c[-1] for c in calls if "ensure" in c]
    assert sorted(spawns) == ["a", "b"] and internas[0]["slugs"] == ["b"] and out["acao"] in ("lancou", "espera")
    assert sorted(json.loads(st.read_text(encoding="utf-8"))["sessoes"]) == ["a", "b"]


def test_paralelo_nao_lanca_dependente_de_sp_em_curso(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a")
    make_sp(root, "b", depends_on=["a"])
    st = _estado(tmp_path, concorrencia=3)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), datetime(2026, 10, 25, 12, 0))
    assert out["slugs"] == ["a"]


def test_concorrencia_1_lanca_por_subagent_como_qualquer_paralelo(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a")
    calls = []
    st = _estado(tmp_path, concorrencia=1, max=5)
    sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), datetime(2026, 10, 25, 12, 0))
    flat = [" ".join(map(str, c)) for c in calls]
    assert any("ensure" in c for c in flat) and not any("--launch" in c for c in flat)


def test_sessao_fechada_fora_de_done_vira_falhada_e_a_fila_lanca_a_seguinte(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Doing")
    make_sp(root, "b")
    st = _estado(tmp_path, concorrencia=2, max=9, sessoes={"a": {"subagent": True}})
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), datetime(2026, 10, 25, 12, 0), slug="a")
    estado = json.loads(st.read_text(encoding="utf-8"))
    assert out["acao"] == "lancou" and out["slugs"] == ["b"]
    assert estado["falhados"] == ["a"] and list(estado["sessoes"]) == ["b"]


def test_ensure_falha_worktree_existente_marca_falhado_sem_bloquear_estado(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a")

    def run(argv, **_):
        class R:
            returncode = 1 if "ensure" in argv else 0
            stdout = ""
            stderr = "worktree sb-a já existe"
        return R()
    st = _estado(tmp_path, concorrencia=2, max=9)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", run, datetime(2026, 10, 25, 12, 0))
    assert out["acao"] == "fim" and "worktree sb-a já existe" in out["motivo"]


def test_retoma_apos_crash_nao_relanca_sessoes_registadas(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Doing")
    make_sp(root, "b")
    (tmp_path / "estado.json.123.tmp").write_text("{lixo", encoding="utf-8")  # escrita atómica interrompida
    st = _estado(tmp_path, concorrencia=1, max=9, sessoes={"a": {"subagent": True}})
    calls = []
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), datetime(2026, 10, 25, 12, 0), slug="zz")
    assert out["acao"] == "espera" and calls == []
    assert json.loads(st.read_text(encoding="utf-8"))["sessoes"] == {"a": {"subagent": True}}
