"""Testes de scripts/sp-fila.py (planeador, limites, passo seguinte; fixtures em ficheiros temporários)."""
import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

_spec = importlib.util.spec_from_file_location("sp_fila", Path(__file__).with_name("sp-fila.py"))
sp_fila = importlib.util.module_from_spec(_spec)
sys.modules["sp_fila"] = sp_fila
_spec.loader.exec_module(sp_fila)


def make_sp(root, slug, folder="TODO", project="p", priority="P2", created="2026-10-01T10:00:00Z", modo="auto",
            gates=True, depends_on=None, kind=None, extra=None):
    path = root / project / "sp" / folder / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"status: {folder}", f"created: {created}", f"updated: {created}", f"slug: {slug}", f"project: {project}",
             f"priority: {priority}"]
    if modo:
        lines.append(f"modo: {modo}")
    if depends_on:
        lines.append(f"depends_on: [{', '.join(depends_on)}]")
    if kind:
        lines.append(f"kind: {kind}")
    for k, v in (extra or {}).items():
        lines.append(f"{k}: {v}")
    if gates:
        lines += ["gates:", "  - cmd: echo ok"]
    lines += ["---", "# corpo"]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def plan(root, **kw):
    return sp_fila.plan(sp_fila.load(root, kw.pop("project", None)), **kw)


def slugs(result):
    return [sp.slug for sp in result[0]]


def reasons(result):
    return {slug: why for slug, why in result[1]}


def test_ordem_prioridade_depois_idade(tmp_path):
    make_sp(tmp_path, "c", priority="P2", created="2026-10-02T00:00:00Z")
    make_sp(tmp_path, "b", priority="P2", created="2026-10-01T00:00:00Z")
    make_sp(tmp_path, "a", priority="P1", created="2026-10-09T00:00:00Z")
    assert slugs(plan(tmp_path)) == ["a", "b", "c"]


def test_dependencia_manda_sobre_prioridade(tmp_path):
    make_sp(tmp_path, "base", priority="P3")
    make_sp(tmp_path, "topo", priority="P1", depends_on=["base"])
    assert slugs(plan(tmp_path)) == ["base", "topo"]


def test_dependencia_ja_done_nao_bloqueia(tmp_path):
    make_sp(tmp_path, "feito", folder="Done")
    make_sp(tmp_path, "x", depends_on=["feito"])
    assert slugs(plan(tmp_path)) == ["x"]


def test_exclui_manual_e_sem_modo(tmp_path):
    make_sp(tmp_path, "m", modo="manual")
    make_sp(tmp_path, "s", modo=None)
    r = plan(tmp_path)
    assert slugs(r) == []
    assert "modo" in reasons(r)["m"] and "modo" in reasons(r)["s"]


def test_exclui_sem_gates(tmp_path):
    make_sp(tmp_path, "g", gates=False)
    assert "gates" in reasons(plan(tmp_path))["g"]


def test_exclui_dependencia_em_falta_e_cascata(tmp_path):
    make_sp(tmp_path, "a", depends_on=["inexistente"])
    make_sp(tmp_path, "b", depends_on=["a"])
    r = plan(tmp_path)
    assert slugs(r) == []
    assert "dependência" in reasons(r)["a"] and "dependência" in reasons(r)["b"]


def test_dependencia_em_sp_manual_exclui(tmp_path):
    make_sp(tmp_path, "m", modo="manual")
    make_sp(tmp_path, "x", depends_on=["m"])
    assert "dependência" in reasons(plan(tmp_path))["x"]


def test_ciclo(tmp_path):
    make_sp(tmp_path, "a", depends_on=["b"])
    make_sp(tmp_path, "b", depends_on=["a"])
    make_sp(tmp_path, "ok")
    r = plan(tmp_path)
    assert slugs(r) == ["ok"]
    assert "ciclo" in reasons(r)["a"] and "ciclo" in reasons(r)["b"]


