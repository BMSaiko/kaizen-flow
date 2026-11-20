#!/usr/bin/env python3
"""Pré-voo do kf (`kaizen preflight`): diagnostica git/worktree e ferramentas antes de arrancar ou retomar um SP.

Deteta, cada um com o seu EC do catálogo e o comando de correção segura:
  EC-065 git/Python ausentes · EC-031 checkout principal fora do ramo principal · EC-061 ramo errado
  EC-062 worktree do SP em falta · EC-060 árvore suja · EC-064 merge/rebase/cherry-pick a meio
  EC-025 ramo atrás do principal · EC-063 worktree por limpar (prunable) · EC-027 SP órfão (lock morto)
Nunca altera nada por defeito. `--fix` executa só as correções da lista segura (stash com etiqueta,
`worktree prune`, `checkout`), uma a uma e só com confirmação no terminal (EOF = não).
Nível: `erro` impede arrancar (o michi em auto pára como `bloqueado`); `aviso` informa.

Uso: python -I scripts/sp-preflight.py [<slug>] [--repo DIR] [--ramo R] [--sem-orfao] [--fix] [--json]
rc: 0 limpo · 1 há problemas (ou correção recusada) · 2 erro de uso (pasta fora de git, slug inválido)
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kf_errlog  # noqa: E402
import kf_erros  # noqa: E402
import kf_git  # noqa: E402
from painel_backend import run_hidden  # noqa: E402

NADA = "nada alterado"
# EC-055: margem para os ficheiros dentro da worktree caberem nos 260 do Windows (sem limite noutros SO)
LIMITE_CAMINHO = 200 if os.name == "nt" else None
_DATA = re.compile(r"-\d{4}-\d{2}-\d{2}$")
_ESTADOS_GIT = (("MERGE_HEAD", "merge"), ("rebase-merge", "rebase"), ("rebase-apply", "rebase"),
                ("CHERRY_PICK_HEAD", "cherry-pick"), ("REVERT_HEAD", "revert"))


class ErroUso(Exception):
    def __init__(self, msg, ec, porque, proximo):
        super().__init__(msg)
        self.ec, self.porque, self.proximo = ec, porque, proximo


@dataclass
class Problema:
    ec: str
    nivel: str  # "erro" | "aviso"
    oque: str
    porque: str
    proximo: str
    fix: list = None  # argv da correção segura (só com --fix + confirmação) ou None

    def texto(self):
        return kf_erros.erro(self.ec, self.oque, self.porque, NADA, self.proximo)


def _git(repo, *args):
    return kf_git.run(repo, *args, cache=True)


def _slug_valido(slug):
    return bool(slug) and slug not in (".", "..") and not any(c in slug for c in ("/", "\\", ":", " "))


def _base(slug):
    return _DATA.sub("", slug)


def ramo_do_sp(slug, ramo):
    """O ramo é do SP? `agent/<slug>`, `agent/<slug sem data>` ou com sufixo `-N` (worktrees repetidas)."""
    if not ramo:
        return False
    return ramo == f"agent/{slug}" or re.fullmatch(rf"agent/{re.escape(_base(slug))}(-\d+)?", ramo) is not None


def worktrees(repo):
    """[{path, ramo, prunable}] de `git worktree list --porcelain`; a primeira é o checkout principal."""
    out, atual = [], None
    for linha in _git(repo, "worktree", "list", "--porcelain").stdout.splitlines():
        if linha.startswith("worktree "):
            atual = {"path": linha[len("worktree "):], "ramo": None, "prunable": False}
            out.append(atual)
        elif atual is not None and linha.startswith("branch "):
            atual["ramo"] = linha[len("branch "):].removeprefix("refs/heads/")
        elif atual is not None and linha.startswith("prunable"):
            atual["prunable"] = True
    return out


def _mesmo(a, b):
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return str(a) == str(b)


def _existe_ramo(repo, ramo):
    return _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{ramo}").returncode == 0


def ramo_principal(repo, principal, dado=None):
    if dado:
        return dado
    try:
        import kaizen_config
        dev = kaizen_config.desenvolvimento(principal)
        if dev and dev.get("ramo_principal"):
            return dev["ramo_principal"]
    except Exception:  # noqa: BLE001 — sem config, deteta pelos ramos
        pass
    return next((r for r in ("main", "master") if _existe_ramo(repo, r)), None)


def _ferramentas(which):
    probs = []
    if which("git") is None:
        probs.append(Problema("EC-065", "erro", "git não está no PATH", "o pré-voo e o fluxo de worktrees precisam do git",
                              "instalar o git (https://git-scm.com) e abrir um terminal novo"))
    if not any(which(n) for n in ("python3", "python", "py")):
        probs.append(Problema("EC-065", "erro", "Python não está no PATH", "os scripts do kaizen-flow correm em Python 3",
                              "instalar o Python 3 (https://python.org) e abrir um terminal novo"))
    return probs


def _orfaos(alvo):
    try:
        from sp_carregar import carregar
        resume = carregar(HERE / "sp-resume.py", "sp_resume")
        return resume.candidatos(alvo)
    except Exception:  # noqa: BLE001 — sem a API do resume, o pré-voo não falha por isso
        return []


def diagnosticar(slug=None, repo=".", ramo=None, ignorar_orfao=False, which=shutil.which):
    """Lista de Problema (vazia = limpo). Só lê: nenhum comando que altere o repo corre aqui."""
    if slug is not None and not _slug_valido(slug):
        raise ErroUso(f"slug inválido «{slug}»", "EC-067", "o slug é o nome do SP, sem `/`, `\\`, `:` nem espaços",
                      "`kaizen preflight <slug>` com o slug do SP (`sp-list.py`)")
    probs = _ferramentas(which)
    if any("git" in p.oque for p in probs):
        return probs
    repo = Path(repo)
    top = _git(repo, "rev-parse", "--show-toplevel") if repo.is_dir() else None
    if top is None or top.returncode != 0:
        raise ErroUso(f"{repo} não é um repositório git", "EC-062", "o pré-voo corre dentro de um repositório ou worktree git",
                      "correr na pasta do projeto ou passar `--repo <pasta>`")
    top = top.stdout.strip()
    wts = worktrees(repo)
    principal = wts[0]["path"] if wts else top
    rp = ramo_principal(repo, principal)
    atual = next((w for w in wts if _mesmo(w["path"], top)), {"path": top, "ramo": kf_git.branch_atual(top)})
    no_principal = _mesmo(top, principal)
    alvo = atual
    if no_principal and rp and atual.get("ramo") != rp and not (slug and ramo_do_sp(slug, atual.get("ramo"))):
        probs.append(Problema(
            "EC-031", "erro", f"checkout principal {principal} está em «{atual.get('ramo') or 'HEAD destacado'}», não em «{rp}»",
            "o checkout principal fica no ramo principal; o trabalho faz-se numa worktree",
            f"git -C \"{principal}\" checkout {rp}", fix=["git", "-C", principal, "checkout", rp]))
    if slug:
        esperado = ramo or f"agent/{_base(slug)}"
        do_sp = next((w for w in wts if (w["ramo"] == ramo if ramo else ramo_do_sp(slug, w["ramo"])) and not w["prunable"]), None)
        if ramo_do_sp(slug, atual.get("ramo")) or (ramo and atual.get("ramo") == ramo):
            alvo = atual
        elif do_sp is not None:
            if no_principal:
                alvo = do_sp
            else:
                probs.append(Problema(
                    "EC-061", "erro", f"worktree {top} está em «{atual.get('ramo')}», não no ramo do SP «{do_sp['ramo']}»",
                    "cada SP trabalha só na sua worktree", f"cd \"{do_sp['path']}\" (a worktree do SP)"))
                alvo = do_sp
        elif no_principal:
            criar = "" if _existe_ramo(repo, esperado) else "-b "
            destino = Path(principal).parent / f"{Path(principal).name}-{_base(slug)}"
            probs.append(Problema(
                "EC-062", "erro", f"o SP {slug} não tem worktree (ramo «{esperado}»)",
                "o SP corre numa worktree própria, fora do checkout principal",
                f"git -C \"{principal}\" worktree add \"{destino}\" {criar}{esperado}"))
            if LIMITE_CAMINHO and len(str(destino)) > LIMITE_CAMINHO:
                probs.append(Problema(
                    "EC-055", "erro", f"o caminho da worktree tem {len(str(destino))} caracteres: {destino}",
                    "no Windows os ficheiros dentro dela passam dos 260 caracteres e o git deixa-a a meio",
                    "git config --global core.longpaths true, ou um repo num caminho mais curto"))
            alvo = None
        else:
            fix = ["git", "-C", top, "checkout", esperado] if _existe_ramo(repo, esperado) else None
            probs.append(Problema(
                "EC-061", "erro", f"worktree {top} está em «{atual.get('ramo') or 'HEAD destacado'}», não em «{esperado}»",
                "cada SP trabalha no seu ramo `agent/<slug>`",
                f"git -C \"{top}\" checkout {esperado}" if fix else f"git -C \"{top}\" switch -c {esperado}", fix=fix))
    if alvo is not None:
        probs += _estado_da_arvore(alvo["path"], alvo.get("ramo"), rp, slug)
        orfaos = [] if ignorar_orfao else _orfaos(alvo["path"])
        for o in orfaos if not slug else [s for s in orfaos if s == slug]:
            probs.append(Problema("EC-027", "aviso", f"SP {o} ficou a meio sem dono vivo (órfão)",
                                  "o painel que o corria fechou ou morreu", f"kaizen resume {o}"))
    for w in wts:
        if w["prunable"]:
            probs.append(Problema("EC-063", "aviso", f"worktree registada sem pasta: {w['path']}",
                                  "a pasta foi apagada sem `git worktree prune`",
                                  f"git -C \"{repo}\" worktree prune  (corrigível com --fix)",
                                  fix=["git", "-C", str(repo), "worktree", "prune"]))
    return probs


def _estado_da_arvore(path, ramo, rp, slug):
    probs = []
    paths = _git(path, "rev-parse", *[a for n, _ in _ESTADOS_GIT for a in ("--git-path", n)]).stdout.splitlines()
    for (_nome, oper), p in zip(_ESTADOS_GIT, paths):
        if (Path(p) if Path(p).is_absolute() else Path(path) / p).exists():
            probs.append(Problema(
                "EC-064", "erro", f"{oper} a meio em {path}", f"um `git {oper}` parou (conflito ou interrupção)",
                f"resolver e `git -C \"{path}\" {oper} --continue`, ou `git -C \"{path}\" {oper} --abort` (à mão)"))
            break
    sujos = [l[3:].strip().strip('"') for l in _git(path, "status", "--porcelain", "-uall").stdout.splitlines() if l.strip()]
    sujos = [s for s in sujos if not s.startswith(".kaizen/")]  # estado do próprio kf (journal, checkpoint), não trabalho
    if sujos:
        lista = ", ".join(sujos[:5]) + (f" (+{len(sujos) - 5})" if len(sujos) > 5 else "")
        etiqueta = f"preflight-{_base(slug) if slug else 'wt'}-{time.strftime('%Y%m%d-%H%M%S')}"
        probs.append(Problema(
            "EC-060", "aviso", f"árvore suja em {path}: {lista}", "há alterações por commitar no arranque",
            f"commitar o trabalho, ou `git -C \"{path}\" stash push -u -m {etiqueta}` (corrigível com --fix)",
            fix=["git", "-C", path, "stash", "push", "-u", "-m", etiqueta]))
    if rp and ramo and ramo != rp:
        r = _git(path, "rev-list", "--count", f"HEAD..{rp}")
        n = int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else 0
        if n:
            probs.append(Problema(
                "EC-025", "aviso", f"ramo «{ramo}» está {n} commit(s) atrás de «{rp}»",
                "o ramo principal avançou depois de a worktree ser criada", f"git -C \"{path}\" merge {rp}"))
    return probs


# --- correção ------------------------------------------------------------------

def _sem_c(argv):
    resto, i = [], 1
    while i < len(argv):
        if argv[i] == "-C" and i + 1 < len(argv):
            i += 2
            continue
        resto.append(argv[i])
        i += 1
    return resto


def _fix_seguro(argv):
    """Só git, e só: `stash push` (guarda, não apaga), `worktree prune` (metadados de pastas já apagadas), `checkout <ramo>`."""
    if not argv or argv[0] != "git":
        return False
    r = _sem_c(argv)
    if r[:2] == ["stash", "push"]:
        return True
    if r == ["worktree", "prune"]:
        return True
    return len(r) == 2 and r[0] == "checkout" and not r[1].startswith("-")


def _perguntar(cmd):
    try:
        return input(f"Executar `{cmd}`? [s/N] ").strip().lower() in ("s", "sim", "y", "yes")
    except EOFError:  # EC-006: EOF vale não
        return False


def corrigir(problema, confirmar):
    """(rc, mensagem). Executa `problema.fix` só se for seguro E `confirmar()` disser sim."""
    if not problema.fix:
        return 1, f"{problema.ec}: sem correção automática; fazer à mão: {problema.proximo}"
    if not _fix_seguro(problema.fix):
        return 2, f"{problema.ec}: correção recusada (fora da lista segura): {' '.join(problema.fix)}"
    if not confirmar():
        return 1, f"{problema.ec}: não confirmado; {NADA}"
    r = run_hidden(problema.fix, capture_output=True, text=True, encoding="utf-8", errors="replace")
    kf_git.invalidar()
    saida = ((r.stdout or "") + (r.stderr or "")).strip()
    return (0, f"{problema.ec}: feito: {' '.join(problema.fix)}") if r.returncode == 0 else (1, f"{problema.ec}: falhou: {saida}")


# --- CLI -------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Pré-voo do kaizen-flow: git/worktree/ferramentas (kaizen preflight)")
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--repo", default=".", help="repo ou worktree (defeito: cwd)")
    ap.add_argument("--ramo", help="ramo esperado do SP (defeito: agent/<slug>)")
    ap.add_argument("--sem-orfao", action="store_true", help="não reportar o próprio SP como órfão (usado pelo kaizen resume)")
    ap.add_argument("--fix", action="store_true", help="executar as correções seguras, uma a uma, com confirmação")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    try:
        probs = diagnosticar(a.slug, a.repo, a.ramo, a.sem_orfao)
    except ErroUso as e:
        print(kf_erros.erro(e.ec, str(e), e.porque, NADA, e.proximo), file=sys.stderr)
        return 2
    probs.sort(key=lambda p: p.nivel != "erro")
    ms = int((time.perf_counter() - t0) * 1000)
    if a.json:
        print(json.dumps({"repo": str(a.repo), "slug": a.slug, "ms": ms, "problemas": [asdict(p) for p in probs]},
                         ensure_ascii=False, indent=1))
    elif not probs:
        print(f"pré-voo {a.repo}: limpo ({ms} ms)")
    else:
        erros = sum(p.nivel == "erro" for p in probs)
        print(f"pré-voo {a.repo}: {erros} erro(s), {len(probs) - erros} aviso(s) ({ms} ms)\n")
        print("\n\n".join(p.texto() for p in probs))
    if not a.fix or not probs:
        return 1 if probs else 0
    for p in probs:
        if p.fix:
            r, msg = corrigir(p, lambda p=p: _perguntar(" ".join(p.fix)))
            print(msg, file=sys.stderr if r else sys.stdout)
    kf_git.invalidar()
    restantes = diagnosticar(a.slug, a.repo, a.ramo, a.sem_orfao)
    return 1 if restantes else 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows em pipe: cp1252 parte os acentos no Node
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(kf_errlog.executar("sp-preflight", main))
