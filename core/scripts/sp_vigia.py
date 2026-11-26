"""Vigia da fila de painéis (sem LLM): lê o estado de cada SP em disco e age.

`passo(ctx, mem)` é um tick: `done` de SP auto → merge (lock global do `sb-agent`), fecha o painel, limpa a worktree e
lança o seguinte; SP manual, gates vermelhos ou conflito → `bloqueado` com motivo; `pergunta`/`bloqueado`/`falhou` →
log, um por transição (sem toasts nem prefixos de título: o herdr avisa por si); painel morto sem estado → `falhou`;
agente herdr `blocked` → `pergunta` (e de volta a `a-correr` quando volta a trabalhar). Cada tick publica «fila n/N · vagas»
como metadata do workspace e a espera entre ticks acorda por evento do herdr (`agent wait`). `falhou`/`bloqueado` por gate com
nível de modelo acima → relançado uma vez nesse nível (`sp_escalada`), sem avançar a fila. Devolve "continua" ou "fim".
Os efeitos vivem no `Contexto` (o real é `ContextoReal`; os testes trocam-no).

Uso: módulo importado por sp-vigia.py; sem execução direta
rc: sem execução direta"""
import contextlib
import hashlib
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_leitura  # noqa: E402
import sp_vigia_reacao  # noqa: E402
from painel_backend import popen_sem_janela, run_hidden  # noqa: E402
from sp_disco import guardar, ler_json  # noqa: E402
import kf_erros  # noqa: E402

AVISAM = ("pergunta", "bloqueado", "falhou")
MAX_PARALELO = 3
ESPERA_MIN = 1.0  # um evento já «em curso» (agente blocked) não pode fazer girar o ciclo
LOCK_OCUPADO = "outro merge em curso"
INTERVALO = 10.0
ECRA_LINHAS = 15  # cauda do ecrã lida para quota/rede/sessão (o resto é histórico)
EC_PAUSA = (kf_erros.EC_QUOTA, kf_erros.EC_REDE, kf_erros.EC_SESSAO)
RETOMA_TEXTO = "continua"  # enviado ao painel quando a pausa (quota/rede) acaba
TICK_TEXTO = "continua"  # tick: turn parado (agente idle/done) sem estado final
TICK_ESPERA = 2  # ticks do vigia seguidos com o agente parado antes do 1.º envio (~20 s)
TICK_TETO = 5  # envios seguidos sem o agente voltar a `working`; depois → `bloqueado`
TICK_INTERVALO = 60.0  # segundos mínimos entre dois envios


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
    def nota_relatorio(self, path, texto): raise NotImplementedError
    def estado_global(self): raise NotImplementedError
    def log(self, msg): raise NotImplementedError

    def agora(self):
        return datetime.now()

    def agente_estado(self, pane):
        """Estado do agente no painel segundo o multiplexer (herdr: idle/working/blocked/done); None se não sabe."""
        return  # noqa: RET501

    def metadata(self, texto):
        """Publica `texto` como metadata do workspace (herdr); sem efeito nos outros backends."""

    def esperar(self, intervalo, dormir):
        """Pausa entre ticks; o contexto real acorda mais cedo por evento do herdr."""
        dormir(intervalo)

    def pausar(self, slug, msg, motivo, retoma_em):
        """SP a-correr → bloqueado por quota/rede/sessão, com `motivo` e `retoma_em` (o contexto real grava os campos)."""
        self.transitar(slug, "bloqueado", msg)

    def retomar(self, slug, msg):
        """bloqueado (pausa acabada) → a-correr, limpando `motivo` e `retoma_em`."""
        self.transitar(slug, "a-correr", msg)

    def escalar(self, sp):
        """Relança o SP no nível seguinte se `sp_escalada` o pedir; {de, para, ...} ou None (sem escalada)."""
        return

    def texto_sp(self, sp):
        """Texto do SP na worktree (restricoes/permitir/## Decisões para a reação); None se não há."""
        return

    def registar_reacao(self, sp, linha):
        """Acrescenta a reação do vigia a `## Report modo auto` do SP."""

    def retomar_contexto(self, sp):
        """Handoff no próprio painel (`sp-handoff.py --launch --auto`); True se lançou."""
        return False


