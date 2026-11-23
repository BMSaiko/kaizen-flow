import pytest

from herdr_fake import FakeHerdr
from herdr_ops import HerdrErro, HerdrOps


def _ops(**kw):
    f = FakeHerdr(**kw)
    return f, HerdrOps(f, sleep=lambda s: None)


def test_painel_novo_cria_workspace_e_reutiliza(tmp_path):
    f, o = _ops()
    p1 = o.painel_novo(tmp_path)
    assert p1 and len(f.workspaces) == 1
    p2 = o.painel_novo(tmp_path)  # workspace do projeto já existe: tab nova
    assert p2 != p1 and len(f.workspaces) == 1 and f.chamadas[-1][1:3] == ["tab", "create"]


def test_painel_novo_sem_id_devolve_none():
    o = HerdrOps(lambda argv, **kw: type("R", (), {"returncode": 0, "stdout": "{}", "stderr": ""})())
    assert o.painel_novo("/x", workspace_por_projeto=False) is None


def test_lancar_agente_usa_cd_e_command(tmp_path):
    f, o = _ops()
    p = o.painel_novo(tmp_path)
    o.lancar_agente(p, "/work/wt", ["claude", "--model", "haiku"])
    assert f.chamadas[-1][-1] == "cd /work/wt && command claude --model haiku"
    assert o.estado(p) == "idle"


def test_estado_unknown_sem_agente():
    f, o = _ops()
    assert o.estado("w9:p9") == "unknown"


def test_prompt_e_esperar():
    f, o = _ops()
    p = o.painel_novo("/w")
    o.lancar_agente(p, "/w")
    a = o.prompt(p, "/michi x", esperar=True, timeout_ms=1000)
    assert a["completion_seq"] == 1 and "--wait" in f.chamadas[-1]
    assert o.esperar(p, ate=["idle", "done"], timeout_ms=5)["agent_status"] == "idle"
    assert f.chamadas[-1][-4:] == ["--until", "done", "--timeout", "5"]


def test_prompt_blocked_levanta_codigo():
    f, o = _ops(agente_estado="blocked")
    p = o.painel_novo("/w")
    o.lancar_agente(p, "/w")
    with pytest.raises(HerdrErro) as e:
        o.prompt(p, "x")
    assert e.value.code == "agent_blocked"


def test_prompt_agente_inexistente():
    f, o = _ops()
    with pytest.raises(HerdrErro) as e:
        o.prompt("w1:p1", "x")
    assert e.value.code == "agent_not_found"


def test_renomear_metadata_foco_fechar():
    f, o = _ops()
    p = o.painel_novo("/w")
    o.lancar_agente(p, "/w")
    o.renomear_agente(p, "sp1")
    assert o.agentes()[p]["name"] == "sp1"
    o.metadata(p, "kf", "SP x")
    o.fechar(p)
    assert p not in o.agentes() and p not in {x["pane_id"] for x in o.paineis()}


def test_workspace_metadata_e_workspace_do_pane():
    fake = FakeHerdr()
    ops = HerdrOps(run=fake)
    ops.workspace_metadata("w1", "sp-fila", "fila 1/3 · 2 vagas")
    assert ["herdr", "workspace", "report-metadata", "--source", "sp-fila", "--token", "fila=fila 1/3 · 2 vagas", "w1"] in fake.chamadas
    assert ops.workspace_do_pane("nao-existe") is None


def test_criar_enviar_fechar_por_nome_com_herdr(tmp_path, monkeypatch):
    """Nome canónico ponta a ponta no herdr: abrir→registar→enviar→fechar por nome; heimdall recusado."""
    import kf_nomes as kn
    import kf_term_orq as orq
    import painel_backend as pb
    monkeypatch.setenv("SP_FILA_ROOT", str(tmp_path / "estado"))
    monkeypatch.delenv("HERDR_PANE_ID", raising=False)
    fake = FakeHerdr()
    b = pb.HerdrBackend(run=fake)
    enviados = []
    b.enviar = lambda id, texto: enviados.append((id, texto)) or True  # o ecrã do fake não ecoa texto
    pane = b.abrir(["claude"], str(tmp_path))
    kn.registar("sp-x", "herdr", pane, str(tmp_path), "sp", "x")
    sb = tmp_path / "sb"
    sb.mkdir()
    heim = b.abrir(["claude"], str(sb))
    kn.registar("heimdall", "herdr", heim, str(sb), "livre", "heimdall", raiz_sb=str(sb))
    saidas = []
    assert orq.acao(type("A", (), {"acao": "enviar", "painel": "sp-x", "alvo": "olá", "linhas": 0})(), b,
                    entrada=lambda _: "s", saida=saidas.append) == 0
    assert enviados == [(pane, "olá")]
    assert orq.acao(type("A", (), {"acao": "matar", "painel": "heimdall", "alvo": None, "linhas": 0})(), b,
                    entrada=lambda _: "s", saida=saidas.append) == 2 and heim in b.listar()
    assert orq.acao(type("A", (), {"acao": "matar", "painel": "sp-x", "alvo": None, "linhas": 0})(), b,
                    entrada=lambda _: "s", saida=saidas.append) == 0
    assert pane not in b.listar() and kn.resolver("sp-x") is None and kn.resolver("heimdall")
