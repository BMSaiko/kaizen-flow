#!/usr/bin/env python3
"""`kaizen demo --factory`: prova a factory de ponta a ponta num projeto de exemplo, sem rede nem agente.

Uso: python -I kf_demo_factory.py --dir DIR   (DIR = repo git já com o kaizen-flow instalado; chamado por `kaizen demo --factory`)
Cria `VISION.md` (uma app UI minúscula) e o design system; decompõe, corre a factory com fakes deterministicos (agente, gh, CI) e
mostra cada gate e cada paragem esperada: gate vermelho (-> SP de correção), orçamento excedido (pausa), release (pausa),
`publish` recusado sem `--confirmo`. Gates de design (`ds-validate`, `ds-lint`) são reais; tipos, complexidade e cobertura de diff são
simulados (o projeto de exemplo não tem código tipado). O e2e real (herdr + gh + CI) é opt-in e está em docs/factory.md.
rc: 0 todos os cenários como esperado · 1 algum cenário falhou · 2 uso
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

VISION = """---
projeto: mini
ui: sim
stack: html-css
design_system: DESIGN.md
orcamento: 5 USD por SP, 20 USD por dia
---
# mini

## Goal
Uma página de tarefas minúscula.

## Users
- Quem quer uma lista simples.

## Success criteria
- [ ] `node --version` corre
- [ ] Observação: a página usa só tokens do design system

## Constraints
- Só HTML e CSS.

## Non-goals
- Sem contas.

