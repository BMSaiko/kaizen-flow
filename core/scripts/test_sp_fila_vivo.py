"""Testes de scripts/sp-fila.py: estado vivo e classificação das sessões (a correr, parada, bloqueada)."""
import json
from sp_fila_testlib import (
    sp_fila,
    make_sp,
    plan,
    slugs,
    AGORA,
    RECENTE,
    VELHA,
    vivo,
    _arranque,
    PARADA,
)


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


def test_vivo_a_arrancar_sem_painel_registado_ou_sem_prompt():
    assert _arranque(inicio="2026-10-29T11:59:30") == "a arrancar"
    assert _arranque(painel="7", inicio="2026-10-29T11:59:30", ecra="Welcome to Claude Code") == "a arrancar"
    assert _arranque(painel="7", inicio="2026-10-29T11:59:30", ecra="❯ ") == "a correr"
    assert _arranque(inicio="2026-10-29T11:00:00") == "morto"


def test_painel_lancado_le_o_json_do_spawn():
    saida = json.dumps([{"slug": "b", "ok": True, "painel": "3", "worktree": "C:\\wt\\sb-b"},
                        {"slug": "a", "ok": True, "painel": 9, "worktree": "C:\\wt\\sb-a"}])
    assert sp_fila._painel_lancado("a", saida) == {"painel": "9", "worktree": "C:\\wt\\sb-a"}
    sem_painel = json.dumps([{"slug": "a", "ok": True, "painel": None, "worktree": "C:\\wt"}])
    assert sp_fila._painel_lancado("a", sem_painel) == {} and sp_fila._painel_lancado("a", None) == {}
    assert sp_fila._painel_lancado("a", "a: painel 9 em C:\\wt") == {}  # texto livre já não é lido


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
    chamadas = []
    assert sp_fila.sem_commit(items, git(lambda a: chamadas.append(a) or "a.md\n")) == {"b"}
    assert len(chamadas) == 1  # uma chamada por diretório, não por SP
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
