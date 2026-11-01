#!/usr/bin/env python3
"""Vigia um PR por polling (gh pr view, só leitura) e imprime uma linha por mudança de estado.

Uso: python -I scripts/pr_watch.py <nº|URL> [--repo CAMINHO] [--intervalo S] [--max-min M] [--uma-vez]

Estados: erro, conflito, pendente, aguarda-review, pronto, merged, closed.
Consulta de 60 em 60 s e pára em pronto/merged (rc 0), closed (2), erro (5) ou conflito (6);
continua em pendente e aguarda-review. Outros rc: 3 limite de duração, 4 gh falhou seguidamente, 64 uso.
Com --uma-vez consulta uma vez (rc 0 se o estado não for de paragem).
Nunca faz merge, push nem escreve no GitHub.
"""
import argparse
import json
import re
import subprocess
import sys
import time

CAMPOS = "state,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup"
FALHAS = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}
OK = {"SUCCESS", "SKIPPED", "NEUTRAL"}
PEDE_REVIEW = {"REVIEW_REQUIRED", "CHANGES_REQUESTED"}
# estados que terminam a vigia -> rc
PARAGEM = {"merged": 0, "pronto": 0, "closed": 2, "erro": 5, "conflito": 6}


class GhError(RuntimeError):
    pass


def pr_ref(valor):
    """Aceita nº ou URL; rejeita o que o gh trataria como flag."""
    v = str(valor).strip()
    if re.fullmatch(r"\d+", v) or re.fullmatch(r"https://[^\s]+/pull/\d+/?", v):
        return v
    raise ValueError(f"PR inválido: {valor!r} (nº ou URL .../pull/N)")


def fetch(pr, repo=None):
    r = subprocess.run(["gh", "pr", "view", pr, "--json", CAMPOS],
                       capture_output=True, text=True, cwd=repo, timeout=60)
    if r.returncode != 0:
        raise GhError((r.stderr or "gh falhou").strip())
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise GhError(f"JSON inválido: {e}")


def _nome(c):
    return c.get("name") or c.get("context") or "?"


def _veredicto(c):
    """'ok' | 'erro' | 'pendente' para um check (CheckRun ou StatusContext)."""
    if c.get("__typename") == "StatusContext" or "state" in c and "status" not in c:
        s = (c.get("state") or "").upper()
        if s in FALHAS:
            return "erro"
        return "ok" if s == "SUCCESS" else "pendente"
    if (c.get("status") or "").upper() != "COMPLETED":
        return "pendente"
    concl = (c.get("conclusion") or "").upper()
    if concl in FALHAS:
        return "erro"
    return "ok" if concl in OK else "pendente"


def classify(d):
    """Devolve (estado, detalhe). Prioridade: merged, closed, erro, conflito, pendente, aguarda-review, pronto."""
    estado = (d.get("state") or "").upper()
    if estado == "MERGED":
        return "merged", ""
    if estado == "CLOSED":
        return "closed", ""
    checks = d.get("statusCheckRollup") or []
    vs = [(c, _veredicto(c)) for c in checks]
    falhados = [c for c, v in vs if v == "erro"]
    if falhados:
        det = "; ".join(f"{_nome(c)} ({c.get('detailsUrl') or c.get('targetUrl') or 'sem url'})" for c in falhados)
        return "erro", det
    if (d.get("mergeable") or "").upper() == "CONFLICTING":
        return "conflito", "o ramo tem conflitos com a base"
    if any(v == "pendente" for _, v in vs) or (d.get("mergeable") or "").upper() == "UNKNOWN":
        return "pendente", ""
    rev = (d.get("reviewDecision") or "").upper()
    if rev in PEDE_REVIEW:
        return "aguarda-review", rev.lower()
    return "pronto", "checks verdes, sem conflitos"


def watch(pr, repo=None, fetch_fn=fetch, sleep=time.sleep, interval=60, max_seconds=7200,
          clock=time.monotonic, max_falhas=5, uma_vez=False):
    inicio = clock()
    ultimo = None
    falhas = 0
    while True:
        try:
            d = fetch_fn(pr, repo)
            falhas = 0
        except GhError as e:
            falhas += 1
            if falhas >= max_falhas:
                print(f"PR {pr}: gh falhou {falhas}x seguidas ({e}); a parar", flush=True)
                return 4
            sleep(interval)
            continue
        est, det = classify(d)
        chave = (est, det if est != "pendente" else "")
        if chave != ultimo:
            print(f"PR {pr}: {est}" + (f" - {det}" if det else ""), flush=True)
            ultimo = chave
        if est in PARAGEM:
            return PARAGEM[est]
        if uma_vez:
            return 0
        if clock() - inicio >= max_seconds:
            print(f"PR {pr}: limite de duração atingido ({max_seconds}s); a parar (último: {est})", flush=True)
            return 3
        sleep(interval)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pr")
    ap.add_argument("--repo", help="caminho local do repo (cwd do gh)")
    ap.add_argument("--intervalo", type=int, default=60, help="segundos entre consultas (mín. 10)")
    ap.add_argument("--max-min", type=int, default=120, help="duração máxima em minutos")
    ap.add_argument("--uma-vez", action="store_true", help="consulta uma vez e sai")
    a = ap.parse_args(argv)
    try:
        ref = pr_ref(a.pr)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 64
    return watch(ref, a.repo, interval=max(10, a.intervalo), max_seconds=a.max_min * 60, uma_vez=a.uma_vez)


if __name__ == "__main__":
    sys.exit(main())
