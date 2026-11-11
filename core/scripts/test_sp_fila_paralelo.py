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


def test_concorrencia_1_sp_move_doing_corre_na_worktree_do_filho(tmp_path):
    """Prova real falhou (problema 4): o `sp-move doing` corria no checkout de master; tem de ser o script da worktree, com cwd lá."""
    root = tmp_path / "sps"
    make_sp(root, "a")
    make_sp(root, "b")
    calls = []

    def run(argv, **kw):
        calls.append((argv, kw.get("cwd")))
        return _runner([])(argv)
    st = _estado(tmp_path, concorrencia=1, max=None)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", run, datetime(2026, 10, 25, 12, 0))
    assert out["acao"] == "lancou" and out["slugs"] == ["a"]
    flat = [" ".join(map(str, c[0])) for c in calls]
    assert sum("ensure" in c for c in flat) == 1 and not any("--launch" in c for c in flat)
    moves = [c for c in calls if "sp-move.py" in " ".join(map(str, c[0]))]
    assert len(moves) == 1
    argv, cwd = moves[0]
    assert Path(cwd) == Path("/wt/sb-a") and Path(argv[2]) == Path("/wt/sb-a") / "scripts" / "sp-move.py"
    assert str(sys.modules["sp_fila_execucao"].SCRIPTS) not in " ".join(map(str, argv))


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


def test_paralelo_faz_ensure_antes_do_sp_move_para_doing(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a")
    calls = []
    st = _estado(tmp_path, concorrencia=1, max=None)
    sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), datetime(2026, 10, 25, 12, 0))
    flat = [" ".join(map(str, c)) for c in calls]
    i_ensure = next(i for i, c in enumerate(flat) if "ensure" in c)
    i_move = next(i for i, c in enumerate(flat) if "sp-move.py" in c)
    assert i_ensure < i_move


# --- modo da mãe (`execucao:`): sequencial / paralelo ---

def _prog(root, execucao="", filhos=(("a", ()), ("b", ("a",)), ("c", ("b",)))):
    make_sp(root, "mae", kind="program", modo="manual", extra={"execucao": execucao} if execucao else None)
    for s, deps in filhos:
        make_sp(root, s, depends_on=list(deps) or None, extra={"parent": "mae"})


def _fechar(root, slug, folder="Done"):
    src = next((root / "p" / "sp").glob(f"*/{slug}.md"))
    dst = root / "p" / "sp" / folder / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.replace(dst)


def _main_programa(tmp_path, monkeypatch, *extra):
    visto = {}
    monkeypatch.setattr(sp_fila, "seguinte", lambda *a, **k: visto.setdefault("ok", {"acao": "espera", "sessoes": []}))
    st = tmp_path / "estado.json"
    rc = sp_fila.main(["--programa", "mae", "--estado", str(st), "--root", str(tmp_path / "sps"),
                       "--relatorios", str(tmp_path / "rel"), *extra])
    return rc, (json.loads(st.read_text(encoding="utf-8")) if st.exists() else None)


def test_programa_sem_execucao_recusa_com_comando(tmp_path, monkeypatch, capsys):
    _prog(tmp_path / "sps")
    rc, estado = _main_programa(tmp_path, monkeypatch)
    assert rc == 1 and estado is None
    assert "modo por escolher: sp-execucao.py mae sequencial|paralelo" in capsys.readouterr().err


def test_programa_sequencial_e_um_de_cada_vez(tmp_path, monkeypatch):
    _prog(tmp_path / "sps", "sequencial")
    rc, estado = _main_programa(tmp_path, monkeypatch)
    assert rc == 0 and estado["modo"] == "sequencial" and estado["concorrencia"] == 1 and estado["max"] is None


def test_programa_paralelo_teto_3(tmp_path, monkeypatch):
    _prog(tmp_path / "sps", "paralelo")
    rc, estado = _main_programa(tmp_path, monkeypatch)
    assert rc == 0 and estado["modo"] == "paralelo" and estado["concorrencia"] == sp_fila.MAX_PARALELO == 3


def test_concorrencia_acima_de_3_recusa(tmp_path, monkeypatch, capsys):
    rc = sp_fila.main(["--concorrencia", "4", "--estado", str(tmp_path / "e.json"), "--root", str(tmp_path / "sps")])
    assert rc == 1 and "máx. 3" in capsys.readouterr().err


