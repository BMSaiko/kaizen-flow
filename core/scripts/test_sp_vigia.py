"""Testes do vigia da fila (`sp_vigia.passo`) com estado, backend, git e relógio falsos."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import painel_backend  # noqa: E402
import sp_vigia  # noqa: E402
from sp_carregar import carregar  # noqa: E402


class Backend:
    def __init__(self, mortos=()):
        self.mortos = set(mortos)
        self.titulos, self.fechados = {}, []

    def estado(self, pane):
        return "morto" if pane in self.mortos else "vivo"

    def titulo(self, pane, texto):
        self.titulos[pane] = texto
        return True

    def fechar(self, pane):
        self.fechados.append(pane)
        return True


class Ctx(sp_vigia.Contexto):
    """Contexto falso: tudo em memória, regista as chamadas."""

    def __init__(self, sps, modos=None, merges=None, fim_apos=None, backend=None):
        self.sps = {s: {"slug": s, "pane": f"p-{s}", "worktree": f"/wt/{s}", **d} for s, d in sps.items()}
        self.modos = modos or {}
        self.merges = merges or {}
        self.fim_apos = fim_apos
        self.backend = backend or Backend()
        self.chamadas, self.toasts, self.notas, self.maes = [], [], [], []
        self.global_existe = True
        self.arrumos = {}

    def ler_fila(self):
        return {"fila": {"id": "f1"}, "sps": {s: dict(d) for s, d in self.sps.items()}}

    def transitar(self, slug, estado, msg=None):
        self.chamadas.append(("transitar", slug, estado, msg))
        self.sps[slug]["estado"] = estado
        self.sps[slug]["msg"] = msg

    def modo(self, sp):
        return self.modos.get(sp["slug"], "auto")

    def arrumar(self, sp):
        return self.arrumos.get(sp["slug"], (0, ""))

    def merge(self, slug):
        self.chamadas.append(("merge", slug))
        r = self.merges.get(slug, (0, "ok"))
        if isinstance(r, list):
            return r.pop(0)
        return r

    def clean(self, slug):
        self.chamadas.append(("clean", slug))
        return 0, "ok"

    def seguinte(self, slug):
        self.chamadas.append(("seguinte", slug))
        if self.fim_apos == slug:
            return {"acao": "fim", "relatorio": "/rel.md", "fechar_mae": "mae"}
        return {"acao": "espera", "sessoes": []}

    def fechar_mae(self, mae):
        self.maes.append(mae)
        return 0, "ok"

    def toast(self, texto):
        self.toasts.append(texto)

    def nota_relatorio(self, path, texto):
        self.notas.append((path, texto))

    def estado_global(self):
        return self.global_existe

    def log(self, msg):
        pass


def nomes(ctx):
    return [c[0] for c in ctx.chamadas]


def test_done_auto_faz_merge_fecha_limpa_e_lanca_seguinte():
    ctx, mem = Ctx({"a": {"estado": "done"}}), sp_vigia.memoria_nova()
    assert sp_vigia.passo(ctx, mem) == "continua"
    assert nomes(ctx) == ["merge", "clean", "seguinte"]
    assert ctx.backend.fechados == ["p-a"]
    sp_vigia.passo(ctx, mem)  # o mesmo done não volta a ser tratado
    assert nomes(ctx) == ["merge", "clean", "seguinte"]


def test_done_manual_fica_bloqueado_sem_merge_e_avisa():
    ctx = Ctx({"a": {"estado": "done"}}, modos={"a": "manual"})
    sp_vigia.passo(ctx, sp_vigia.memoria_nova())
    assert ("merge", "a") not in ctx.chamadas
    assert ctx.sps["a"]["estado"] == "bloqueado" and "manual" in ctx.sps["a"]["msg"]
    assert ctx.backend.fechados == []
    assert ctx.backend.titulos["p-a"] == "! a" and ctx.toasts and "a" in ctx.toasts[0]


def test_gates_vermelhos_ou_conflito_bloqueiam_com_motivo():
    ctx = Ctx({"a": {"estado": "done"}}, merges={"a": (1, "gates falhados após o rebase")})
    sp_vigia.passo(ctx, sp_vigia.memoria_nova())
    assert ctx.sps["a"]["estado"] == "bloqueado" and "gates falhados" in ctx.sps["a"]["msg"]
    assert "clean" not in nomes(ctx) and "seguinte" not in nomes(ctx)
    assert ctx.backend.fechados == []


def test_arrumar_falhado_bloqueia_sem_merge():
    ctx = Ctx({"a": {"estado": "done"}})
    ctx.arrumos["a"] = (1, "caminho sensível por commitar: .env")
    sp_vigia.passo(ctx, sp_vigia.memoria_nova())
    assert "merge" not in nomes(ctx)
    assert ctx.sps["a"]["estado"] == "bloqueado" and ".env" in ctx.sps["a"]["msg"]


def _repo(tmp_path):
    import subprocess
    def g(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    g("init", "-q")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    (tmp_path / "mae.md").write_text("state: TODO\n", encoding="utf-8")
    g("add", "-A")
    g("commit", "-q", "-m", "base")
    return g


def test_arrumar_worktree_commita_resto_e_apaga_commit_md(tmp_path):
    import subprocess
    _repo(tmp_path)
    (tmp_path / "mae.md").write_text("state: Done\n", encoding="utf-8")
    (tmp_path / "COMMIT_1.md").write_text("x", encoding="utf-8")
    rc, out = sp_vigia.arrumar_worktree(subprocess.run, tmp_path, "a")
    assert rc == 0 and "1 caminho" in out
    assert not (tmp_path / "COMMIT_1.md").exists()
    st = subprocess.run(["git", "-C", str(tmp_path), "status", "--porcelain"], capture_output=True, text=True)
    assert st.stdout == ""
    assert sp_vigia.arrumar_worktree(subprocess.run, tmp_path, "a") == (0, "")


def test_arrumar_worktree_recusa_segredos(tmp_path):
    import subprocess
    _repo(tmp_path)
    (tmp_path / ".env").write_text("K=1", encoding="utf-8")
    rc, out = sp_vigia.arrumar_worktree(subprocess.run, tmp_path, "a")
    assert rc == 1 and ".env" in out


def test_clean_repete_enquanto_worktree_em_uso():
    class R:
        def __init__(self, rc, out):
            self.returncode, self.stdout, self.stderr = rc, out, ""
    seq = [R(1, "erro: worktree em uso"), R(1, "erro: worktree em uso"), R(0, "limpo")]
    c = sp_vigia.ContextoReal.__new__(sp_vigia.ContextoReal)
    c.run, c.repo, c.scripts = (lambda *a, **k: seq.pop(0)), ".", Path("scripts")
    assert c.clean("x", pausa=0) == (0, "limpo") and seq == []


def test_lock_ocupado_tenta_no_tick_seguinte():
    ctx = Ctx({"a": {"estado": "done"}}, merges={"a": [(1, "outro merge em curso (lock x)"), (0, "ok")]})
    mem = sp_vigia.memoria_nova()
    sp_vigia.passo(ctx, mem)
    assert ctx.sps["a"]["estado"] == "done" and "seguinte" not in nomes(ctx)
    sp_vigia.passo(ctx, mem)
    assert nomes(ctx) == ["merge", "merge", "clean", "seguinte"]


def test_duas_filas_disputam_o_lock_de_merge():
    lock = {"dono": None}

    def fazer(nome):
        def merge(slug):
            if lock["dono"] not in (None, nome):
                return 1, "outro merge em curso"
            lock["dono"] = nome
            return 0, "ok"
        return merge

    a, b = Ctx({"a": {"estado": "done"}}), Ctx({"b": {"estado": "done"}})
    a.merge, b.merge = fazer("A"), fazer("B")
    ma, mb = sp_vigia.memoria_nova(), sp_vigia.memoria_nova()
    sp_vigia.passo(a, ma)
    sp_vigia.passo(b, mb)  # A ainda tem o lock: B espera
    assert "seguinte" in nomes(a) and "seguinte" not in nomes(b)
    lock["dono"] = None
    sp_vigia.passo(b, mb)
    assert "seguinte" in nomes(b)


def test_avisos_por_transicao_sem_repetir():
    ctx, mem = Ctx({"a": {"estado": "pergunta"}}), sp_vigia.memoria_nova()
    sp_vigia.passo(ctx, mem)
    sp_vigia.passo(ctx, mem)
    assert ctx.backend.titulos["p-a"] == "? a" and len(ctx.toasts) == 1
    ctx.sps["a"]["estado"] = "a-correr"
    sp_vigia.passo(ctx, mem)
    assert ctx.backend.titulos["p-a"] == "a"
    ctx.sps["a"]["estado"] = "pergunta"
    sp_vigia.passo(ctx, mem)
    assert len(ctx.toasts) == 2


def test_falhou_marca_avisa_e_liberta_uma_vez():
    ctx, mem = Ctx({"a": {"estado": "falhou"}}), sp_vigia.memoria_nova()
    sp_vigia.passo(ctx, mem)
    sp_vigia.passo(ctx, mem)
    assert ctx.backend.titulos["p-a"] == "x a" and len(ctx.toasts) == 1
    assert nomes(ctx).count("seguinte") == 1


def test_bloqueado_nao_chama_seguinte():
    ctx = Ctx({"a": {"estado": "bloqueado"}})
    sp_vigia.passo(ctx, sp_vigia.memoria_nova())
    assert "seguinte" not in nomes(ctx) and ctx.backend.titulos["p-a"] == "! a"


def test_painel_morto_sem_estado_passa_a_falhou():
    ctx = Ctx({"a": {"estado": "a-correr"}}, backend=Backend(mortos={"p-a"}))
    sp_vigia.passo(ctx, sp_vigia.memoria_nova())
    assert ctx.sps["a"]["estado"] == "falhou" and ctx.sps["a"]["msg"] == "painel fechou sem estado"
    assert ("seguinte", "a") in ctx.chamadas


def test_pendente_sem_pane_nao_e_morto():
    ctx = Ctx({"a": {"estado": "a-correr", "pane": None}}, backend=Backend(mortos={None}))
    sp_vigia.passo(ctx, sp_vigia.memoria_nova())
    assert ctx.chamadas == []


def test_fim_fecha_mae_e_regista_kaizen_sync_pendente():
    ctx = Ctx({"a": {"estado": "done"}}, fim_apos="a")
    assert sp_vigia.passo(ctx, sp_vigia.memoria_nova()) == "fim"
    assert ctx.maes == ["mae"]
    assert ctx.notas and ctx.notas[0][0] == "/rel.md" and "/kaizen-sync" in ctx.notas[0][1]


def test_fila_parada_termina_o_vigia():
    ctx = Ctx({"a": {"estado": "a-correr"}})
    ctx.global_existe = False
    assert sp_vigia.passo(ctx, sp_vigia.memoria_nova()) == "fim"


def test_erro_inesperado_num_sp_nao_para_os_outros():
    ctx = Ctx({"a": {"estado": "done"}, "b": {"estado": "pergunta"}})

    def rebenta(slug):
        raise RuntimeError("boom")
    ctx.merge = rebenta
    sp_vigia.passo(ctx, sp_vigia.memoria_nova())
    assert ctx.backend.titulos["p-b"] == "? b"


def test_pidfile_um_so_vigia(tmp_path):
    pid = tmp_path / "vigia.pid"
    assert sp_vigia.reclamar_pidfile(pid, 111, vivo=lambda p: False)
    assert not sp_vigia.reclamar_pidfile(pid, 222, vivo=lambda p: True)
    assert sp_vigia.reclamar_pidfile(pid, 333, vivo=lambda p: False)  # dono morto: obsoleto
    assert pid.read_text().strip() == "333"


def test_memoria_persiste(tmp_path):
    mem = sp_vigia.memoria_nova()
    mem["avisos"]["a"] = "pergunta"
    mem["tratados"].append("b")
    p = tmp_path / "vigia.json"
    sp_vigia.guardar_memoria(p, mem)
    assert sp_vigia.ler_memoria(p) == mem
    assert sp_vigia.ler_memoria(tmp_path / "nada.json") == sp_vigia.memoria_nova()


# --- passo 4: ciclo, pidfile, arranque destacado e paragem ---------------------------------------

class CtxCiclo:
    backend = None

    def __init__(self, ticks):
        self.ticks, self.logs = ticks, []

    def estado_global(self):
        self.ticks -= 1
        return self.ticks > 0

    def ler_fila(self):
        return {"sps": {}}

    def log(self, msg):
        self.logs.append(msg)


def test_correr_ate_fim_guarda_memoria(tmp_path):
    mem = tmp_path / "vigia.json"
    sonos = []
    assert sp_vigia.correr(CtxCiclo(3), mem, intervalo=5, dormir=sonos.append) == "fim"
    assert sonos == [5, 5] and mem.is_file()


def test_correr_uma_vez():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        assert sp_vigia.correr(CtxCiclo(9), Path(d) / "m.json", uma_vez=True, dormir=lambda s: 1 / 0) == "continua"


def test_caminhos_na_pasta_da_fila(tmp_path):
    assert [p.name for p in sp_vigia.caminhos(tmp_path)] == ["vigia.pid", "vigia.log", "vigia.json"]


def test_arrancar_destacado():
    chamadas = []
    sp_vigia.arrancar("f1", "x/sp-vigia.py", run=lambda argv, **kw: chamadas.append((argv, kw)))
    argv, kw = chamadas[0]
    assert argv[-2:] == ["x/sp-vigia.py", "f1"] and "-I" in argv
    assert kw["creationflags"] == painel_backend._FLAGS["destacado"]


def test_parar_mata_vivo_e_apaga_pidfile(tmp_path):
    pf = tmp_path / "vigia.pid"
    pf.write_text("42", encoding="utf-8")
    mortos = []
    assert sp_vigia.parar(pf, lambda p: True, mortos.append) == 42
    assert mortos == [42] and not pf.exists()


def test_parar_pid_morto_so_apaga(tmp_path):
    pf = tmp_path / "vigia.pid"
    pf.write_text("42", encoding="utf-8")
    assert sp_vigia.parar(pf, lambda p: False, lambda p: 1 / 0) is None and not pf.exists()
    assert sp_vigia.parar(pf, lambda p: True, lambda p: 1 / 0) is None


def _cli():
    m = carregar(Path(__file__).parent / "sp-vigia.py", "sp_vigia_cli", registar=False, fresco=True)
    return m


def test_cli_um_tick_apaga_pidfile(tmp_path, monkeypatch):
    cli = _cli()
    (tmp_path / "f1").mkdir()
    monkeypatch.setattr(cli.pe, "raiz", lambda root=None: tmp_path)
    ctx = CtxCiclo(9)
    assert cli.main(["f1", "--uma-vez"], contexto=ctx) == 0
    assert not (tmp_path / "f1" / "vigia.pid").exists() and (tmp_path / "f1" / "vigia.json").is_file()


def test_cli_recusa_segundo_vigia(tmp_path, monkeypatch):
    cli = _cli()
    (tmp_path / "f1").mkdir()
    (tmp_path / "f1" / "vigia.pid").write_text("99999", encoding="utf-8")
    monkeypatch.setattr(cli.pe, "raiz", lambda root=None: tmp_path)
    monkeypatch.setattr(cli.pe, "pid_vivo", lambda p: True)
    assert cli.main(["f1", "--uma-vez"], contexto=CtxCiclo(9)) == 1


def test_cli_fila_desconhecida(tmp_path, monkeypatch):
    cli = _cli()
    monkeypatch.setattr(cli.pe, "raiz", lambda root=None: tmp_path)
    assert cli.main(["nao-existe"]) == 1


def test_memoria_do_vigia_nao_e_estado_de_sp(tmp_path):
    import sp_painel_estado as pe
    fid = pe.criar_fila(programa="m", root=tmp_path)
    sp_vigia.guardar_memoria(sp_vigia.caminhos(tmp_path / fid)[2], sp_vigia.memoria_nova())
    assert pe.ler(fid, root=tmp_path)["sps"] == {}


def test_cli_erro_fatal_vai_para_o_log(tmp_path, monkeypatch):
    cli = _cli()
    (tmp_path / "f1").mkdir()
    monkeypatch.setattr(cli.pe, "raiz", lambda root=None: tmp_path)

    class Rebenta(CtxCiclo):
        def ler_fila(self):
            raise RuntimeError("boom")
    ctx = Rebenta(9)
    try:
        cli.main(["f1", "--uma-vez"], contexto=ctx)
    except RuntimeError:
        pass
    assert any("vigia morreu" in m and "boom" in m for m in ctx.logs)
    assert not (tmp_path / "f1" / "vigia.pid").exists()


def test_contexto_real_usa_o_estado_da_fila(tmp_path):
    import sp_fila_estado as fe
    c = sp_vigia.ContextoReal("fila-x", tmp_path / "v.log", backend=object())
    assert c.estado_path == fe.estado_de("fila-x")
    assert c.estado_path != fe.ESTADO


# --- escalada de modelo (sp_escalada) ------------------------------------------------------------

import pytest  # noqa: E402
import sp_escalada  # noqa: E402

PARAGEM = "## Paragem DA\n- Passo: 3.1\n- Tentativas: 2\n- Causa: teste vermelho\n- Próximo passo: rever\n"


def _sp_texto(nivel="simples", perfil=None, escalar=None, paragem=True, escalado=False):
    fm = ["---", "slug: a", f"michi_modelo: {nivel}"] + ([f"perfil: {perfil}"] if perfil else []) \
        + ([f"escalar: {escalar}"] if escalar else []) + ["---", "# SP", ""]
    corpo = (PARAGEM if paragem else "") + ("## Report modo auto\n- escalado: simples → default\n" if escalado else "")
    return "\n".join(fm) + corpo


@pytest.mark.parametrize("perfil,escalar,nivel,estado,paragem,esperado", [
    (None, None, "simples", "falhou", True, ("simples", "default")),
    ("normal", None, "default", "bloqueado", True, ("default", "complexo")),
    ("autonomo", None, "complexo", "falhou", True, ("complexo", "critico")),
    ("cauteloso", None, "simples", "falhou", True, None),
    ("cauteloso", "sim", "simples", "falhou", True, ("simples", "default")),
    ("normal", "nao", "simples", "falhou", True, None),
    (None, None, "critico", "falhou", True, None),
    (None, None, "simples", "falhou", False, None),
    (None, None, "simples", "pergunta", True, None),
    (None, None, "simples", "done", True, None),
])
def test_decidir_tabela_perfil_nivel_causa(perfil, escalar, nivel, estado, paragem, esperado):
    r = sp_escalada.decidir(_sp_texto(nivel, perfil, escalar, paragem), estado)
    assert (r[:2] if r else None) == esperado
    if r:
        assert r[2] == "teste vermelho"


def test_decidir_uma_so_escalada():
    assert sp_escalada.decidir(_sp_texto(escalado=True), "falhou") is None


def test_deve_escalar_puro():
    base = {"estado": "falhou", "paragem": "x", "escalado": False, "seguinte": "default"}
    assert sp_escalada.deve_escalar({}, base)
    assert not sp_escalada.deve_escalar({}, {**base, "seguinte": None})
    assert not sp_escalada.deve_escalar({"perfil": "cauteloso"}, base)


def test_causa_paragem_ultima_secao():
    t = "## Paragem DA\n- Causa: velha\n## Outra\n" + PARAGEM
    assert sp_escalada.causa_paragem(t) == "teste vermelho" and sp_escalada.causa_paragem("# nada") is None


def test_registar_report_cria_ou_acrescenta_e_mantem_eol(tmp_path):
    p = tmp_path / "a.md"
    p.write_bytes(b"# SP\r\n")
    sp_escalada.registar_report(p, "- escalado: x")
    assert p.read_bytes() == b"# SP\r\n\r\n## Report modo auto\r\n\r\n- escalado: x\r\n"
    p.write_bytes(b"# SP\n## Report modo auto\n- feito\n\n## Reflect\n- r\n")
    sp_escalada.registar_report(p, "- escalado: y")
    assert p.read_bytes() == b"# SP\n## Report modo auto\n- feito\n- escalado: y\n\n## Reflect\n- r\n"


def test_relancar_abre_painel_no_nivel_seguinte_na_mesma_vaga():
    from sp_fila_testlib import PainelFalso
    import sp_painel_estado as pe
    fila = pe.criar_fila(None)
    pe.registar(fila, "esc-a", worktree="/wt/esc-a", pane="7")
    pe.transitar("esc-a", "a-correr", fila=fila)
    pe.transitar("esc-a", "falhou", msg="gate", fila=fila)
    painel = PainelFalso()
    painel.enviar = lambda pane, texto: painel.enviados.append((pane, texto)) or True
    res = sp_escalada.relancar("esc-a", "complexo", {"pane": "7", "worktree": "/wt/esc-a"}, fila, painel)
    assert res["estado"] == "a-correr" and res["modelo"] == "claude-opus-5-5"
    assert painel.fechados == ["7"] and painel.abertos[0][1] == "/wt/esc-a"
    assert painel.abertos[0][0][:3] == ["claude", "--model", "claude-opus-5-5"]
    assert "## Paragem DA" in painel.enviados[0][1] and "/michi --auto esc-a" in painel.enviados[0][1]
    reg = pe.ler(fila, "esc-a")
    assert reg["estado"] == "a-correr" and reg["modelo"] == "claude-opus-5-5"


def test_vigia_escalada_relanca_sem_avancar_a_fila():
    class CtxEsc(Ctx):
        def escalar(self, sp):
            self.chamadas.append(("escalar", sp["slug"]))
            self.sps[sp["slug"]]["estado"] = "a-correr"
            return {"de": "simples", "para": "default", "estado": "a-correr"}
    ctx, mem = CtxEsc({"a": {"estado": "falhou"}}), sp_vigia.memoria_nova()
    sp_vigia.passo(ctx, mem)
    assert nomes(ctx) == ["escalar"] and mem["escalados"] == ["a"]
    assert any("escalado simples → default" in t for t in ctx.toasts)
    ctx.sps["a"]["estado"] = "falhou"  # falha de novo no nível novo: a fila avança como hoje
    sp_vigia.passo(ctx, mem)
    assert nomes(ctx) == ["escalar", "seguinte"]


def test_vigia_sem_escalada_comportamento_de_sempre():
    ctx, mem = Ctx({"a": {"estado": "falhou"}}), sp_vigia.memoria_nova()
    sp_vigia.passo(ctx, mem)
    assert nomes(ctx) == ["seguinte"] and "escalados" not in mem


def test_contexto_real_escala_uma_vez_e_regista(tmp_path, monkeypatch):
    wt = tmp_path / "wt"
    sp = wt / "knowledge" / "p" / "sp" / "Doing" / "a.md"
    sp.parent.mkdir(parents=True)
    sp.write_text(_sp_texto("default"), encoding="utf-8")
    estado = tmp_path / "estado.json"
    estado.write_text('{"usados": 0}', encoding="utf-8")
    ctx = sp_vigia.ContextoReal.__new__(sp_vigia.ContextoReal)
    ctx.fila, ctx.backend, ctx.run, ctx.estado_path, ctx.log_path = "f", None, None, estado, tmp_path / "v.log"
    chamadas = []
    monkeypatch.setattr(sp_escalada, "relancar", lambda *a, **k: chamadas.append(a[:2]) or {"estado": "a-correr", "pane": "9"})
    r = ctx.escalar({"slug": "a", "worktree": str(wt), "estado": "bloqueado"})
    assert r["de"] == "default" and r["para"] == "complexo" and chamadas == [("a", "complexo")]
    assert "- escalado: default → complexo" in sp.read_text(encoding="utf-8")
    import json
    assert json.loads(estado.read_text(encoding="utf-8"))["escaladas"] == [{"slug": "a", "de": "default", "para": "complexo"}]
    assert ctx.escalar({"slug": "a", "worktree": str(wt), "estado": "falhou"}) is None


# --- pausa por quota/rede/sessão (preflight-erros-ux, EC-016/017/066) -----------------

from datetime import datetime as _dt  # noqa: E402

QUOTA = "trabalho...\n✻ a pensar\nClaude usage limit reached. Your limit will reset at 3pm (Europe/Lisbon).\n> "


class BackendEcra(Backend):
    def __init__(self, ecras, mortos=(), envio_ok=True):
        super().__init__(mortos)
        self.ecras, self.enviados, self.envio_ok = ecras, [], envio_ok

    def ecra(self, pane):
        v = self.ecras.get(pane, "")
        return v.pop(0) if isinstance(v, list) else v

    def enviar(self, pane, texto):
        self.enviados.append((pane, texto))
        return self.envio_ok


class CtxPausa(Ctx):
    def __init__(self, *a, agora=None, **kw):
        super().__init__(*a, **kw)
        self._agora = agora or _dt(2026, 11, 18, 10, 0, 0)
        self.escaladas = []

    def agora(self):
        return self._agora

    def pausar(self, slug, msg, motivo, retoma_em):
        self.chamadas.append(("pausar", slug, motivo, retoma_em))
        self.sps[slug].update(estado="bloqueado", msg=msg, motivo=motivo, retoma_em=retoma_em)

    def retomar(self, slug, msg):
        self.chamadas.append(("retomar", slug))
        self.sps[slug].update(estado="a-correr", msg=msg, motivo=None, retoma_em=None)

    def escalar(self, sp):
        self.escaladas.append(sp["slug"])
        return None


def test_quota_no_ecra_parado_bloqueia_com_motivo_e_retoma_em():
    ctx = CtxPausa({"a": {"estado": "a-correr"}}, backend=BackendEcra({"p-a": QUOTA}))
    mem = sp_vigia.memoria_nova()
    sp_vigia.passo(ctx, mem)
    assert ctx.sps["a"]["estado"] == "a-correr"  # 1.º tick: ainda não se sabe se o ecrã está parado
    sp_vigia.passo(ctx, mem)
    sp = ctx.sps["a"]
    assert sp["estado"] == "bloqueado" and sp["motivo"].startswith("EC-016") and sp["retoma_em"] == "2026-11-18T15:00:00"
    assert "retoma automática às 2026-11-18T15:00:00" in sp["msg"]
    assert ctx.backend.titulos["p-a"].startswith("! ")
    sp_vigia.passo(ctx, mem)
    assert ctx.escaladas == []  # pausa de quota não escala de modelo


def test_ecra_a_mexer_com_texto_de_quota_nao_bloqueia():
    ctx = CtxPausa({"a": {"estado": "a-correr"}}, backend=BackendEcra({"p-a": [QUOTA, QUOTA + "\nmais uma linha", QUOTA]}))
    mem = sp_vigia.memoria_nova()
    for _ in range(3):
        sp_vigia.passo(ctx, mem)
    assert ctx.sps["a"]["estado"] == "a-correr"


def test_ecra_normal_parado_nao_bloqueia():
    ctx = CtxPausa({"a": {"estado": "a-correr"}}, backend=BackendEcra({"p-a": "> a pensar\n"}))
    mem = sp_vigia.memoria_nova()
    sp_vigia.passo(ctx, mem)
    sp_vigia.passo(ctx, mem)
    assert ctx.sps["a"]["estado"] == "a-correr"


def test_sessao_expirada_bloqueia_sem_retoma_automatica():
    ctx = CtxPausa({"a": {"estado": "a-correr"}}, backend=BackendEcra({"p-a": "OAuth token has expired · Please run /login\n> "}))
    mem = sp_vigia.memoria_nova()
    sp_vigia.passo(ctx, mem)
    sp_vigia.passo(ctx, mem)
    sp = ctx.sps["a"]
    assert sp["estado"] == "bloqueado" and sp["motivo"].startswith("EC-066") and sp["retoma_em"] is None
    assert "kaizen resume a" in sp["msg"]
    ctx._agora = _dt(2026, 11, 20)
    sp_vigia.passo(ctx, mem)
    assert ctx.sps["a"]["estado"] == "bloqueado" and ctx.backend.enviados == []


def test_retoma_so_depois_de_retoma_em_e_envia_continua():
    sps = {"a": {"estado": "bloqueado", "motivo": "EC-016 quota", "retoma_em": "2026-11-18T15:00:00", "msg": "x"}}
    ctx = CtxPausa(sps, backend=BackendEcra({}), agora=_dt(2026, 11, 18, 14, 59))
    mem = sp_vigia.memoria_nova()
    sp_vigia.passo(ctx, mem)
    assert ctx.sps["a"]["estado"] == "bloqueado" and ctx.backend.enviados == []
    ctx._agora = _dt(2026, 11, 18, 15, 0, 1)
    sp_vigia.passo(ctx, mem)
    assert ctx.sps["a"]["estado"] == "a-correr" and ctx.backend.enviados == [("p-a", "continua")]
    assert ctx.sps["a"]["retoma_em"] is None


def test_retoma_com_envio_falhado_volta_a_pausa_com_hora_nova():
    sps = {"a": {"estado": "bloqueado", "motivo": "EC-017 rede", "retoma_em": "2026-11-18T09:00:00", "msg": "x"}}
    ctx = CtxPausa(sps, backend=BackendEcra({}, envio_ok=False))
    sp_vigia.passo(ctx, sp_vigia.memoria_nova())
    sp = ctx.sps["a"]
    assert sp["estado"] == "bloqueado" and sp["retoma_em"] == "2026-11-18T10:30:00"


def test_retoma_com_painel_morto_fica_para_o_kaizen_resume():
    sps = {"a": {"estado": "bloqueado", "motivo": "EC-016 quota", "retoma_em": "2026-11-18T09:00:00"}}
    ctx = CtxPausa(sps, backend=BackendEcra({}, mortos=("p-a",)))
    sp_vigia.passo(ctx, sp_vigia.memoria_nova())
    assert ctx.sps["a"]["estado"] == "bloqueado" and ctx.backend.enviados == []


def test_bloqueado_sem_pausa_continua_a_escalar():
    ctx = CtxPausa({"a": {"estado": "bloqueado", "msg": "gate"}}, backend=BackendEcra({}))
    sp_vigia.passo(ctx, sp_vigia.memoria_nova())
    assert ctx.escaladas == ["a"]


def test_contexto_real_grava_motivo_e_retoma_em(tmp_path):
    import sp_painel_estado as pe
    pe.criar_fila("f1", root=tmp_path, ordem=["a"])
    pe.registar("f1", "a", root=tmp_path, pane="1")
    pe.transitar("a", "a-correr", fila="f1", root=tmp_path)
    ctx = sp_vigia.ContextoReal.__new__(sp_vigia.ContextoReal)
    ctx.pe, ctx.fila = pe, "f1"
    orig = pe.transitar
    try:
        pe.transitar = lambda *a, **kw: orig(*a, root=tmp_path, **kw)
        ctx.pausar("a", "msg", "EC-016 quota", "2026-11-18T15:00:00")
        sp = pe.ler("f1", "a", root=tmp_path)
        assert sp["estado"] == "bloqueado" and sp["motivo"] == "EC-016 quota" and sp["retoma_em"] == "2026-11-18T15:00:00"
        ctx.retomar("a", "ok")
        sp = pe.ler("f1", "a", root=tmp_path)
        assert sp["estado"] == "a-correr" and sp["motivo"] is None and sp["retoma_em"] is None
    finally:
        pe.transitar = orig
