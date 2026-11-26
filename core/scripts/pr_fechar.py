#!/usr/bin/env python3
"""Fecho `worktree-pr`: vigia o PR (pr_watch) e faz merge só com checks verdes (`pr_merge: auto-se-verde`).

Uso: python -I scripts/pr_fechar.py <nº|URL> [--repo CAMINHO] [--intervalo S] [--max-min M]
     [--sp SLUG] [--pentest-relatorio F] [--review-estado F] [--tentativa N] [--max-tentativas M]
Com perfil `qualidade` na config do repo: antes do merge corre os gates bloqueantes (vermelho = sem merge) e exige
`pentest` (relatório «sem achados») e `review` (estado APROVADO) conforme `qualidade.fases`; o motivo fica no estado
`bloqueado` do SP (`--sp`). Sem perfil, comportamento antigo.
Estratégia e permissão vêm de `desenvolvimento` em kaizen.config.json (`--repo`, defeito raiz do vault).
Merge por `gh pr merge --<estratégia> --delete-branch`; nunca `--admin`, nunca force.
rc: 0 merged, 10 sem permissão de merge, 11 bloqueado, 12 conflito, 13 vermelho corrigível, 3 limite de duração, 4 gh falhou, 64 uso
Desfechos (rc): 0 merged, 10 pronto mas sem permissão de merge (pr_merge pergunta|nunca),
11 bloqueado (checks vermelhos, review pedida, PR fechado ou erro), 12 conflito, 3 limite de duração,
4 gh falhou, 64 uso/sem método worktree-pr, 13 vermelho corrigível (check do PR ou gate local vermelho com
tentativa < --max-tentativas: corrigir, commit+push e repetir com --tentativa n+1, sem perguntar ao user).
Esgotadas as tentativas, conflito ou review pedida: SP `bloqueado` (motivo com o URL do PR), sem merge.
Em rc≠0 não há merge; a linha final diz o motivo.
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
import json  # noqa: E402
import kaizen_config  # noqa: E402
import kaizen_engine  # noqa: E402
import pr_watch  # noqa: E402


def _gates_bloqueantes(repo, perfil):
    """Corre os gates bloqueantes do perfil em `repo`; devolve o comando do 1.º vermelho ou None."""
    sp_gates = kaizen_engine.load("sp-gates")
    gates = sp_gates.juntar_perfil([], {**perfil, "consultivos": []}, repo)
    bad = sp_gates.problems(gates)
    if bad:
        return bad[0]
    res = sp_gates.run(gates)
    return next((r["cmd"] for r in res if r["rc"] != 0), None)


def _prova_fases(perfil, pentest_relatorio, review_estado):
    """Motivo se falta/falha a prova de uma fase exigida pelo perfil; None se tudo cumprido."""
    if "pentest" in perfil["fases"]:
        try:
            txt = Path(pentest_relatorio).read_text(encoding="utf-8") if pentest_relatorio else None
        except OSError:
            txt = None
        if txt is None or txt.strip() != "sem achados":
            return "pentest: relatório em falta ou com achados"
    if "review" in perfil["fases"]:
        try:
            ok = json.loads(Path(review_estado).read_text(encoding="utf-8")).get("veredicto") == "APROVADO" if review_estado else False
        except (OSError, ValueError, AttributeError):
            ok = False
        if not ok:
            return "review-ciclo: sem veredicto APROVADO"
    return None


def _bloquear(slug, motivo):
    """Regista `bloqueado` com o motivo no estado do SP (melhor esforço: SP fora de fila só imprime)."""
    if not slug:
        return
    try:
        kaizen_engine.load("sp_painel_estado").transitar(slug, "bloqueado", msg=motivo)
    except Exception as e:  # noqa: BLE001 - o rc 11 já trava o merge
        print(f"aviso: bloqueado não registado ({e})", file=sys.stderr)


def _gh_merge(pr, estrategia, repo):
    r = run_hidden(["gh", "pr", "merge", pr, f"--{estrategia}", "--delete-branch"],
                       capture_output=True, text=True, cwd=repo, timeout=120)
    return r.returncode, (r.stderr or r.stdout).strip()


def _vermelho(pr, motivo, tentativa, max_tentativas, sp):
    """Vermelho (check do PR ou gate local): 13 corrigível enquanto há tentativas; esgotadas, bloqueia o SP (11)."""
    if tentativa < max_tentativas:
        return 13, f"vermelho corrigível (tentativa {tentativa}/{max_tentativas}): {motivo}; corrigir, push e repetir; sem merge"
    motivo = f"{motivo}; PR {pr}; {max_tentativas} tentativas esgotadas"
    _bloquear(sp, motivo)
    return 11, f"{motivo}; sem merge"


def _vigia_parou(rc, pr, tentativa, max_tentativas, sp, detalhe):
    """Traduz o rc do vigia em (rc, mensagem) quando não há merge a fazer; None se o PR está verde."""
    if rc == 0:
        return None
    if rc == 6:
        _bloquear(sp, f"conflito com a base; PR {pr}")
        return 12, "conflito com a base; sem merge"
    if rc in (3, 4):
        return rc, "vigia parou (limite de duração ou gh falhou); sem merge"
    if rc == 5:
        return _vermelho(pr, f"checks vermelhos: {detalhe()}", tentativa, max_tentativas, sp)
    return 11, "PR fechado ou erro; sem merge"


def fechar(pr, repo, watch_fn=None, fetch_fn=pr_watch.fetch, merge_fn=_gh_merge, interval=60, max_seconds=7200,
           sp=None, pentest_relatorio=None, review_estado=None, gates_fn=_gates_bloqueantes, tentativa=1, max_tentativas=3):
    """Devolve (rc, mensagem). `watch_fn(pr, repo)` devolve o rc do pr_watch (injetável nos testes)."""
    d = kaizen_config.desenvolvimento(repo)
    if d is None or d["metodo"] != "worktree-pr":
        return 64, "projeto sem método worktree-pr"
    if watch_fn is None:
        def watch_fn(p, r):
            return pr_watch.watch(p, r, fetch_fn=fetch_fn, interval=interval, max_seconds=max_seconds)
    def detalhe():
        try:
            return pr_watch.classify(fetch_fn(pr, repo))[1] or "sem detalhe"
        except pr_watch.GhError:
            return "sem detalhe"
    parou = _vigia_parou(watch_fn(pr, repo), pr, tentativa, max_tentativas, sp, detalhe)
    if parou:
        return parou
    try:
        estado, det = pr_watch.classify(fetch_fn(pr, repo))
    except pr_watch.GhError as e:
        return 4, f"gh falhou: {e}"
    if estado == "merged":
        return 0, "já merged"
    if estado != "pronto":
        _bloquear(sp, f"{estado}{' - ' + det if det else ''}; PR {pr}")
        return 11, f"{estado}{' - ' + det if det else ''}; sem merge"
    if d["pr_merge"] != "auto-se-verde":
        return 10, f"pronto, mas pr_merge={d['pr_merge']}; sem merge"
    perfil = kaizen_config.qualidade(repo)
    if perfil:
        vermelho = gates_fn(repo, perfil)
        if vermelho:
            return _vermelho(pr, f"gate bloqueante vermelho: {vermelho}", tentativa, max_tentativas, sp)
        motivo = _prova_fases(perfil, pentest_relatorio, review_estado)
        if motivo:
            _bloquear(sp, motivo)
            return 11, f"{motivo}; sem merge"
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
    ap.add_argument("--sp", help="slug do SP onde registar `bloqueado` com o motivo")
    ap.add_argument("--pentest-relatorio", help="ficheiro do `pentest.py --relatorio` (exigido pelo perfil)")
    ap.add_argument("--review-estado", help="JSON de estado do `review_ciclo.py` (exigido pelo perfil)")
    ap.add_argument("--tentativa", type=int, default=1, help="nº da tentativa de correção (1 = primeira)")
    ap.add_argument("--max-tentativas", type=int, default=3, help="tentativas antes de bloquear o SP")
    a = ap.parse_args(argv)
    try:
        ref = pr_watch.pr_ref(a.pr)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 64
    rc, msg = fechar(ref, a.repo, interval=max(10, a.intervalo), max_seconds=a.max_min * 60,
                   sp=a.sp, pentest_relatorio=a.pentest_relatorio, review_estado=a.review_estado,
                   tentativa=a.tentativa, max_tentativas=a.max_tentativas)
    print(f"PR {ref}: {msg}", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
