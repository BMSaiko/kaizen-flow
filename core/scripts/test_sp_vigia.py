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
