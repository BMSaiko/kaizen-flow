"""Testes de scripts/sp-fila.py (planeador, limites, passo seguinte; fixtures em ficheiros temporários)."""
import importlib.util
import json
import sys
from datetime import datetime
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
            "lancado": None, "projeto": None, "inicio": "2026-10-25T10:00:00", "commits": []}
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
    assert json.loads(st.read_text(encoding="utf-8"))["lancado"] == "a"
    assert json.loads(st.read_text(encoding="utf-8"))["usados"] == sp_fila.REQ_POR_SP


def test_seguinte_regista_feito_e_falhado_e_nao_avanca_dependentes(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Done")
    make_sp(root, "b", folder="Doing")
    make_sp(root, "dep-b", depends_on=["b"])
    make_sp(root, "livre", priority="P3")
    calls = []
    st = _estado(tmp_path, lancado="b", feitos=["a"])
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), datetime(2026, 10, 25, 12, 0))
    estado = json.loads(st.read_text(encoding="utf-8")) if st.exists() else {}
    assert out["slug"] == "livre"
    assert estado["falhados"] == ["b"]
    assert estado["lancado"] == "livre"


def test_seguinte_fim_escreve_relatorio_e_apaga_estado(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Done")
    make_sp(root, "excl", modo="manual")
    calls = []
    st = _estado(tmp_path, lancado="a")
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
    st = _estado(tmp_path, lancado="a", max=1)
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
