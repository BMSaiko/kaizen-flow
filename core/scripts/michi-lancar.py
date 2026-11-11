"""Plano de lançamento do michi num sub-agent `Agent` (sessão principal): worktree, SP para Doing nela e item JSON.

Reutiliza `sp_fila_subagents.lancar` (worktree + prompt) e `item_agent` (modelo do `michi_modelo` do SP, `effort: low`).
O principal chama `Agent` com o item, termina o turno sem polling e trata a última linha `ESTADO:` (michi-orquestracao §Sub-agentes).

Uso: python -I scripts/michi-lancar.py <slug> [--root R]
rc: 0 ok (uma linha JSON), 1 SP inexistente ou erro
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_fila_subagents as sfs  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
_RUN = subprocess.run


def existe(slug, root):
    return any((Path(root) / "knowledge" / "projects").glob(f"*/*/sp/*/{slug}.md"))


def plano_sp(slug, root, run=None):
    """Item do `Agent` para `slug`: worktree (ensure), `sp-move.py --start` dentro dela (o checkout principal fica intacto),
    prompt, model e `effort: low`; RuntimeError se falhar."""
    run = run or _RUN
    item = sfs.lancar(slug, run=run, root=root)
    wt = Path(item["worktree"])
    r = run([sys.executable, "-I", str(wt / "scripts" / "sp-move.py"), slug, "--start"], capture_output=True, text=True,
            encoding="utf-8", cwd=str(wt))
    if r.returncode != 0:
        raise RuntimeError(f"sp-move --start {slug}: {(r.stderr or r.stdout or '').strip()}")
    return sfs.item_agent(item, description=slug)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slug")
    ap.add_argument("--root", default=str(SCRIPTS.parent))
    a = ap.parse_args(argv)
    if not existe(a.slug, a.root):
        print(f"SP não encontrado: {a.slug}", file=sys.stderr)
        return 1
    try:
        print(json.dumps(plano_sp(a.slug, a.root)))  # ASCII: stdout cp1252 no Windows
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
