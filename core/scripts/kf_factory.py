#!/usr/bin/env python3
"""Factory autónoma de um projeto: VISION.md -> backlog -> fila -> gates -> PR -> merge -> reflect -> próximo marco.

Uso:
  python -I scripts/kf_factory.py run <projeto> [--visao VISION.md] [--repo DIR] [--dir DIR] [--release-feito]   # corre até uma pausa ou ao fim
  python -I scripts/kf_factory.py status <projeto> [--dir DIR]                                  # marco, fila, gasto, próxima paragem
  python -I scripts/kf_factory.py stop <projeto> [--dir DIR]                                    # pede paragem limpa (a volta em curso acaba)
Modo manual (a autonomia desliga-se, os gates e o orçamento não):
  run <projeto> --manual         decompõe e pára em `aguarda-aprovacao`; SPs à mão (sem `-visao-mN-`) entram também; `run --auto` sai do modo
  approve <projeto> [--so a,b]   liberta SPs (sem --so: todos os pendentes); só estes são lançados
  step <projeto>                 corre o próximo SP elegível até ao merge e pára em `passo`
  pause|resume|skip|takeover <projeto> <sp>   pausa um SP · devolve-o à factory · dá-o por cumprido · assume-o (a factory não lhe toca;
                                 quando o humano o acaba, o PR fecha com os mesmos gates e CI verde)
Com a factory viva o comando fica em `<projeto>.cmd.jsonl` e a volta seguinte aplica-o; sem factory aplica-se logo.
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
PARAGENS = ("orcamento", "gate-bloqueado", "release", "visao-invalida", "parado", "aguarda-aprovacao", "manual", "passo")
COMANDOS = ("approve", "pause", "resume", "skip", "takeover")
FORA = ("corrigido", "falhou", "pausado", "saltado", "humano")  # fases que a factory não lança
MAX_VOLTAS = 10000
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

    def avulsos(self, projeto):
        """SPs do projeto feitos à mão (slug sem `-visao-mN-`, não-mães), com `marco` 0; só contam no modo manual."""
        return []

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
    def __init__(self, projeto, portos, pasta, intervalo=30, vivo=None):
        self.projeto = _slug_ok(projeto)
        self.p = portos
        self.pasta = Path(pasta)
        self.caminho = self.pasta / f"{projeto}.json"
        self.stop_f = self.pasta / f"{projeto}.stop"
        self.log = Registo(self.pasta / "factory.log.jsonl")
        self.lock = Lock(self.pasta / f"{projeto}.lock", vivo=vivo)
        self.intervalo = intervalo
        self.max_voltas = MAX_VOLTAS

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
    def run(self, release_feito=False, manual=None, passo=False):
        if not self.lock.adquirir():
            self.log("recusa", razao="outra factory ativa")
            print(f"factory {self.projeto}: já corre (lock {self.lock.caminho}); `kaizen factory stop {self.projeto}` ou espera", file=sys.stderr)
            return RC_LOCK
        try:
            self.stop_f.unlink(missing_ok=True)
            e = self.ler()
            retomada = e["estado"] in ("a-correr", "pausada")
            e.update(estado="a-correr", paragem="", razao="")
            if manual is not None:
                e["manual"] = manual
            self._passo = passo
            self._ini = self._merged(e)
            self._drenar(e)
            if release_feito and e["marco"] not in e.get("release_ok", []):
                e.setdefault("release_ok", []).append(e["marco"])
            self.guardar(e)
            self.log("retoma" if retomada else "inicio")
            return self._ciclo(e)
        finally:
            self.lock.libertar()

    # modo manual --------------------------------------------------------------
    @staticmethod
    def _merged(e):
        return {s for s, r in e["sps"].items() if r["fase"] in ("merged", "substituido")}

    def comando(self, nome, sp=None, so=None):
        """Aplica já (sem factory viva) ou deixa em fila para a volta seguinte (factory viva); rc 0, 2 = pedido inválido."""
        cmd = {"cmd": nome, "sp": sp, "so": so}
        if self.lock.adquirir():
            try:
                e = self.ler()
                rc = self._aplicar(e, cmd)
                if rc == RC_OK:
                    self.guardar(e)
                return rc
            finally:
                self.lock.libertar()
        self.pasta.mkdir(parents=True, exist_ok=True)
        with (self.pasta / f"{self.projeto}.cmd.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(cmd, ensure_ascii=False) + "\n")
        self.log("comando-em-fila", razao=nome, slug=sp)
        return RC_OK

    def _drenar(self, e):
        fila = self.pasta / f"{self.projeto}.cmd.jsonl"
        tmp = fila.with_suffix(".drenar")
        try:
            os.replace(fila, tmp)
        except OSError:
            return
        for linha in tmp.read_text(encoding="utf-8").splitlines():
            try:
                self._aplicar(e, json.loads(linha))
            except ValueError:
                continue
        tmp.unlink(missing_ok=True)
        self.guardar(e)

    def _conhecidos(self):
        return list(self.p.backlog(self.projeto)) + list(self.p.avulsos(self.projeto))

    def _aplicar(self, e, c):
        nome, sp = c.get("cmd"), c.get("sp")
        if nome not in COMANDOS:
            return RC_USO
        if nome == "approve":
            pend = [b["slug"] for b in self._conhecidos() if b["estado"] != "done"]
            alvo = c.get("so") or pend
            if any(x not in {b["slug"] for b in self._conhecidos()} for x in alvo):
                print(f"factory {self.projeto}: SP desconhecido em {alvo}", file=sys.stderr)
                self.log("recusa", razao="approve: SP desconhecido")
                return RC_USO
            e["aprovados"] = sorted(set(e.get("aprovados", [])) | set(alvo))
            self.log("aprovar", razao=",".join(alvo))
            return RC_OK
        if not sp or not SLUG_RE.match(sp):
            print(f"factory {self.projeto}: {nome} precisa de um <sp> válido", file=sys.stderr)
            return RC_USO
        reg = e["sps"].setdefault(sp, {"fase": "novo", "correcoes": 0, "pr": None})
        if nome == "resume":
            if reg["fase"] in ("pausado", "saltado", "humano"):
                reg["fase"] = reg.pop("antes", "novo")
                reg.pop("humano", None)
        elif reg["fase"] not in ("pausado", "saltado", "humano", "merged", "substituido"):
            reg["antes"] = reg["fase"]
            reg["fase"] = {"pause": "pausado", "skip": "saltado", "takeover": "humano"}[nome]
            reg["humano"] = nome == "takeover"
        self.log(nome, slug=sp)
        return RC_OK

    def _humanos(self, e, itens):
        """SPs assumidos pelo humano: se acabou (Done, ou PR aberto com gates verdes) segue para o merge normal, sem lançar nem corrigir."""
        estados = {b["slug"]: b["estado"] for b in itens}
        for slug, reg in e["sps"].items():
            if reg["fase"] != "humano" or slug not in estados:
                continue
            if estados[slug] == "done":
                reg["fase"] = "merged"
                self.guardar(e)
                continue
            r = self.p.resultado(slug)
            if r["estado"] == "done" and r.get("gates_ok", False) and r.get("pr"):
                reg.update(fase="pr", pr=r["pr"])
                self.guardar(e)
                self.log("gates-verdes", slug=slug, pr=r["pr"])

    def _alvo(self, e, pendentes, feitos):
        aprov = set(e.get("aprovados", []))
        for b in pendentes:
            fase = e["sps"].get(b["slug"], {}).get("fase")
            if fase in FORA or not all(d in feitos for d in b.get("depende", [])):
                continue
            if e.get("manual") and b["slug"] not in aprov and fase in (None, "novo"):
                continue
            return b
        return None

    def _sem_alvo(self, e, pendentes, rotulo):
        """Razão da pausa quando nada é lançável."""
        if e.get("manual"):
            aprov = set(e.get("aprovados", []))
            por = [b["slug"] for b in pendentes if b["slug"] not in aprov and e["sps"].get(b["slug"], {}).get("fase", "novo") == "novo"]
            if por:
                return self._pausar(e, "aguarda-aprovacao", f"{len(por)} SP(s) por aprovar: {', '.join(por[:5])}")
            mao = [b["slug"] for b in pendentes if e["sps"].get(b["slug"], {}).get("fase") in ("pausado", "humano")]
            if mao:
                return self._pausar(e, "manual", f"a aguardar o humano: {', '.join(mao[:5])}")
        return self._pausar(e, "gate-bloqueado", f"{rotulo}: dependências por cumprir")

    def _backlog(self, e):
        """Backlog do projeto (decompõe se faltar) ou o rc da pausa se o VISION não decompõe."""
        backlog = self.p.backlog(self.projeto)
        if backlog:
            return backlog
        rc, msg = self.p.decompor(self.projeto)
        self.log("decompor", rc=rc)
        if rc != 0:
            return self._pausar(e, "visao-invalida", msg or "decompor falhou")
        return self.p.backlog(self.projeto) or self._pausar(e, "visao-invalida", "VISION sem marcos")

    def _concluir(self, e, pend_av):
        if pend_av:
            return self._sem_alvo(e, pend_av, "SPs avulsos")
        e["estado"] = "concluida"
        self.guardar(e)
        self.log("fim")
        return RC_OK

    def _ciclo(self, e):
        for _ in range(self.max_voltas):
            if self.stop_f.exists():
                return self._pausar(e, "parado", "stop pedido")
            self._drenar(e)
            backlog = self._backlog(e)
            if isinstance(backlog, int):
                return backlog
            avulsos = [b for b in self.p.avulsos(self.projeto) if b["slug"] not in {x["slug"] for x in backlog}] if e.get("manual") else []
            self._humanos(e, backlog + avulsos)
            subst = {s for s, r in e["sps"].items() if r["fase"] in ("substituido", "saltado")}  # corrigido por merge, ou dado por cumprido
            feitos = {b["slug"] for b in backlog + avulsos if b["estado"] == "done"} | subst
            pend_av = [b for b in avulsos if b["estado"] != "done" and b["slug"] not in subst]
            marcos = sorted({b["marco"] for b in backlog})
            fechados = e.setdefault("fechados", [])
            e["marco"] = next((m for m in marcos if m not in fechados), marcos[-1] + 1)
            atuais = [b for b in backlog if b["marco"] == e["marco"]]
            pendentes = [b for b in atuais if b["estado"] != "done" and b["slug"] not in subst]
            alvo = self._alvo(e, pend_av, feitos) if pend_av else None
            if alvo:
                rc = self._sp(e, alvo)
            elif e["marco"] > marcos[-1]:
                return self._concluir(e, pend_av)
            elif not pendentes:
                rc = self._fechar_marco(e, atuais)
            else:
                alvo = self._alvo(e, pendentes, feitos)
                rc = self._sp(e, alvo) if alvo else self._sem_alvo(e, pendentes + pend_av, f"marco {e['marco']}")
            if rc is not None:
                return rc
            if self._passo and self._merged(e) - self._ini:
                return self._pausar(e, "passo", "1 SP concluído (`step` para o seguinte, `run` para continuar)")
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
        if reg["correcoes"] >= MAX_CORRECOES or reg.get("humano"):
            reg["fase"] = "falhou"
            return self._pausar(e, "gate-bloqueado", f"{slug}: {motivo} (correção automática já tentada)")
        reg["correcoes"] += 1
        reg["fase"] = "corrigido"
        try:
            novo = self.p.corrigir(slug, motivo)
        except RuntimeError as exc:
            reg["fase"] = "falhou"
            return self._pausar(e, "gate-bloqueado", f"{slug}: {motivo} ({exc})")
        self.log("correcao", slug=slug, novo=novo)
        e["sps"][novo] = {"fase": "novo", "correcoes": MAX_CORRECOES, "pr": None, "corrige": slug}
        if e.get("manual"):
            e["aprovados"] = sorted(set(e.get("aprovados", [])) | {novo})  # a correção é da factory, não pede nova aprovação
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
            return self._pausar(e, "release", f"marco {m} exige release (`kf_release.py plan|prepare`; tag/publish só humano, `publish --confirmo`)")
        e.setdefault("fechados", []).append(m)
        e["marco"] = m + 1
        self.guardar(e)
        return None

    def estado_texto(self):
        e = self.ler()
        sps = e["sps"]
        fila = [f"{s}:{r['fase']}" for s, r in sps.items()]
        proxima = {"aguarda-aprovacao": "`kaizen factory approve <projeto> [--so a,b]` e depois `run` ou `step`", "manual": "o humano acaba o SP (ou `resume`/`skip <sp>`) e `run`",
                   "passo": "`step` para o seguinte ou `run` para continuar", "orcamento": "subir `orcamento` no kaizen.config.json e `factory run`", "gate-bloqueado": "corrigir o gate e `factory run`",
                   "release": "`kf_release.py prepare`, merge do PR, `publish --confirmo` e `factory run --release-feito`", "visao-invalida": "`kaizen vision validate` e corrigir", "parado": "`factory run`"}
        prox = proxima.get(e.get("paragem"), "-") if e["estado"] == "pausada" else ("a correr" if e["estado"] == "a-correr" else "-")
        modo = f" · manual ({len(e.get('aprovados', []))} aprovados)" if e.get("manual") else ""
        return (f"factory {self.projeto}: {e['estado']}{modo} · marco {e['marco']} · gasto dia {e['gasto']:.2f} USD · falhas seguidas {e['seguidas']}\n"
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

    def _itens(self, projeto):
        import sp_fila_plano
        from sp_list_mod import DEFAULT_ROOT
        out = []
        for sp, fm in sp_fila_plano.load(self.root or DEFAULT_ROOT, projeto):
            dep = fm.get("depends_on") or []
            dep = re.findall(r"[a-z0-9][a-z0-9-]*", dep) if isinstance(dep, str) else list(dep)
            titulo = str(fm.get("title", "")) + str(fm.get("release", ""))
            out.append((sp.slug, {"slug": sp.slug, "marco": marco_de(sp.slug), "estado": {"Done": "done", "Doing": "doing"}.get(sp.status, "todo"),
                                  "depende": dep, "release": "release" in titulo.lower()}, str(fm.get("parent") or "")))
        return out

    def backlog(self, projeto):
        return [b for _, b, _ in self._itens(projeto) if b["marco"]]

    def avulsos(self, projeto):
        itens = self._itens(projeto)
        maes = {p for _, _, p in itens if p}
        return [b for slug, b, _ in itens if not b["marco"] and slug not in maes]

    def decompor(self, projeto):
        r = self._py("sp-decompor.py", str(self.visao), "--repo", str(self.repo))
        return r.returncode, (r.stderr or r.stdout or "").strip()[-300:]

    def lancar(self, slug):
        self._py("sp-fila.py", "--seguinte", "--slug", slug)

    def resultado(self, slug):
        r = self._py("sp-estado.py", slug)
        txt = r.stdout or ""
        if "Done" in txt.split("\n", 1)[0]:
            pr = self._pr(slug)
            return {"estado": "done", "pr": pr, "gates_ok": pr is not None, "motivo": "" if pr else "SP em Done sem PR aberto"}
        estado = "falhou" if "falhou" in txt else "bloqueado" if "bloqueado" in txt else "a-correr"
        return {"estado": estado, "pr": None, "gates_ok": False, "motivo": txt.strip()[-200:]}

    def _pr(self, slug):
        """Número do PR aberto do ramo `agent/<nome>` do SP (nome como sb-worktree: minúsculas, `-`, 31 caracteres) ou None."""
        nome = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")[:31].rstrip("-")
        r = self.run(["gh", "pr", "list", "--head", f"agent/{nome}", "--state", "open", "--json", "number", "--jq", ".[0].number"],
                     capture_output=True, text=True, cwd=str(self.repo))
        out = (r.stdout or "").strip()
        return out if r.returncode == 0 and out.isdigit() else None

    def merge(self, pr, slug):
        r = self._py("pr_fechar.py", str(pr), "--repo", str(self.repo), "--sp", slug)
        return r.returncode, (r.stdout or r.stderr or "").strip()[-200:]

    def reflect(self, projeto, marco):
        self.log_reflect = (projeto, marco)  # o `/reflect final` corre no painel do último SP do marco; aqui só fica registado

    def corrigir(self, slug, motivo):
        novo = f"{slug}-correcao"[:60]
        r = self._py("sp-new.py", "--project", self.projeto, "--slug", novo, "--priority", "P1",
                     "--depends-on", slug, "--restricoes", f"corrige: {motivo}"[:300])
        if r.returncode:
            raise RuntimeError(f"sp-new falhou: {(r.stderr or r.stdout or '').strip()[-200:]}")
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
    ap.add_argument("sub", choices=("run", "status", "stop", "step") + COMANDOS)
    ap.add_argument("projeto")
    ap.add_argument("sp", nargs="?", help="SP alvo de pause|resume|skip|takeover")
    ap.add_argument("--manual", action="store_true", help="com `run`: decompõe e pára a pedir aprovação (approve) antes de lançar")
    ap.add_argument("--auto", action="store_true", help="com `run`: sai do modo manual")
    ap.add_argument("--so", help="com `approve`: slugs separados por vírgula")
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
    if a.sub in COMANDOS:
        return f.comando(a.sub, sp=a.sp, so=[x for x in a.so.split(",") if x] if a.so else None)
    manual = True if a.manual else False if a.auto else None
    return f.run(release_feito=a.release_feito, manual=manual, passo=a.sub == "step")


if __name__ == "__main__":
    sys.exit(main())
