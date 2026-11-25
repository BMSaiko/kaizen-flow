"""Testes de kf_factory: máquina de estados da factory com portos falsos (feliz, orçamento, gate vermelho, retoma, lock, release)."""
import json


import kf_factory as kf

P = "demo"


class Falso(kf.Portos):
    """Backlog em memória: cada SP termina com `resultados[slug]` (lista consumida); `esperar` não dorme."""

    def __init__(self, marcos=2, release=(), resultados=None, cfg=None, custos=None, dia=0.0, merge_rc=None):
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
            self.sps[slug]["estado"] = "done"
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
    return kf.Fabrica(P, falso, tmp_path / "f", intervalo=0, max_voltas=200, **kw)


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
