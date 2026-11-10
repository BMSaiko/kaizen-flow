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


def test_plano_inclui_model_michi_exec_em_cada_item(monkeypatch):
    monkeypatch.setattr(sfs, "modelo_agent", lambda papel="michi-exec": "claude-sonnet-5-5")
    itens = json.loads(sfs.plano([{"slug": "a", "worktree": "w", "prompt": "p"}]))["itens"]
    assert itens[0]["model"] == "claude-sonnet-5-5"


def test_modelo_agent_le_o_papel_michi_exec():
    import modelos
    if not modelos.DEFAULT.exists():  # pacote kaizen-flow sem .claude/modelos.json
        assert sfs.modelo_agent() is None
        return
    assert sfs.modelo_agent() == modelos.papel(modelos.load(), "michi-exec")["model"]
