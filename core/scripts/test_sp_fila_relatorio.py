"""Testes de scripts/sp-fila.py: relatório final, gastos e incidentes da vigia."""
import json
from datetime import datetime
from pathlib import Path
from sp_fila_testlib import (
    sp_fila,
    make_sp,
    _runner,
    _estado,
    vivo,
    PARADA,
    _secao_vigia,
    _relatorio_com,
)


def test_relatorio_le_sp_movido_depois_do_load(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a")
    sp = next(s for s, _ in sp_fila.load(root))
    (root / "p" / "sp" / "Doing").mkdir()
    sp.path.rename(root / "p" / "sp" / "Doing" / sp.path.name)
    assert "slug: a" in sp_fila._ler_sp(sp)


def test_gastos_soma_sessoes_sem_limitar():
    estado = {"sessoes": {"a": {}}, "feitos": ["b"], "falhados": ["c"]}
    linhas, total = sp_fila.gastos(estado, {"a": 1.5, "b": 0.25, "x": 9.0})
    assert linhas == [("a", 1.5), ("b", 0.25), ("c", 0.0)] and total == 1.75
    assert "total: 1.75" in sp_fila.render_gastos(estado, {"a": 1.5, "b": 0.25})


def test_cli_gastos_le_o_estado(tmp_path, capsys, monkeypatch):
    st = _estado(tmp_path, sessoes={"a": {}})
    monkeypatch.setattr(sp_fila, "_custos", lambda: {"a": 2.0})
    assert sp_fila.main(["--gastos", "--estado", str(st)]) == 0
    assert "a: 2.00" in capsys.readouterr().out


def test_relatorio_final_inclui_gasto(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Done")
    st = _estado(tmp_path, sessoes={"a": {}})
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), datetime(2026, 10, 25, 12, 0), custo_fn=lambda: {"a": 3.0})
    assert "a: 3.00 USD" in Path(out["relatorio"]).read_text(encoding="utf-8")


def test_relatorio_agrega_gaps_de_reflect_e_falhas(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "ok", folder="Done")
    make_sp(root, "mau", folder="Doing")
    (root / "p" / "sp" / "Done" / "ok.md").write_text(
        "---\nstatus: Done\nslug: ok\nproject: p\npriority: P2\n---\n## Reflect\nReflect DA: correu mal · patch · x.py\nReflect DP: sem patch\n", encoding="utf-8")
    st = _estado(tmp_path, sessoes={"ok": {}, "mau": {}})
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), datetime(2026, 10, 28, 12, 0))
    texto = Path(out["relatorio"]).read_text(encoding="utf-8")
    sec = texto.split("## Reflect (lacunas)")[1].split("\n## ")[0]
    assert "ok: Reflect DA: correu mal" in sec and "sem patch" not in sec
    assert "## Falhas" in texto and "mau: não chegou a Done (fase Doing)" in texto


# --- estado vivo (par-monitor) ---


def test_relatorio_tem_no_maximo_30_linhas(tmp_path):
    root = tmp_path / "sps"
    for i in range(25):
        make_sp(root, f"f{i}", folder="Done")
        make_sp(root, f"x{i}", modo="manual")
    st = _estado(tmp_path, sessoes={f"f{i}": {} for i in range(25)}, max=99)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), datetime(2026, 10, 25, 12, 0))
    texto = Path(out["relatorio"]).read_text(encoding="utf-8")
    assert len(texto.splitlines()) <= 30
    assert "mais" in texto and "## Próximos passos" in texto and "Fim:" in texto


def test_relatorio_vigia_sem_incidentes_diz_nenhum(tmp_path):
    texto = _relatorio_com(tmp_path, vigia={"pid": 1, "ts": "2026-11-06T11:59:00", "incidentes": []})
    assert "- nenhum" in _secao_vigia(texto)


def test_relatorio_vigia_ausente_com_sessoes_avisa(tmp_path):
    assert "sem vigia" in _secao_vigia(_relatorio_com(tmp_path)).lower()


