"""Vigia da fila de painéis (sem LLM): lê o estado de cada SP em disco e age.

`passo(ctx, mem)` é um tick: `done` de SP auto → merge (lock global do `sb-agent`), fecha o painel, limpa a worktree e
lança o seguinte; SP manual, gates vermelhos ou conflito → `bloqueado` com motivo; `pergunta`/`bloqueado`/`falhou` →
título `? `/`! `/`x ` + toast, um por transição; painel morto sem estado → `falhou`. Devolve "continua" ou "fim".
Os efeitos vivem no `Contexto` (o real é `ContextoReal`; os testes trocam-no).

Uso: módulo importado por sp-vigia.py; sem execução direta
rc: sem execução direta"""
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_leitura  # noqa: E402
from painel_backend import popen_sem_janela, run_hidden  # noqa: E402
from sp_disco import guardar, ler_json  # noqa: E402

MARCAS = {"pergunta": "? ", "bloqueado": "! ", "falhou": "x "}
LOCK_OCUPADO = "outro merge em curso"
INTERVALO = 10.0


def memoria_nova():
    return {"avisos": {}, "tratados": []}


def ler_memoria(path):
    dados = ler_json(path)
    try:
        return {"avisos": dict(dados.get("avisos") or {}), "tratados": list(dados.get("tratados") or [])}
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


def arrancar(fila, script, run=subprocess.Popen):
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


def toast_windows(texto, run=subprocess.Popen):
    """Balão do Windows por PowerShell `NotifyIcon` (spike 2026-11-11); processo destacado, sem esperar."""
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
        self.estado_path = Path(estado_path or fe.estado_de(fila))
        self.rel_dir = Path(rel_dir or fe.RELATORIOS)
        self.root = root
        if backend is None:
            import kaizen_config
            backend = painel_backend.escolher(kaizen_config.painel_backend(fe.REPO))
        self.backend = backend

    def _py(self, *args, cwd=None):
        r = self.run([sys.executable, "-I", *map(str, args)], capture_output=True, text=True,
                     encoding="utf-8", errors="replace", cwd=str(cwd or self.repo))
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()

    def ler_fila(self):
        return self.pe.ler(self.fila)

    def transitar(self, slug, estado, msg=None):
        self.pe.transitar(slug, estado, msg=msg, fila=self.fila)

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

    def toast(self, texto):
        toast_windows(texto)

    def nota_relatorio(self, path, texto):
        with open(path, "a", encoding="utf-8") as f:
            f.write(texto)

    def estado_global(self):
        return self.estado_path.exists()

    def log(self, msg):
        from datetime import datetime
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
