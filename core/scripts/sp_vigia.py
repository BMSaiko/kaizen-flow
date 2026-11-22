"""Vigia da fila de painéis (sem LLM): lê o estado de cada SP em disco e age.

`passo(ctx, mem)` é um tick: `done` de SP auto → merge (lock global do `sb-agent`), fecha o painel, limpa a worktree e
lança o seguinte; SP manual, gates vermelhos ou conflito → `bloqueado` com motivo; `pergunta`/`bloqueado`/`falhou` →
título `? `/`! `/`x ` + toast, um por transição; painel morto sem estado → `falhou`. `falhou`/`bloqueado` por gate com
nível de modelo acima → relançado uma vez nesse nível (`sp_escalada`), sem avançar a fila. Devolve "continua" ou "fim".
Os efeitos vivem no `Contexto` (o real é `ContextoReal`; os testes trocam-no).

Uso: módulo importado por sp-vigia.py; sem execução direta
rc: sem execução direta"""
import hashlib
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_leitura  # noqa: E402
from painel_backend import popen_sem_janela, run_hidden  # noqa: E402
from sp_disco import guardar, ler_json  # noqa: E402
import kf_erros  # noqa: E402

MARCAS = {"pergunta": "? ", "bloqueado": "! ", "falhou": "x "}
LOCK_OCUPADO = "outro merge em curso"
INTERVALO = 10.0
ECRA_LINHAS = 15  # cauda do ecrã lida para quota/rede/sessão (o resto é histórico)
EC_PAUSA = (kf_erros.EC_QUOTA, kf_erros.EC_REDE, kf_erros.EC_SESSAO)
RETOMA_TEXTO = "continua"  # enviado ao painel quando a pausa (quota/rede) acaba


def memoria_nova():
    return {"avisos": {}, "tratados": []}


def ler_memoria(path):
    dados = ler_json(path)
    try:
        mem = {"avisos": dict(dados.get("avisos") or {}), "tratados": list(dados.get("tratados") or [])}
        if dados.get("escalados"):
            mem["escalados"] = list(dados["escalados"])
        return mem
    except (AttributeError, TypeError, ValueError):
        return memoria_nova()


def guardar_memoria(path, mem):
    guardar(path, mem)


def reclamar_pidfile(path, pid, vivo):
    """Um só vigia por fila: escreve `pid` se não há dono vivo; False se outro vigia vivo já o tem."""
    p = Path(path)
    try:
        atual = int(p.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        atual = None
    if atual is not None and atual != pid and vivo(atual):
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(pid), encoding="utf-8")
    return True


class Contexto:
    """Efeitos do vigia. Ver `ContextoReal` para o significado de cada método."""
    backend = None

    def ler_fila(self): raise NotImplementedError
    def transitar(self, slug, estado, msg=None): raise NotImplementedError
    def modo(self, sp): raise NotImplementedError
    def arrumar(self, sp): raise NotImplementedError
    def merge(self, slug): raise NotImplementedError
    def clean(self, slug): raise NotImplementedError
    def seguinte(self, slug): raise NotImplementedError
    def fechar_mae(self, mae): raise NotImplementedError
    def toast(self, texto): raise NotImplementedError
    def nota_relatorio(self, path, texto): raise NotImplementedError
    def estado_global(self): raise NotImplementedError
    def log(self, msg): raise NotImplementedError

    def agora(self):
        return datetime.now()

    def pausar(self, slug, msg, motivo, retoma_em):
        """SP a-correr → bloqueado por quota/rede/sessão, com `motivo` e `retoma_em` (o contexto real grava os campos)."""
        self.transitar(slug, "bloqueado", msg)

    def retomar(self, slug, msg):
        """bloqueado (pausa acabada) → a-correr, limpando `motivo` e `retoma_em`."""
        self.transitar(slug, "a-correr", msg)

    def escalar(self, sp):
        """Relança o SP no nível seguinte se `sp_escalada` o pedir; {de, para, ...} ou None (sem escalada)."""
        return


