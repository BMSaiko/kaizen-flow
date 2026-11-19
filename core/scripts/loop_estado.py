#!/usr/bin/env python3
"""Estado persistente dos loops de manutenção (`/ronda`, `/manutencao`), para sobreviver a `/handoff` e `/clear`.

Um ficheiro por loop em `~/.claude/loops/<skill>.json` (ou `$SB_LOOPS_DIR`): `fim` (epoch), permissões do grill,
última ação, alvos e ações. Estado com `fim` passado conta como inativo. O handoff e o hook de retoma leem-no
para a sessão nova continuar o loop sem novo grill nem perguntas.

Uso:
  python -I scripts/loop_estado.py set <skill> --fim <epoch|HH:MM|Nh|Nm> [--perm "..."] [--acao X] [--alvos "..."] [--acoes "a,b"]
  python -I scripts/loop_estado.py get <skill>
  python -I scripts/loop_estado.py clear <skill>
  python -I scripts/loop_estado.py ativos
rc: 0 ok, 1 erro (get sem estado ativo = 1)
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

SKILL_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def base_dir(base=None):
    return Path(base or os.environ.get("SB_LOOPS_DIR") or Path.home() / ".claude" / "loops")


def _path(skill, base=None):
    if not SKILL_RE.match(skill or ""):
        raise ValueError(f"nome de loop inválido: {skill!r}")
    return base_dir(base) / f"{skill}.json"


def parse_fim(texto, now=None):
    """`fim` como epoch: número, `HH:MM` (hoje, ou amanhã se já passou), `Nh` ou `Nm` (duração)."""
    now = now or time.time()
    t = str(texto).strip().lower()
    if re.fullmatch(r"\d{9,}", t):
        return int(t)
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([hm])", t)
    if m:
        return int(now + float(m.group(1)) * (3600 if m.group(2) == "h" else 60))
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", t)
    if m:
        agora = datetime.fromtimestamp(now)
        alvo = agora.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if alvo <= agora:
            alvo += timedelta(days=1)
        return int(alvo.timestamp())
    raise ValueError(f"fim inválido: {texto!r}")


def set_estado(skill, fim, base=None, **campos):
    """Grava o estado (atómico); `fim` em epoch. Campos extra ficam como estão (None é ignorado)."""
    path = _path(skill, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    dados = {"skill": skill, "fim": int(fim)}
    dados.update({k: v for k, v in campos.items() if v not in (None, "")})
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(dados, fh, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return dados


def get_estado(skill, base=None, now=None):
    """Estado ativo do loop (dict) ou None se não existe, está corrompido ou o `fim` já passou."""
    try:
        dados = json.loads(_path(skill, base).read_text(encoding="utf-8"))
        fim = int(dados["fim"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return dados if fim > (now or time.time()) else None


def clear(skill, base=None):
    _path(skill, base).unlink(missing_ok=True)


def ativos(base=None, now=None):
    """Estados ativos, por nome. Nunca levanta (corrompidos e expirados ficam de fora)."""
    pasta = base_dir(base)
    if not pasta.is_dir():
        return []
    found = []
    for f in sorted(pasta.glob("*.json")):
        dados = get_estado(f.stem, base, now) if SKILL_RE.match(f.stem) else None
        if dados:
            found.append(dados)
    return found


def _hora(epoch):
    return datetime.fromtimestamp(epoch).strftime("%H:%M")


def bloco_handoff(base=None, now=None):
    """Bloco `## Loops ativos` para o fim do handoff; "" sem loops ativos."""
    est = ativos(base, now)
    if not est:
        return ""
    linhas = ["## Loops ativos"]
    for d in est:
        partes = [f"/{d['skill']} até {_hora(d['fim'])} (fim={d['fim']})"]
        for rotulo, chave in (("permissões", "perm"), ("última ação", "acao"), ("alvos", "alvos"), ("ações", "acoes")):
            if d.get(chave):
                partes.append(f"{rotulo}: {d[chave]}")
        linhas.append("- " + "; ".join(partes))
    linhas.append("Retomar: `python -I scripts/loop_estado.py get <loop>`; reutilizar permissões, sem grill nem perguntas.")
    return "\n".join(linhas)


def ordem_retoma(base=None, now=None):
    """Texto para o hook de retoma injetar na sessão nova; "" sem loops ativos."""
    est = ativos(base, now)
    if not est:
        return ""
    nomes = ", ".join(f"/{d['skill']} (até {_hora(d['fim'])})" for d in est)
    return (f"[loop] Loop ativo interrompido por /clear: {nomes}. Retoma-o já: `python -I scripts/loop_estado.py get <loop>` "
            "dá fim, permissões, última ação e alvos; segue o ciclo da skill a partir da ação seguinte, sem novo grill, "
            "sem AskUserQuestion, e re-arma `ScheduleWakeup` 60 s enquanto agora < fim. Ao terminar: `loop_estado.py clear <loop>`.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Estado persistente dos loops de manutenção")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set")
    s.add_argument("skill")
    s.add_argument("--fim", required=True)
    for nome in ("perm", "acao", "alvos", "acoes"):
        s.add_argument(f"--{nome}")
    for nome in ("get", "clear"):
        sub.add_parser(nome).add_argument("skill")
    sub.add_parser("ativos")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "set":
            dados = set_estado(args.skill, parse_fim(args.fim), perm=args.perm, acao=args.acao,
                               alvos=args.alvos, acoes=args.acoes)
            print(json.dumps(dados, ensure_ascii=False))
        elif args.cmd == "get":
            dados = get_estado(args.skill)
            if not dados:
                print(f"sem estado ativo: {args.skill}", file=sys.stderr)
                return 1
            print(json.dumps(dados, ensure_ascii=False))
        elif args.cmd == "clear":
            clear(args.skill)
        else:
            for d in ativos():
                print(json.dumps(d, ensure_ascii=False))
    except (ValueError, OSError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