def test_exclui_doing_programa_e_done(tmp_path):
    make_sp(tmp_path, "em-curso", folder="Doing")
    make_sp(tmp_path, "mae", kind="program")
    make_sp(tmp_path, "feito", folder="Done")
    r = plan(tmp_path)
    assert slugs(r) == []
    assert "Doing" in reasons(r)["em-curso"] and "programa" in reasons(r)["mae"]
    assert "feito" not in reasons(r)


def test_autorizacao_insuficiente(tmp_path):
    make_sp(tmp_path, "pp", extra={"push": "pergunta"})
    make_sp(tmp_path, "pc", extra={"commit": "nunca", "push": "auto"})
    make_sp(tmp_path, "pr", extra={"commit": "auto", "push": "pergunta", "pr": "auto"})
    make_sp(tmp_path, "ok", extra={"commit": "auto", "push": "auto", "pr": "auto"})
    make_sp(tmp_path, "nunca", extra={"commit": "nunca", "push": "nunca", "pr": "nunca"})
    r = plan(tmp_path)
    assert sorted(slugs(r)) == ["nunca", "ok"]
    for s in ("pp", "pc", "pr"):
        assert "autorização" in reasons(r)[s]


def test_filtro_projeto(tmp_path):
    make_sp(tmp_path, "a", project="p1")
    make_sp(tmp_path, "b", project="p2")
    assert slugs(plan(tmp_path, project="p2")) == ["b"]


def test_max_corta_a_lista(tmp_path):
    for s in "abc":
        make_sp(tmp_path, s)
    assert slugs(plan(tmp_path, maximo=2)) == ["a", "b"]


def test_limite_razoes():
    estado = {"max": 2, "ate": "18:00", "orcamento": 100, "usados": 0, "feitos": ["a", "b"], "falhados": []}
    noon = datetime(2026, 10, 25, 12, 0)
    assert "máximo" in sp_fila.limite(estado, noon)
    estado = {"max": 5, "ate": "18:00", "orcamento": 100, "usados": 0, "feitos": [], "falhados": []}
    assert sp_fila.limite(estado, datetime(2026, 10, 25, 18, 0)) and "hora" in sp_fila.limite(estado, datetime(2026, 10, 25, 18, 0))
    assert sp_fila.limite(estado, noon) is None
    estado["usados"] = 60
    estado["orcamento"] = 100
    assert "orçamento" in sp_fila.limite(estado, noon)


def test_sem_orcamento_de_requests_nao_ha_limite():
    estado = {"max": 5, "ate": None, "orcamento": None, "usados": 9999, "feitos": [], "falhados": []}
    assert sp_fila.limite(estado, datetime(2026, 10, 25, 12, 0)) is None


def _runner(calls):
    def run(argv, **_):
        calls.append(argv)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()
    return run


def _estado(tmp_path, **over):
    base = {"max": 3, "ate": None, "orcamento": 200, "usados": 0, "feitos": [], "falhados": [], "saltados": [],
            "sessoes": {}, "projeto": None, "inicio": "2026-10-25T10:00:00", "commits": []}
    base.update(over)
    f = tmp_path / "estado.json"
    f.write_text(json.dumps(base), encoding="utf-8")
    return f


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


