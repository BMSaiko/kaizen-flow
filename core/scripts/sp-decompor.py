#!/usr/bin/env python3
"""Decompõe um VISION.md validado num programa de SPs (mãe + filhos) em sp/TODO, sem grill humano.

Uso:
  python -I scripts/sp-decompor.py <VISION.md> [--root DIR] [--repo REPO] [--gate CMD ...] [--priority P1] [--data AAAA-MM-DD] [--dry-run]
Cada marco de `## Milestones` vira um filho `<projeto>-visao-m<N>-<data>`; a mãe é `<projeto>-visao-<data>`.
Marco: `N. título [ficheiros F, horas H] (depende: 1, 2) \\`comando\\``. Sem `depende:` depende do marco anterior.
Sem `[ficheiros, horas]` assume 4 ficheiros e 2 h (registado como `Assuncao:`). Teto por filho: 6 ficheiros e 3 h.
Gate do filho: o comando do marco (ou o primeiro critério com comando do VISION) mais os gates de `--gate` ou de `sp-gates --sugerir REPO`.
Decisões do VISION (Goal, Constraints, Non-goals, stack, orçamento) viram `## Decisões`; o que falta vira `Assuncao:`.
Idempotente: um marco já existente (qualquer data) não é recriado; só se criam os que faltam. Valida tudo (`sp-validate`) e remove o que criou se algo falhar.
rc: 0 ok (ou nada a criar) · 1 VISION inválido, marco inválido ou SP gerado inválido · 2 uso
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402

sp_visao = kaizen_engine.load("sp-visao")
sp_new = kaizen_engine.load("sp-new")
sp_list = kaizen_engine.load("sp-list")
sp_gates = kaizen_engine.load("sp-gates")
sp_escalao = kaizen_engine.load("sp-escalao")
sp_validate = kaizen_engine.load("sp-validate")

MAX_FICHEIROS = 6
MAX_HORAS = 3.0
PADRAO_FICHEIROS = 4
PADRAO_HORAS = 2.0
MARCO = re.compile(r"^\s*(?:(\d+)[.)]|[-*])\s+(.*\S)\s*$")
DEPENDE = re.compile(r"\(\s*depende\s*:\s*([\d\s,+]+)\)", re.I)
ESTIMA = re.compile(r"\[\s*ficheiros\s+(\d+)\s*,\s*horas\s+(\d+(?:[.,]\d+)?)\s*\]", re.I)
COMANDO = re.compile(r"`([^`]+)`")


class DecomporErro(Exception):
    pass


def _criterios(seccoes):
    return [m.group(1).strip() for ln in seccoes.get("Success criteria", []) if (m := sp_visao.CRITERIO.match(ln))]


def _comando_visao(seccoes):
    for c in _criterios(seccoes):
        m = COMANDO.search(c)
        if m:
            return m.group(1).strip()
    return None


def parse_marcos(linhas, comando_visao=None):
    """Lista de marcos {n, titulo, deps, ficheiros, horas, assumido, cmd}; levanta DecomporErro se inválido."""
    marcos = []
    for ln in linhas:
        m = MARCO.match(ln)
        if not m or sp_visao.PLACEHOLDER.match(m.group(2)):
            continue
        n = len(marcos) + 1
        if m.group(1) and int(m.group(1)) != n:
            raise DecomporErro(f"marco {m.group(1)} fora de sequência (esperado {n})")
        texto = m.group(2)
        dep = DEPENDE.search(texto)
        est = ESTIMA.search(texto)
        cmd = COMANDO.search(texto)
        deps = [int(x) for x in re.findall(r"\d+", dep.group(1))] if dep else ([n - 1] if n > 1 else [])
        titulo = COMANDO.sub("", ESTIMA.sub("", DEPENDE.sub("", texto))).strip(" -—:;,")
        marcos.append({
            "n": n, "titulo": titulo or f"marco {n}", "deps": deps,
            "ficheiros": int(est.group(1)) if est else PADRAO_FICHEIROS,
            "horas": float(est.group(2).replace(",", ".")) if est else PADRAO_HORAS,
            "assumido": est is None, "cmd": (cmd.group(1).strip() if cmd else comando_visao),
        })
    if not marcos:
        raise DecomporErro("VISION sem marcos em `## Milestones`")
    return marcos


def validar_marcos(marcos):
    for mc in marcos:
        for d in mc["deps"]:
            if d < 1 or d > len(marcos) or d == mc["n"]:
                raise DecomporErro(f"marco {mc['n']} depende de {d}, que não é outro marco")
        if mc["ficheiros"] > MAX_FICHEIROS or mc["horas"] > MAX_HORAS:
            esc = sp_escalao.classificar(mc["ficheiros"], "baixo", mc["horas"])
            raise DecomporErro(f"marco {mc['n']} grande ({mc['ficheiros']} ficheiros, {mc['horas']:g} h; escalão {esc}; teto {MAX_FICHEIROS} ficheiros e {MAX_HORAS:g} h): dividir")
        if not mc["cmd"]:
            raise DecomporErro(f"marco {mc['n']} sem comando: pôr `comando` no marco ou um critério com comando no VISION")
    try:
        sp_new._sem_ciclos({f"m{mc['n']}": [f"m{d}" for d in mc["deps"]] for mc in marcos}, [f"m{mc['n']}" for mc in marcos])
    except sp_new.SpNewError as exc:
        raise DecomporErro(str(exc)) from exc


def _decisoes(campos, seccoes):
    dec = [f"Objetivo (VISION): {' '.join(sp_visao._util(seccoes.get('Goal', [])))}"]
    dec += [f"Restrição (VISION): {x}" for x in sp_visao._util(seccoes.get("Constraints", []))]
    dec += [f"Fora de âmbito (VISION): {x}" for x in sp_visao._util(seccoes.get("Non-goals", []))]
    dec.append(f"Stack (VISION): {campos['stack']}")
    dec.append(f"Orçamento (VISION): {campos['orcamento']}")
    return dec


def _corpo_filho(ctx, mc):
    projeto, campos, seccoes, total, slug_de = ctx["projeto"], ctx["campos"], ctx["seccoes"], ctx["total"], ctx["slug_de"]
    util = sp_visao._util
    deps = ", ".join(f"`{slug_de(d)}`" for d in mc["deps"]) or "nenhuma"
    ficheiros = f"{mc['ficheiros']} ficheiros, {mc['horas']:g} h" + (" (Assuncao: estimativa por omissão)" if mc["assumido"] else "")
    corpo = {
        1: f"You are the maintainer of {projeto} ({campos['stack']}), delivering one milestone of its VISION.",
        2: f"Milestone {mc['n']} of {total} of the {projeto} VISION. Goal: {' '.join(util(seccoes['Goal']))} Users: {'; '.join(util(seccoes['Users']))}. Depends on: {deps}.",
        3: f"{mc['titulo']}.",
        4: f"- [ ] `{mc['cmd']}`",
        5: "\n".join(f"- {x}" for x in [*util(seccoes["Constraints"]), *[f"Não fazer: {x}" for x in util(seccoes["Non-goals"])]]),
        6: f"- Assuncao: ficheiros a definir no DR; estimativa {ficheiros}.",
        7: "1. Ler o código e o contexto do marco.\n2. Testes vermelhos para o critério.\n3. Implementar até ao verde.\n4. Correr os gates, commit por fase e PR.",
        8: f"`{mc['cmd']}` passa e os gates do SP estão verdes.",
    }
    texto = [f"# Super Prompt - {slug_de(mc['n'])}", ""]
    for n, nome in sp_validate.SECTION_NAMES.items():
        texto += [f"## {n}. {nome}", "", corpo[n], ""]
    texto += ["## Decisões", ""] + [f"- {d}" for d in _decisoes(campos, seccoes)] + [""]
    if campos["ui"].strip().lower() == "sim":
        texto += ["## Esboço", "", f"Assuncao: esboço do ecrã a produzir no DR com o design system `{campos['design_system']}`.", ""]
    return "\n".join(texto)


def _corpo_mae(projeto, seccoes, marcos, slug_de):
    util = sp_visao._util
    lista = "\n".join(f"{mc['n']}. `{slug_de(mc['n'])}` {mc['titulo']}" for mc in marcos)
    corpo = {
        1: f"You are the maintainer of {projeto}, coordinating the milestones of its VISION.",
        2: f"Programa gerado de `VISION.md` por `sp-decompor.py`. Goal: {' '.join(util(seccoes['Goal']))}",
        3: f"Entregar os {len(marcos)} marcos do VISION de {projeto}.",
        4: "\n".join(f"- [ ] {c}" for c in _criterios(seccoes)),
        5: "\n".join(f"- {x}" for x in util(seccoes["Constraints"])),
        6: "- Filhos do programa em `children:`; cada um com os seus gates.",
        7: f"Executar os filhos pela ordem das dependências:\n{lista}",
        8: "Todos os filhos em Done e os critérios de sucesso do VISION cumpridos.",
    }
    texto = [f"# Super Prompt - programa {projeto}", ""]
    for n, nome in sp_validate.SECTION_NAMES.items():
        texto += [f"## {n}. {nome}", "", corpo[n], ""]
    return "\n".join(texto)


def _com_corpo(path, corpo):
    """Mantém o frontmatter gerado por `sp-new` e substitui o corpo."""
    texto = path.read_text(encoding="utf-8")
    fim = texto.index("\n---\n", 4) + len("\n---\n")
    path.write_text(texto[:fim] + corpo + "\n", encoding="utf-8", newline="\n")


def _gates(args):
    if args.gate:
        return list(args.gate)
    if args.repo:
        return list(sp_gates.detect_gates(args.repo))
    return []


def _planear(args):
    texto = sp_visao._ler(args.visao)
    campos, seccoes, problemas = sp_visao.analisar(texto)
    if problemas:
        raise DecomporErro("VISION inválido: " + "; ".join(problemas))
    marcos = parse_marcos(seccoes["Milestones"], _comando_visao(seccoes))
    validar_marcos(marcos)
    return campos, seccoes, marcos


def _auth(projeto, root):
    try:
        return sp_new.resolver_auth(projeto, {"commit": None, "push": None, "pr": None, "merge": None, "restricoes": None})
    except TypeError:
        return None


def _slugs(projeto, marcos, existentes, hoje):
    def achado(prefixo):
        rx = re.compile(rf"^{re.escape(prefixo)}-\d{{4}}-\d{{2}}-\d{{2}}$")
        return next((s for s in sorted(existentes) if rx.match(s)), None)

    mae_existente = achado(f"{projeto}-visao")
    slugs = {mc["n"]: achado(f"{projeto}-visao-m{mc['n']}") or sp_new.full_slug(projeto, f"visao-m{mc['n']}", hoje) for mc in marcos}
    return mae_existente, slugs


def _criar_mae(ctx, marcos, mae, args):
    slugs = ctx["slugs"]
    extra = ["kind: program", "children:"]
    for mc in marcos:
        extra += [f"  - slug: {slugs[mc['n']]}", f"    depends_on: [{', '.join(slugs[d] for d in mc['deps'])}]", "    state: TODO"]
    p = sp_new.create(ctx["root"], ctx["projeto"], mae, args.priority, ctx["hoje"], extra=extra, modo="auto", auth=ctx["auth"], programa=True)
    _com_corpo(p, _corpo_mae(ctx["projeto"], ctx["seccoes"], marcos, ctx["slug_de"]))
    return p


def _criar_filho(ctx, mc, mae, gates_base, args):
    slugs, deps = ctx["slugs"], [ctx["slugs"][d] for d in mc["deps"]]
    gates = list(dict.fromkeys([*gates_base, mc["cmd"]]))
    p = sp_new.create(ctx["root"], ctx["projeto"], slugs[mc["n"]], args.priority, ctx["hoje"], parent=mae, depends_on=deps,
                      modo="auto", auth=ctx["auth"], gates=gates, prova=mc["cmd"], decisoes=_decisoes(ctx["campos"], ctx["seccoes"]), ui=ctx["ui"])
    _com_corpo(p, _corpo_filho(ctx, mc))
    return p


def _criar(ctx, criados, args):
    """Cria mãe e filhos em falta, acrescentando a `criados` (o chamador limpa em caso de erro)."""
    mae, gates_base = ctx["mae"], _gates(args)
    if not ctx["mae_existente"]:
        criados.append(_criar_mae(ctx, ctx["marcos"], mae, args))
    for mc in ctx["faltam"]:
        criados.append(_criar_filho(ctx, mc, mae, gates_base, args))
        if ctx["mae_existente"]:
            sp_new.link_parent(ctx["root"], ctx["projeto"], mae, ctx["slugs"][mc["n"]], [ctx["slugs"][d] for d in mc["deps"]])


def _validar(criados):
    erros = []
    for p in criados:
        erros += [f"{p.name}: {e}" for e in sp_validate.validate(p.read_text(encoding="utf-8"), p.parent.name)]
    if erros:
        raise DecomporErro("SP gerado inválido: " + "; ".join(erros))


def decompor(args):
    campos, seccoes, marcos = _planear(args)
    projeto, root, hoje = campos["projeto"].strip(), Path(args.root), date.fromisoformat(args.data)
    existentes = {sp.slug for sp in sp_list.collect(root, include_done=True) if sp.project == projeto}
    mae_existente, slugs = _slugs(projeto, marcos, existentes, hoje)
    faltam = [mc for mc in marcos if slugs[mc["n"]] not in existentes]
    if not faltam:
        print(f"nada a criar: os {len(marcos)} marcos de {projeto} já têm SP")
        return 0
    if args.dry_run:
        for mc in faltam:
            print(f"criaria {slugs[mc['n']]} (depende: {', '.join(slugs[d] for d in mc['deps']) or '-'})")
        return 0
    mae = mae_existente or sp_new.full_slug(projeto, "visao", hoje)
    ctx = {"projeto": projeto, "campos": campos, "seccoes": seccoes, "total": len(marcos), "slugs": slugs, "slug_de": slugs.__getitem__,
           "root": root, "hoje": hoje, "mae": mae, "mae_existente": mae_existente, "marcos": marcos, "faltam": faltam, "auth": _auth(projeto, root), "ui": campos["ui"].strip().lower() == "sim"}
    criados = []
    try:
        _criar(ctx, criados, args)
        _validar(criados)
    except (DecomporErro, sp_new.SpNewError) as exc:
        for p in criados:
            p.unlink(missing_ok=True)
        sp_list.sp_indice.invalidar()
        raise DecomporErro(str(exc)) from exc
    for p in criados:
        print(p)
    print(f"{len(criados)} SP(s) criados em TODO (programa {mae}); correr `sp-fila` para os executar")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("visao", help="caminho do VISION.md")
    ap.add_argument("--root", default=str(sp_list.DEFAULT_ROOT), help=argparse.SUPPRESS)
    ap.add_argument("--repo", help="repo cujos gates sugeridos (sp-gates --sugerir) entram em cada filho")
    ap.add_argument("--gate", action="append", help="gate extra de cada filho (repetível; substitui --repo)")
    ap.add_argument("--priority", default="P2", choices=("P1", "P2", "P3"))
    ap.add_argument("--data", default=date.today().isoformat(), help="AAAA-MM-DD usada nos slugs")
    ap.add_argument("--dry-run", action="store_true", help="só lista o que criaria")
    args = ap.parse_args(argv)
    try:
        date.fromisoformat(args.data)
        return decompor(args)
    except (DecomporErro, FileNotFoundError, UnicodeDecodeError, ValueError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-decompor", main))
