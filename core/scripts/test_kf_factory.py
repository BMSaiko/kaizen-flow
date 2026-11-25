"""Testes de kf_factory: máquina de estados da factory com portos falsos (feliz, orçamento, gate vermelho, retoma, lock, release)."""
import json

import pytest


import kf_factory as kf

P = "demo"


class Falso(kf.Portos):
    """Backlog em memória: cada SP termina com `resultados[slug]` (lista consumida); `esperar` não dorme."""

    def __init__(self, marcos=2, release=(), resultados=None, cfg=None, **kw):
        custos, dia, merge_rc = kw.get("custos"), kw.get("dia", 0.0), kw.get("merge_rc")
        self.sps = {f"{P}-visao-m{n}-x": {"slug": f"{P}-visao-m{n}-x", "marco": n, "estado": "todo",
                                         "depende": [f"{P}-visao-m{n - 1}-x"] if n > 1 else [], "release": n in release}
                    for n in range(1, marcos + 1)}
        self.por_decompor = True
        self.decompor_rc = 0
        self.chamadas = []
        self.resultados = resultados or {}
        self.cfg, self.custos, self.dia = cfg, custos or {}, dia
        self.merge_rc = merge_rc or {}
        self.painel = {}

    def backlog(self, projeto):
        return [] if self.por_decompor else [dict(v) for v in self.sps.values()]

    def avulsos(self, projeto):
        return [dict(x) for x in getattr(self, "avulsos_l", [])]

    def decompor(self, projeto):
        self.chamadas.append("decompor")
        if self.decompor_rc == 0:
            self.por_decompor = False
        return self.decompor_rc, "VISION com placeholders" if self.decompor_rc else ""

    def lancar(self, slug):
        self.chamadas.append(f"lancar:{slug}")

    def resultado(self, slug):
        fila = self.resultados.get(slug)
        if fila:
            return fila.pop(0)
        return {"estado": "done", "pr": f"{slug}#1", "gates_ok": True, "motivo": ""}

    def merge(self, pr, slug):
        self.chamadas.append(f"merge:{slug}")
        rc = self.merge_rc.get(slug, 0)
        if rc == 0:
            (self.sps.get(slug) or next(x for x in getattr(self, "avulsos_l", []) if x["slug"] == slug))["estado"] = "done"
        return rc, "ci vermelho" if rc else "merged"

    def reflect(self, projeto, marco):
        self.chamadas.append(f"reflect:{marco}")

    def corrigir(self, slug, motivo):
        novo = f"{slug}-correcao"
        m = self.sps[slug]["marco"]
        self.sps[novo] = {"slug": novo, "marco": m, "estado": "todo", "depende": [], "release": False}
        self.chamadas.append(f"corrigir:{slug}")
        return novo

    def custo(self, slug):
        return self.custos.get(slug, 0.0)

    def custo_dia(self):
        return self.dia

    def orcamento(self):
        return self.cfg

    def esperar(self, segundos):
        self.chamadas.append("esperar")


def fab(tmp_path, falso, **kw):
    fa = kf.Fabrica(P, falso, tmp_path / "f", intervalo=0, **kw)
    fa.max_voltas = 200
    return fa


def log(tmp_path):
    f = tmp_path / "f" / "factory.log.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines()]


def test_ec_086_feliz_decompoe_corre_marcos_ate_ao_merge_e_conclui(tmp_path):
    f = Falso()
    assert fab(tmp_path, f).run() == kf.RC_OK
    assert f.chamadas == ["decompor", f"lancar:{P}-visao-m1-x", f"merge:{P}-visao-m1-x", "reflect:1",
                          f"lancar:{P}-visao-m2-x", f"merge:{P}-visao-m2-x", "reflect:2"]
    e = json.loads((tmp_path / "f" / f"{P}.json").read_text())
    assert e["estado"] == "concluida" and e["reflect"] == [1, 2]


def test_backlog_existente_nao_volta_a_decompor(tmp_path):
    f = Falso()
    f.por_decompor = False
    fab(tmp_path, f).run()
    assert "decompor" not in f.chamadas


def test_ec_087_visao_invalida_pausa_sem_lancar(tmp_path):
    f = Falso()
    f.decompor_rc = 1
    assert fab(tmp_path, f).run() == kf.RC_PAUSA
    e = json.loads((tmp_path / "f" / f"{P}.json").read_text())
    assert e["paragem"] == "visao-invalida" and not any(c.startswith("lancar") for c in f.chamadas)