def test_cli_dry_run_mostra_ordem_e_exclusoes(tmp_path, capsys):
    make_sp(tmp_path, "um", priority="P1")
    make_sp(tmp_path, "man", modo="manual")
    rc = sp_fila.main(["--dry-run", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0 and "um" in out and "man" in out and "modo" in out


def _arvore(root, mae_extra):
    make_sp(root, "mae", kind="program", modo="manual", extra=mae_extra)
    for s in ("f1", "f2", "f3"):
        make_sp(root, s, extra={"parent": "mae"})
    make_sp(root, "fora")


def test_programa_restringe_a_arvore(tmp_path):
    _arvore(tmp_path, {})
    items = sp_fila.load(tmp_path)
    assert slugs(sp_fila.plan(items, so=sp_fila.descendentes(items, "mae"))) == ["f1", "f2", "f3"]


def test_orcamento_tempo_e_custo_em_limite():
    base = {"max": 9, "ate": None, "orcamento": 999, "usados": 0, "feitos": [], "falhados": [],
            "inicio": "2026-10-25T10:00:00", "horas": 2.0, "usd": 5.0}
    assert "tempo" in sp_fila.limite(base, datetime(2026, 10, 25, 12, 0))
    assert sp_fila.limite(base, datetime(2026, 10, 25, 11, 0)) is None
    assert "custo" in sp_fila.limite(base, datetime(2026, 10, 25, 11, 0), custo=5.0)


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


def test_dois_escritores_simultaneos_nao_perdem_registos(tmp_path):
    import threading
    st = _estado(tmp_path)

    def escreve(prefixo):
        for i in range(15):
            sp_fila.atualizar(st, lambda e, k=f"{prefixo}{i}": e["sessoes"].update({k: {}}))

    ts = [threading.Thread(target=escreve, args=(p,)) for p in "xy"]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(json.loads(st.read_text(encoding="utf-8"))["sessoes"]) == 30


def test_permission_error_ao_libertar_bloqueio_e_tentado_de_novo(tmp_path, monkeypatch):
    # Windows: antivírus/indexador seguram o .lock; unlink falha com PermissionError e não pode matar o escritor
    st = _estado(tmp_path)
    real, falhas = Path.unlink, []

    def unlink_instavel(self, *a, **k):
        if str(self).endswith(".lock") and len(falhas) < 3:
            falhas.append(self)
            raise PermissionError(13, "Acesso negado")
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", unlink_instavel)
    sp_fila.atualizar(st, lambda e: e["sessoes"].update({"w": {}}))
    assert len(falhas) == 3 and not Path(f"{st}.lock").exists()


def test_permission_error_ao_criar_bloqueio_e_tentado_de_novo(tmp_path, monkeypatch):
    # Windows devolve PermissionError (não FileExistsError) enquanto o dono apaga o .lock
    st = _estado(tmp_path)
    real, falhas = sp_fila.os.open, []

    def open_instavel(p, *a, **k):
        if str(p).endswith(".lock") and len(falhas) < 3:
            falhas.append(p)
            raise PermissionError(13, "Acesso negado")
        return real(p, *a, **k)

    monkeypatch.setattr(sp_fila.os, "open", open_instavel)
    sp_fila.atualizar(st, lambda e: e["sessoes"].update({"w": {}}))
    assert len(falhas) == 3 and "w" in json.loads(st.read_text(encoding="utf-8"))["sessoes"]


def test_permission_error_no_replace_e_tentado_de_novo(tmp_path, monkeypatch):
    # Windows: os.replace falha enquanto um leitor sem bloqueio tem o estado aberto
    st = _estado(tmp_path)
    real, falhas = sp_fila.os.replace, []

    def replace_instavel(a, b):
        if len(falhas) < 3:
            falhas.append(a)
            raise PermissionError(13, "Acesso negado")
        return real(a, b)

    monkeypatch.setattr(sp_fila.os, "replace", replace_instavel)
    sp_fila.atualizar(st, lambda e: e["sessoes"].update({"w": {}}))
    assert len(falhas) == 3 and "w" in json.loads(st.read_text(encoding="utf-8"))["sessoes"]


def test_bloqueio_antigo_e_removido_e_escrita_e_atomica(tmp_path):
    import os
    st = _estado(tmp_path)
    lock = Path(f"{st}.lock")
    lock.write_text("morto", encoding="utf-8")
    os.utime(lock, (0, 0))
    sp_fila.atualizar(st, lambda e: e["sessoes"].update({"z": {}}))
    assert not lock.exists() and "z" in json.loads(st.read_text(encoding="utf-8"))["sessoes"]
    assert not list(tmp_path.glob("*.tmp"))


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
    assert sum("--spawn" in c and "--sem-registo" in c for c in flat) == 2
    assert not any("--launch" in c or "push" in c for c in flat)


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
    st = _estado(tmp_path, concorrencia=3, max=1, orcamento=1, usd=0.01, horas=0.0001)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), datetime(2026, 10, 25, 23, 0), custo_fn=lambda: {"a": 99.0})
    assert out["slugs"] == ["a", "b", "c"]


