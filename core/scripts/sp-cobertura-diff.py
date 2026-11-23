#!/usr/bin/env python3
"""Cobertura das linhas adicionadas/alteradas pelo diff (não a média global).

Uso: sp-cobertura-diff.py [--repo R] [--base REF] [--cobertura F ...] [--limiar N]
Lê relatórios já gerados (lcov, JSON do coverage.py ou Cobertura XML); por defeito procura
`coverage/lcov.info`, `coverage/coverage.json` e `coverage/python.xml` no repo. Não corre testes nem usa a rede.
Só conta linhas de código (py, js, ts...) fora de testes; linhas que o relatório não lista (não executáveis) não contam.
Limiar: `--limiar` ou `qualidade.coberturaDiff` em kaizen.config.json (defeito 85).
rc: 0 cobertura >= limiar (ou sem linhas de código), 1 abaixo, 2 relatórios em falta ou ilegíveis
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_config  # noqa: E402
import pentest  # noqa: E402

CODIGO = re.compile(r"\.(py|js|jsx|ts|tsx|mjs|cjs|vue|svelte)$")
RELATORIOS = ("coverage/lcov.info", "coverage/coverage.json", "coverage/python.xml")


def _norm(p):
    return str(p).replace("\\", "/")


def _lcov(texto):
    out, cur = {}, None
    for raw in texto.splitlines():
        if raw.startswith("SF:"):
            cur = out.setdefault(_norm(raw[3:].strip()), {})
        elif raw.startswith("DA:") and cur is not None:
            partes = raw[3:].split(",")
            try:
                ln, hits = int(partes[0]), int(float(partes[1]))
            except (ValueError, IndexError):
                continue
            cur[ln] = cur.get(ln, 0) + hits
    return out


def _json_coverage(texto):
    out = {}
    for f, d in (json.loads(texto).get("files") or {}).items():
        linhas = dict.fromkeys(d.get("executed_lines", []), 1)
        linhas.update(dict.fromkeys(d.get("missing_lines", []), 0))
        out[_norm(f)] = linhas
    return out


def _cobertura_xml(texto, repo):
    raiz = ET.fromstring(texto)  # noqa: S314 — ficheiro local gerado pelo CI
    fontes = [_norm(s.text.strip()) for s in raiz.iter("source") if s.text and s.text.strip()]
    out = {}
    for c in raiz.iter("class"):
        nome = _norm(c.get("filename", ""))
        if not nome:
            continue
        chave = nome
        for s in fontes:
            cand = Path(s) / nome
            if cand.is_absolute() and Path(repo).resolve() in cand.resolve().parents:
                chave = _norm(cand.resolve().relative_to(Path(repo).resolve()))
                break
        linhas = out.setdefault(chave, {})
        for ln in c.iter("line"):
            try:
                n = int(ln.get("number"))
                linhas[n] = linhas.get(n, 0) + int(float(ln.get("hits", 0)))
            except (TypeError, ValueError):
                continue
    return out


def ler_relatorio(caminho, repo="."):
    """{caminho: {linha: hits}} de um relatório lcov, JSON do coverage.py ou Cobertura XML (deteta pelo conteúdo)."""
    texto = Path(caminho).read_text(encoding="utf-8")
    s = texto.lstrip()
    if s.startswith("<"):
        return _cobertura_xml(texto, repo)
    if s.startswith("{"):
        return _json_coverage(texto)
    return _lcov(texto)


def juntar(dados, novo):
    for f, linhas in novo.items():
        alvo = dados.setdefault(f, {})
        for ln, h in linhas.items():
            alvo[ln] = alvo.get(ln, 0) + h
    return dados


def _procurar(dados, ficheiro):
    """Linhas do relatório para `ficheiro` (relativo ao repo): igualdade ou sufixo por componente de caminho."""
    if ficheiro in dados:
        return dados[ficheiro]
    for f, linhas in dados.items():
        if f.endswith("/" + ficheiro) or ficheiro.endswith("/" + f):
            return linhas
    return None


def e_codigo(p):
    p = _norm(p)
    return bool(CODIGO.search(p)) and not pentest.TESTE.search(p) and "/tests/" not in "/" + p \
        and "/__tests__/" not in "/" + p and not p.endswith("conftest.py")


def calcular(repo, base, dados):
    """(cobertas, total, por_ficheiro{f: [linhas por cobrir]}, sem_dados[f]) sobre as linhas adicionadas."""
    cobertas = total = 0
    por_cobrir, sem_dados = {}, []
    for f, ln, _t in pentest.added_lines(repo, base):
        if not e_codigo(f):
            continue
        linhas = _procurar(dados, _norm(f))
        if linhas is None:
            if f not in sem_dados:
                sem_dados.append(f)
            continue
        if ln not in linhas:
            continue
        total += 1
        if linhas[ln] > 0:
            cobertas += 1
        else:
            por_cobrir.setdefault(f, []).append(ln)
    return cobertas, total, por_cobrir, sem_dados


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--cobertura", nargs="+", help="relatórios lcov/JSON/Cobertura (defeito: coverage/ do repo)")
    ap.add_argument("--limiar", type=float)
    a = ap.parse_args(argv)
    repo = Path(a.repo)
    limiar = a.limiar if a.limiar is not None else kaizen_config.cobertura_diff(repo)
    ficheiros = [Path(x) for x in a.cobertura] if a.cobertura else [repo / r for r in RELATORIOS if (repo / r).is_file()]
    if not ficheiros:
        print("sp-cobertura-diff: sem relatório de cobertura (gerar com KAIZEN_COVERAGE=1 npm test ou --cobertura F)", file=sys.stderr)
        return 2
    dados = {}
    for f in ficheiros:
        try:
            juntar(dados, ler_relatorio(f, repo))
        except (OSError, ValueError, ET.ParseError) as e:
            print(f"sp-cobertura-diff: {f} ilegível: {e}", file=sys.stderr)
            return 2
    cobertas, total, por_cobrir, sem_dados = calcular(repo, a.base, dados)
    for f, lns in por_cobrir.items():
        print(f"sem cobertura: {f}:{','.join(map(str, lns))}")
    for f in sem_dados:
        print(f"sem dados de cobertura (não contado): {f}")
    if total == 0:
        print("cobertura do diff: sem linhas de código a medir")
        return 0
    pct = 100 * cobertas / total
    print(f"cobertura do diff: {pct:.1f}% ({cobertas}/{total}) limiar {limiar:g}%")
    return 0 if pct >= limiar else 1


if __name__ == "__main__":
    sys.exit(main())