def _seguro(ctx, f, *a):
    try:
        return f(*a)
    except Exception as e:  # noqa: BLE001 — um aviso falhado nunca pára o vigia
        ctx.log(f"aviso falhou: {e}")
        return None


def _avisar(ctx, mem, sp):
    slug, estado, pane = sp["slug"], sp.get("estado"), sp.get("pane")
    if mem["avisos"].get(slug) == estado:
        return
    marca = MARCAS.get(estado)
    if marca is None:  # voltou a correr: título limpo, aviso seguinte volta a sair
        if slug in mem["avisos"] and pane:
            _seguro(ctx, ctx.backend.titulo, pane, slug)
        mem["avisos"].pop(slug, None)
        return
    if pane:
        _seguro(ctx, ctx.backend.titulo, pane, marca + slug)
    msg = sp.get("msg")
    _seguro(ctx, ctx.toast, f"{marca}{slug}" + (f": {msg}" if msg else ""))
    mem["avisos"][slug] = estado
    ctx.log(f"aviso {estado} {slug}")


def _fim(ctx, res):
    mae = res.get("fechar_mae")
    if mae:
        rc, out = ctx.fechar_mae(mae)
        ctx.log(f"fecho da mãe {mae}: rc={rc} {out}")
    if res.get("relatorio"):
        _seguro(ctx, ctx.nota_relatorio, res["relatorio"],
                "\n## Pendente para o utilizador\n- `/kaizen-sync` pedido pelo `sp-fechar` (não corre nos painéis nem no vigia).\n"
                + ("" if not mae else f"- Mãe `{mae}`: ver o log do vigia se o fecho falhou.\n"))
    ctx.log(f"fila terminada: {res.get('motivo') or ''}")
    return "fim"


def _seguinte(ctx, mem, slug):
    mem["tratados"].append(slug)
    res = ctx.seguinte(slug) or {}
    ctx.log(f"seguinte {slug}: {res.get('acao')}")
    return _fim(ctx, res) if res.get("acao") == "fim" else None


def _bloquear(ctx, mem, sp, motivo):
    ctx.transitar(sp["slug"], "bloqueado", motivo)
    _avisar(ctx, mem, {**sp, "estado": "bloqueado", "msg": motivo})


def _done(ctx, mem, sp):
    slug = sp["slug"]
    if ctx.modo(sp) != "auto":
        return _bloquear(ctx, mem, sp, "SP manual: merge pelo utilizador")
    rc, out = ctx.arrumar(sp)
    if rc != 0:
        return _bloquear(ctx, mem, sp, "resto do fecho por commitar: " + (out or "").strip()[-300:])
    if out:
        ctx.log(f"arrumar {slug}: {out}")
    rc, out = ctx.merge(slug)
    if rc != 0:
        if LOCK_OCUPADO in (out or ""):
            ctx.log(f"merge {slug}: lock ocupado, repetir")
            return None
        return _bloquear(ctx, mem, sp, "merge recusado: " + (out or "").strip()[-300:])
    ctx.log(f"merge {slug}: {out}")
    if sp.get("pane"):
        _seguro(ctx, ctx.backend.fechar, sp["pane"])
    rc, out = ctx.clean(slug)
    if rc != 0:
        ctx.log(f"clean {slug} falhou: {out}")
    return _seguinte(ctx, mem, slug)


def ec_pausa(sp):
    """EC da pausa (quota/rede/sessão) gravada no `motivo` do SP, ou None."""
    ecs = kf_erros.ecs_em(sp.get("motivo") or "")
    return ecs[0] if ecs and ecs[0] in EC_PAUSA else None