def test_ec_088_orcamento_excedido_pausa_antes_de_lancar(tmp_path):
    f = Falso(cfg={"spUsd": 5.0, "diaUsd": 10.0, "falhasSeguidas": 3}, dia=10.0)
    assert fab(tmp_path, f).run() == kf.RC_PAUSA
    e = json.loads((tmp_path / "f" / f"{P}.json").read_text())
    assert e["paragem"] == "orcamento" and "diaUsd" in e["razao"]
    assert not any(c.startswith("lancar") for c in f.chamadas)


def test_ec_089_gate_vermelho_cria_correcao_e_continua(tmp_path):
    m1 = f"{P}-visao-m1-x"
    f = Falso(marcos=1, resultados={m1: [{"estado": "falhou", "pr": None, "gates_ok": False, "motivo": "ruff vermelho"}]})
    assert fab(tmp_path, f).run() == kf.RC_OK
    assert f"corrigir:{m1}" in f.chamadas and f"merge:{m1}-correcao" in f.chamadas
    assert f.chamadas.count("reflect:1") == 1
    assert [x["evento"] for x in log(tmp_path)].count("correcao") == 1


def test_ec_089_segundo_gate_vermelho_do_mesmo_sp_pausa(tmp_path):
    m1 = f"{P}-visao-m1-x"
    verm = {"estado": "falhou", "pr": None, "gates_ok": False, "motivo": "tipos vermelhos"}
    f = Falso(marcos=1, resultados={m1: [dict(verm)], f"{m1}-correcao": [dict(verm)]})
    assert fab(tmp_path, f).run() == kf.RC_PAUSA
    e = json.loads((tmp_path / "f" / f"{P}.json").read_text())
    assert e["paragem"] == "gate-bloqueado" and "tipos vermelhos" in e["razao"]


def test_falhas_seguidas_param_por_orcamento(tmp_path):
    m1 = f"{P}-visao-m1-x"
    verm = {"estado": "falhou", "pr": None, "gates_ok": False, "motivo": "x"}
    f = Falso(marcos=1, cfg={"falhasSeguidas": 1}, resultados={m1: [dict(verm)]})
    assert fab(tmp_path, f).run() == kf.RC_PAUSA
    assert json.loads((tmp_path / "f" / f"{P}.json").read_text())["paragem"] == "orcamento"


def test_merge_recusado_por_ci_nao_marca_done(tmp_path):
    m1 = f"{P}-visao-m1-x"
    f = Falso(marcos=1, merge_rc={m1: 11})
    assert fab(tmp_path, f).run() == kf.RC_OK  # a correção (sem ci vermelho) conclui o marco
    assert f.sps[m1]["estado"] == "todo" and f.sps[f"{m1}-correcao"]["estado"] == "done"


def test_ec_090_release_pausa_no_marco_e_retoma_com_release_feito(tmp_path):
    f = Falso(release=(1,))
    assert fab(tmp_path, f).run() == kf.RC_PAUSA
    e = json.loads((tmp_path / "f" / f"{P}.json").read_text())
    assert e["paragem"] == "release" and f"lancar:{P}-visao-m2-x" not in f.chamadas
    assert fab(tmp_path, f).run(release_feito=True) == kf.RC_OK
    assert f.chamadas.count("reflect:1") == 1  # o reflect do marco 1 não se repete


def test_ec_091_retoma_apos_crash_nao_relanca_nem_remerge(tmp_path):
    f = Falso(marcos=1)
    m1 = f"{P}-visao-m1-x"
    fa = fab(tmp_path, f)
    fa.guardar({"projeto": P, "estado": "a-correr", "marco": 1, "sps": {m1: {"fase": "lancado", "correcoes": 0, "pr": None}},
                "seguidas": 0, "gasto": 0.0, "paragem": "", "razao": "", "reflect": []})
    f.por_decompor = False
    assert fa.run() == kf.RC_OK
    assert not any(c.startswith("lancar") for c in f.chamadas) and f.chamadas.count(f"merge:{m1}") == 1
    assert [x["evento"] for x in log(tmp_path)][0] == "retoma"