def _seguro(ctx, f, *a):
    try:
        return f(*a)
    except Exception as e:  # noqa: BLE001 — um aviso falhado nunca pára o vigia
        ctx.log(f"aviso falhou: {e}")
        return None


def _avisar(ctx, mem, sp):
    """Uma linha de log por transição para pergunta/bloqueado/falhou (o aviso ao utilizador é nativo do herdr)."""
    slug, estado = sp["slug"], sp.get("estado")
    if mem["avisos"].get(slug) == estado:
        return
    if estado not in AVISAM:  # voltou a correr: a próxima transição volta a registar-se
        mem["avisos"].pop(slug, None)
        return
    mem["avisos"][slug] = estado
    msg = sp.get("msg")
    ctx.log(f"aviso {estado} {slug}" + (f": {msg}" if msg else ""))


def texto_fila(sps):
    """«fila n/N · v vagas»: SPs done sobre o total e vagas livres do teto global."""
    estados = [sp.get("estado") for sp in sps.values()]
    ativos = sum(1 for e in estados if e in ("a-correr", "pergunta"))
    return f"fila {sum(1 for e in estados if e == 'done')}/{len(estados)} · {max(MAX_PARALELO - ativos, 0)} vagas"


def _publicar(ctx, mem, sps):
    texto = texto_fila(sps)
    if mem.get("meta") != texto:
        mem["meta"] = texto
        _seguro(ctx, ctx.metadata, texto)


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
    ctx.log(f"retoma {sp['slug']}: {RETOMA_TEXTO} enviado")
    return True


def _evento_agente(ctx, sp):
    """Agente herdr `blocked` num SP a-correr → `pergunta`; a trabalhar outra vez → `a-correr`. True se transitou."""
    ag = _seguro(ctx, ctx.agente_estado, sp["pane"])
    if sp.get("estado") == "a-correr" and ag == "blocked":
        ctx.transitar(sp["slug"], "pergunta", "agente bloqueado (herdr)")
        ctx.log(f"aviso pergunta {sp['slug']}: agente bloqueado (herdr)")
        return True
    if sp.get("estado") == "pergunta" and ag == "working":
        ctx.transitar(sp["slug"], "a-correr", "agente voltou a trabalhar (herdr)")
        return True
    return False


