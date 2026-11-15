#!/usr/bin/env python3
"""Checkpoint e rollback seguro para o michi: reverte só o que mudou desde o checkpoint.

`save` regista o HEAD e o estado (hash + cópia) dos ficheiros sujos/não rastreados nesse momento.
`restore` leva cada ficheiro alterado desde então de volta ao estado do checkpoint (ou ao do HEAD se estava
limpo); ficheiros que já estavam sujos antes (trabalho do user) voltam ao estado sujo do checkpoint, e os
que o michi não tocou ficam como estão. Só caminhos explícitos (`git restore --source=HEAD -- <ficheiro>`
ou escrita da cópia); nunca `reset --hard`, `clean -f`, `add -A` nem stash. Apaga apenas ficheiros que
não existiam no checkpoint. Sem `--apply` o `restore` só mostra o plano. Recusa se o HEAD mudou.

Os checkpoints vivem fora do vault (defeito `~/.claude/michi-checkpoints/<slug>/`).

Uso:
  python -I scripts/michi-checkpoint.py save --slug S [--repo R] [--dir D]
  python -I scripts/michi-checkpoint.py restore --slug S [--n N] [--only f ...] [--apply]
  python -I scripts/michi-checkpoint.py list --slug S
rc: 0 ok, 1 erro de checkpoint
"""
import argparse
import hashlib
import json
import re
from pathlib import Path as _P
import sys as _s
_s.path.insert(0, str(_P(__file__).resolve().parent))
from painel_backend import run_hidden  # noqa: E402
import sys
from pathlib import Path

DEFAULT_DIR = Path.home() / ".claude" / "michi-checkpoints"
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class CheckpointError(Exception):
    pass


def _git(repo, *args, text=False):
    proc = run_hidden(["git", "-C", str(repo), "-c", "core.quotepath=off", *args], capture_output=True)
    if proc.returncode != 0:
        raise CheckpointError(f"git {args[0]} falhou: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout.decode("utf-8", "replace") if text else proc.stdout


def _head(repo):
    return _git(repo, "rev-parse", "HEAD", text=True).strip()


def _dirty(repo):
    """Caminhos (relativos, com /) sujos ou não rastreados; renomeações contam os dois lados."""
    parts = _git(repo, "status", "--porcelain=v1", "-z", "-uall").decode("utf-8", "replace").split("\0")
    paths, i = set(), 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.add(entry[3:])
        if entry[0] in "RC" or entry[1] in "RC":
            if i < len(parts) and parts[i]:
                paths.add(parts[i])
            i += 1
    return paths


def _sha(path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _slug_dir(store, slug):
    if not SLUG_RE.fullmatch(slug or ""):
        raise CheckpointError(f"slug inválido '{slug}'")
    return Path(store) / slug


def _inside(repo, rel):
    target = (Path(repo) / rel).resolve()
    if Path(repo).resolve() not in target.parents:
        raise CheckpointError(f"caminho fora do repo: {rel}")
    return target


def list_checkpoints(store, slug):
    base = _slug_dir(store, slug)
    out = []
    for f in sorted(base.glob("checkpoint-*.json"), key=lambda p: int(p.stem.rsplit("-", 1)[1])):
        out.append(json.loads(f.read_text(encoding="utf-8")))
    return out


def save(repo, store, slug):
    base = _slug_dir(store, slug)
    base.mkdir(parents=True, exist_ok=True)
    n = len(list_checkpoints(store, slug)) + 1
    blobs = base / f"blobs-{n}"
    files = {}
    for i, rel in enumerate(sorted(_dirty(repo))):
        src = Path(repo) / rel
        sha = _sha(src)
        entry = {"sha": sha}
        if sha is not None:
            blobs.mkdir(exist_ok=True)
            (blobs / str(i)).write_bytes(src.read_bytes())
            entry["blob"] = f"blobs-{n}/{i}"
        files[rel] = entry
    (base / f"checkpoint-{slug}-{n}.patch").write_bytes(_git(repo, "diff", "HEAD"))
    manifest = {"n": n, "slug": slug, "head": _head(repo), "files": files}
    (base / f"checkpoint-{slug}-{n}.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return n


def restore(repo, store, slug, n=None, only=None, apply=True):
    """Devolve os caminhos revertidos (ou a reverter, com `apply=False`)."""
    cps = list_checkpoints(store, slug)
    if not cps:
        raise CheckpointError(f"sem checkpoints para '{slug}'")
    cp = next((c for c in cps if c["n"] == n), None) if n else cps[-1]
    if cp is None:
        raise CheckpointError(f"checkpoint {n} não existe para '{slug}'")
    if _head(repo) != cp["head"]:
        raise CheckpointError("o HEAD mudou desde o checkpoint; rollback manual")
    base = _slug_dir(store, slug)
    candidates = set(_dirty(repo)) | set(cp["files"])
    if only:
        wanted = {Path(p).as_posix() for p in only}
        for rel in wanted:
            _inside(repo, rel)
        candidates &= wanted
    done = []
    for rel in sorted(candidates):
        target = _inside(repo, rel)
        saved = cp["files"].get(rel)
        if saved is not None and saved["sha"] is not None:
            if _sha(target) == saved["sha"]:
                continue
            if apply:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((base / saved["blob"]).read_bytes())
        else:
            in_head = bool(_git(repo, "ls-tree", "HEAD", "--", rel, text=True).strip())
            if saved is not None and saved["sha"] is None:  # já estava apagado no checkpoint
                if not target.exists():
                    continue
                if apply:
                    target.unlink()
            elif in_head:  # estava limpo: volta ao HEAD
                if apply:
                    _git(repo, "restore", "--source=HEAD", "--staged", "--worktree", "--", rel)
            else:  # não existia: foi criado depois
                if not target.exists():
                    continue
                if apply:
                    target.unlink()
        done.append(rel)
    return done


def main(argv=None):
    ap = argparse.ArgumentParser(description="Checkpoint/rollback seguro do michi")
    ap.add_argument("cmd", choices=("save", "restore", "list"))
    ap.add_argument("--slug", required=True)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--dir", default=str(DEFAULT_DIR))
    ap.add_argument("--n", type=int)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--apply", action="store_true", help="restore: aplicar (defeito: só mostrar o plano)")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "save":
            n = save(args.repo, args.dir, args.slug)
            print(f"checkpoint {n} guardado em {_slug_dir(args.dir, args.slug)}")
        elif args.cmd == "list":
            for c in list_checkpoints(args.dir, args.slug):
                print(f"{c['n']}  HEAD {c['head'][:9]}  {len(c['files'])} ficheiros sujos")
        else:
            done = restore(args.repo, args.dir, args.slug, args.n, args.only, args.apply)
            verb = "revertidos" if args.apply else "a reverter (use --apply)"
            print(f"{len(done)} {verb}" + "".join(f"\n- {p}" for p in done))
    except CheckpointError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