def test_ec_092_lock_recusa_segunda_factory_viva_e_toma_o_de_pid_morto(tmp_path):
    pasta = tmp_path / "f"
    pasta.mkdir()
    (pasta / f"{P}.lock").write_text("999999")
    assert fab(tmp_path, Falso(), vivo=lambda pid: True).run() == kf.RC_LOCK
    assert (pasta / f"{P}.lock").exists()
    assert fab(tmp_path, Falso(), vivo=lambda pid: False).run() == kf.RC_OK
    assert not (pasta / f"{P}.lock").exists()


def test_stop_pausa_limpa_e_run_seguinte_retoma(tmp_path):
    f = Falso()
    assert kf.main(["stop", P, "--dir", str(tmp_path / "f")], portos=f) == kf.RC_OK
    fa = fab(tmp_path, f)
    fa.stop_f.write_text("x")
    # `run` limpa o pedido antigo ao arrancar (stop vale para a corrida em curso, não para a seguinte)
    assert fa.run() == kf.RC_OK


def test_stop_durante_a_corrida_para_na_volta_seguinte(tmp_path):
    f = Falso()
    fa = fab(tmp_path, f)
    original = f.lancar

    def lancar(slug):
        original(slug)
        fa.stop_f.write_text("x")
    f.lancar = lancar
    assert fa.run() == kf.RC_PAUSA
    assert json.loads((tmp_path / "f" / f"{P}.json").read_text())["paragem"] == "parado"


def test_ec_093_log_so_tem_campos_simples_sem_segredos(tmp_path):
    f = Falso()
    fab(tmp_path, f).run()
    campos = {k for x in log(tmp_path) for k in x}
    assert campos <= {"ts", "evento", "slug", "marco", "rc", "pr", "razao", "paragem", "avisos", "estado", "motivo", "seguidas", "novo"}
    Registo = kf.Registo(tmp_path / "f" / "x.jsonl")
    Registo("teste", slug="a", objeto={"token": "segredo"})
    assert "segredo" not in (tmp_path / "f" / "x.jsonl").read_text()


def test_status_mostra_marco_fila_gasto_e_proxima_paragem(tmp_path, capsys):
    f = Falso(release=(1,))
    fab(tmp_path, f).run()
    assert kf.main(["status", P, "--dir", str(tmp_path / "f")], portos=f) == kf.RC_OK
    out = capsys.readouterr().out
    assert "pausada" in out and "marco 1" in out and "gasto dia" in out and "release" in out and f"{P}-visao-m1-x:merged" in out


def test_projeto_invalido_e_rc_2():
    assert kf.main(["run", "../x"], portos=Falso()) == kf.RC_USO


def test_marco_de_le_o_numero_do_slug():
    assert kf.marco_de("demo-visao-m3-2026-11-23") == 3 and kf.marco_de("outro") == 0


def test_portos_reais_backlog_le_estado_e_dependencias(tmp_path):
    from sp_fila_testlib import make_sp
    make_sp(tmp_path, f"{P}-visao-m1-d", folder="Done", project=P)
    make_sp(tmp_path, f"{P}-visao-m2-d", folder="TODO", project=P, depends_on=[f"{P}-visao-m1-d"])
    make_sp(tmp_path, "solto", folder="TODO", project=P)
    r = kf.PortosReais(P, tmp_path / "VISION.md", tmp_path, root=tmp_path)
    b = {x["slug"]: x for x in r.backlog(P)}
    assert set(b) == {f"{P}-visao-m1-d", f"{P}-visao-m2-d"}
    assert b[f"{P}-visao-m1-d"]["estado"] == "done" and b[f"{P}-visao-m2-d"]["depende"] == [f"{P}-visao-m1-d"]


def test_portos_reais_decompor_chama_o_script_com_o_vision(tmp_path):
    chamadas = []

    class R:
        returncode, stdout, stderr = 1, "", "VISION inválido"

    r = kf.PortosReais(P, tmp_path / "VISION.md", tmp_path, run=lambda argv, **kw: chamadas.append(argv) or R())
    assert r.decompor(P) == (1, "VISION inválido")
    assert chamadas[0][-3:] == [str(tmp_path / "VISION.md"), "--repo", str(tmp_path)]


def test_portos_reais_resultado_done_procura_o_pr_do_ramo_do_sp(tmp_path):
    chamadas = []

    def run(argv, **kw):
        chamadas.append(argv)

        class R:
            returncode = 0
            stderr = ""
            stdout = "Done · P1\n" if "sp-estado.py" in argv[2] else "42\n"
        return R()

    r = kf.PortosReais(P, tmp_path / "VISION.md", tmp_path, run=run)
    assert r.resultado("demo-visao-m1-2026-11-23") == {"estado": "done", "pr": "42", "gates_ok": True, "motivo": ""}
    assert "agent/demo-visao-m1-2026-11-23" in chamadas[-1]


