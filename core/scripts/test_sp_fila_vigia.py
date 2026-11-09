"""Testes de scripts/sp-fila.py: vigia destacada, fixtures do painel e paragem da vigia."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from sp_fila_testlib import (
    sp_fila,
    make_sp,
    slugs,
    _runner,
    _estado,
    AGORA,
    vivo,
    PARADA,
    _cls,
    _Proc,
    _ps,
)


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


def test_run_hidden_esconde_a_janela_de_consola(monkeypatch):
    visto = {}
    monkeypatch.setattr(sp_fila.subprocess, "run", lambda *a, **kw: visto.update(kw))
    sp_fila.run_hidden(["wezterm", "cli", "list"])
    assert visto["creationflags"] == sp_fila.NO_WINDOW
    assert sp_fila.seguinte.__defaults__[0] is sp_fila.run_hidden


# --- arranque automático do seguinte (kf-fila-arranque-automatico) ---


def test_vigiar_lanca_o_seguinte_ao_fechar_e_continua_a_vigiar():
    passos = iter([[("a", "fechado", "SP em Done")], [("b", "a correr", "")], [("b", "fechado", "SP em Done")]])
    lancados, saida = [], []

    def lancar(slug):
        lancados.append(slug)
        return (slug == "a", f"lançou b depois de {slug}" if slug == "a" else "fila vazia")

    rc = sp_fila.vigiar(lambda: next(passos), 1, lambda s: None, saida.append, lancar_seguinte=lancar)
    assert rc == 0 and lancados == ["a", "b"]
    assert "a · fila · lançou b depois de a" in saida and "b · fila · fila vazia" in saida


def test_vigiar_regista_a_razao_quando_nao_lanca():
    saida = []
    sp_fila.vigiar(lambda: [("a", "fechado", "SP em Done")], 1, lambda s: None, saida.append,
                   lancar_seguinte=lambda slug: (False, "limite de SPs atingido"))
    assert saida[-1] == "a · fila · limite de SPs atingido"


def test_lancar_seguinte_auto_traduz_a_resposta_do_seguinte(tmp_path):
    def fn(acao):
        return lambda *a, **k: acao
    lancou = sp_fila.lancar_seguinte_auto("r", "e", "rel", "a", seguinte_fn=fn({"acao": "lancou", "slugs": ["b", "c"]}))
    assert lancou == (True, "lançou b, c")
    assert sp_fila.lancar_seguinte_auto("r", "e", "rel", "a", seguinte_fn=fn({"acao": "espera", "sessoes": ["x"]})) == (False, "a aguardar · x")
    fim = sp_fila.lancar_seguinte_auto("r", "e", "rel", "a", seguinte_fn=fn({"acao": "fim", "motivo": "fila vazia", "relatorio": "p"}))
    assert fim == (False, "fila terminada: fila vazia")

    def rebenta(*a, **k):
        raise OSError("sem acesso")
    ok, motivo = sp_fila.lancar_seguinte_auto("r", "e", "rel", "a", seguinte_fn=rebenta)
    assert ok is False and "sem acesso" in motivo


def test_lancar_seguinte_auto_passa_o_slug_que_fechou():
    vistos = {}

    def fn(root, estado, rel, slug=None):
        vistos["slug"] = slug
        return {"acao": "espera", "sessoes": []}
    sp_fila.lancar_seguinte_auto("r", "e", "rel", "kf-x", seguinte_fn=fn)
    assert vistos["slug"] == "kf-x"


def test_contar_tails_conta_so_os_que_seguem_o_log_da_vigia():
    saida = "tail -F C:/" "Users/x/.claude/sp-fila-vigia.log\ntail -F /var/log/outro.log\ntail -f ~/.claude/sp-fila-vigia.log\npython sp-fila.py\n"
    run = lambda *a, **k: type("R", (), {"stdout": saida})()
    assert sp_fila.contar_tails(run) == 2
    win = r'"C:\Program Files\Git\usr\bin\tail.exe" -F C:' r'\Users\x\.claude\sp-fila-vigia.log'
    assert sp_fila.contar_tails(lambda *a, **k: type("R", (), {"stdout": win})()) == 1
    def rebenta(*a, **k):
        raise OSError("x")
    assert sp_fila.contar_tails(rebenta) == 0


def test_estado_vivo_cli_avisa_de_monitores_duplicados(tmp_path, capsys, monkeypatch):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Doing")
    est = tmp_path / "e.json"
    sp_fila.guardar(est, {"sessoes": {"a": {"inicio": "2026-10-29T11:59:00"}}})
    monkeypatch.setattr(sp_fila, "contar_tails", lambda run=None: 2)
    sp_fila.main(["--estado-vivo", "--estado", str(est), "--root", str(root)])
    assert "2 Monitores" in capsys.readouterr().out


def test_vigia_destacado_nao_arma_segunda_vigia(tmp_path, capsys, monkeypatch):
    est = tmp_path / "e.json"
    sp_fila.guardar(est, {"sessoes": {"a": {}}, "vigia": {"pid": 77, "ts": datetime.now().isoformat(timespec="seconds")}})
    chamadas = []
    monkeypatch.setattr(sp_fila, "destacar", lambda *a, **k: chamadas.append(a))
    assert sp_fila.main(["--vigiar", "--destacado", "--estado", str(est)]) == 0
    assert chamadas == [] and "vigia já ativo (pid 77)" in capsys.readouterr().out


def test_garantir_vigia_ausente_arma():
    armadas = []
    res = sp_fila.garantir_vigia({"sessoes": {"a": {}}}, lambda: armadas.append(1) or _Proc(5), AGORA)
    assert res == ("armada", 5) and armadas == [1]


def test_garantir_vigia_parada_rearma():
    velha = {"sessoes": {"a": {}}, "vigia": {"pid": 9, "ts": (AGORA - timedelta(minutes=10)).isoformat(timespec="seconds")}}
    assert sp_fila.garantir_vigia(velha, lambda: _Proc(6), AGORA) == ("armada", 6)


def test_garantir_vigia_viva_nao_arma():
    nova = {"sessoes": {"a": {}}, "vigia": {"pid": 9, "ts": AGORA.isoformat(timespec="seconds")}}
    armadas = []
    assert sp_fila.garantir_vigia(nova, lambda: armadas.append(1) or _Proc(1), AGORA) == ("viva", 9)
    assert armadas == []


def test_armar_vigia_do_handoff_chama_sp_fila_destacado(capsys):
    handoff = __import__("importlib").util.spec_from_file_location("sp_handoff_t", Path(__file__).parent / "sp-handoff.py")
    mod = __import__("importlib").util.module_from_spec(handoff)
    handoff.loader.exec_module(mod)
    chamadas = []

    class R:
        returncode, stdout, stderr = 0, "vigia destacado (pid 3)\n", ""
    assert mod.armar_vigia(run=lambda argv, **kw: chamadas.append(argv) or R()) == 0
    assert chamadas[0][-2:] == ["--vigiar", "--destacado"] and "vigia destacado (pid 3)" in capsys.readouterr().out


def test_ajuda_descreve_arranque_automatico_e_monitor_unico(capsys):
    sp_fila.main(["--ajuda"])
    out = capsys.readouterr().out
    assert "lança o seguinte" in out and "substitui" in out


# --- limites de segurança (skill-sp-fila) ---


def test_parar_vigia_viva_mata_so_o_pid_registado_e_avisa_do_tail():
    mortos = []
    parou, msg = sp_fila.parar_vigia({"pid": 4242}, run=_ps("python -I scripts/sp-fila.py --vigiar --intervalo 20"),
                                     matar=lambda pid, sig: mortos.append(pid), eu=lambda: 1)
    assert parou and mortos == [4242] and "4242" in msg and "tail" in msg


def test_parar_vigia_pid_morto_nao_mata_nada():
    mortos = []
    parou, msg = sp_fila.parar_vigia({"pid": 4242}, run=_ps(""), matar=lambda pid, sig: mortos.append(pid), eu=lambda: 1)
    assert not parou and mortos == [] and "4242" in msg


def test_parar_vigia_pid_reutilizado_por_processo_alheio_nao_mata_nada():
    mortos = []
    parou, _ = sp_fila.parar_vigia({"pid": 4242}, run=_ps("notepad.exe leiame.txt"), matar=lambda pid, sig: mortos.append(pid), eu=lambda: 1)
    assert not parou and mortos == []


def test_parar_vigia_sem_registo_ou_pid_invalido_e_nao_se_mata_a_si_propria():
    mortos = []
    for v in (None, {}, {"pid": "x"}, {"pid": 7}):
        assert not sp_fila.parar_vigia(v, run=_ps("sp-fila --vigiar"), matar=lambda pid, sig: mortos.append(pid), eu=lambda: 7)[0]
    assert mortos == []


def test_parar_vigia_erro_ao_matar_nao_levanta():
    def falha(pid, sig):
        raise PermissionError("negado")
    parou, msg = sp_fila.parar_vigia({"pid": 9}, run=_ps("sp-fila.py --vigiar"), matar=falha, eu=lambda: 1)
    assert not parou and "negado" in msg


def test_fim_da_fila_para_a_vigia_registada(tmp_path, monkeypatch):
    import sp_fila_execucao
    vistos = []
    monkeypatch.setattr(sp_fila_execucao, "parar_vigia", lambda v: vistos.append(v) or (True, "vigia parada (pid 55)"))
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Done")
    st = _estado(tmp_path, sessoes={"a": {}}, vigia={"pid": 55, "ts": "2026-10-25T11:59:00"})
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), datetime(2026, 10, 25, 12, 0))
    assert out["acao"] == "fim" and not st.exists()
    assert vistos == [{"pid": 55, "ts": "2026-10-25T11:59:00"}] and "55" in out["vigia"]


def test_parar_abandona_a_fila_e_para_a_vigia(tmp_path, monkeypatch, capsys):
    vistos = []
    monkeypatch.setattr(sp_fila, "parar_vigia", lambda v: vistos.append(v) or (True, "vigia parada (pid 55)"))
    st = _estado(tmp_path, vigia={"pid": 55, "ts": "2026-10-25T11:59:00"})
    assert sp_fila.main(["--parar", "--estado", str(st)]) == 0
    assert not st.exists() and len(vistos) == 1
    assert "vigia parada (pid 55)" in capsys.readouterr().out


def test_resumo_arranque_vigia_parada_avisa_com_idade_e_sp():
    estado = {"inicio": "2026-10-29T09:00:00", "sessoes": {"meu-sp": {"painel": "7"}},
              "vigia": {"pid": 1, "ts": (AGORA - timedelta(minutes=30)).isoformat()}}
    out = sp_fila.resumo_arranque(estado, AGORA, [("meu-sp", "bloqueado", "precisa de aprovação do user: git commit")])
    assert "SP meu-sp" in out and "painel 7" in out
    assert "aprovações pendentes: meu-sp" in out
    assert "há 30 min" in out and "PARADA" in out


def test_resumo_arranque_sem_vigia_nem_pendentes():
    out = sp_fila.resumo_arranque({"sessoes": {"a": {"painel": "3"}}}, AGORA, [("a", "a correr", "")])
    assert "aprovações pendentes: nenhuma" in out and "nunca armada" in out


def test_tail_da_vigia_so_le_linhas_novas():
    assert sp_fila.VIGIA_TAIL.startswith("tail -n 0 -F ")
    assert "tail -n 0 -F" in sp_fila.AJUDA and "tail -F" not in sp_fila.AJUDA.replace("tail -n 0 -F", "")
    assert "tail -n 0 -F" in sp_fila.AVISO_TAIL