def test_sequencial_cadeia_de_3_fecha_a_mae(tmp_path):
    root = tmp_path / "sps"
    _prog(root, "sequencial")
    st = _estado(tmp_path, concorrencia=1, max=None, modo="sequencial", programa="mae", projeto="p")
    t = datetime(2026, 11, 10, 12, 0)
    ordem = []
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), t)
    while out["acao"] == "lancou":
        assert len(out["itens"]) == 1
        ordem.append(out["slug"])
        _fechar(root, out["slug"])
        out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), t, slug=out["slug"])
    assert ordem == ["a", "b", "c"] and out["acao"] == "fim" and out["fechar_mae"] == "mae"
    rel = Path(out["relatorio"]).read_text(encoding="utf-8")
    mae = next((root / "p" / "sp").glob("*/mae.md")).read_text(encoding="utf-8")
    assert "Modo: sequencial" in rel and "Modo: sequencial" in mae


def test_sequencial_falha_a_meio_para_a_cadeia(tmp_path):
    root = tmp_path / "sps"
    _prog(root, "sequencial", filhos=(("a", ()), ("b", ("a",)), ("x", ())))
    st = _estado(tmp_path, concorrencia=1, max=None, modo="sequencial", programa="mae", projeto="p")
    t = datetime(2026, 11, 10, 12, 0)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), t)
    assert out["slugs"] == ["a"]
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), t, slug="a")  # a não chegou a Done
    assert out["acao"] == "fim" and "cadeia parada" in out["motivo"] and not out.get("fechar_mae")
    rel = Path(out["relatorio"]).read_text(encoding="utf-8")
    assert "por correr: `b`" in rel and "por correr: `x`" in rel


def test_paralelo_5_filhos_teto_3_e_vagas_por_dependencia(tmp_path):
    root = tmp_path / "sps"
    _prog(root, "paralelo", filhos=(("a", ()), ("b", ()), ("c", ()), ("d", ()), ("e", ("a",))))
    st = _estado(tmp_path, concorrencia=3, max=None, modo="paralelo", programa="mae", projeto="p")
    t = datetime(2026, 11, 10, 12, 0)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), t)
    assert out["slugs"] == ["a", "b", "c"]
    vivos, lancados = set(out["slugs"]), list(out["slugs"])
    for fecha in ("b", "a", "c", "d", "e"):
        _fechar(root, fecha)
        vivos.discard(fecha)
        out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), t, slug=fecha)
        if out["acao"] == "lancou":
            vivos |= set(out["slugs"])
            lancados += out["slugs"]
            if "e" in out["slugs"]:
                assert lancados.index("a") < lancados.index("e") and "a" not in vivos
        assert len(vivos) <= 3
    assert lancados.index("d") == 3 and sorted(lancados) == ["a", "b", "c", "d", "e"]
    assert out["acao"] == "fim" and out["fechar_mae"] == "mae"
    assert "Modo: paralelo" in Path(out["relatorio"]).read_text(encoding="utf-8")


def test_paralelo_falha_a_meio_so_corta_os_dependentes(tmp_path):
    root = tmp_path / "sps"
    _prog(root, "paralelo", filhos=(("a", ()), ("b", ()), ("e", ("a",))))
    st = _estado(tmp_path, concorrencia=3, max=None, modo="paralelo", programa="mae", projeto="p")
    t = datetime(2026, 11, 10, 12, 0)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), t)
    assert out["slugs"] == ["a", "b"]
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), t, slug="a")  # falhou
    assert out["acao"] == "espera"
    _fechar(root, "b")
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), t, slug="b")
    assert out["acao"] == "fim" and not out.get("fechar_mae")
    rel = Path(out["relatorio"]).read_text(encoding="utf-8")
    assert "- b" in rel and "por correr: `e`" in rel


def test_progresso_da_mae_vai_para_a_worktree_dela_nunca_master(tmp_path, monkeypatch):
    """Prova real: o `## Progresso` sujava a mãe em master e partia o merge dela."""
    ex = sys.modules["sp_fila_execucao"]
    repo = tmp_path / "repo"
    root = repo / "sps"
    _prog(root, "sequencial", filhos=(("a", ()),))
    wt = tmp_path / "wt-mae"
    copia = wt / "sps" / "p" / "sp" / "TODO" / "mae.md"
    copia.parent.mkdir(parents=True)
    copia.write_text("---\nslug: mae\n---\n", encoding="utf-8")
    monkeypatch.setattr(ex, "REPO", repo)
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        r = _runner([])(argv)
        if "ensure" in argv and argv[-1] == "mae":
            r.stdout = f"{wt}\n"
        return r
    st = _estado(tmp_path, concorrencia=1, max=None, modo="sequencial", programa="mae", projeto="p", sessoes={"a": {}})
    _fechar(root, "a")
    out = sp_fila.seguinte(root, st, tmp_path / "rel", run, datetime(2026, 11, 10, 12, 0), slug="a")
    assert out["acao"] == "fim" and out["fechar_mae"] == "mae"
    assert "## Progresso" in copia.read_text(encoding="utf-8")
    assert "## Progresso" not in (root / "p" / "sp" / "TODO" / "mae.md").read_text(encoding="utf-8")
