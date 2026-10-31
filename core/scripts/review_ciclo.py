#!/usr/bin/env python3
"""Ciclo de review: corrigir -> rever até aprovação, com limite de iterações.

Uso: review_ciclo.py <estado.json> --achados <ficheiro> [--max 3] [--criar-sps --project P [--prefixo S]]
O ficheiro de achados tem uma linha por achado: `[bloqueante|menor] ficheiro:linha descrição`.
Veredicto (stdout, primeira linha): APROVADO | CORRIGIR | ESCALAR.
rc 0 aprovado, 1 corrigir (SPs gerados com --criar-sps; repetir o review depois), 2 escalar ao utilizador.
Só lê o ficheiro de achados e escreve o estado; o review em si é só leitura.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

LINHA = re.compile(r"^\[(bloqueante|menor)\]\s+(\S+)\s+(.*)$")


def ler_achados(path):
    out = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        m = LINHA.match(raw.strip())
        if m:
            out.append({"sev": m.group(1), "onde": m.group(2), "desc": m.group(3)})
    return out


def decidir(estado, achados, maximo):
    """Atualiza o estado e devolve (veredicto, bloqueantes)."""
    bloq = [a for a in achados if a["sev"] == "bloqueante"]
    estado["iteracao"] = estado.get("iteracao", 0) + 1
    estado.setdefault("historico", []).append({"iteracao": estado["iteracao"], "bloqueantes": len(bloq), "menores": len(achados) - len(bloq)})
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
    a = ap.parse_args(argv)
    if a.criar_sps and not a.project:
        ap.error("--criar-sps exige --project")
    ep = Path(a.estado)
    estado = json.loads(ep.read_text(encoding="utf-8")) if ep.exists() else {}
    if estado.get("veredicto") in ("APROVADO", "ESCALAR"):
        print(f"{estado['veredicto']} (ciclo já terminado; apagar {ep.name} para recomeçar)")
        return 0 if estado["veredicto"] == "APROVADO" else 2
    ver, bloq = decidir(estado, ler_achados(a.achados), a.max)
    ep.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{ver} (iteração {estado['iteracao']}/{a.max}, {len(bloq)} bloqueantes)")
    for b in bloq:
        print(f"[bloqueante] {b['onde']} {b['desc']}")
    if ver == "CORRIGIR" and a.criar_sps:
        for slug, ok in criar_sps(bloq, a.project, a.prefixo, estado["iteracao"]):
            print(f"SP {slug}: {'criado' if ok else 'falhou'}")
    return {"APROVADO": 0, "CORRIGIR": 1, "ESCALAR": 2}[ver]


if __name__ == "__main__":
    sys.exit(main())
