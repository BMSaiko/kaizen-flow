#!/usr/bin/env python3
"""Factory autónoma de um projeto: VISION.md -> backlog -> fila -> gates -> PR -> merge -> reflect -> próximo marco.

Uso:
  python -I scripts/kf_factory.py run <projeto> [--visao VISION.md] [--repo DIR] [--dir DIR] [--release-feito]   # corre até uma pausa ou ao fim
  python -I scripts/kf_factory.py status <projeto> [--dir DIR]                                  # marco, fila, gasto, próxima paragem
  python -I scripts/kf_factory.py stop <projeto> [--dir DIR]                                    # pede paragem limpa (a volta em curso acaba)
Estado em `<dir>/<projeto>.json` (defeito `.kaizen/factory/`), registo em `<dir>/factory.log.jsonl`, lock `<dir>/<projeto>.lock`.
A máquina (`Fabrica`) só fala com `Portos` (decompor, backlog, lançar, resultado, merge, reflect, correção, custo): os testes
trocam-nos por fakes; `PortosReais` liga-os a sp-decompor, sp-fila, pr_fechar e sp-metricas.
Pausa limpa (`pausada`, com `paragem`): orcamento · gate-bloqueado · release · visao-invalida · parado; `run` retoma onde ficou.
Nunca tag/publish; o registo guarda só slugs, fases e números (sem segredos nem conteúdo de conversas).
rc: 0 concluída · 3 pausada (ver `paragem`) · 1 erro · 2 uso · 4 outra factory já corre neste projeto
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kf_orcamento  # noqa: E402

HERE = Path(__file__).resolve().parent
RC_OK, RC_ERRO, RC_USO, RC_PAUSA, RC_LOCK = 0, 1, 2, 3, 4
PARAGENS = ("orcamento", "gate-bloqueado", "release", "visao-invalida", "parado")
MAX_CORRECOES = 1  # um SP de correção por SP; o segundo gate vermelho no mesmo marco pausa
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MARCO_RE = re.compile(r"-visao-m(\d+)-")


def _agora():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug_ok(nome):
    if not SLUG_RE.match(nome or ""):
        raise ValueError(f"projeto inválido: {nome!r}")
    return nome


def marco_de(slug):
    m = MARCO_RE.search(slug)
    return int(m.group(1)) if m else 0


class Lock:
    """Uma factory por projeto: ficheiro criado com O_EXCL; um lock cujo pid morreu é tomado."""

    def __init__(self, caminho, pid=None, vivo=None):
        self.caminho = Path(caminho)
        self.pid = pid or os.getpid()
        self.vivo = vivo or _pid_vivo

    def adquirir(self):
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._ativo():
                    return False
                self.caminho.unlink(missing_ok=True)  # órfão: o dono morreu (crash)
                continue
            with os.fdopen(fd, "w") as f:
                f.write(str(self.pid))
            return True
        return False

    def _ativo(self):
        try:
            pid = int(self.caminho.read_text().strip())
        except (OSError, ValueError):
            return False
        return pid != self.pid and self.vivo(pid)

    def libertar(self):
        try:
            if self.caminho.read_text().strip() == str(self.pid):
                self.caminho.unlink()
        except OSError:
            pass


def _pid_vivo(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class Registo:
    """`factory.log.jsonl`: uma linha por evento, só campos simples (slug, fase, números)."""

    def __init__(self, caminho):
        self.caminho = Path(caminho)

    def __call__(self, evento, **campos):
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        linha = {"ts": _agora(), "evento": evento, **{k: v for k, v in campos.items() if isinstance(v, (str, int, float, bool, list, type(None)))}}
        with self.caminho.open("a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")


class Portos:
    """Interface das ações externas (os testes herdam e substituem; sem dependências de rede)."""

    def backlog(self, projeto):
        """[{slug, marco, estado: todo|doing|done, depende: [slug], release: bool}]; vazio = ainda por decompor."""
        raise NotImplementedError

    def decompor(self, projeto):
        """Gera o backlog a partir do VISION; (rc, msg), rc 0 = ok."""
        raise NotImplementedError

    def lancar(self, slug):
        """Lança o SP na fila (painel herdr); idempotente."""
        raise NotImplementedError

    def resultado(self, slug):
        """{estado: a-correr|done|falhou|bloqueado, pr: str|None, gates_ok: bool, motivo: str}."""
        raise NotImplementedError

    def merge(self, pr, slug):
        """Merge só com CI verde (pr_fechar); (rc, msg)."""
        raise NotImplementedError

    def reflect(self, projeto, marco):
        """`/reflect final` do marco; devolve None."""
        raise NotImplementedError

    def corrigir(self, slug, motivo):
        """Cria o SP de correção de um gate vermelho; devolve o slug novo."""
        raise NotImplementedError

    def custo(self, slug):
        """USD equivalentes à API gastos pelo SP."""
        return 0.0

    def custo_dia(self):
        return 0.0

    def orcamento(self):
        """Dict `orcamento` do kaizen.config.json ou None."""
        return

    def esperar(self, segundos):
        time.sleep(segundos)


class Fabrica:
    def __init__(self, projeto, portos, pasta, intervalo=30, max_voltas=10000, vivo=None):
        self.projeto = _slug_ok(projeto)
        self.p = portos
        self.pasta = Path(pasta)
        self.caminho = self.pasta / f"{projeto}.json"
        self.stop_f = self.pasta / f"{projeto}.stop"
        self.log = Registo(self.pasta / "factory.log.jsonl")
        self.lock = Lock(self.pasta / f"{projeto}.lock", vivo=vivo)
        self.intervalo = intervalo
        self.max_voltas = max_voltas

    # estado -----------------------------------------------------------------
    def ler(self):
        try:
            return json.loads(self.caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"projeto": self.projeto, "estado": "novo", "marco": 1, "sps": {}, "seguidas": 0, "gasto": 0.0, "paragem": "", "razao": "", "reflect": []}

    def guardar(self, e):
        self.pasta.mkdir(parents=True, exist_ok=True)
        e["atualizado"] = _agora()
        tmp = self.caminho.with_suffix(".tmp")
        tmp.write_text(json.dumps(e, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.caminho)

    def _pausar(self, e, paragem, razao):
        assert paragem in PARAGENS
        e.update(estado="pausada", paragem=paragem, razao=razao)
        self.guardar(e)
        self.log("pausa", paragem=paragem, razao=razao)
        return RC_PAUSA

    # orquestração -----------------------------------------------------------
    def run(self, release_feito=False):
        if not self.lock.adquirir():
            self.log("recusa", razao="outra factory ativa")
            print(f"factory {self.projeto}: já corre (lock {self.lock.caminho}); `kaizen factory stop {self.projeto}` ou espera", file=sys.stderr)
            return RC_LOCK
        try:
            self.stop_f.unlink(missing_ok=True)
            e = self.ler()
            retomada = e["estado"] in ("a-correr", "pausada")
            e.update(estado="a-correr", paragem="", razao="")
            if release_feito and e["marco"] not in e.get("release_ok", []):
                e.setdefault("release_ok", []).append(e["marco"])
            self.guardar(e)
            self.log("retoma" if retomada else "inicio")
            return self._ciclo(e)
        finally:
            self.lock.libertar()

    def _ciclo(self, e):
        for _ in range(self.max_voltas):
            if self.stop_f.exists():
                return self._pausar(e, "parado", "stop pedido")
            backlog = self.p.backlog(self.projeto)
            if not backlog:
                rc, msg = self.p.decompor(self.projeto)
                self.log("decompor", rc=rc)
                if rc != 0:
                    return self._pausar(e, "visao-invalida", msg or "decompor falhou")
                backlog = self.p.backlog(self.projeto)
                if not backlog:
                    return self._pausar(e, "visao-invalida", "VISION sem marcos")
            marcos = sorted({b["marco"] for b in backlog})
            fechados = e.setdefault("fechados", [])
            e["marco"] = next((m for m in marcos if m not in fechados), marcos[-1] + 1)
            if e["marco"] > marcos[-1]:
                e["estado"] = "concluida"
                self.guardar(e)
                self.log("fim")
                return RC_OK
            subst = {s for s, r in e["sps"].items() if r["fase"] == "substituido"}  # SP original cuja correção já fez merge
            atuais = [b for b in backlog if b["marco"] == e["marco"]]
            pendentes = [b for b in atuais if b["estado"] != "done" and b["slug"] not in subst]
            feitos = {b["slug"] for b in backlog if b["estado"] == "done"} | subst
            if not pendentes:
                rc = self._fechar_marco(e, atuais)
                if rc is not None:
                    return rc
                continue
            alvo = next((b for b in pendentes if all(d in feitos for d in b.get("depende", []))
                         and e["sps"].get(b["slug"], {}).get("fase") not in ("corrigido", "falhou")), None)
            if alvo is None:
                return self._pausar(e, "gate-bloqueado", f"marco {e['marco']}: dependências por cumprir")
            rc = self._sp(e, alvo)
            if rc is not None:
                return rc
        return self._pausar(e, "parado", "limite de voltas")

    def _sp(self, e, alvo):
        slug = alvo["slug"]
        reg = e["sps"].setdefault(slug, {"fase": "novo", "correcoes": 0, "pr": None})
        cfg = self.p.orcamento()
        gasto = self.p.custo(slug)
        dec = kf_orcamento.decidir(cfg, sp_usd=gasto, dia_usd=self.p.custo_dia(), seguidas=e["seguidas"])
        e["gasto"] = round(self.p.custo_dia(), 4)
        if dec["estado"] == "parar":
            return self._pausar(e, "orcamento", dec["razao"])
        if dec["avisos"]:
            self.log("aviso-orcamento", avisos=dec["avisos"])
        if reg["fase"] == "novo":
            self.p.lancar(slug)
            reg["fase"] = "lancado"
            self.guardar(e)
            self.log("lancar", slug=slug, marco=e["marco"])
        if reg["fase"] == "lancado":
            r = self.p.resultado(slug)
            if r["estado"] == "a-correr":
                self.p.esperar(self.intervalo)
                return None
            if r["estado"] == "done" and r.get("gates_ok", False) and r.get("pr"):
                reg.update(fase="pr", pr=r["pr"])
                self.guardar(e)
                self.log("gates-verdes", slug=slug, pr=r["pr"])
            else:
                return self._falha(e, slug, reg, r)
        if reg["fase"] == "pr":
            rc, msg = self.p.merge(reg["pr"], slug)
            self.log("merge", slug=slug, rc=rc)
            if rc != 0:
                return self._falha(e, slug, reg, {"estado": "bloqueado", "motivo": msg})
            reg["fase"] = "merged"
            e["seguidas"] = 0
            if reg.get("corrige"):
                e["sps"][reg["corrige"]]["fase"] = "substituido"
            self.guardar(e)
            return None
        if reg["fase"] in ("merged", "substituido"):
            self.p.esperar(self.intervalo)  # merged, à espera de o backlog o ver em Done
        return None

    def _falha(self, e, slug, reg, r):
        motivo = r.get("motivo") or r["estado"]
        e["seguidas"] += 1
        self.log("falha", slug=slug, estado=r["estado"], motivo=motivo, seguidas=e["seguidas"])
        dec = kf_orcamento.decidir(self.p.orcamento(), sp_usd=0, dia_usd=0, seguidas=e["seguidas"])
        if dec["estado"] == "parar":
            reg["fase"] = "falhou"
            return self._pausar(e, "orcamento", dec["razao"])
        if reg["correcoes"] >= MAX_CORRECOES:
            reg["fase"] = "falhou"
            return self._pausar(e, "gate-bloqueado", f"{slug}: {motivo} (correção automática já tentada)")
        reg["correcoes"] += 1
        reg["fase"] = "corrigido"
        novo = self.p.corrigir(slug, motivo)
        self.log("correcao", slug=slug, novo=novo)
        e["sps"][novo] = {"fase": "novo", "correcoes": MAX_CORRECOES, "pr": None, "corrige": slug}
        self.guardar(e)
        return None

    def _fechar_marco(self, e, atuais):
        m = e["marco"]
        if m not in e["reflect"]:
            self.p.reflect(self.projeto, m)
            e["reflect"].append(m)
            self.guardar(e)
            self.log("reflect", marco=m)
        if any(b.get("release") for b in atuais) and m not in e.get("release_ok", []):
            return self._pausar(e, "release", f"marco {m} exige release (humano; tag/publish nunca em auto)")
        e.setdefault("fechados", []).append(m)
        e["marco"] = m + 1
        self.guardar(e)
        return None

    def estado_texto(self):
        e = self.ler()
        sps = e["sps"]
        fila = [f"{s}:{r['fase']}" for s, r in sps.items()]
        proxima = {"orcamento": "subir `orcamento` no kaizen.config.json e `factory run`", "gate-bloqueado": "corrigir o gate e `factory run`",
                   "release": "fazer o release e `factory run --release-feito`", "visao-invalida": "`kaizen vision validate` e corrigir", "parado": "`factory run`"}
        prox = proxima.get(e.get("paragem"), "-") if e["estado"] == "pausada" else ("a correr" if e["estado"] == "a-correr" else "-")
        return (f"factory {self.projeto}: {e['estado']} · marco {e['marco']} · gasto dia {e['gasto']:.2f} USD · falhas seguidas {e['seguidas']}\n"
                f"fila: {', '.join(fila) or '-'}\nparagem: {e.get('paragem') or '-'} {e.get('razao') or ''}\npróxima paragem/ação: {prox}")


class PortosReais(Portos):
    """Liga os portos aos scripts do núcleo (sp-decompor, sp-fila, pr_fechar, sp-metricas) por subprocesso, sem rede própria."""

    def __init__(self, projeto, visao, repo, root=None, run=None):
        import subprocess
        self.projeto, self.visao, self.repo = projeto, Path(visao), Path(repo)
        self.root = root
        self.run = run or subprocess.run

    def _py(self, script, *args):
        return self.run([sys.executable, "-I", str(HERE / script), *args], capture_output=True, text=True, cwd=str(self.repo))

    def backlog(self, projeto):
        import sp_fila_plano
        from sp_list_mod import DEFAULT_ROOT
        itens = sp_fila_plano.load(self.root or DEFAULT_ROOT, projeto)
        out = []
        for sp, fm in itens:
            m = marco_de(sp.slug)
            if not m:
                continue
            dep = fm.get("depends_on") or []
            dep = re.findall(r"[a-z0-9][a-z0-9-]*", dep) if isinstance(dep, str) else list(dep)
            titulo = str(fm.get("title", "")) + str(fm.get("release", ""))
            out.append({"slug": sp.slug, "marco": m, "estado": {"Done": "done", "Doing": "doing"}.get(sp.status, "todo"),
                        "depende": dep, "release": "release" in titulo.lower()})
        return out

    def decompor(self, projeto):
        r = self._py("sp-decompor.py", str(self.visao), "--repo", str(self.repo))
        return r.returncode, (r.stderr or r.stdout or "").strip()[-300:]

    def lancar(self, slug):
        self._py("sp-fila.py", "--seguinte", "--slug", slug)

    def resultado(self, slug):
        r = self._py("sp-estado.py", slug)
        txt = r.stdout or ""
        if "Done" in txt.split("\n", 1)[0]:
            return {"estado": "done", "pr": None, "gates_ok": True, "motivo": ""}
        estado = "falhou" if "falhou" in txt else "bloqueado" if "bloqueado" in txt else "a-correr"
        return {"estado": estado, "pr": None, "gates_ok": False, "motivo": txt.strip()[-200:]}

    def merge(self, pr, slug):
        r = self._py("pr_fechar.py", str(pr), "--repo", str(self.repo), "--sp", slug)
        return r.returncode, (r.stdout or r.stderr or "").strip()[-200:]

    def reflect(self, projeto, marco):
        self.log_reflect = (projeto, marco)  # o `/reflect final` corre no painel do último SP do marco; aqui só fica registado

    def corrigir(self, slug, motivo):
        novo = f"{slug}-correcao"[:60]
        self._py("sp-new.py", novo, "--project", self.projeto, "--depends-on", slug)
        return novo

    def custo(self, slug):
        try:
            import kaizen_engine
            return float(kaizen_engine.load("sp-metricas").custo_por_slug().get(slug, 0.0))
        except Exception:  # noqa: BLE001 — medir nunca impede a factory
            return 0.0

    def custo_dia(self):
        return kf_orcamento.gasto_dia()

    def orcamento(self):
        import kaizen_config
        return kaizen_config.orcamento(self.repo)


def main(argv=None, portos=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sub", choices=("run", "status", "stop"))
    ap.add_argument("projeto")
    ap.add_argument("--visao", help="VISION.md (defeito <repo>/VISION.md)")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--dir", help="pasta de estado (defeito <repo>/.kaizen/factory)")
    ap.add_argument("--intervalo", type=int, default=30)
    ap.add_argument("--release-feito", action="store_true", help="com `run`: o release do marco pausado já foi feito pelo humano")
    a = ap.parse_args(argv)
    try:
        _slug_ok(a.projeto)
    except ValueError as err:
        print(err, file=sys.stderr)
        return RC_USO
    repo = Path(a.repo).resolve()
    pasta = Path(a.dir) if a.dir else repo / ".kaizen" / "factory"
    portos = portos or PortosReais(a.projeto, a.visao or repo / "VISION.md", repo)
    f = Fabrica(a.projeto, portos, pasta, intervalo=a.intervalo)
    if a.sub == "status":
        print(f.estado_texto())
        return RC_OK
    if a.sub == "stop":
        pasta.mkdir(parents=True, exist_ok=True)
        f.stop_f.write_text(_agora())
        f.log("stop-pedido")
        print(f"factory {a.projeto}: paragem pedida (acaba a volta em curso)")
        return RC_OK
    return f.run(release_feito=a.release_feito)


if __name__ == "__main__":
    sys.exit(main())