def _falha_no_ecra(ctx, mem, sp):
    """SP a correr com a cauda do ecrã parada em dois ticks e com quota/rede/sessão → `bloqueado` com motivo e retoma.

    Parada = igual ao tick anterior: um agente a trabalhar (ou a escrever sobre quotas) muda o ecrã e não bloqueia."""
    ler = getattr(ctx.backend, "ecra", None)
    if ler is None:
        return False
    texto = _seguro(ctx, ler, sp["pane"]) or ""
    cauda = "\n".join([l for l in str(texto).splitlines() if l.strip()][-ECRA_LINHAS:])
    marca = hashlib.sha1(cauda.encode("utf-8", "replace")).hexdigest()
    ecras = mem.setdefault("ecras", {})
    anterior, ecras[sp["slug"]] = ecras.get(sp["slug"]), marca
    if not cauda or anterior != marca:
        return False
    r = kf_erros.classificar_falha(cauda, None, agora=ctx.agora())
    if r is None:
        return False
    ec, motivo, retoma = r
    proximo = f"retoma automática às {retoma}" if retoma else f"fazer login no harness e `kaizen resume {sp['slug']}`"
    msg = f"{ec} {motivo}; {proximo}"
    ctx.pausar(sp["slug"], msg, f"{ec} {motivo}", retoma)
    ctx.log(f"pausa {sp['slug']}: {msg}")
    _avisar(ctx, mem, {**sp, "estado": "bloqueado", "msg": msg})
    return True


def _retomar_pausa(ctx, mem, sp):
    """Pausa por quota/rede com `retoma_em` já passado e painel vivo: volta a `a-correr` e envia «continua»."""
    pane = sp.get("pane")
    if ec_pausa(sp) not in (kf_erros.EC_QUOTA, kf_erros.EC_REDE) or not sp.get("retoma_em") or not pane:
        return False
    if not kf_erros.ja_passou(sp["retoma_em"], ctx.agora()) or ctx.backend.estado(pane) == "morto":
        return False
    enviar = getattr(ctx.backend, "enviar", None)
    if enviar is None:
        return False
    try:
        ctx.retomar(sp["slug"], f"retomado depois da pausa ({ec_pausa(sp)})")
    except Exception as e:  # noqa: BLE001 — sem vaga ou estado mudado: tenta no tick seguinte
        ctx.log(f"retoma {sp['slug']} adiada: {e}")
        return False
    if not _seguro(ctx, enviar, pane, RETOMA_TEXTO):
        ctx.log(f"retoma {sp['slug']}: envio falhou, volta à pausa")
        ctx.pausar(sp["slug"], sp.get("msg") or "", sp.get("motivo"), kf_erros.retoma_padrao(ctx.agora()))
        return False
    mem.setdefault("ecras", {}).pop(sp["slug"], None)
    mem["avisos"].pop(sp["slug"], None)
    _seguro(ctx, ctx.backend.titulo, pane, sp["slug"])
    ctx.log(f"retoma {sp['slug']}: {RETOMA_TEXTO} enviado")
    return True


def _um(ctx, mem, sp):
    slug, estado = sp["slug"], sp.get("estado")
    if slug in mem["tratados"]:
        return None
    if estado == "done":
        return _done(ctx, mem, sp)
    if estado == "a-correr" and sp.get("pane") and ctx.backend.estado(sp["pane"]) == "morto":
        ctx.transitar(slug, "falhou", "painel fechou sem estado")
        sp = {**sp, "estado": "falhou", "msg": "painel fechou sem estado"}
        estado = "falhou"
    if estado == "a-correr" and sp.get("pane") and _falha_no_ecra(ctx, mem, sp):
        return None
    if estado == "bloqueado" and _retomar_pausa(ctx, mem, sp):
        return None
    if estado in ("falhou", "bloqueado") and slug not in mem.get("escalados", []) and not ec_pausa(sp):
        esc = _seguro(ctx, ctx.escalar, sp)
        if esc is not None:
            mem.setdefault("escalados", []).append(slug)  # uma tentativa por SP, mesmo se o relançamento falhou
        if esc and esc.get("estado", "a-correr") == "a-correr":
            ctx.log(f"escalada {slug}: {esc.get('de')} → {esc.get('para')}")
            _seguro(ctx, ctx.toast, f"^ {slug}: escalado {esc.get('de')} → {esc.get('para')}")
            mem["avisos"].pop(slug, None)
            return None
    _avisar(ctx, mem, sp)
    if estado == "falhou":
        return _seguinte(ctx, mem, slug)
    return None