def test_portos_reais_done_sem_pr_nao_segue_para_merge(tmp_path):
    class R:
        returncode, stderr = 0, ""
        stdout = ""
    run = lambda argv, **kw: type("X", (), {"returncode": 0, "stderr": "", "stdout": "Done\n" if "sp-estado.py" in argv[2] else ""})()  # noqa: E731
    r = kf.PortosReais(P, tmp_path / "VISION.md", tmp_path, run=run)
    res = r.resultado("demo-visao-m1-x")
    assert res["estado"] == "done" and res["pr"] is None and not res["gates_ok"]


def test_portos_reais_corrigir_usa_flags_do_sp_new(tmp_path):
    chamadas = []

    class R:
        returncode, stderr, stdout = 0, "", ""
    r = kf.PortosReais(P, tmp_path / "VISION.md", tmp_path, run=lambda argv, **kw: chamadas.append(argv) or R())
    assert r.corrigir("demo-m1-2026-11-23", "gate vermelho") == "demo-m1-2026-11-23-correcao"
    a = chamadas[0]
    assert "sp-new.py" in a[2] and a[a.index("--slug") + 1] == "demo-m1-2026-11-23-correcao"
    assert a[a.index("--depends-on") + 1] == "demo-m1-2026-11-23" and "--priority" in a and "--project" in a
    assert "gate vermelho" in a[a.index("--restricoes") + 1]


def test_portos_reais_corrigir_falha_do_sp_new_levanta(tmp_path):
    class R:
        returncode, stderr, stdout = 1, "slug existente", ""
    r = kf.PortosReais(P, tmp_path / "VISION.md", tmp_path, run=lambda argv, **kw: R())
    with pytest.raises(RuntimeError, match="slug existente"):
        r.corrigir("demo-x", "m")


# modo manual -------------------------------------------------------------------
M1, M2 = f"{P}-visao-m1-x", f"{P}-visao-m2-x"


def estado(tmp_path):
    return json.loads((tmp_path / "f" / f"{P}.json").read_text())


def test_ec_094_manual_decompoe_e_para_em_aguarda_aprovacao(tmp_path):
    f = Falso()
    assert fab(tmp_path, f).run(manual=True) == kf.RC_PAUSA
    e = estado(tmp_path)
    assert e["paragem"] == "aguarda-aprovacao" and e["manual"] is True
    assert f.chamadas == ["decompor"]


def test_ec_095_approve_so_liberta_os_sps_escolhidos(tmp_path):
    f = Falso(marcos=1)
    f.sps[f"{P}-b"] = {"slug": f"{P}-b", "marco": 1, "estado": "todo", "depende": [], "release": False}
    fab(tmp_path, f).run(manual=True)
    assert fab(tmp_path, f).comando("approve", so=[M1]) == kf.RC_OK
    assert fab(tmp_path, f).run() == kf.RC_PAUSA
    assert f"lancar:{M1}" in f.chamadas and f"lancar:{P}-b" not in f.chamadas
    assert estado(tmp_path)["paragem"] == "aguarda-aprovacao"


def test_approve_sem_so_liberta_tudo_e_run_conclui(tmp_path):
    f = Falso()
    fab(tmp_path, f).run(manual=True)
    assert fab(tmp_path, f).comando("approve") == kf.RC_OK
    assert fab(tmp_path, f).run() == kf.RC_OK
    assert f.chamadas.count("reflect:1") == 1 and estado(tmp_path)["estado"] == "concluida"


def test_approve_slug_desconhecido_e_rc_2_e_nao_grava(tmp_path):
    f = Falso()
    fab(tmp_path, f).run(manual=True)
    assert fab(tmp_path, f).comando("approve", so=["nao-existe"]) == kf.RC_USO
    assert estado(tmp_path).get("aprovados", []) == []


def test_ec_096_step_executa_um_sp_e_para(tmp_path):
    f = Falso()
    fab(tmp_path, f).run(manual=True)
    fab(tmp_path, f).comando("approve")
    assert fab(tmp_path, f).run(passo=True) == kf.RC_PAUSA
    assert estado(tmp_path)["paragem"] == "passo"
    assert f"merge:{M1}" in f.chamadas and f"lancar:{M2}" not in f.chamadas
    assert fab(tmp_path, f).run(passo=True) == kf.RC_PAUSA
    assert f"merge:{M2}" in f.chamadas