def test_relatorio_vigia_lista_incidentes_gravados(tmp_path):
    inc = ["vigia parou 5 min", "a: PARADA SEM FECHAR"]
    sec = _secao_vigia(_relatorio_com(tmp_path, vigia={"pid": 1, "ts": "2026-11-06T11:59:00", "incidentes": inc}))
    assert "vigia parou 5 min" in sec and "a: PARADA SEM FECHAR" in sec


def test_relatorio_com_vigia_respeita_max_linhas(tmp_path):
    inc = [f"s{i}: morto" for i in range(60)]
    texto = _relatorio_com(tmp_path, vigia={"pid": 1, "ts": "2026-11-06T11:59:00", "incidentes": inc})
    assert len(texto.splitlines()) <= 30 and "mais" in _secao_vigia(texto)


def test_batida_vigia_preserva_incidentes_e_regista_paragem(tmp_path):
    st = _estado(tmp_path, sessoes={"a": {}}, vigia={"pid": 1, "ts": "2026-11-06T11:50:00", "incidentes": ["x"]})
    sp_fila.batida_vigia(st, agora=lambda: datetime(2026, 11, 6, 12, 0, 0))
    v = json.loads(st.read_text(encoding="utf-8"))["vigia"]
    assert v["incidentes"][0] == "x" and any("vigia parou 10 min" in i for i in v["incidentes"])


def test_registar_incidente_acrescenta_sem_duplicar(tmp_path):
    st = _estado(tmp_path)
    sp_fila.registar_incidente(st, "a: morto")
    sp_fila.registar_incidente(st, "a: morto")
    assert json.loads(st.read_text(encoding="utf-8"))["vigia"]["incidentes"] == ["a: morto"]


def test_vigiar_regista_incidente_de_sessao_morta():
    achados = []
    passos = iter([[("a", "morto", "sem processo")]])
    sp_fila.vigiar(lambda: next(passos), 1, lambda s: None, lambda m: None, incidente=achados.append)
    assert achados == ["a: morto"]


def test_vigia_estado_so_com_sessoes_e_vigia_tolera_feitos_ausentes(tmp_path):
    st = tmp_path / "estado.json"
    st.write_text(json.dumps({"sessoes": {}, "vigia": {"pid": 1}}), encoding="utf-8")
    estado = sp_fila.ler(st)
    assert estado["feitos"] == [] and estado["falhados"] == []
    assert estado["vigia"] == {"pid": 1}


# --- relatório na worktree (fila-relatorio-integrado) ---


def test_destino_fora_do_repo_fica_igual(tmp_path):
    from sp_fila_relatorio import destino_relatorio
    chamadas = []
    assert destino_relatorio(tmp_path / "rel", datetime(2026, 11, 7, 12, 0), lambda *a, **k: chamadas.append(a)) == (tmp_path / "rel", None)
    assert chamadas == []


def test_destino_dentro_do_repo_usa_worktree(tmp_path):
    from sp_fila_relatorio import destino_relatorio
    import sp_fila_estado as ee
    wt = tmp_path / "wt"

    class R:
        returncode = 0
        stdout = f"ok{chr(10)}{wt}{chr(10)}"
        stderr = ""
    chamadas = []

    def run(argv, **k):
        chamadas.append(argv)
        return R()
    rel = ee.REPO / "knowledge" / "infra" / "reports" / "sp-fila"
    novo, slug = destino_relatorio(rel, datetime(2026, 11, 7, 12, 0), run)
    assert novo == wt / "knowledge" / "infra" / "reports" / "sp-fila"
    assert slug == "fila-relatorio-2026-11-07-1200"
    assert "ensure" in chamadas[0] and slug in chamadas[0]


def test_commit_md_lista_o_relatorio(tmp_path):
    from sp_fila_relatorio import escrever_commit_md
    rel = tmp_path / "knowledge" / "infra" / "reports" / "sp-fila" / "fila-x.md"
    rel.parent.mkdir(parents=True)
    rel.write_text("x", encoding="utf-8")
    p = escrever_commit_md(tmp_path, rel, datetime(2026, 11, 7, 12, 0))
    t = p.read_text(encoding="utf-8")
    assert p.parent == tmp_path and p.name.startswith("COMMIT_")
    assert "git add knowledge/infra/reports/sp-fila/fila-x.md" in t and "vault:" in t


# --- fc-robustez: cenários de falha do modo --concorrencia ---
