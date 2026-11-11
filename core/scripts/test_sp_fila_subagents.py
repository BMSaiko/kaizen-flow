"""Testes do backend de subagents do `/sp-fila` (sp_fila_subagents)."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sp_fila_subagents as sfs  # noqa: E402


def _run_ok(saida, chamadas=None):
    def run(argv, **kw):
        if chamadas is not None:
            chamadas.append(argv)
        return SimpleNamespace(returncode=0, stdout=saida, stderr="")
    return run


def test_prompt_tem_michi_worktree_e_regra_sem_perguntas():
    p = sfs.prompt("abc-2026-11-10", r"C:\wt\sb-abc")
    assert "/michi abc-2026-11-10" in p
    assert r"C:\wt\sb-abc" in p
    assert "AskUserQuestion" in p  # diz que não existe e o que fazer em vez dela
    for estado in sfs.ESTADOS:
        assert estado in p


def test_prompt_proibe_saltar_verificacoes_do_fecho():
    p = sfs.prompt("abc-2026-11-10", r"C:\wt\sb-abc")
    assert "--sem-budget" in p and "--sem-testes" in p and "Nunca" in p


def test_lancar_corre_ensure_e_usa_ultima_linha_como_worktree():
    chamadas = []
    item = sfs.lancar("abc", run=_run_ok("aviso qualquer\nC:\\wt\\sb-abc\n", chamadas))
    assert chamadas[0][-2:] == ["ensure", "abc"]
    assert chamadas[0][1] == "-I" and chamadas[0][2].endswith("sb-worktree.py")
    assert item["slug"] == "abc"
    assert item["worktree"] == r"C:\wt\sb-abc"
    assert item["prompt"] == sfs.prompt("abc", r"C:\wt\sb-abc")


def test_lancar_falha_levanta_runtimeerror_com_stderr():
    def run(argv, **kw):
        return SimpleNamespace(returncode=1, stdout="", stderr="worktree suja")
    try:
        sfs.lancar("abc", run=run)
    except RuntimeError as e:
        assert "worktree suja" in str(e)
    else:
        raise AssertionError("devia levantar")


def test_lancar_sem_saida_levanta():
    try:
        sfs.lancar("abc", run=_run_ok("  \n"))
    except RuntimeError as e:
        assert "abc" in str(e)
    else:
        raise AssertionError("devia levantar")


def test_plano_json_com_itens_e_instrucao():
    itens = [{"slug": "a", "worktree": "w/a", "prompt": "p"}, {"slug": "b", "worktree": "w/b", "prompt": "q"}]
    dados = json.loads(sfs.plano(itens))
    assert dados["acao"] == "lancar"
    assert [i["slug"] for i in dados["itens"]] == ["a", "b"]
    assert all(i["run_in_background"] is True for i in dados["itens"])
    assert "--seguinte --slug" in dados["no_fim"]


def test_plano_vazio_e_lista_vazia():
    assert json.loads(sfs.plano([]))["itens"] == []


def test_estado_final_le_ultima_linha_estado():
    assert sfs.estado_final("bla\nESTADO: done") == "done"
    assert sfs.estado_final("ESTADO: pergunta\nqual a cor?") == "pergunta"
    assert sfs.estado_final("sem marcador") == "desconhecido"
    assert sfs.estado_final("ESTADO: inventado") == "desconhecido"


def test_plano_usa_o_modelo_do_nivel_de_cada_sp(monkeypatch):
    monkeypatch.setattr(sfs, "modelo_agent", lambda nivel=None: {"simples": "m-s", "complexo": "m-c"}.get(nivel, "m-d"))
    itens = json.loads(sfs.plano([{"slug": "a", "worktree": "w", "prompt": "p", "michi_modelo": "simples"},
                                  {"slug": "b", "worktree": "w", "prompt": "p", "michi_modelo": "complexo"},
                                  {"slug": "c", "worktree": "w", "prompt": "p"}]))["itens"]
    assert [i["model"] for i in itens] == ["m-s", "m-c", "m-d"]


def test_plano_effort_low_em_todos_os_itens(monkeypatch):
    monkeypatch.setattr(sfs, "modelo_agent", lambda nivel=None: "m")
    itens = json.loads(sfs.plano([{"slug": s, "worktree": "w", "prompt": "p", "michi_modelo": n}
                                  for s, n in (("a", "simples"), ("b", "complexo"), ("c", None))]))["itens"]
    assert itens and all(i.get("effort") == "low" for i in itens)


def test_plano_sem_modelos_sai_sem_model_e_com_effort_low(monkeypatch):
    monkeypatch.setattr(sfs, "modelos", None)
    item = json.loads(sfs.plano([{"slug": "a", "worktree": "w", "prompt": "p"}]))["itens"][0]
    assert "model" not in item and item["effort"] == "low"


def test_modelo_agent_segue_modelos_michi():
    import modelos
    if not modelos.DEFAULT.exists():  # pacote kaizen-flow sem .claude/modelos.json
        assert sfs.modelo_agent("complexo") is None
        return
    cfg = modelos.load()
    assert sfs.modelo_agent("complexo") == modelos.michi(cfg, "complexo")[0]["model"]
    assert sfs.modelo_agent(None) == modelos.michi(cfg, "default")[0]["model"]


def test_estado_continuar_e_aceite():
    assert "continuar" in sfs.ESTADOS
    assert sfs.estado_final("progresso gravado\nESTADO: continuar") == "continuar"


def test_prompt_tem_continuar_e_aninhamento():
    p = sfs.prompt("s", "w")
    assert "ESTADO: continuar" in p and "## Progresso" in p and "Agent" in p


def test_nivel_do_sp_le_o_frontmatter(tmp_path):
    d = tmp_path / "knowledge" / "projects" / "x" / "y" / "sp" / "TODO"
    d.mkdir(parents=True)
    (d / "s-1.md").write_text("---\nslug: s-1\nmichi_modelo: simples\n---\n# x\n", encoding="utf-8")
    (d / "s-2.md").write_text("---\nslug: s-2\n---\n", encoding="utf-8")
    assert sfs.nivel_sp("s-1", tmp_path) == "simples"
    assert sfs.nivel_sp("s-2", tmp_path) is None
    assert sfs.nivel_sp("nao-existe", tmp_path) is None