def test_step_sem_aprovacao_em_manual_nao_lanca(tmp_path):
    f = Falso()
    fab(tmp_path, f).run(manual=True)
    assert fab(tmp_path, f).run(passo=True) == kf.RC_PAUSA
    assert estado(tmp_path)["paragem"] == "aguarda-aprovacao" and not any(c.startswith("lancar") for c in f.chamadas)


def test_ec_097_pause_e_resume_de_um_sp(tmp_path):
    f = Falso(marcos=1)
    f.sps[f"{P}-b"] = {"slug": f"{P}-b", "marco": 1, "estado": "todo", "depende": [], "release": False}
    fab(tmp_path, f).run(manual=True)
    fab(tmp_path, f).comando("approve")
    assert fab(tmp_path, f).comando("pause", sp=M1) == kf.RC_OK
    assert fab(tmp_path, f).run() == kf.RC_PAUSA
    assert f"lancar:{P}-b" in f.chamadas and f"lancar:{M1}" not in f.chamadas
    assert estado(tmp_path)["paragem"] == "manual"
    assert fab(tmp_path, f).comando("resume", sp=M1) == kf.RC_OK
    assert fab(tmp_path, f).run() == kf.RC_OK and f"merge:{M1}" in f.chamadas


def test_ec_098_skip_cumpre_a_dependencia_sem_lancar(tmp_path):
    f = Falso()
    fab(tmp_path, f).run(manual=True)
    fab(tmp_path, f).comando("approve")
    assert fab(tmp_path, f).comando("skip", sp=M1) == kf.RC_OK
    assert fab(tmp_path, f).run() == kf.RC_OK
    assert f"lancar:{M1}" not in f.chamadas and f"lancar:{M2}" in f.chamadas
    assert f.chamadas.count("reflect:1") == 1


def test_ec_099_takeover_a_factory_nao_toca_e_fecha_com_os_mesmos_gates(tmp_path):
    f = Falso(marcos=1, resultados={M1: [{"estado": "a-correr", "pr": None, "gates_ok": False, "motivo": ""}]})
    fab(tmp_path, f).run(manual=True)
    fab(tmp_path, f).comando("approve")
    assert fab(tmp_path, f).comando("takeover", sp=M1) == kf.RC_OK
    assert fab(tmp_path, f).run() == kf.RC_PAUSA
    assert estado(tmp_path)["paragem"] == "manual" and not any(c in (f"lancar:{M1}", f"merge:{M1}") for c in f.chamadas)
    assert fab(tmp_path, f).run() == kf.RC_OK  # o humano acabou: resultado done com PR e gates verdes
    assert f"merge:{M1}" in f.chamadas and f"lancar:{M1}" not in f.chamadas


def test_takeover_gate_vermelho_nao_cria_correcao_automatica(tmp_path):
    verm = {"estado": "falhou", "pr": None, "gates_ok": False, "motivo": "ruff"}
    f = Falso(marcos=1, resultados={M1: [dict(verm), dict(verm)]})
    fab(tmp_path, f).run(manual=True)
    fab(tmp_path, f).comando("approve")
    fab(tmp_path, f).comando("takeover", sp=M1)
    assert fab(tmp_path, f).run() == kf.RC_PAUSA
    assert not any(c.startswith("corrigir") for c in f.chamadas) and f"merge:{M1}" not in f.chamadas


def test_comando_com_factory_viva_fica_em_fila_e_a_volta_aplica(tmp_path):
    f = Falso()
    fab(tmp_path, f).run(manual=True)
    pasta = tmp_path / "f"
    (pasta / f"{P}.lock").write_text("999999")
    assert fab(tmp_path, f, vivo=lambda pid: True).comando("approve") == kf.RC_OK
    assert estado(tmp_path).get("aprovados", []) == [] and (pasta / f"{P}.cmd.jsonl").exists()
    (pasta / f"{P}.lock").unlink()
    assert fab(tmp_path, f).run() == kf.RC_OK
    assert not (pasta / f"{P}.cmd.jsonl").exists()


