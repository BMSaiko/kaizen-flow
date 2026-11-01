#!/usr/bin/env python3
"""Ciclo de review: corrigir -> rever até aprovação, com limite de iterações.

Uso: review_ciclo.py <estado.json> --achados <ficheiro> [--max 3] [--criar-sps --project P [--prefixo S]]
     [--ficheiros F... [--raiz D]] [--checklist codigo|ui|docs]
O ficheiro de achados tem uma linha por achado: `[bloqueante|menor] ficheiro:linha descrição | verificar: como confirmar a correção`.
Com --ficheiros, o estado guarda o hash de cada um e a iteração seguinte só manda rever os alterados.
Veredicto (stdout, primeira linha): APROVADO | CORRIGIR | ESCALAR.
rc 0 aprovado, 1 corrigir (SPs gerados com --criar-sps; repetir o review depois), 2 escalar ao utilizador.
Só lê o ficheiro de achados e escreve o estado; o review em si é só leitura.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

LINHA = re.compile(r"^\[(bloqueante|menor)\]\s+(\S+)\s+(.*)$")
VERIFICAR = re.compile(r"\s*\|\s*verificar:\s*(.*)$")

CHECKLISTS = {
    "codigo": ["testes cobrem o comportamento novo e os casos limite", "erros e entradas inválidas tratados", "sem segredos, injeção ou caminhos não validados", "sem regressão nas interfaces públicas"],
    "ui": ["estados vazio, erro e carregamento", "teclado e contraste (acessibilidade)", "responsivo em largura estreita", "prova visual anexada"],
    "docs": ["links e wikilinks resolvem", "frontmatter e MOC/README atualizados", "sem duplicar regra existente", "orçamento de contexto respeitado"],
}


def checklist(tipo):
    return "\n".join(f"- [ ] {i}" for i in CHECKLISTS[tipo])


def hashes(raiz, ficheiros):
    out = {}
    for f in ficheiros:
        p = Path(raiz) / f
        out[f] = hashlib.sha1(p.read_bytes()).hexdigest() if p.is_file() else ""
    return out


def alterados(estado, novos):
    antes = estado.get("hashes")
    if antes is None:
        return sorted(novos)
    return sorted(f for f, h in novos.items() if antes.get(f) != h)


def resumo(estado):
    linhas = ["| iteração | bloqueantes | menores | a rever |", "|---|---|---|---|"]
    for h in estado.get("historico", []):
        linhas.append(f"| {h['iteracao']} | {h['bloqueantes']} | {h['menores']} | {len(h['rever']) if 'rever' in h else '-'} |")
    return "\n".join(linhas)


def ler_achados(path):
    out = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        m = LINHA.match(raw.strip())
        if m:
            desc = m.group(3)
            v = VERIFICAR.search(desc)
            out.append({"sev": m.group(1), "onde": m.group(2), "desc": VERIFICAR.sub("", desc), "verificar": v.group(1) if v else ""})
    return out


def decidir(estado, achados, maximo):
    """Atualiza o estado e devolve (veredicto, bloqueantes)."""
    bloq = [a for a in achados if a["sev"] == "bloqueante"]
    estado["iteracao"] = estado.get("iteracao", 0) + 1
    estado.setdefault("historico", []).append({"iteracao": estado["iteracao"], "bloqueantes": len(bloq), "menores": len(achados) - len(bloq), "achados": achados})
    if not bloq:
        estado["veredicto"] = "APROVADO"
    elif estado["iteracao"] >= maximo:
        estado["veredicto"] = "ESCALAR"
    else:
        estado["veredicto"] = "CORRIGIR"
    return estado["veredicto"], bloq


def criar_sps(bloq, project, prefixo, iteracao):
    sp_new = Path(__file__).with_name("sp-new.py")
    res = []
    for i, a in enumerate(bloq, 1):
        slug = f"{prefixo}-{iteracao}-{i}"
        r = subprocess.run([sys.executable, "-I", str(sp_new), "--project", project, "--slug", slug, "--priority", "P1", "--escopo", a["onde"]],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        res.append((slug, r.returncode == 0))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("estado")
    ap.add_argument("--achados", required=True)
    ap.add_argument("--max", type=int, default=3)
    ap.add_argument("--criar-sps", action="store_true")
    ap.add_argument("--project")
    ap.add_argument("--prefixo", default="review")
    ap.add_argument("--ficheiros", nargs="+")
    ap.add_argument("--raiz", default=".")
    ap.add_argument("--checklist", choices=sorted(CHECKLISTS))
    a = ap.parse_args(argv)
    if a.criar_sps and not a.project:
        ap.error("--criar-sps exige --project")
    ep = Path(a.estado)
    estado = json.loads(ep.read_text(encoding="utf-8")) if ep.exists() else {}
    if estado.get("veredicto") in ("APROVADO", "ESCALAR"):
        print(f"{estado['veredicto']} (ciclo já terminado; apagar {ep.name} para recomeçar)")
        return 0 if estado["veredicto"] == "APROVADO" else 2
    rever = None
    if a.ficheiros:
        novos = hashes(a.raiz, a.ficheiros)
        rever = alterados(estado, novos)
        estado["hashes"] = novos
    ver, bloq = decidir(estado, ler_achados(a.achados), a.max)
    if rever is not None:
        estado["historico"][-1]["rever"] = rever
    ep.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{ver} (iteração {estado['iteracao']}/{a.max}, {len(bloq)} bloqueantes)")
    for b in bloq:
        print(f"[bloqueante] {b['onde']} {b['desc']}" + (f" | verificar: {b['verificar']}" if b["verificar"] else ""))
    if rever is not None:
        print("Rever só: " + (", ".join(rever) or "(nada alterado)"))
    if a.checklist:
        print("Checklist:\n" + checklist(a.checklist))
    print(resumo(estado))
    if ver == "CORRIGIR" and a.criar_sps:
        for slug, ok in criar_sps(bloq, a.project, a.prefixo, estado["iteracao"]):
            print(f"SP {slug}: {'criado' if ok else 'falhou'}")
    return {"APROVADO": 0, "CORRIGIR": 1, "ESCALAR": 2}[ver]


if __name__ == "__main__":
    sys.exit(main())