## Milestones
1. Layout [ficheiros 2, horas 1] `node --version`
2. Tema (depende: 1) `node --version`
3. Release v0.1.0 (depende: 2) `node --version`
"""
HTML = '<!doctype html>\n<html lang="pt"><head><meta charset="utf-8"><title>mini</title><link rel="stylesheet" href="styles.css"></head>\n<body><main><h1>Tarefas</h1><ul><li>Primeira</li></ul></main></body></html>\n'
CSS_OK = "body { color: var(--color-text); background: var(--color-bg); }\n"
CSS_BUG = "body { color: var(--color-text); background: #ff0000; }\n"  # literal de cor fora dos tokens: o gate de design apanha
CSS_FIX = "body { color: var(--color-text); background: var(--color-bg); }\n"


def say(fase, msg):
    print(f"[{fase}] {msg}", flush=True)


def py(dirp, script, *args):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}  # Windows: sem isto a consola cp1252 estraga os acentos
    return subprocess.run([sys.executable, "-I", "-B", str(dirp / "scripts" / script), *args], cwd=str(dirp), capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)


def mostrar(r):
    for linha in ((r.stdout or "") + (r.stderr or "")).splitlines():
        if linha.strip():
            print(f"    {linha}")


def gates_design(dirp):
    """Gates reais de design (tokens válidos, sem literais fora dos tokens) mais os simulados; devolve (ok, motivo)."""
    for nome, script, args in (("ds-validate", "ds-validate.py", ["--dir", "."]), ("ds-lint", "ds-lint.py", ["--dir", "."])):
        r = py(dirp, script, *args)
        say("gates", f"{nome}: rc {r.returncode}")
        mostrar(r)
        if r.returncode:
            return False, f"{nome} vermelho: {((r.stdout or '') + (r.stderr or '')).strip().splitlines()[0]}"
    say("gates", "tipos, complexidade, cobertura de diff: rc 0 (simulados; o exemplo não tem código tipado)")
    return True, ""


def lancar_agente(dirp, agente, slug):
    py(dirp, "sp-move.py", slug, "doing")
    for prefixo, ficheiros in agente.items():
        if slug.startswith(prefixo):
            for nome, conteudo in ficheiros.items():
                (dirp / nome).write_text(conteudo, encoding="utf-8")
    say("factory", f"agente simulado trabalhou em {slug}")


def resultado_demo(dirp, slug):
    if "correcao" in slug:
        (dirp / "styles.css").write_text(CSS_FIX, encoding="utf-8")
    ok, motivo = gates_design(dirp)
    if not ok:
        return {"estado": "bloqueado", "pr": None, "gates_ok": False, "motivo": motivo}
    return {"estado": "done", "pr": f"{slug}#1", "gates_ok": True, "motivo": ""}


def criar_correcao(dirp, slug):
    novo = f"{slug[:-11]}-correcao-{slug[-10:]}"  # sp-new só acrescenta a data se o slug não acabar já numa
    r = py(dirp, "sp-new.py", "--project", "mini", "--slug", novo, "--priority", "P2", "--gate", "node --version")
    say("gate-vermelho", f"gate vermelho em {slug}: criado o SP de correção {novo} (rc {r.returncode})")
    return novo


def classe_demo(kf):
    """Portos da demo: backlog e decomposição reais; agente, PR e CI são fakes (o agente escreve `agente[slug]` e os gates correm a sério)."""

    class Demo(kf.PortosReais):
        def __init__(self, dirp, agente):
            super().__init__("mini", dirp / "VISION.md", dirp)
            self.dirp, self.agente = dirp, agente

        def backlog(self, projeto):
            itens = super().backlog(projeto)
            for b in itens:
                b["release"] = "-m3-" in b["slug"]
            return itens

        def lancar(self, slug):
            lancar_agente(self.dirp, self.agente, slug)

        def resultado(self, slug):
            return resultado_demo(self.dirp, slug)

        def merge(self, pr, slug):
            r = py(self.dirp, "sp-move.py", slug, "done")
            say("factory", f"PR simulado {pr}: CI verde, merge de {slug}")
            return r.returncode, "merged"

        def corrigir(self, slug, motivo):
            return criar_correcao(self.dirp, slug)

        def custo(self, slug):
            return 0.5

        def orcamento(self):
            return {"spUsd": 5, "diaUsd": 20}

        def esperar(self, segundos):
            pass

    return Demo


def fazer_portos(kf, dirp, agente):
    return classe_demo(kf)(dirp, agente)



def fabrica(kf, portos, pasta):
    f = kf.Fabrica("mini", portos, pasta, intervalo=0)
    f.max_voltas = 400
    return f


def cenario_orcamento(kf, pasta):
    """Backlog em memória de um SP cujo custo já passa o teto: a factory tem de parar antes de o lançar."""

    class Caro(kf.Portos):
        lancados = []

        def backlog(self, projeto):
            return [{"slug": "mini-visao-m1-x", "marco": 1, "estado": "todo", "depende": [], "release": False}]

        def lancar(self, slug):
            self.lancados.append(slug)

        def custo(self, slug):
            return 6.0

        def orcamento(self):
            return {"spUsd": 5}

        def esperar(self, segundos):
            pass

    caro = Caro()
    rc = fabrica(kf, caro, pasta).run()
    return rc, caro.lancados


def preparar(dirp):
    """Projeto de exemplo: VISION.md, design system, página e CSS limpo."""
    say("projeto", f"projeto de exemplo `mini` (UI) em {dirp}")
    (dirp / "VISION.md").write_text(VISION, encoding="utf-8")
    for s in ("TODO", "Doing", "Done"):
        (dirp / "knowledge" / "projects" / "kaizen" / "mini" / "sp" / s).mkdir(parents=True, exist_ok=True)
    mostrar(py(dirp, "ds-init.py", "mini"))
    (dirp / "index.html").write_text(HTML, encoding="utf-8")
    (dirp / "styles.css").write_text(CSS_OK, encoding="utf-8")
    say("visao", "VISION.md validado por máquina")
    r = py(dirp, "sp-visao.py", "validate", "VISION.md")
    mostrar(r)
    return r.returncode


def etapa_release(kf, dirp):
    """Marcos 1-3: gate vermelho -> correção, pausa `release` e retoma. Devolve a mensagem de erro ou ''."""
    say("decompor", "a factory decompõe os marcos em SPs (sem grill humano)")
    agente = {
        "mini-visao-m1-": {"index.html": HTML},
        "mini-visao-m2-": {"styles.css": CSS_BUG},  # o agente simulado deixa um literal de cor: gate vermelho
    }
    pasta = dirp / ".kaizen" / "factory"
    portos = fazer_portos(kf, dirp, agente)
    say("factory", "run: marco 1 limpo, marco 2 com gate vermelho, marco 3 é a release")
    f = fabrica(kf, portos, pasta)
    rc = f.run()
    e = f.ler()
    if rc != kf.RC_PAUSA or e.get("paragem") != "release":
        return f"esperava pausa `release`, obtive rc {rc} {e.get('paragem')}"
    if '"evento": "correcao"' not in (pasta / "factory.log.jsonl").read_text(encoding="utf-8"):
        return "o gate vermelho não gerou SP de correção"
    say("release", f"paragem: {e['paragem']} ({e['razao']}); o humano faz a release e a factory retoma")
    rc = fabrica(kf, portos, pasta).run(release_feito=True)
    if rc != kf.RC_OK:
        return f"esperava factory concluída, obtive rc {rc}"
    say("release", "retomada com --release-feito: factory concluída (rc 0)")
    return ""


def etapa_orcamento(kf, dirp):
    say("orcamento", "um SP já acima do teto de custo: a factory pára antes de o lançar")
    rc, lancados = cenario_orcamento(kf, dirp / ".kaizen" / "factory-orcamento")
    e2 = kf.Fabrica("mini", kf.Portos(), dirp / ".kaizen" / "factory-orcamento").ler()
    if rc != kf.RC_PAUSA or e2.get("paragem") != "orcamento" or lancados:
        return f"esperava pausa por orçamento sem lançar, obtive rc {rc} {e2.get('paragem')} {lancados}"
    say("orcamento", f"paragem: {e2['paragem']} ({e2['razao']}); nada foi lançado")
    return ""


def etapa_publish(dirp):
    say("publish-recusado", "publish sem confirmação humana")
    subprocess.run(["git", "init", "-q"], cwd=str(dirp), capture_output=True)
    r = py(dirp, "kf_release.py", "publish", "--repo", ".")
    mostrar(r)
    if r.returncode != 3:
        return f"esperava rc 3, obtive {r.returncode}"
    say("publish-recusado", "rc 3: recusado sem --confirmo (tag e publish nunca em auto)")
    return ""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True)
    dirp = Path(ap.parse_args(argv).dir).resolve()
    for fluxo in (sys.stdout, sys.stderr):
        fluxo.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(dirp / "scripts"))
    import kf_factory as kf  # noqa: E402 — a cópia instalada no projeto de exemplo

    if preparar(dirp):
        return 1
    for etapa in (lambda: etapa_release(kf, dirp), lambda: etapa_orcamento(kf, dirp), lambda: etapa_publish(dirp)):
        erro = etapa()
        if erro:
            print(erro, file=sys.stderr)
            return 1
    print("factory demo concluída: gates, correção, orçamento, release e publish provados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