def test_ec_100_retoma_apos_crash_em_modo_manual_mantem_aprovacoes(tmp_path):
    f = Falso(marcos=1)
    fa = fab(tmp_path, f)
    fa.guardar({"projeto": P, "estado": "a-correr", "marco": 1, "manual": True, "aprovados": [M1], "sps": {M1: {"fase": "lancado", "correcoes": 0, "pr": None}},
                "seguidas": 0, "gasto": 0.0, "paragem": "", "razao": "", "reflect": []})
    f.por_decompor = False
    assert fa.run() == kf.RC_OK
    assert not any(c.startswith("lancar") for c in f.chamadas) and f.chamadas.count(f"merge:{M1}") == 1


def test_ec_101_sp_feito_a_mao_entra_no_mesmo_estado_e_exige_aprovacao(tmp_path):
    f = Falso(marcos=1)
    f.avulsos_l = [{"slug": "meu-sp", "marco": 0, "estado": "todo", "depende": [], "release": False}]
    fab(tmp_path, f).run(manual=True)
    assert fab(tmp_path, f).comando("approve", so=["meu-sp"]) == kf.RC_OK
    assert fab(tmp_path, f).run() == kf.RC_PAUSA
    assert "lancar:meu-sp" in f.chamadas and "merge:meu-sp" in f.chamadas and f"lancar:{M1}" not in f.chamadas
    assert estado(tmp_path)["sps"]["meu-sp"]["fase"] == "merged"


def test_sem_manual_os_sps_avulsos_nao_entram(tmp_path):
    f = Falso(marcos=1)
    f.avulsos_l = [{"slug": "meu-sp", "marco": 0, "estado": "todo", "depende": [], "release": False}]
    assert fab(tmp_path, f).run() == kf.RC_OK
    assert "lancar:meu-sp" not in f.chamadas


def test_run_auto_sai_do_modo_manual(tmp_path):
    f = Falso(marcos=1)
    fab(tmp_path, f).run(manual=True)
    assert fab(tmp_path, f).run(manual=False) == kf.RC_OK
    assert estado(tmp_path)["manual"] is False


def test_main_encaminha_approve_step_e_comandos_por_sp(tmp_path, capsys):
    f = Falso()
    d = str(tmp_path / "f")
    assert kf.main(["run", P, "--manual", "--dir", d, "--intervalo", "0"], portos=f) == kf.RC_PAUSA
    assert kf.main(["approve", P, "--so", M1, "--dir", d], portos=f) == kf.RC_OK
    assert kf.main(["step", P, "--dir", d, "--intervalo", "0"], portos=f) == kf.RC_PAUSA
    assert kf.main(["pause", P, M2, "--dir", d], portos=f) == kf.RC_OK
    assert kf.main(["pause", P, "--dir", d], portos=f) == kf.RC_USO  # falta o SP
    assert kf.main(["resume", P, M2, "--dir", d], portos=f) == kf.RC_OK
    assert kf.main(["skip", P, M2, "--dir", d], portos=f) == kf.RC_OK
    assert kf.main(["takeover", P, "../x", "--dir", d], portos=f) == kf.RC_USO


def test_status_manual_mostra_aprovacao_e_proxima_acao(tmp_path, capsys):
    f = Falso()
    fab(tmp_path, f).run(manual=True)
    assert kf.main(["status", P, "--dir", str(tmp_path / "f")], portos=f) == kf.RC_OK
    out = capsys.readouterr().out
    assert "manual" in out and "aguarda-aprovacao" in out and "factory approve" in out


def test_portos_reais_avulsos_so_sps_sem_marco_e_que_nao_sao_maes(tmp_path):
    from sp_fila_testlib import make_sp
    make_sp(tmp_path, f"{P}-visao-m1-d", folder="TODO", project=P)
    make_sp(tmp_path, "meu-sp", folder="TODO", project=P)
    make_sp(tmp_path, "feito", folder="Done", project=P)
    make_sp(tmp_path, "mae", folder="TODO", project=P)
    make_sp(tmp_path, "filho", folder="TODO", project=P, extra={"parent": "mae"})
    r = kf.PortosReais(P, tmp_path / "VISION.md", tmp_path, root=tmp_path)
    av = {x["slug"]: x for x in r.avulsos(P)}
    assert {s for s, x in av.items() if x["estado"] != "done"} == {"meu-sp", "filho"} and av["feito"]["estado"] == "done"
    assert all(x["marco"] == 0 for x in av.values()) and f"{P}-visao-m1-d" not in av and "mae" not in av
