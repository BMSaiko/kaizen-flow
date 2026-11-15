#!/usr/bin/env python3
"""Fecho `worktree-pr`: vigia o PR (pr_watch) e faz merge só com checks verdes (`pr_merge: auto-se-verde`).

Uso: python -I scripts/pr_fechar.py <nº|URL> [--repo CAMINHO] [--intervalo S] [--max-min M]
Estratégia e permissão vêm de `desenvolvimento` em kaizen.config.json (`--repo`, defeito raiz do vault).
Merge por `gh pr merge --<estratégia> --delete-branch`; nunca `--admin`, nunca force.
rc: 0 merged, 10 sem permissão de merge, 11 bloqueado, 12 conflito, 3 limite de duração, 4 gh falhou, 64 uso
Desfechos (rc): 0 merged, 10 pronto mas sem permissão de merge (pr_merge pergunta|nunca),
11 bloqueado (checks vermelhos, review pedida, PR fechado ou erro), 12 conflito, 3 limite de duração,
4 gh falhou, 64 uso/sem método worktree-pr. Em rc≠0 não há merge; a linha final diz o motivo.
"""
import argparse
from pathlib import Path as _P
import sys as _s
_s.path.insert(0, str(_P(__file__).resolve().parent))
from painel_backend import run_hidden  # noqa: E402
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kaizen_config  # noqa: E402
import pr_watch  # noqa: E402


def _gh_merge(pr, estrategia, repo):
    r = run_hidden(["gh", "pr", "merge", pr, f"--{estrategia}", "--delete-branch"],
                       capture_output=True, text=True, cwd=repo, timeout=120)
    return r.returncode, (r.stderr or r.stdout).strip()


def fechar(pr, repo, watch_fn=None, fetch_fn=pr_watch.fetch, merge_fn=_gh_merge, interval=60, max_seconds=7200):
    """Devolve (rc, mensagem). `watch_fn(pr, repo)` devolve o rc do pr_watch (injetável nos testes)."""
    d = kaizen_config.desenvolvimento(repo)
    if d is None or d["metodo"] != "worktree-pr":
        return 64, "projeto sem método worktree-pr"
    if watch_fn is None:
        def watch_fn(p, r):
            return pr_watch.watch(p, r, fetch_fn=fetch_fn, interval=interval, max_seconds=max_seconds)
    rc = watch_fn(pr, repo)
    if rc == 6:
        return 12, "conflito com a base; sem merge"
    if rc in (3, 4):
        return rc, "vigia parou (limite de duração ou gh falhou); sem merge"
    if rc != 0:
        return 11, "checks vermelhos, PR fechado ou erro; sem merge"
    try:
        estado, det = pr_watch.classify(fetch_fn(pr, repo))
    except pr_watch.GhError as e:
        return 4, f"gh falhou: {e}"
    if estado == "merged":
        return 0, "já merged"
    if estado != "pronto":
        return 11, f"{estado}{' - ' + det if det else ''}; sem merge"
    if d["pr_merge"] != "auto-se-verde":
        return 10, f"pronto, mas pr_merge={d['pr_merge']}; sem merge"
    mrc, out = merge_fn(pr, d["merge_estrategia"], repo)
    if mrc != 0:
        return 11, f"gh pr merge falhou: {out}"
    return 0, f"merged ({d['merge_estrategia']})"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pr")
    ap.add_argument("--repo", default=str(HERE.parent))
    ap.add_argument("--intervalo", type=int, default=60)
    ap.add_argument("--max-min", type=int, default=120)
    a = ap.parse_args(argv)
    try:
        ref = pr_watch.pr_ref(a.pr)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 64
    rc, msg = fechar(ref, a.repo, interval=max(10, a.intervalo), max_seconds=a.max_min * 60)
    print(f"PR {ref}: {msg}", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
