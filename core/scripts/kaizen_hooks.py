"""Hooks do kaizen: corre os comandos de `kaizen-hooks.json` quando um evento do michi/SP dispara.

Bloqueantes correm na fase `pre` (rc≠0 ou timeout aborta); informativos na `post` (falha só avisa).
O comando vem só do ficheiro de config, nunca do SP. Contexto: env KAIZEN_* e JSON no stdin.
Uso: python -I scripts/kaizen_hooks.py fire <evento> --slug S --project P [--de X --para Y]
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_config  # noqa: E402

LOG = Path.home() / ".claude" / "kaizen-hooks.log"


class HookBlocked(Exception):
    pass


def default_repo():
    return Path(os.environ.get("KAIZEN_REPO") or Path(__file__).resolve().parent.parent)


def _log(line):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} {line}\n")
    except OSError:
        pass


def _matches(cond, ctx):
    return all(str(ctx.get(k)) == str(v) for k, v in cond.items())


def fire(event, ctx, repo=None, phase="all"):
    """Devolve avisos (lista de str); levanta HookBlocked se um bloqueante falhar."""
    repo = Path(repo) if repo else default_repo()
    ctx = {k: v for k, v in ctx.items() if v is not None}
    env = {**os.environ, "KAIZEN_EVENT": event}
    for k, v in ctx.items():
        env[f"KAIZEN_{k.upper()}"] = str(v)
    payload = json.dumps({"event": event, **ctx}, ensure_ascii=False)
    warnings = []
    for h in kaizen_config.hooks(repo):
        blocking = h["modo"] == "bloqueante"
        if h["event"] != event or not _matches(h["if"], ctx):
            continue
        if phase != "all" and (phase == "pre") != blocking:
            continue
        try:
            r = subprocess.run(h["cmd"], shell=True, cwd=repo, env=env, input=payload, text=True,
                               capture_output=True, timeout=h["timeout"])
            ok, detail = r.returncode == 0, f"rc={r.returncode} {(r.stderr or r.stdout).strip()[:200]}"
        except subprocess.TimeoutExpired:
            ok, detail = False, f"timeout {h['timeout']}s"
        except OSError as exc:
            ok, detail = False, str(exc)
        _log(f"{event} {h['modo']} {'ok' if ok else 'FALHOU'} {h['cmd']!r} {detail}")
        if not ok:
            msg = f"hook {h['modo']} falhou em {event}: {h['cmd']} ({detail})"
            if blocking:
                raise HookBlocked(msg)
            warnings.append(msg)
    return warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fire")
    f.add_argument("event")
    f.add_argument("--slug")
    f.add_argument("--project")
    f.add_argument("--de")
    f.add_argument("--para")
    f.add_argument("--path")
    f.add_argument("--phase", choices=("all", "pre", "post"), default="all")
    a = ap.parse_args(argv)
    ctx = {"slug": a.slug, "project": a.project, "de": a.de, "para": a.para, "path": a.path}
    try:
        for w in fire(a.event, ctx, phase=a.phase):
            print(f"aviso: {w}", file=sys.stderr)
    except HookBlocked as exc:
        print(f"bloqueado: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