def _tick_continuar(ctx, mem, sp):
    """SP a-correr com o agente herdr parado (`idle`/`done`) sem estado final: envia `continua` com espera, intervalo e teto.

    Contadores em `mem["ticks"]`; zerados quando o agente volta a trabalhar ou deixa de estar parado. True se agiu."""
    ticks = mem.setdefault("ticks", {})
    slug = sp["slug"]
    ag = _seguro(ctx, ctx.agente_estado, sp["pane"])
    if sp.get("estado") != "a-correr" or ag not in ("idle", "done") or ec_pausa(sp):
        ticks.pop(slug, None)
        return False
    enviar = getattr(ctx.backend, "enviar", None)
    if enviar is None:
        return False
    t = ticks.setdefault(slug, {"parado": 0, "enviados": 0, "ultimo": None})
    t["parado"] += 1
    if t["parado"] < TICK_ESPERA:
        return False
    agora = ctx.agora()
    if t["ultimo"] and (agora - datetime.fromisoformat(t["ultimo"])).total_seconds() < TICK_INTERVALO:
        return False
    if t["enviados"] >= TICK_TETO:
        _bloquear(ctx, mem, sp, f"turn parado sem estado ({t['enviados']} ticks)")
        ticks.pop(slug, None)
        return True
    if not _seguro(ctx, enviar, sp["pane"], TICK_TEXTO):
        return False
    t["enviados"] += 1
    t["ultimo"] = agora.isoformat()
    ctx.log(f"tick {slug}: {TICK_TEXTO} enviado ({t['enviados']}/{TICK_TETO})")
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
    if sp.get("pane") and estado in ("a-correr", "pergunta") and _evento_agente(ctx, sp):
        return None
    if estado == "a-correr" and sp.get("pane") and _falha_no_ecra(ctx, mem, sp):
        return None
    if estado == "a-correr" and sp.get("pane") and _tick_continuar(ctx, mem, sp):
        return None
    if estado == "bloqueado" and _retomar_pausa(ctx, mem, sp):
        return None
    if estado in ("bloqueado", "pergunta") and sp.get("pane") and not ec_pausa(sp) and sp_vigia_reacao.reagir(ctx, mem, sp):
        return None
    if estado in ("falhou", "bloqueado") and slug not in mem.get("escalados", []) and not ec_pausa(sp):
        esc = _seguro(ctx, ctx.escalar, sp)
        if esc is not None:
            mem.setdefault("escalados", []).append(slug)  # uma tentativa por SP, mesmo se o relançamento falhou
        if esc and esc.get("estado", "a-correr") == "a-correr":
            ctx.log(f"escalada {slug}: {esc.get('de')} → {esc.get('para')}")
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
    _seguro(ctx, _publicar, ctx, mem, ctx.ler_fila().get("sps", {}))
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
        ctx.esperar(intervalo, dormir)


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

    def texto_sp(self, sp):
        path = _sp_na_worktree(sp.get("worktree"), sp["slug"])
        try:
            return path.read_text(encoding="utf-8") if path else None
        except OSError:
            return None

    def registar_reacao(self, sp, linha):
        import sp_escalada
        path = _sp_na_worktree(sp.get("worktree"), sp["slug"])
        if path is not None and path.parent.name != "Done":
            sp_escalada.registar_report(path, linha)

    def retomar_contexto(self, sp):
        """`sp-handoff.py --launch <SP> --auto` no painel do SP (mesmo painel, SP e vaga; repete o prompt da fila)."""
        path, nome = _sp_na_worktree(sp.get("worktree"), sp["slug"]), getattr(self.backend, "nome", None)
        if path is None or not nome:
            return False
        rc, out = self._py(self.scripts / "sp-handoff.py", "--launch", path, "--auto", "--pane", sp["pane"], "--backend", nome,
                           cwd=sp["worktree"])
        if rc:
            self.log(f"retoma de contexto {sp['slug']}: {out[-300:]}")
        return rc == 0

    def _ops(self):
        """HerdrOps sobre o backend atual, ou None se o painel não é herdr."""
        if getattr(self.backend, "nome", None) != "herdr":
            return None
        import herdr_ops
        return herdr_ops.HerdrOps(run=self.backend.run)

    def agente_estado(self, pane):
        ops = self._ops()
        return ops.estado(pane) if ops else None

    def metadata(self, texto):
        ops = self._ops()
        pane = next((sp.get("pane") for sp in self.ler_fila().get("sps", {}).values() if sp.get("pane")), None)
        ws = ops.workspace_do_pane(pane) if ops and pane else None
        if ws:
            ops.workspace_metadata(ws, "sp-fila", texto)

    def esperar(self, intervalo, dormir):
        """Acorda por evento: `agent wait` (blocked/done) no 1.º agente a correr, com o intervalo como teto."""
        import time
        import herdr_ops
        ops = self._ops()
        pane = next((sp.get("pane") for sp in self.ler_fila().get("sps", {}).values()
                     if sp.get("pane") and sp.get("estado") == "a-correr"), None)
        if ops is None or pane is None:
            return dormir(intervalo)
        t0 = time.monotonic()
        with contextlib.suppress(herdr_ops.HerdrErro, OSError):
            ops.esperar(pane, ate=("blocked", "done"), timeout_ms=int(intervalo * 1000))
        resto = ESPERA_MIN - (time.monotonic() - t0)
        if resto > 0:
            dormir(resto)

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