def passo(ctx, mem):
    """Um tick do vigia; "fim" quando a fila acabou ou foi parada (`sp-fila.py --parar`)."""
    if not ctx.estado_global():
        ctx.log("estado da fila desapareceu (--parar): fim")
        return "fim"
    for sp in list(ctx.ler_fila().get("sps", {}).values()):
        try:
            if _um(ctx, mem, sp) == "fim":
                return "fim"
        except Exception as e:  # noqa: BLE001 — erro num SP fica no log e no estado; os outros seguem
            ctx.log(f"erro em {sp.get('slug')}: {e!r}")
            try:
                if sp.get("estado") not in ("bloqueado", "falhou"):
                    _bloquear(ctx, mem, sp, f"erro do vigia: {e}")
            except Exception as e2:  # noqa: BLE001
                ctx.log(f"erro a bloquear {sp.get('slug')}: {e2!r}")
    return "continua"


def correr(ctx, mem_path, intervalo=INTERVALO, uma_vez=False, dormir=None):
    """Ciclo do vigia: `passo` + memória em disco + pausa, até "fim" (ou um só tick com `uma_vez`)."""
    import time
    dormir = dormir or time.sleep
    mem = ler_memoria(mem_path)
    while True:
        res = passo(ctx, mem)
        guardar_memoria(mem_path, mem)
        if res == "fim" or uma_vez:
            return res
        dormir(intervalo)


def caminhos(pasta):
    """pidfile, log e memória do vigia dentro da pasta da fila de painéis."""
    p = Path(pasta)
    return p / "vigia.pid", p / "vigia.log", p / "vigia.json"


