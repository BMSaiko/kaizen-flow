#!/usr/bin/env python3
"""Report da fase 10 do michi, montado só com fontes duráveis do SP. Não faz commit.

Secções fixas: Alterado · Verificado · Provas · Dificuldades · Em aberto.
- Alterado: `git diff --stat` contra a base (por omissão `master`); num SP de repo externo (gate com
  `cwd` num repo git fora do vault) usa esse repo e a base `main`/`master` dele.
- Verificado: comandos de `gates:`; o RC vem de `--gates` (corre-os) e, sem isso, fica «não corrido».
- Provas: `## Prova` do SP (inclui `## Prova de done`).
- Dificuldades: causas das linhas `Reflect <fase>:` (obrigatória; vazia = aviso e rc 3).
- Em aberto: critérios `- [ ]` por cumprir.

Uso: python -I scripts/sp-report.py <slug|caminho.md> [--base master] [--gates] [--project P]
rc: 0 ok, 1 erro, 3 secção «Dificuldades» vazia
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path as _P
import sys as _s
_s.path.insert(0, str(_P(__file__).resolve().parent))
from painel_backend import run_hidden  # noqa: E402
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kf_git  # noqa: E402
import sp_leitura  # noqa: E402
from sp_carregar import carregar  # noqa: E402
SEM_PATCH = re.compile(r"^(?:[-*]\s*)?Reflect\s+[^:]*:\s*sem patch\.?\s*$", re.I)
LINHA = re.compile(r"^(?:[-*]\s*)?Reflect\b[^:\n]*:\s*\S", re.I)


def _load(name: str, filename: str):
    return carregar(HERE / filename, name, fresco=True)


def section(text: str, prefix: str) -> str:
    return sp_leitura.seccao(text, prefix)


def dificuldades(text: str) -> list[str]:
    """Linhas `Reflect <fase>: ...` com causa (exclui «sem patch» puro)."""
    out = []
    for linha in section(text, "Reflect").splitlines():
        s = linha.strip()
        if LINHA.match(s) and not SEM_PATCH.match(s):
            out.append(s.lstrip("-* ").strip())
    return out


def dificuldades_ok(text: str) -> bool:
    return bool(dificuldades(text))


def _bullets(linhas: list[str], vazio: str) -> str:
    return "\n".join(f"- {l}" for l in linhas) if linhas else f"- {vazio}"


def aviso_atraso(atras: int, base: str = "master") -> str:
    if atras <= 0:
        return ""
    return f"AVISO: a worktree está {atras} commit(s) atrás de {base}; o diff pode mostrar remoções que não são deste SP (fazer rebase/merge de {base}).\n"


def _atras(base: str, cwd) -> int:
    r = kf_git.run(cwd or ".", "rev-list", "--count", f"HEAD..{base}", run=run_hidden)
    return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else 0


def gerar(text: str, slug: str, diff_stat: list[str] | None = None, gates: list[dict] | None = None, atras: int = 0,
          repo: str | None = None) -> str:
    sp_gates = _load("sp_gates_report", "sp-gates.py")
    rc_por_cmd = {g["cmd"]: g for g in (gates or [])}
    verificado = []
    for g in sp_gates.parse_gates(text):
        r = rc_por_cmd.get(g["cmd"])
        rc = "não corrido" if r is None else ("timeout" if r.get("timeout") else r["rc"])
        verificado.append(f"`{g['cmd']}` rc={rc}")
    provas = [l.strip().lstrip("-* ").strip() for l in section(text, "Prova").splitlines() if l.strip()]
    abertos = [m.strip() for m in re.findall(r"^- \[ \]\s*(.+)$", section(text, "4."), re.M)]
    dif = dificuldades(text)
    partes = [
        f"# Report — {slug}",
        "## Alterado\n" + (f"repo: {repo}\n" if repo else "") + aviso_atraso(atras) + ("\n".join(f"    {l}" for l in diff_stat) if diff_stat else "- sem diff contra a base"),
        "## Verificado\n" + _bullets(verificado, "sem gates no frontmatter"),
        "## Provas\n" + _bullets(provas, "sem `## Prova` no SP"),
        "## Dificuldades\n" + (_bullets(dif, "") if dif else "- SEM DIFICULDADES REGISTADAS: escrever «nenhuma» com a justificação ou correr `/reflect fase`"),
        "## Em aberto\n" + _bullets(abertos, "nada"),
    ]
    return "\n\n".join(partes) + "\n"


def _git_stat(base: str, cwd=None, desde_merge_base: bool = False) -> list[str]:
    """`git diff --stat <base>` (inclui a árvore de trabalho); repo externo: `<base>...HEAD`, só os commits do ramo."""
    ref = f"{base}...HEAD" if desde_merge_base else base
    r = kf_git.run(cwd or HERE.parent, "diff", "--stat", ref, run=run_hidden)
    return r.stdout.splitlines() if r.returncode == 0 else []


def _git_linha(cwd, *args) -> str:
    r = kf_git.run(cwd, *args, run=run_hidden)
    return r.stdout.strip() if r.returncode == 0 else ""


def _comum(cwd) -> Path | None:
    """Pasta `.git` comum (igual para o checkout principal e todas as worktrees do mesmo repo)."""
    d = _git_linha(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(d).resolve() if d else None


def repo_alvo(gates: list[dict], vault) -> Path | None:
    """Raiz git do primeiro gate com `cwd` absoluto noutro repo (SP de repo externo); None se não há.
    Checkout principal e worktrees do vault não contam (mesmo `--git-common-dir`)."""
    vault_comum = _comum(vault)
    for g in gates:
        cwd = Path(g.get("cwd") or ".")
        if not cwd.is_absolute() or not cwd.is_dir():
            continue
        top, comum = _git_linha(cwd, "rev-parse", "--show-toplevel"), _comum(cwd)
        if top and comum and comum != vault_comum:
            return Path(top).resolve()
    return None


def resolver(ref: str, project: str | None, roots, sp_list) -> tuple[Path | None, str, Path | None]:
    """(caminho, slug, raiz) do SP; caminho None e o motivo em `slug` se não encontrado ou ambíguo."""
    p = Path(ref)
    if p.suffix == ".md":
        if not p.is_file():
            return None, f"SP não encontrado: {ref}", None
        return p, sp_list.parse_frontmatter(p.read_text(encoding="utf-8")).get("slug") or p.stem, HERE.parent
    for root in roots:
        achados = sp_list.encontrar(sp_list.collect(sp_list.default_root(Path(root)), include_done=True), ref, project)
        if len(achados) > 1:
            return None, f"SP ambíguo: {ref} ({', '.join(s.slug for s in achados)}); usar o slug completo ou --project", None
        if achados:
            return achados[0].path, achados[0].slug, Path(root)
    return None, f"SP não encontrado: {ref}", None


def base_de(repo, pedida: str | None) -> str:
    """`pedida` se dada; senão `main` ou `master` (a primeira que existe no repo)."""
    if pedida:
        return pedida
    for b in ("main", "master"):
        if kf_git.run(repo, "rev-parse", "--verify", "-q", b, run=run_hidden).returncode == 0:
            return b
    return "master"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Report da fase 10 do michi")
    ap.add_argument("sp", help="slug ou caminho .md")
    ap.add_argument("--base", help="base do diff (defeito: master; repo externo: main/master dele)")
    ap.add_argument("--gates", action="store_true", help="corre os gates do SP para registar o RC")
    ap.add_argument("--project")
    a = ap.parse_args(argv)
    sp_gates = _load("sp_gates_run", "sp-gates.py")
    sp_list = _load("sp_list_report", "sp-list.py")
    roots = [] if Path(a.sp).suffix == ".md" else sp_gates.sp_roots(a.sp)
    caminho, slug, raiz = resolver(a.sp, a.project, roots, sp_list)
    if caminho is None:
        print(slug)
        return 1
    text = caminho.read_text(encoding="utf-8")
    res = None
    if a.gates:
        res = sp_gates.run(sp_gates.parse_gates(text))
    ext = repo_alvo(sp_gates.parse_gates(text), HERE.parent)
    if ext:
        base = base_de(ext, a.base)
        print(gerar(text, slug, _git_stat(base, ext, desde_merge_base=True), res, 0, f"{ext} (base {base}...HEAD)"))
    else:
        base = a.base or "master"
        print(gerar(text, slug, _git_stat(base, raiz), res, _atras(base, raiz)))
    return 0 if dificuldades_ok(text) else 3


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-report", main))
