#!/usr/bin/env python3
"""Estado persistente dos loops de manutenção (`/ronda`, `/manutencao`), para sobreviver a `/handoff` e `/clear`.

Um ficheiro por loop em `~/.claude/loops/<skill>.json` (ou `$SB_LOOPS_DIR`): `fim` (epoch), permissões do grill,
última ação, alvos e ações. Estado com `fim` passado conta como inativo. O handoff e o hook de retoma leem-no
para a sessão nova continuar o loop sem novo grill nem perguntas.

Dono: o `set` da CLI grava `sessao` (`CLAUDE_CODE_SESSION_ID`) e `pid` (`CLAUDE_PID`, o processo do Claude Code,
que sobrevive ao `/clear`). Os hooks só aplicam o regime de loop na sessão dona (`ativos(session_id=...)`);
estado sem dono não afeta ninguém. `adotar` passa a posse à sessão atual.

Uso:
  python -I scripts/loop_estado.py set <skill> --fim <epoch|HH:MM|Nh|Nm> [--perm "..."] [--acao X] [--alvos "..."] [--acoes "a,b"]
  python -I scripts/loop_estado.py get <skill>
  python -I scripts/loop_estado.py clear <skill>
  python -I scripts/loop_estado.py ativos
  python -I scripts/loop_estado.py adotar <skill>           # a sessão atual passa a dona do loop
  python -I scripts/loop_estado.py log <skill> "linha"      # uma linha por volta (sobrevive ao clear)
  python -I scripts/loop_estado.py tentativa <skill> <chave> # conta tentativas de um erro; rc 1 acima do teto (5)
  python -I scripts/loop_estado.py lock|unlock <skill> <repo> # um loop por repo; lock rc 1 se outro loop ativo o tem
rc: 0 ok, 1 erro (get sem estado ativo = 1)
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time
from typing import Any
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
    t = re.sub(r"^at[eé]\s+[aà]s\s+", "", str(texto).strip().lower())
    if re.fullmatch(r"\d{1,2}", t) and "até" in str(texto).lower() or re.fullmatch(r"\d{1,2}", t) and "ate" in str(texto).lower():
        t = f"{t}:00"  # «até às 10» = 10:00
    t = re.sub(r"^(\d{1,2})h(\d{2})$", r"\1:\2", t)  # 10h30 = 10:30
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


TODOS = object()  # sentinela: `ativos` sem filtro de dono


def _pids_ancestrais(pid=None):
    """PIDs do processo atual e dos ancestrais (Linux, /proc); fora de Linux só o próprio e o pai."""
    pids, atual = [], pid or os.getpid()
    for _ in range(64):
        pids.append(atual)
        try:
            stat = Path(f"/proc/{atual}/stat").read_text(encoding="utf-8")
            atual = int(stat.rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            if len(pids) == 1:
                pids.append(os.getppid())
            break
        if atual <= 1:
            break
    return pids


def e_dono(dados, session_id=None, pids=None):
    """True se a sessão (`session_id`) ou um processo ancestral (`pid` do Claude Code) é dono do loop."""
    if dados.get("sessao") and session_id and str(session_id) == str(dados["sessao"]):
        return True
    try:
        pid = int(dados.get("pid") or 0)
    except (TypeError, ValueError):
        return False
    return pid > 1 and pid in (pids if pids is not None else _pids_ancestrais())


def dono_do_env(env=None):
    """`sessao` e `pid` da sessão atual, lidos do ambiente que o Claude Code dá aos subprocessos."""
    env = os.environ if env is None else env
    campos = {"sessao": env.get("CLAUDE_CODE_SESSION_ID") or None, "pid": None}
    if str(env.get("CLAUDE_PID", "")).isdigit():
        campos["pid"] = int(env["CLAUDE_PID"])
    return campos


def clear(skill, base=None):
    _path(skill, base).unlink(missing_ok=True)


def ativos(base=None, now=None, session_id=TODOS):
    """Estados ativos, por nome. Com `session_id` só os da sessão dona (`e_dono`). Nunca levanta."""
    pasta = base_dir(base)
    if not pasta.is_dir():
        return []
    found = []
    for f in sorted(pasta.glob("*.json")):
        dados = get_estado(f.stem, base, now) if SKILL_RE.match(f.stem) else None
        if dados and (session_id is TODOS or e_dono(dados, session_id)):
            found.append(dados)
    return found


TETO_TENTATIVAS = 5


def _sub(nome, base=None):
    pasta = base_dir(base) / nome
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def log(skill, linha, base=None):
    """Acrescenta uma linha (com hora) ao log do loop; usado no relatório final e na retoma."""
    _path(skill, base)  # valida o nome
    with open(_sub("logs", base) / f"{skill}.log", "a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now().strftime('%H:%M')} {linha}\n")


def ler_log(skill, base=None):
    try:
        return (base_dir(base) / "logs" / f"{skill}.log").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def tentativa(skill, chave, base=None):
    """Regista mais uma tentativa de corrigir `chave`; devolve o total."""
    _path(skill, base)
    f = _sub("tentativas", base) / f"{skill}.json"
    try:
        dados = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    dados[chave] = int(dados.get(chave, 0)) + 1
    f.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return dados[chave]


def tentativas_esgotadas(skill, chave, base=None):
    try:
        dados = json.loads((base_dir(base) / "tentativas" / f"{skill}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return int(dados.get(chave, 0)) > TETO_TENTATIVAS


def _lock_path(repo, base=None):
    if not SKILL_RE.match(re.sub(r"[^a-z0-9-]", "-", repo.lower()) or ""):
        raise ValueError(f"repo inválido: {repo!r}")
    return _sub("locks", base) / (re.sub(r"[^a-z0-9-]", "-", repo.lower()) + ".lock")


def lock(skill, repo, base=None, now=None):
    """Reserva o repo para o loop. False se outro loop ativo o tem (locks de loops expirados caducam)."""
    _path(skill, base)
    f = _lock_path(repo, base)
    try:
        dono = f.read_text(encoding="utf-8").strip()
    except OSError:
        dono = ""
    if dono and dono != skill and get_estado(dono, base, now):
        return False
    f.write_text(skill, encoding="utf-8")
    return True


def unlock(skill, repo, base=None):
    f = _lock_path(repo, base)
    try:
        if f.read_text(encoding="utf-8").strip() == skill:
            f.unlink()
    except OSError:
        pass


def _hora(epoch):
    return datetime.fromtimestamp(epoch).strftime("%H:%M")


def bloco_handoff(base=None, now=None, session_id=TODOS):
    """Bloco `## Loops ativos` para o fim do handoff, só com os loops da sessão atual; "" sem nenhum."""
    if session_id is TODOS:
        session_id = dono_do_env()["sessao"]
    est = ativos(base, now, session_id=session_id)
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


def ordem_retoma(base: Any = None, now: float | None = None, session_id: str | None = None) -> str:
    """Texto para o hook de retoma injetar na sessão nova; "" sem loops ativos de que ela seja dona."""
    est = ativos(base, now, session_id=session_id)
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
    for nome in ("get", "clear", "adotar"):
        sub.add_parser(nome).add_argument("skill")
    sub.add_parser("ativos")
    lg = sub.add_parser("log")
    lg.add_argument("skill")
    lg.add_argument("linha")
    tt = sub.add_parser("tentativa")
    tt.add_argument("skill")
    tt.add_argument("chave")
    for nome in ("lock", "unlock"):
        lk = sub.add_parser(nome)
        lk.add_argument("skill")
        lk.add_argument("repo")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "set":
            anterior = get_estado(args.skill) or {}
            dono = {k: v or anterior.get(k) for k, v in dono_do_env().items()}
            if anterior.get("sessao") and dono["sessao"] != anterior.get("sessao"):
                dono = {k: anterior.get(k) for k in dono}  # só `adotar` muda a posse
            dados = set_estado(args.skill, parse_fim(args.fim), perm=args.perm, acao=args.acao,
                               alvos=args.alvos, acoes=args.acoes, **dono)
            print(json.dumps(dados, ensure_ascii=False))
        elif args.cmd == "get":
            dados = get_estado(args.skill)
            if not dados:
                print(f"sem estado ativo: {args.skill}", file=sys.stderr)
                return 1
            print(json.dumps(dados, ensure_ascii=False))
        elif args.cmd == "adotar":
            dados = get_estado(args.skill)
            if not dados:
                print(f"sem estado ativo: {args.skill}", file=sys.stderr)
                return 1
            campos = {k: v for k, v in dados.items() if k not in ("skill", "fim", "sessao", "pid")}
            dados = set_estado(args.skill, dados["fim"], **campos, **dono_do_env())
            print(json.dumps(dados, ensure_ascii=False))
        elif args.cmd == "clear":
            clear(args.skill)
        elif args.cmd == "log":
            log(args.skill, args.linha)
        elif args.cmd == "tentativa":
            n = tentativa(args.skill, args.chave)
            print(n)
            return 0 if n <= TETO_TENTATIVAS else 1
        elif args.cmd == "lock":
            if not lock(args.skill, args.repo):
                print(f"repo ocupado por outro loop: {args.repo}", file=sys.stderr)
                return 1
        elif args.cmd == "unlock":
            unlock(args.skill, args.repo)
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
