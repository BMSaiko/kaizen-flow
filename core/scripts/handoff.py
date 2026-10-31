#!/usr/bin/env python3
"""Apoio ao /handoff: passa uma conversa livre (sem SP) para uma sessão nova através de um ficheiro efémero.

O ficheiro vive em `<spRoot>/handoffs/<data>-<HHMM>-<slug>.md`. Só a sessão nova o
apaga, depois de o ler (`--consume`). Este script, ao escrever, só limpa `handoffs/*.md` com mais de 7 dias.
Nunca faz commit.

Uso:
  python -I scripts/handoff.py --write --slug <slug> --file <corpo.md>
  python -I scripts/handoff.py --launch <ficheiro> [--auto] [--dry-run]
  python -I scripts/handoff.py --consume <ficheiro>

`--launch` não abre janelas: em segundo plano, passados ~5 s, escreve `/clear` e depois o prompt de
continuação no painel do WezTerm onde o Claude Code já corre ($WEZTERM_PANE). `--auto` (usado após o
aviso do context-guard) recusa lançar se o ficheiro não existir em `handoffs/`.
"""
import argparse
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402
import handoff_pane as pane_lib  # noqa: E402
from handoff_pane import ENTER_GAP, SEND_DELAY, SEND_GAP, HandoffError  # noqa: E402
from sp_progresso import check_delta  # noqa: E402

_cfg = kaizen_engine.load("kaizen_config")

HANDOFFS_DIR = _cfg.sp_root(Path(__file__).resolve().parent.parent) / "handoffs"
MAX_AGE_DAYS = 7
DEFAULT_SLUG = "conversa"


def _slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return slug or DEFAULT_SLUG


def cleanup(folder, keep=None, max_age_days=MAX_AGE_DAYS, now=None):
    """Apaga só `*.md` diretamente em `folder` com mais de `max_age_days`; nunca `keep`."""
    cutoff = (now or time.time()) - max_age_days * 86400
    for f in Path(folder).glob("*.md"):
        if keep is not None and f.resolve() == Path(keep).resolve():
            continue
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def write(folder, body, slug, now=None):
    check_delta(body)
    now = now or datetime.now()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{now:%Y-%m-%d-%H%M}-{_slugify(slug)}.md"
    head = f"---\ntype: handoff\ncreated: {now:%Y-%m-%dT%H:%M:%S}\n---\n"
    text = f"{head}# Handoff {now:%Y-%m-%d %H:%M} ({_slugify(slug)})\n\n{body.replace(chr(13) + chr(10), chr(10)).strip(chr(10))}\n"
    path.write_bytes(text.encode("utf-8"))
    cleanup(folder, keep=path)
    return path


def _check(path):
    path = Path(path)
    if path.suffix != ".md" or path.parent.name != "handoffs":
        raise HandoffError(f"não é um ficheiro de handoff (esperado handoffs/*.md): {path}")
    if not path.is_file():
        raise HandoffError(f"o handoff não existe: {path}")
    return path


def consume(path, out=print):
    """Imprime o handoff e só depois o apaga (se imprimir falhar, o ficheiro fica)."""
    path = _check(path)
    out(path.read_bytes().decode("utf-8"))
    path.unlink()


def continuation_prompt(path):
    return (f'Continua a conversa anterior: corre `python -I scripts/handoff.py --consume "{path}"` '
            "(lê o handoff e só depois o apaga) e segue o Próximo passo.")


def send(text, pane, delay=SEND_DELAY, gap=SEND_GAP, enter_gap=ENTER_GAP, run=pane_lib.run_hidden, sleep=time.sleep,
         inspect=None):
    pane_lib.send_lines(["/clear", text], pane, pane_lib.send_argv, pane_lib.enter_argv, delay, gap, enter_gap, run, sleep, inspect)


def launch(path, pane=None):
    pane = pane or pane_lib.pane_id()
    pane_lib.send_argv(pane, continuation_prompt(path))
    pane_lib.pane_exists(pane)
    return pane_lib.launch_detached(__file__, ["--send", str(path), "--pane", str(pane)])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Apoio ao /handoff")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--launch", metavar="FICHEIRO")
    group.add_argument("--consume", metavar="FICHEIRO")
    group.add_argument("--send", metavar="FICHEIRO", help=argparse.SUPPRESS)
    ap.add_argument("--slug", default="", help="com --write: nome curto da conversa")
    ap.add_argument("--file", help="ficheiro com o corpo do handoff (com --write)")
    ap.add_argument("--pane", help="painel do WezTerm (default: $WEZTERM_PANE)")
    ap.add_argument("--dry-run", action="store_true", help="com --launch: só mostra os comandos")
    ap.add_argument("--auto", action="store_true", help="com --launch: modo do context-guard")
    ap.add_argument("--dir", default=str(HANDOFFS_DIR), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        if args.auto and not args.launch:
            raise HandoffError("--auto só com --launch")
        if args.write:
            if not args.file:
                raise HandoffError("--write exige --file")
            print(write(args.dir, Path(args.file).read_text(encoding="utf-8"), args.slug))
        elif args.consume:
            consume(args.consume)
        elif args.send:
            send(continuation_prompt(args.send), args.pane or pane_lib.pane_id(), inspect=pane_lib.check_prompt)
        else:
            if args.auto:
                _check(args.launch)
            if args.dry_run:
                pane = args.pane or pane_lib.pane_id()
                for text in ("/clear", continuation_prompt(args.launch)):
                    print(subprocess.list2cmdline(pane_lib.send_argv(pane, text)))
                    print(subprocess.list2cmdline(pane_lib.enter_argv(pane)))
            else:
                launch(args.launch, args.pane)
                print(f"a continuar neste painel em {SEND_DELAY:.0f}s: /clear e a leitura de {args.launch}")
    except (HandoffError, OSError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
