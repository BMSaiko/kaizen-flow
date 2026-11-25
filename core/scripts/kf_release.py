#!/usr/bin/env python3
"""Release assistida: automatiza o reversível (versão, CHANGELOG, PR com prova dos gates) e isola a decisão humana (tag).

Uso:
  python -I scripts/kf_release.py plan    [--repo DIR]                       # propõe versão e CHANGELOG; só leitura
  python -I scripts/kf_release.py prepare [--repo DIR] [--gate CMD]... [--data AAAA-MM-DD] [--base main]
  python -I scripts/kf_release.py publish [--repo DIR] --confirmo            # só com o humano: cria e empurra a tag vX.Y.Z

`plan`: bump semver pelos commits convencionais desde a última tag `v*` (`!`/BREAKING CHANGE = major, feat = minor, fix/perf = patch).
`prepare`: branch `agent/release-x-y-z`, bump do package.json, CHANGELOG `[Unreleased]` -> `[x.y.z]`, gates, commit, push e `gh pr create`
(nunca merge: o merge é do `pr_fechar.py`, só com CI verde). `--gate` repetível (defeito: npm test, ruff, audit, catalog).
`publish`: exige `--confirmo` (vindo do humano, mesmo em modo auto); só cria e empurra a tag (sem force, nunca reescreve tags);
o publish no npm continua pelo workflow `publish.yml` com provenance (nunca `npm publish` local).
rc: 0 ok, 1 gate vermelho, 2 nada a lançar, 3 sem `--confirmo`, 4 recusado (árvore suja, ramo, versão ou tag), 5 git/gh falhou, 64 uso
"""
import argparse
import datetime
import json
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from painel_backend import run_hidden  # noqa: E402

GATES = ("npm test", "python -m ruff check .", "node bin/kaizen.js audit", "node bin/kaizen.js catalog")
SEPARADOR = "\x1e"
CAMPO = "\x1f"
TIPO = re.compile(r"^(\w+)(\([^)]*\))?(!)?:\s*(.+)$")
SECCOES = {"feat": "Added", "fix": "Fixed", "perf": "Changed", "refactor": "Changed"}


class Recusa(Exception):
    """Recusa legítima (rc 4)."""


