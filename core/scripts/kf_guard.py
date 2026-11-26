"""Guarda dos casos indesejados: bloqueia, com a razão, o que o agente não deve fazer sozinho.

Casos: alterar ficheiros protegidos (`protectedFiles` em kaizen.config.json), ler segredos, force-push,
`--admin`, merge com CI não verde, tag/publish fora de `kf_release.py publish --confirmo`, escrever fora do repo.
Override só para ficheiros protegidos: env `KAIZEN_ALLOW_PROTECTED=<razão>`; fica registado em `~/.claude/kaizen-guard.log`.

Uso: hook PreToolUse (JSON no stdin, sem argumentos) · `python -I scripts/kf_guard.py diff [--base REF] [--repo DIR]`
rc: 0 permitido, 2 bloqueado (razão no stderr; no `diff`, 1)
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collections.abc import Callable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_config  # noqa: E402

LOG = Path.home() / ".claude" / "kaizen-guard.log"
SEGREDOS = re.compile(r"(^|/)(\.env(\..*)?|.*\.(key|pem|p12|pfx)|id_rsa.*|secrets\..*|\.secrets.*)$")
LEITORES = {"cat", "less", "more", "head", "tail", "bat", "grep", "rg", "sed", "awk", "cp", "xxd", "base64", "strings", "source", "."}


def _log(linha: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} {linha}\n")
    except OSError:
        pass


def e_segredo(caminho: object) -> bool:
    return bool(SEGREDOS.search(str(caminho).replace("\\", "/")))


def _rel(caminho: str, repo: str | Path) -> str | None:
    try:
        return Path(os.path.abspath(Path(repo) / caminho)).relative_to(os.path.abspath(repo)).as_posix()
    except ValueError:
        return None


def e_protegido(caminho: str, repo: str | Path) -> bool:
    rel = _rel(caminho, repo)
    return rel is not None and rel in kaizen_config.protected_files(repo)


def _dentro(caminho: str, repo: str | Path) -> bool:
    p = os.path.realpath(Path(repo) / caminho)
    bases = [os.path.realpath(repo), os.path.realpath(tempfile.gettempdir())]
    return any(p == b or p.startswith(b + os.sep) for b in bases)


def ci_verde(repo: str | Path) -> bool:
    """True só com todos os checks do PR atual a passar; sem `gh` ou erro = não verde."""
    try:
        r = subprocess.run(["gh", "pr", "checks", "--json", "state"], cwd=repo, capture_output=True, text=True, timeout=60)
        estados = [c.get("state") for c in json.loads(r.stdout or "[]")]
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and bool(estados) and all(e in ("SUCCESS", "SKIPPED") for e in estados)


def _segmentos(cmd: str) -> list[list[str]]:
    try:
        toks = shlex.split(cmd, posix=True)
    except ValueError:
        toks = cmd.split()
    segs: list[list[str]] = [[]]
    for t in toks:
        if t in ("&&", "||", ";", "|"):
            segs.append([])
        else:
            segs[-1].append(t)
    return [s for s in segs if s]


def _force(a: str) -> bool:
    return a.startswith("--force") or a == "-f" or bool(re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", a))


def _git(s: list[str]) -> str | None:
    sub = next((a for i, a in enumerate(s[1:], 1) if not a.startswith("-") and s[i - 1] not in ("-C", "-c")), "")
    if sub == "push" and any(_force(a) for a in s):
        return "force-push é proibido"
    if sub == "push" and any(a.startswith("+") or a in ("--tags", "--follow-tags") for a in s[2:]):
        return "push forçado/de tags é proibido (tag só por `kf_release.py publish --confirmo`)"
    if sub == "tag" and not any(a in ("-l", "--list", "-d", "--delete", "-v", "--verify") for a in s):
        return "criar tag é decisão humana (`kf_release.py publish --confirmo`)"
    return None


def _gh(s: list[str], repo: str | Path, ci: Callable[[str | Path], bool]) -> str | None:
    if "--admin" in s:
        return "`--admin` ignora as proteções do ramo: proibido"
    if s[1:3] == ["pr", "merge"] and not ci(repo):
        return "merge só com o CI verde (checks por passar ou a falhar)"
    if s[1:3] == ["release", "create"]:
        return "release/tag é decisão humana"
    return None


def _segmento(s: list[str], repo: str | Path, ci: Callable[[str | Path], bool]) -> str | None:
    nome = Path(s[0]).name
    if nome in LEITORES and any(e_segredo(a) for a in s[1:] if not a.startswith("-")):
        return "ler segredos (.env, chaves, certificados) é proibido"
    if nome in ("npm", "pnpm", "yarn") and "publish" in s[1:3]:
        return "publish é decisão humana (workflow `publish.yml` com provenance)"
    if nome == "git":
        return _git(s)
    if nome == "gh":
        return _gh(s, repo, ci)
    return None


def _bash(cmd: str, repo: str | Path, ci: Callable[[str | Path], bool]) -> str | None:
    return next((r for r in (_segmento(s, repo, ci) for s in _segmentos(cmd)) if r), None)


def avaliar(tool: str, tool_input: dict[str, Any], repo: str | Path, env: Mapping[str, str] | None = None,
            ci: Callable[[str | Path], bool] = ci_verde) -> str | None:
    """Devolve a razão do bloqueio ou None se permitido."""
    env = os.environ if env is None else env
    if tool == "Bash":
        return _bash(str(tool_input.get("command", "")), repo, ci)
    alvo = tool_input.get("file_path") or tool_input.get("notebook_path") or tool_input.get("path")
    if not alvo:
        return None
    if e_segredo(alvo):
        return f"{alvo}: segredos nunca passam pelo agente"
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        if not _dentro(alvo, repo):
            return f"{alvo}: escrita fora do repo/worktree"
        if e_protegido(alvo, repo):
            razao = (env.get("KAIZEN_ALLOW_PROTECTED") or "").strip()
            if not razao:
                return f"{alvo} é ficheiro de contexto protegido: só com pedido explícito (KAIZEN_ALLOW_PROTECTED=<razão>)"
            _log(f"override {alvo}: {razao}")
    return None


def alterados_protegidos(repo: str | Path, base: str = "origin/main") -> list[str]:
    """Ficheiros protegidos alterados no diff face à base (só leitura)."""
    r = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        r = subprocess.run(["git", "diff", "--name-only", base], cwd=repo, capture_output=True, text=True)
    prot = set(kaizen_config.protected_files(repo))
    return sorted(f for f in r.stdout.split() if f in prot)


def cmd_diff(repo: str | Path, base: str, env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    tocados = alterados_protegidos(repo, base)
    if not tocados:
        return 0
    razao = (env.get("KAIZEN_ALLOW_PROTECTED") or "").strip()
    if razao:
        _log(f"override diff {', '.join(tocados)}: {razao}")
        return 0
    print(f"ficheiros protegidos alterados sem autorização: {', '.join(tocados)} (KAIZEN_ALLOW_PROTECTED=<razão>)", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["diff"]:
        repo, base = ".", "origin/main"
        for i, a in enumerate(argv):
            if a == "--repo" and i + 1 < len(argv):
                repo = argv[i + 1]
            if a == "--base" and i + 1 < len(argv):
                base = argv[i + 1]
        return cmd_diff(repo, base)
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(data, dict):
        return 0
    repo = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    razao = avaliar(data.get("tool_name", ""), data.get("tool_input") or {}, repo)
    if razao:
        print(f"kf_guard: bloqueado — {razao}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