def arrancar(fila, script, run=None):
    """Lança `sp-vigia.py <fila>` destacado da sessão (sobrevive ao fim do turno); devolve o processo."""
    return popen_sem_janela([sys.executable, "-I", str(script), str(fila)], "destacado", run=run, close_fds=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def parar(pidfile, vivo, matar):
    """Termina o vigia dono do pidfile (se vivo) e apaga o pidfile; devolve o pid terminado ou None."""
    p = Path(pidfile)
    try:
        pid = int(p.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    alvo = pid if vivo(pid) else None
    if alvo is not None:
        matar(alvo)
    p.unlink(missing_ok=True)
    return alvo


def matar_pid(pid):
    if os.name == "nt":
        run_hidden(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        import signal
        os.kill(pid, signal.SIGTERM)


# --- contexto real -------------------------------------------------------------------------------

def arrumar_worktree(run, wt, slug):
    """Commit do resto do fecho (sem COMMIT_*.md nem segredos); apaga os COMMIT_*.md da raiz."""
    def git(*a):
        r = run(["git", "-C", str(wt), *a], capture_output=True, text=True,
                encoding="utf-8", errors="replace")
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).rstrip()  # porcelain: espaço inicial conta

    for f in Path(wt).glob("COMMIT_*.md"):
        f.unlink()
    rc, out = git("status", "--porcelain", "-uall")
    if rc:
        return rc, out
    caminhos = []
    for linha in out.splitlines():
        p = linha[3:].split(" -> ")[-1].strip().strip('"')
        nome = Path(p).name
        if nome.startswith(".env") or nome.endswith((".key", ".pem", ".p12", ".pfx")):
            return 1, f"caminho sensível por commitar: {p}"
        caminhos.append(p)
    if not caminhos:
        return 0, ""
    rc, out = git("add", "-A", "--", *caminhos)
    if rc:
        return rc, out
    rc, out = git("commit", "-q", "-m", f"vault: resto do fecho de {slug} (vigia sp-fila)")
    return (rc, out) if rc else (0, f"commit de {len(caminhos)} caminho(s)")


def _sp_na_worktree(worktree, slug):
    if not worktree:
        return None
    for p in Path(worktree).glob(f"knowledge/**/sp/*/{slug}.md"):
        return p
    return None


def modo_do_sp(path):
    """`modo:` do frontmatter (None se não há ficheiro ou campo)."""
    try:
        texto = Path(path).read_text(encoding="utf-8")
    except (OSError, TypeError):
        return None
    return sp_leitura.frontmatter(texto).get("modo") or None


def toast_windows(texto, run=None):
    """Balão do Windows por PowerShell `NotifyIcon` (spike 2026-11-11); no Linux, `notify-send`. Processo destacado, sem esperar."""
    if sys.platform != "win32":
        return popen_sem_janela(["notify-send", "-a", "sp-fila", "sp-fila", str(texto)[:200]], run=run,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t = str(texto).replace("'", "''")[:200]
    ps = ("Add-Type -AssemblyName System.Windows.Forms; $n=New-Object System.Windows.Forms.NotifyIcon; "
          "$n.Icon=[System.Drawing.SystemIcons]::Information; $n.Visible=$true; "
          f"$n.ShowBalloonTip(8000,'sp-fila','{t}','Info'); Start-Sleep 9; $n.Dispose()")
    return popen_sem_janela(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], run=run,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class ContextoReal(Contexto):
    def __init__(self, fila, log_path, root=None, estado_path=None, rel_dir=None, backend=None, run=None):
        import painel_backend
        import sp_fila_estado as fe
        import sp_painel_estado as pe
        self.pe, self.fila, self.log_path = pe, fila, Path(log_path)
        self.run = run or fe.run_hidden
        self.scripts, self.repo = fe.SCRIPTS, fe.REPO
        self.fe = fe
        self._estado_path = Path(estado_path) if estado_path else None
        self.painel_path = fe.estado_de(fila)  # fila.json dos painéis: nunca é o estado da sp-fila
        self.rel_dir = Path(rel_dir or fe.RELATORIOS)
        self.root = root
        if backend is None:
            import kaizen_config
            backend = painel_backend.escolher(kaizen_config.painel_backend(fe.REPO), herdr=kaizen_config.herdr(fe.REPO))
        self.backend = backend

    def _py(self, *args, cwd=None):
        r = self.run([sys.executable, "-I", *map(str, args)], capture_output=True, text=True,
                     encoding="utf-8", errors="replace", cwd=str(cwd or self.repo))
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()

    def ler_fila(self):
        return self.pe.ler(self.fila)

    def transitar(self, slug, estado, msg=None):
        self.pe.transitar(slug, estado, msg=msg, fila=self.fila)

    def pausar(self, slug, msg, motivo, retoma_em):
        self.pe.transitar(slug, "bloqueado", msg=msg, fila=self.fila, motivo=motivo, retoma_em=retoma_em)

    def retomar(self, slug, msg):
        self.pe.transitar(slug, "a-correr", msg=msg, fila=self.fila, motivo=None, retoma_em=None)

    def modo(self, sp):
        return modo_do_sp(_sp_na_worktree(sp.get("worktree"), sp["slug"]))

    def arrumar(self, sp):
        """Commita o que o `sp-fechar` deixou na worktree (mãe, métricas) e apaga o COMMIT_*.md.

        Só corre em SP `auto` (o `_done` já filtrou). Devolve (0, "") se a worktree estava limpa.
        """
        wt = sp.get("worktree")
        if not wt or not Path(wt).is_dir():
            return 0, ""
        return arrumar_worktree(self.run, Path(wt), sp["slug"])

    def merge(self, slug):
        return self._py(self.scripts / "sb-worktree.py", "merge", slug)

    def clean(self, slug, tentativas=6, pausa=5.0):
        """Clean com repetição: o painel acabado de fechar ainda segura a worktree uns segundos."""
        import time
        for i in range(tentativas):
            rc, out = self._py(self.scripts / "sb-worktree.py", "clean", slug)
            if rc == 0 or "em uso" not in (out or "") or i == tentativas - 1:
                return rc, out
            time.sleep(pausa)
        return rc, out

    def seguinte(self, slug):
        import kaizen_engine
        import sp_fila_execucao as fx
        root = self.root or kaizen_engine.load("sp-list").DEFAULT_ROOT
        try:
            if self.estado_path is None:
                self.log(f"seguinte {slug}: fila sem estado da sp-fila (painéis avulsos)")
                return {"acao": "erro"}
            return fx.seguinte(root, self.estado_path, self.rel_dir, slug=slug, backend=self.backend)
        except (fx.IntegracaoPendente, fx.SlugObrigatorio, TimeoutError, ValueError) as e:
            self.log(f"seguinte {slug}: {e}")
            return {"acao": "erro"}

    def fechar_mae(self, mae):
        """Fecho da mãe na worktree dela: ensure → sp-move done → commit → merge → clean."""
        rc, out = self._py(self.scripts / "sb-worktree.py", "ensure", mae)
        if rc:
            return rc, f"ensure: {out}"
        wt = Path(out.splitlines()[-1].strip())
        rc, out = self._py(wt / "scripts" / "sp-move.py", mae, "done", cwd=wt)
        if rc:
            return rc, f"sp-move: {out}"
        for argv in (["git", "-C", str(wt), "add", "-A"],
                     ["git", "-C", str(wt), "commit", "-q", "-m", f"docs: fecho do SP {mae} (vigia sp-fila)"]):
            r = self.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode:
                return r.returncode, f"{argv[3]}: {(r.stdout or '') + (r.stderr or '')}".strip()
        rc, out = self.merge(mae)
        if rc:
            return rc, f"merge: {out}"
        return self.clean(mae)

    def escalar(self, sp):
        """Escalada de modelo (`sp_escalada`): decide pelo SP na worktree, relança o painel e regista no SP e na fila."""
        import sp_escalada
        path = _sp_na_worktree(sp.get("worktree"), sp["slug"])
        if path is None or path.parent.name == "Done":
            return None
        decisao = sp_escalada.decidir(path.read_text(encoding="utf-8"), sp.get("estado"))
        if decisao is None:
            return None
        de, para, causa = decisao
        res = sp_escalada.relancar(sp["slug"], para, sp, self.fila, self.backend, run=self.run)
        if res["estado"] != "a-correr":
            self.log(f"escalada {sp['slug']} falhou: {res.get('msg')}")
            return {"de": de, "para": para, **res}
        sp_escalada.registar_report(path, sp_escalada.linha_report(de, para, causa))
        if self.estado_path is not None:
            _seguro(self, sp_escalada.registar_fila, self.estado_path, sp["slug"], de, para)
        return {"de": de, "para": para, "causa": causa, **res}

    def toast(self, texto):
        toast_windows(texto)

    def nota_relatorio(self, path, texto):
        with open(path, "a", encoding="utf-8") as f:
            f.write(texto)

    @property
    def estado_path(self):
        """Estado da fila-mãe (`fila_paineis` == esta fila), procurado a cada uso; None sem mãe."""
        return self._estado_path or self.fe.da_fila_paineis(self.fila)

    @estado_path.setter
    def estado_path(self, valor):
        self._estado_path = Path(valor) if valor else None

    def estado_global(self):
        p = self.estado_path
        return (p or self.painel_path).exists()

    def log(self, msg):
        from datetime import datetime
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