def git(repo, *args, check=True):
    p = run_hidden(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p


def gh(repo, *args):
    return run_hidden(["gh", *args], cwd=str(repo), capture_output=True, text=True, encoding="utf-8")


def calcular_bump(commits):
    """`commits` = [(assunto, corpo)]; devolve major|minor|patch ou None se nada justifica release."""
    nivel = None
    for assunto, corpo in commits:
        m = TIPO.match(assunto)
        tipo = m.group(1) if m else ""
        if (m and m.group(3)) or "BREAKING CHANGE" in corpo:
            return "major"
        if tipo == "feat":
            nivel = "minor"
        elif tipo in ("fix", "perf") and nivel is None:
            nivel = "patch"
    return nivel


def subir(versao, nivel):
    a, b, c = (int(x) for x in versao.split("."))
    return {"major": f"{a + 1}.0.0", "minor": f"{a}.{b + 1}.0", "patch": f"{a}.{b}.{c + 1}"}[nivel]


def _entradas(commits):
    por = {}
    for assunto, _ in commits:
        m = TIPO.match(assunto)
        if m and m.group(1) in SECCOES:
            por.setdefault(SECCOES[m.group(1)], []).append(m.group(4))
    return "".join(f"### {s}\n" + "".join(f"- {t}\n" for t in itens) + "\n" for s, itens in por.items())


def promover_changelog(texto, versao, data, commits):
    """`[Unreleased]` passa a `[versao] - data` e fica um `[Unreleased]` vazio; sem entradas usa os commits."""
    m = re.search(r"^## \[Unreleased\][ \t]*\n(.*?)(?=^## \[|\Z)", texto, re.S | re.M)
    if not m:
        raise Recusa("CHANGELOG sem secção `## [Unreleased]`")
    corpo = m.group(1).strip("\n")
    if not corpo.strip():
        corpo = _entradas(commits).strip("\n")
    if not corpo.strip():
        raise Recusa("CHANGELOG sem entradas e commits sem feat/fix")
    novo = f"## [Unreleased]\n\n## [{versao}] - {data}\n\n{corpo}\n\n"
    return texto[:m.start()] + novo + texto[m.end():]


def versao_atual(repo):
    return json.loads((Path(repo) / "package.json").read_text(encoding="utf-8"))["version"]


def ultima_tag(repo):
    p = git(repo, "describe", "--tags", "--abbrev=0", "--match", "v*", check=False)
    return p.stdout.strip() if p.returncode == 0 else ""


def commits_desde(repo, tag):
    intervalo = f"{tag}..HEAD" if tag else "HEAD"
    saida = git(repo, "log", intervalo, f"--format=%s{CAMPO}%b{SEPARADOR}").stdout
    return [tuple(x.strip("\n") for x in bloco.split(CAMPO, 1)) for bloco in saida.split(SEPARADOR) if bloco.strip()]


def planear(repo):
    """Devolve (versão atual, nova versão, commits) ou None se nada a lançar."""
    commits = commits_desde(repo, ultima_tag(repo))
    nivel = calcular_bump(commits)
    if not nivel:
        return None
    atual = versao_atual(repo)
    return atual, subir(atual, nivel), commits


def cmd_plan(a):
    p = planear(a.repo)
    if not p:
        print("nada a lançar: sem feat/fix/breaking desde a última tag")
        return 2
    atual, nova, commits = p
    data = a.data or datetime.date.today().isoformat()
    texto = (Path(a.repo) / "CHANGELOG.md").read_text(encoding="utf-8")
    try:
        cl = promover_changelog(texto, nova, data, commits)
    except Recusa as e:
        print(f"recusado: {e}")
        return 4
    print(f"versão: {atual} -> {nova} ({len(commits)} commits desde {ultima_tag(a.repo) or 'o início'})")
    print(cl[cl.index(f"## [{nova}]"):].split("\n## [", 1)[0].rstrip())
    return 0


def _correr_gates(repo, gates):
    linhas, ok = [], True
    for g in gates:
        p = run_hidden(shlex.split(g), cwd=str(repo), capture_output=True, text=True, encoding="utf-8")
        ok &= p.returncode == 0
        linhas.append(f"- `{g}` -> rc {p.returncode}")
    return ok, "\n".join(linhas)


def cmd_prepare(a):
    repo = Path(a.repo)
    if git(repo, "status", "--porcelain").stdout.strip():
        print("recusado: árvore de trabalho suja")
        return 4
    p = planear(repo)
    if not p:
        print("nada a lançar: sem feat/fix/breaking desde a última tag")
        return 2
    atual, nova, commits = p
    ramo = f"agent/release-{nova.replace('.', '-')}"
    data = a.data or datetime.date.today().isoformat()
    try:
        cl = promover_changelog((repo / "CHANGELOG.md").read_text(encoding="utf-8"), nova, data, commits)
    except Recusa as e:
        print(f"recusado: {e}")
        return 4
    git(repo, "switch", "-c", ramo)
    pkg = repo / "package.json"
    pkg.write_text(pkg.read_text(encoding="utf-8").replace(f'"version": "{atual}"', f'"version": "{nova}"', 1), encoding="utf-8")
    (repo / "CHANGELOG.md").write_text(cl, encoding="utf-8")
    ok, prova = _correr_gates(repo, a.gate or GATES)
    if not ok:
        print(f"gates vermelhos, sem PR (ramo {ramo} com as edições por commitar):\n{prova}")
        return 1
    git(repo, "add", "package.json", "CHANGELOG.md")
    git(repo, "commit", "-q", "-m", f"chore: release v{nova}")
    git(repo, "push", "-q", "-u", "origin", ramo)
    corpo = (f"## Release v{nova}\n\nBump {atual} -> {nova} e CHANGELOG pelos commits convencionais desde {ultima_tag(repo) or 'o início'}.\n\n"
             f"## Prova (gates)\n\n{prova}\n\n## Depois do merge\n\nTag e publish são decisão humana: `kf_release.py publish --confirmo`.\n")
    r = gh(repo, "pr", "create", "--base", a.base, "--head", ramo, "--title", f"chore: release v{nova}", "--body", corpo)
    if r.returncode != 0:
        print(f"gh pr create falhou: {r.stderr.strip()}")
        return 5
    print(f"PR aberto ({r.stdout.strip()}); merge só com CI verde (`pr_fechar.py`), sem tag")
    return 0


def _verificar_publish(repo, base):
    if git(repo, "status", "--porcelain").stdout.strip():
        raise Recusa("árvore de trabalho suja")
    if git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() != base:
        raise Recusa(f"tag só a partir de `{base}`")
    git(repo, "fetch", "-q", "origin", base)
    if git(repo, "rev-parse", "HEAD").stdout != git(repo, "rev-parse", f"origin/{base}").stdout:
        raise Recusa(f"`{base}` local difere de origin/{base}")
    tag = f"v{versao_atual(repo)}"
    if git(repo, "tag", "--list", tag).stdout.strip() or git(repo, "ls-remote", "--tags", "origin", f"refs/tags/{tag}").stdout.strip():
        raise Recusa(f"a tag {tag} já existe (nunca se reescreve)")
    if f"## [{tag[1:]}]" not in (Path(repo) / "CHANGELOG.md").read_text(encoding="utf-8"):
        raise Recusa(f"CHANGELOG sem secção [{tag[1:]}]")
    return tag


def cmd_publish(a):
    if not a.confirmo:
        print("recusado: tag e publish pedem confirmação humana explícita (`--confirmo`)")
        return 3
    try:
        tag = _verificar_publish(a.repo, a.base)
    except Recusa as e:
        print(f"recusado: {e}")
        return 4
    git(a.repo, "tag", "-a", tag, "-m", tag)
    git(a.repo, "push", "origin", f"refs/tags/{tag}")
    print(f"tag {tag} empurrada; o publish segue pelo workflow `publish.yml` (provenance)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sub", choices=("plan", "prepare", "publish"))
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default="main")
    ap.add_argument("--data")
    ap.add_argument("--gate", action="append")
    ap.add_argument("--confirmo", action="store_true")
    a = ap.parse_args(argv)
    try:
        return {"plan": cmd_plan, "prepare": cmd_prepare, "publish": cmd_publish}[a.sub](a)
    except (RuntimeError, OSError, KeyError, ValueError) as e:
        print(f"falhou: {e}")
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