def test_paralelo_nao_lanca_dependente_de_sp_em_curso(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a")
    make_sp(root, "b", depends_on=["a"])
    st = _estado(tmp_path, concorrencia=3)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), datetime(2026, 10, 25, 12, 0))
    assert out["slugs"] == ["a"]


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

AGORA = datetime(2026, 10, 29, 12, 0, 0)
RECENTE = datetime(2026, 10, 29, 11, 58, 0)
VELHA = datetime(2026, 10, 29, 11, 30, 0)


def vivo(sp_status="Doing", paineis=("7",), painel="7", ecra="working...", atividade=RECENTE, inatividade_s=600):
    return sp_fila.classificar({"painel": painel}, sp_status, set(paineis), ecra, atividade, AGORA, inatividade_s)[0]


def test_vivo_a_correr():
    assert vivo() == "a correr"


def test_vivo_fechado_quando_sp_done_mesmo_sem_painel():
    assert vivo(sp_status="Done", paineis=()) == "fechado"


def test_vivo_morto_sem_painel_ou_painel_desaparecido():
    assert vivo(painel=None) == "morto"
    assert vivo(paineis=("9",)) == "morto"


def test_vivo_bloqueado_por_pergunta_de_permissao():
    assert vivo(ecra="Do you want to proceed?\n❯ 1. Yes\n  2. No") == "bloqueado"


def test_vivo_bloqueado_por_inatividade():
    assert vivo(atividade=VELHA) == "bloqueado"


def _arranque(**sessao):
    return sp_fila.classificar(sessao, "Doing", {"7"}, sessao.pop("ecra", ""), RECENTE, AGORA)[0]


def test_vivo_a_arrancar_sem_painel_registado_ou_sem_prompt():
    assert _arranque(inicio="2026-10-29T11:59:30") == "a arrancar"
    assert _arranque(painel="7", inicio="2026-10-29T11:59:30", ecra="Welcome to Claude Code") == "a arrancar"
    assert _arranque(painel="7", inicio="2026-10-29T11:59:30", ecra="❯ ") == "a correr"
    assert _arranque(inicio="2026-10-29T11:00:00") == "morto"


def test_painel_lancado_le_a_linha_do_spawn():
    assert sp_fila._painel_lancado("a", "x\na: painel 9 em C:\\wt\\sb-a\n") == {"painel": "9", "worktree": "C:\\wt\\sb-a"}
    assert sp_fila._painel_lancado("a", "a: painel - em C:\\wt") == {} and sp_fila._painel_lancado("a", None) == {}


def test_vivo_inatividade_configuravel():
    assert vivo(atividade=VELHA, inatividade_s=3600) == "a correr"


def test_estado_vivo_le_paineis_ecra_e_git_sem_escrever(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Doing")
    make_sp(root, "b", folder="Done")
    estado = {"sessoes": {"a": {"painel": "7", "worktree": str(tmp_path), "inicio": "2026-10-29T11:59:00"},
                          "b": {"painel": "8", "worktree": str(tmp_path), "inicio": "2026-10-29T11:00:00"}}}
    chamadas = []

    class R:
        def __init__(self, out):
            self.stdout = out

    def run(argv, **kw):
        chamadas.append(argv)
        if argv[:3] == ["wezterm", "cli", "list"]:
            return R(json.dumps([{"pane_id": 7}]))
        if "get-text" in argv:
            return R("working...\n❯ ")
        return R("")

    linhas = sp_fila.estado_vivo(estado, sp_fila.load(root), run, AGORA, 600)
    assert [(n, e) for n, e, _ in linhas] == [("a", "a correr"), ("b", "fechado")]
    assert all(c[0] in ("wezterm", "git") and c[:3] != ["wezterm", "cli", "send-text"] for c in chamadas)


def test_cli_estado_vivo_sem_fila_falha(tmp_path, capsys):
    rc = sp_fila.main(["--estado-vivo", "--estado", str(tmp_path / "x.json"), "--root", str(tmp_path)])
    assert rc == 1
    assert "sem fila" in capsys.readouterr().err


def test_estado_vivo_sessao_de_formato_antigo_sem_painel_nem_inicio(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Doing")
    estado = sp_fila.migrar({"lancado": "a", "inicio": "2026-10-26T17:16:15"})

    class R:
        stdout = "[]"

    linhas = sp_fila.estado_vivo(estado, sp_fila.load(root), lambda argv, **kw: R(), AGORA, 600)
    assert [(n, e) for n, e, _ in linhas] == [("a", "morto")]


# --- vigilância ativa (par-vigilancia-ativa) ---

def test_vigiar_imprime_so_as_mudancas_e_sai_quando_todas_terminam():
    passos = iter([
        [("a", "a arrancar", "painel ainda não aberto")],
        [("a", "a arrancar", "painel ainda não aberto")],
        [("a", "a correr", "")],
        [("a", "bloqueado", "à espera de resposta: Do you want to proceed?")],
        [("a", "bloqueado", "à espera de resposta: Do you want to proceed?")],
        [("a", "fechado", "SP em Done")],
    ])
    saida, esperas = [], []
    rc = sp_fila.vigiar(lambda: next(passos), 30, esperas.append, saida.append)
    assert rc == 0 and len(esperas) == 5 and set(esperas) == {30}
    assert saida == ["a · arrancou · painel ainda não aberto", "a · a correr",
                     "a · À ESPERA DE RESPOSTA · à espera de resposta: Do you want to proceed?", "a · terminou · SP em Done"]


def test_vigiar_sai_quando_a_fila_desaparece_e_com_varias_sessoes():
    passos = iter([[("a", "a correr", ""), ("b", "a arrancar", "")], [("a", "fechado", "x"), ("b", "morto", "painel inexistente")]])
    saida = []
    assert sp_fila.vigiar(lambda: next(passos), 1, lambda s: None, saida.append) == 0
    assert saida[-2:] == ["a · terminou · x", "b · morreu · painel inexistente"]
    assert sp_fila.vigiar(lambda: None, 1, lambda s: None, saida.append) == 0


def test_vigiar_sai_quando_todas_as_sessoes_estao_paradas_sem_fechar():
    passos = iter([[("a", "a correr", ""), ("b", "a correr", "")],
                   [("a", "parada sem fechar", "turno acabado"), ("b", "fechado", "SP em Done")]])
    saida = []
    assert sp_fila.vigiar(lambda: next(passos), 1, lambda s: None, saida.append) == 0
    assert saida[-2:] == ["a · PARADA SEM FECHAR · turno acabado", "b · terminou · SP em Done"]


def test_vigiar_para_na_hora_limite_mesmo_com_sessoes_vivas():
    saida, esperas = [], []
    limite = iter([False, False, True])
    rc = sp_fila.vigiar(lambda: [("a", "a correr", "")], 5, esperas.append, saida.append, lambda: next(limite))
    assert rc == 0 and len(esperas) == 2
    assert saida == ["a · a correr", "vigilância terminada: hora limite (--ate)"]


def test_classificar_inclui_a_pergunta_no_motivo():
    est, motivo = sp_fila.classificar({"painel": "7"}, "Doing", {"7"}, "Do you want to proceed?\n❯ 1. Yes", RECENTE, AGORA)
    assert est == "bloqueado" and motivo == f"precisa de aprovação do {sp_fila.USER}: Do you want to proceed?"

# --- sessão parada sem fechar e SP por commitar (par-vigilancia-parada) ---

PARADA = "trabalho feito\n\n✻ Worked for 36s · done 17:52\n❯ \n"


def test_vivo_parada_sem_fechar_quando_o_turno_acabou_e_o_sp_segue_em_doing():
    est, motivo = sp_fila.classificar({"painel": "7"}, "Doing", {"7"}, PARADA, RECENTE, AGORA)
    assert est == "parada sem fechar" and "Doing" in motivo


def test_vivo_parada_nao_vale_com_sp_done_nem_com_done_antigo_no_ecra():
    assert vivo(sp_status="Done", ecra=PARADA) == "fechado"
    antigo = "done 10:00\n" + "\n".join(f"linha {i}" for i in range(20))
    assert vivo(ecra=antigo) == "a correr"


def test_vivo_nao_devolve_a_correr_na_sessao_parada():
    assert vivo(ecra=PARADA) != "a correr"


def test_vigiar_avisa_quando_a_sessao_fica_parada_sem_fechar():
    passos = iter([[("a", "a correr", "")], [("a", "parada sem fechar", "turno acabado e SP ainda em Doing")], [("a", "fechado", "SP em Done")]])
    saida = []
    assert sp_fila.vigiar(lambda: next(passos), 1, lambda s: None, saida.append) == 0
    assert saida[1] == "a · PARADA SEM FECHAR · turno acabado e SP ainda em Doing"


def test_plan_exclui_sp_por_commitar(tmp_path):
    make_sp(tmp_path, "a")
    make_sp(tmp_path, "b")
    fila, excluidos = sp_fila.plan(sp_fila.load(tmp_path), por_commitar={"b"})
    assert slugs((fila, excluidos)) == ["a"]
    assert "por commitar" in dict(excluidos)["b"]


def test_sem_commit_so_marca_sps_fora_do_head(tmp_path):
    make_sp(tmp_path, "a")
    make_sp(tmp_path, "b")
    items = sp_fila.load(tmp_path)

    def git(saida, rc=0):
        def run(argv, **_):
            class R:
                returncode = rc
                stdout = saida(argv)
                stderr = ""
            return R()
        return run
    assert sp_fila.sem_commit(items, git(lambda a: a[-1] if a[-1].startswith("a") else "")) == {"b"}
    assert sp_fila.sem_commit(items, git(lambda a: "", rc=128)) == set()


# --- sem painéis fantasma (par-vigilancia-continua) ---

def test_estado_vivo_acha_o_painel_vivo_pela_worktree_quando_o_registo_aponta_para_outro(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Doing")
    wt = tmp_path / "wt-a"
    wt.mkdir()
    estado = {"sessoes": {"a": {"painel": "3", "worktree": str(wt), "inicio": "2026-10-29T11:59:00"}}}

    class R:
        def __init__(self, out):
            self.stdout = out

    def run(argv, **kw):
        if argv[:3] == ["wezterm", "cli", "list"]:
            return R(json.dumps([{"pane_id": 22, "cwd": "file:///" + str(wt).replace(chr(92), "/")}]))
        if "get-text" in argv:
            assert argv[-1] == "22"
            return R("working...\n❯ ")
        return R("")

    linhas = sp_fila.estado_vivo(estado, sp_fila.load(root), run, AGORA, 600)
    assert [(n, e) for n, e, _ in linhas] == [("a", "a correr")]
    assert estado["sessoes"]["a"]["painel"] == "3"  # só lê


def test_estado_vivo_sem_painel_na_worktree_continua_morto(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Doing")
    estado = {"sessoes": {"a": {"painel": "3", "worktree": str(tmp_path / "wt-a"), "inicio": "2026-10-29T11:00:00"}}}

    class R:
        stdout = json.dumps([{"pane_id": 22, "cwd": "file:///outro"}])

    linhas = sp_fila.estado_vivo(estado, sp_fila.load(root), lambda argv, **kw: R(), AGORA, 600)
    assert [(n, e) for n, e, _ in linhas] == [("a", "morto")]


# --- vigia persistente, heartbeat e aviso (par-vigilancia-continua) ---

def test_vigiar_bate_o_coracao_a_cada_ciclo():
    passos = iter([[("a", "a correr", "")], [("a", "a correr", "")], [("a", "fechado", "SP em Done")]])
    batidas = []
    sp_fila.vigiar(lambda: next(passos), 5, lambda s: None, lambda m: None, batida=lambda: batidas.append(1))
    assert len(batidas) == 3


def test_aviso_vigia_sem_sessoes_nao_avisa():
    assert sp_fila.aviso_vigia({"sessoes": {}}, AGORA) is None


def test_aviso_vigia_sessoes_sem_vigia_avisa_em_voz_alta():
    msg = sp_fila.aviso_vigia({"sessoes": {"a": {}}}, AGORA)
    assert msg and "SEM VIGIA" in msg and "--vigiar --destacado" in msg


def test_aviso_vigia_batida_antiga_avisa_e_recente_nao():
    velha = {"sessoes": {"a": {}}, "vigia": {"pid": 1, "ts": "2026-10-29T11:50:00"}}
    nova = {"sessoes": {"a": {}}, "vigia": {"pid": 1, "ts": "2026-10-29T11:59:30"}}
    assert "PAROU" in sp_fila.aviso_vigia(velha, AGORA)
    assert sp_fila.aviso_vigia(nova, AGORA) is None


def test_cli_estado_vivo_imprime_aviso_sem_vigia(tmp_path, capsys):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Doing")
    est = tmp_path / "e.json"
    sp_fila.guardar(est, {"sessoes": {"a": {"inicio": "2026-10-29T11:59:00"}}})
    sp_fila.main(["--estado-vivo", "--estado", str(est), "--root", str(root)])
    assert "SEM VIGIA" in capsys.readouterr().out


def test_permissao_e_reportada_como_precisa_de_aprovacao():
    ecra = "Bash command\n  git commit -m x\nDo you want to proceed?\n❯ 1. Yes\n  2. No\nEsc to cancel"
    est, motivo = sp_fila.classificar({"painel": "7"}, "Doing", {"7"}, ecra, RECENTE, AGORA, 600)
    assert est == "bloqueado" and f"precisa de aprovação do {sp_fila.USER}" in motivo


def test_vigiar_anuncia_aprovacao_do_bms():
    passos = iter([[("a", "bloqueado", f"precisa de aprovação do {sp_fila.USER}: Do you want to proceed?")], [("a", "fechado", "")]])
    saida = []
    sp_fila.vigiar(lambda: next(passos), 1, lambda s: None, saida.append)
    assert saida[0].startswith(f"a · PRECISA DE APROVAÇÃO DO {sp_fila.USER.upper()}")


def test_vigia_destacado_arranca_processo_proprio_com_log(tmp_path):
    chamadas = []
    log = tmp_path / "vigia.log"
    sp_fila.destacar(["--vigiar"], log, popen=lambda argv, **kw: chamadas.append((argv, kw)))
    argv, kw = chamadas[0]
    assert "--vigiar" in argv and "--destacado" not in argv
    assert kw["stdout"].name == str(log) and kw["stdin"] is not None


# --- ecrãs gravados (par-orquestrador-limpo) ---

FIXTURES = Path(__file__).with_name("fixtures") / "par-watch"


def _fx(nome):
    return (FIXTURES / f"{nome}.txt").read_text(encoding="utf-8")


def _cls(nome, status="Doing"):
    return sp_fila.classificar({"painel": "7"}, status, {"7"}, _fx(nome), RECENTE, AGORA, 600)


def test_fixture_a_correr():
    assert _cls("a-correr") == ("a correr", "")


def test_fixture_pedido_inclui_comando_e_motivo_numa_linha():
    est, motivo = _cls("pedido")
    assert est == "bloqueado" and motivo.startswith(f"precisa de aprovação do {sp_fila.USER}: ")
    assert 'git commit -m "feat: vigia limpo"' in motivo and "Commit as the " in motivo and "\n" not in motivo


def test_fixture_pergunta():
    est, motivo = _cls("pergunta")
    assert est == "bloqueado" and motivo.startswith("à espera de resposta")


def test_fixture_pronto_e_fechado():
    assert _cls("pronto")[0] == "parada sem fechar"
    assert _cls("fechado", "Done")[0] == "fechado"


def test_vigiar_com_fixtures_emite_so_uma_linha_por_mudanca():
    nomes = ["a-correr", "a-correr", "pedido", "pedido", "pergunta", "pronto"]
    passos = iter([[("a", *_cls(n))] for n in nomes] + [[("a", "fechado", "SP em Done")]])
    saida = []
    sp_fila.vigiar(lambda: next(passos), 1, lambda s: None, saida.append)
    assert len(saida) == 4 and all("\n" not in ln for ln in saida)  # a-correr e pedido repetidos suprimidos
    assert saida[1].startswith(f"a · PRECISA DE APROVAÇÃO DO {sp_fila.USER.upper()} · ") and saida[2].startswith("a · À ESPERA DE RESPOSTA") and saida[3].startswith("a · PARADA SEM FECHAR")




def test_vigiar_inativa_nao_repete_a_cada_minuto_e_reavisa_espacado():
    passos = iter([[("a", "bloqueado", f"inativa há {n} min")] for n in (10, 11, 12, 13)] + [[("a", "fechado", "")]])
    tempo = iter([0, 60, 120, 1000, 1001])
    saida = []
    sp_fila.vigiar(lambda: next(passos), 1, lambda s: None, saida.append, relogio=lambda: next(tempo))
    assert saida == ["a · bloqueado · inativa há 10 min", "a · AINDA bloqueado · inativa há 13 min", "a · terminou"]


def test_classificar_spinner_visivel_nao_e_bloqueado():
    ecra = "\n✻ Pensando… (12s · esc to interrupt)\n❯ "
    velho = AGORA - timedelta(minutes=30)
    assert sp_fila.classificar({"painel": "7"}, "Doing", {"7"}, ecra, velho, AGORA, 600) == ("a correr", "")
    assert sp_fila.classificar({"painel": "7"}, "Doing", {"7"}, "❯ ", velho, AGORA, 600)[0] == "bloqueado"


def test_linha_formato_compacto_numa_so_linha():
    assert sp_fila.linha("a", "a correr") == "a · a correr"
    assert sp_fila.linha("a", "bloqueado", "x\n  y ") == "a · bloqueado · x y"


def test_cli_ajuda_imprime_regras_curtas(capsys):
    assert sp_fila.main(["--ajuda"]) == 0
    assert len(capsys.readouterr().out.splitlines()) <= 8


def test_vigiar_fecha_o_painel_uma_vez_quando_fechado():
    passos = iter([[("a", "a correr", "")], [("a", "fechado", "")], [("a", "fechado", "")]])
    fechados = []
    sp_fila.vigiar(lambda: next(passos), 1, lambda s: None, lambda m: None, fechar_painel=fechados.append)
    assert fechados == ["a"]


def test_fechar_painel_sessao_acha_o_painel_pela_worktree(tmp_path):
    estado = tmp_path / "e.json"
    estado.write_text(json.dumps({"sessoes": {"a": {"painel": "9", "worktree": "C:/x/wt"}}}), encoding="utf-8")
    chamadas = []

    def run(cmd, **kw):
        chamadas.append(cmd)
        saida = json.dumps([{"pane_id": 4, "cwd": "file:///C:/x/wt/"}]) if cmd[2] == "list" else ""
        return type("R", (), {"stdout": saida})()

    assert sp_fila.fechar_painel_sessao(estado, "a", run) is True
    assert chamadas[-1] == ["wezterm", "cli", "kill-pane", "--pane-id", "4"]
    assert sp_fila.fechar_painel_sessao(estado, "b", run) is False
