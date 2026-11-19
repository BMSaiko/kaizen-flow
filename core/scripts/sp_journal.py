#!/usr/bin/env python3
"""Checkpoint atómico + journal de passos por SP (estado durável do michi).

Uso: python -I scripts/sp_journal.py estado|inicio|fim|revertido|reconstruir --slug S [--raiz R]

Ficheiros (junto da worktree, ignorados pelo git):
  <raiz>/.kaizen/estado/<slug>.json          checkpoint (fase/passo corrente, `interrompido`)
  <raiz>/.kaizen/estado/<slug>.journal.jsonl eventos {ts, pid, fase, passo, evento, idempotente}

Passo com «inicio» sem «fim»/«revertido» = interrompido: idempotente repete, não idempotente reverte
(rollback de ficheiros por michi-checkpoint.py). Estado corrompido vai para `<ficheiro>.corrupt-<ts>`
(nunca se apaga) e reconstrói-se do git + `phase:` do SP. Fecho da consola conta como Ctrl+C.
rc: 0 ok; 128+sinal se interrompido (Ctrl+C, fecho da consola)
"""
import argparse
import json
import os
import re
import signal
import subprocess  # só para SubprocessError; correr processos é com painel_backend
import sys
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_disco  # noqa: E402
import painel_backend  # noqa: E402

RETRY_S = 2.0  # rename com retry curto contra antivírus/leitor (Windows)
EVENTOS = ("inicio", "fim", "revertido")
_ATUAL = {}  # (raiz, slug) -> (fase, passo) do último `inicio` neste processo
_CALLBACK_CONSOLA = None  # mantém a referência ctypes viva (senão o GC apaga o handler)


@dataclass
class Estado:
    fase: str = None
    passo: str = None
    interrompidos: list = field(default_factory=list)
    acao: str = "nada"  # repetir | reverter | nada
    aviso: str = None
    reconstruido: bool = False
    origem: dict = None
    interrompido: bool = False  # `interrompido: true` do checkpoint (gravado por sinal)


@dataclass
class Corrompido:
    quarentena: Path
    reconstruido: Estado


def _longo(p):
    """Caminho absoluto; no Windows, com prefixo `\\\\?\\` quando passa dos 260 caracteres."""
    p = Path(os.path.abspath(p))
    s = str(p)
    if os.name == "nt" and len(s) >= 240 and not s.startswith("\\\\?\\"):
        return Path("\\\\?\\" + s)
    return p


def caminhos(raiz, slug):
    """(checkpoint, journal) de um SP; as pastas ficam por criar."""
    base = _longo(Path(raiz) / ".kaizen" / "estado")
    return base / f"{slug}.json", base / f"{slug}.journal.jsonl"


def _chave(raiz, slug):
    return (str(Path(raiz).resolve()), slug)


def _agora():
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _quarentena(path):
    """Move `path` para `<path>.corrupt-<ts>` sem nunca sobrescrever; devolve o novo caminho."""
    carimbo = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    destino = path.with_name(f"{path.name}.corrupt-{carimbo}")
    n = 0
    while destino.exists():
        n += 1
        destino = path.with_name(f"{path.name}.corrupt-{carimbo}-{n}")
    os.replace(path, destino)
    return destino


def gravar_checkpoint(raiz, slug, fase, passo, extra=None):
    """Checkpoint atómico (`sp_disco.guardar`, retry ≤ 2 s)."""
    estado_p = caminhos(raiz, slug)[0]
    estado_p.parent.mkdir(parents=True, exist_ok=True)
    dados = {"slug": slug, "fase": fase, "passo": passo, "ts": _agora(), "pid": os.getpid(), "interrompido": False}
    dados.update(extra or {})
    sp_disco.guardar(estado_p, dados, retry_s=RETRY_S)
    return estado_p


def _reparar_cauda(jp):
    """Journal que acaba sem `\\n` (crash a meio da linha): cauda válida fecha-se, inválida vai para quarentena."""
    if not jp.exists() or jp.stat().st_size == 0:
        return
    with open(jp, "rb") as f:
        f.seek(-1, os.SEEK_END)
        if f.read(1) == b"\n":
            return
    dados = jp.read_bytes()
    corte = dados.rfind(b"\n") + 1
    cauda = dados[corte:]
    if _evento(cauda) is not None:
        with open(jp, "ab") as f:
            f.write(b"\n")
        return
    destino = _quarentena_bytes(jp, cauda)
    with open(jp, "r+b") as f:
        f.truncate(corte)
    return destino


def _quarentena_bytes(path, dados):
    carimbo = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    destino = path.with_name(f"{path.name}.corrupt-{carimbo}")
    n = 0
    while destino.exists():
        n += 1
        destino = path.with_name(f"{path.name}.corrupt-{carimbo}-{n}")
    destino.write_bytes(dados)
    return destino


def _acrescentar(raiz, slug, fase, passo, evento, idempotente):
    jp = caminhos(raiz, slug)[1]
    jp.parent.mkdir(parents=True, exist_ok=True)
    _reparar_cauda(jp)
    linha = {"ts": _agora(), "pid": os.getpid(), "fase": fase, "passo": passo, "evento": evento, "idempotente": bool(idempotente)}
    with open(jp, "ab") as f:
        f.write(json.dumps(linha, ensure_ascii=True).encode("ascii") + b"\n")
        f.flush()
        os.fsync(f.fileno())
    try:
        sp_disco.renovar_lock(raiz, slug)  # cada evento é sinal de vida do dono (michi por CLI)
    except (OSError, TimeoutError):
        pass  # o heartbeat nunca parte a API do journal: o evento já está gravado


def inicio(raiz, slug, fase, passo, idempotente=True):
    """Regista o início de um passo e grava o checkpoint."""
    _acrescentar(raiz, slug, fase, passo, "inicio", idempotente)
    _ATUAL[_chave(raiz, slug)] = (fase, passo)
    gravar_checkpoint(raiz, slug, fase, passo)


def fim(raiz, slug, fase, passo):
    _acrescentar(raiz, slug, fase, passo, "fim", True)
    gravar_checkpoint(raiz, slug, fase, passo)


def revertido(raiz, slug, fase, passo):
    _acrescentar(raiz, slug, fase, passo, "revertido", True)
    gravar_checkpoint(raiz, slug, fase, passo)


def _evento(linha):
    """Dict do evento ou None se a linha não for um evento válido."""
    try:
        e = json.loads(linha.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(e, dict) or e.get("evento") not in EVENTOS:
        return None
    if not isinstance(e.get("fase"), str) or not isinstance(e.get("passo"), str):
        return None
    return e


def _ler_journal(jp):
    """(eventos, aviso) ou None se houver linha inválida antes do fim (corrompido)."""
    dados = jp.read_bytes()
    if not dados:
        return [], None
    partes = dados.split(b"\n")
    terminado = dados.endswith(b"\n")
    if terminado:
        partes.pop()
    eventos, aviso = [], None
    for i, parte in enumerate(partes):
        e = _evento(parte)
        if e is None:
            if not terminado and i == len(partes) - 1:
                aviso = "última linha do journal truncada: ignorada"
                continue
            return None
        eventos.append(e)
    return eventos, aviso


def _estado_de_eventos(eventos, aviso=None, interrompido=False):
    abertos = {}
    for e in eventos:
        k = (e["fase"], e["passo"])
        if e["evento"] == "inicio":
            abertos.pop(k, None)  # reinício (retoma): conta pela última posição
            abertos[k] = bool(e.get("idempotente", True))
        else:
            abertos.pop(k, None)
    acao = "nada"
    if abertos:
        acao = "repetir" if all(abertos.values()) else "reverter"
    ultimo = eventos[-1] if eventos else {}
    return Estado(
        fase=ultimo.get("fase"),
        passo=ultimo.get("passo"),
        interrompidos=[p for (_, p) in abertos],
        acao=acao,
        aviso=aviso,
        interrompido=interrompido,
    )


def _frontmatter_fase(sp_path):
    try:
        texto = Path(sp_path).read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None
    m = re.match(r"﻿?---\r?\n(.*?)\r?\n---", texto, re.S)
    if not m:
        return None
    f = re.search(r"^phase:\s*(\S+)", m.group(1), re.M)
    return f.group(1) if f else None


def _git(raiz, *args):
    try:
        r = painel_backend.run_hidden(["git", "-C", str(raiz), *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def reconstruir(raiz, slug, sp_path):
    """Estado mínimo a partir do git da worktree e do `phase:` do SP (sem tocar em nada)."""
    origem = {"branch": _git(raiz, "rev-parse", "--abbrev-ref", "HEAD"), "commit": _git(raiz, "log", "-1", "--format=%s")}
    return Estado(
        fase=_frontmatter_fase(sp_path) if sp_path else None,
        reconstruido=True,
        origem=origem,
        aviso="estado reconstruído do git e do frontmatter do SP",
    )


def estado(raiz, slug, sp_path=None):
    """Estado do SP: `Estado`, ou `Corrompido` depois de pôr o ficheiro mau em quarentena."""
    estado_p, jp = caminhos(raiz, slug)
    eventos = []
    aviso = None
    if jp.exists():
        lido = _ler_journal(jp)
        if lido is None:
            q = _quarentena(jp)
            return Corrompido(quarentena=q, reconstruido=reconstruir(raiz, slug, sp_path))
        eventos, aviso = lido
    interrompido = False
    if estado_p.exists():
        try:
            cp = json.loads(estado_p.read_text(encoding="utf-8"))
            if not isinstance(cp, dict):
                raise ValueError("checkpoint não é um objeto")
            interrompido = bool(cp.get("interrompido"))
        except (OSError, ValueError):
            q = _quarentena(estado_p)
            rec = _estado_de_eventos(eventos, aviso) if eventos else reconstruir(raiz, slug, sp_path)
            return Corrompido(quarentena=q, reconstruido=rec)
    return _estado_de_eventos(eventos, aviso, interrompido)


def _ao_interromper(raiz, slug):
    """Grava `interrompido: true` com a fase/passo correntes e liberta o lock deste processo; True se gravou."""
    fase, passo = _ATUAL.get(_chave(raiz, slug), (None, None))
    try:
        gravar_checkpoint(raiz, slug, fase, passo, extra={"interrompido": True})
    except OSError:
        return False
    try:
        sp_disco.libertar_lock(raiz, slug)  # só apaga se for deste pid: o SP fica logo candidato a `kaizen resume`
    except (OSError, TimeoutError):
        pass
    return True


def instalar_sinais(raiz, slug):
    """SIGINT/SIGTERM/SIGBREAK/SIGHUP e (Windows) fecho da consola gravam o checkpoint e saem; False fora da thread principal."""
    global _CALLBACK_CONSOLA
    if threading.current_thread() is not threading.main_thread():
        return False
    anteriores = {}

    def handler(signum, frame):
        _ao_interromper(raiz, slug)
        signal.signal(signum, anteriores.get(signum) or signal.SIG_DFL)
        if signum == signal.SIGINT:
            raise KeyboardInterrupt
        sys.exit(128 + int(signum))

    for nome in ("SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP"):  # EC-069: SIGHUP = painel fechado (Linux/macOS)
        sig = getattr(signal, nome, None)
        if sig is not None:
            anteriores[sig] = signal.signal(sig, handler)
    if os.name == "nt":
        import ctypes

        tipo = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

        def consola(ctrl_type):
            if ctrl_type in (2, 5, 6):  # CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT
                _ao_interromper(raiz, slug)
            return False  # o Windows termina o processo como sempre

        _CALLBACK_CONSOLA = tipo(consola)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_CALLBACK_CONSOLA, True)
    return True


def _para_json(obj):
    if isinstance(obj, Corrompido):
        return {"corrompido": True, "quarentena": str(obj.quarentena), "reconstruido": asdict(obj.reconstruido)}
    return asdict(obj)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Checkpoint atómico + journal de passos por SP")
    ap.add_argument("comando", choices=["estado", "inicio", "fim", "revertido", "reconstruir"])
    ap.add_argument("--slug", required=True)
    ap.add_argument("--raiz", default=".", help="raiz da worktree (defeito: cwd)")
    ap.add_argument("--fase")
    ap.add_argument("--passo")
    ap.add_argument("--nao-idempotente", action="store_true", help="inicio: passo que reverte em vez de repetir")
    ap.add_argument("--sp", help="caminho do SP (frontmatter `phase:`) para estado/reconstruir")
    a = ap.parse_args(argv)
    if a.comando in ("inicio", "fim", "revertido") and not (a.fase and a.passo):
        ap.error("--fase e --passo são obrigatórios")
    if a.comando == "inicio":
        inicio(a.raiz, a.slug, a.fase, a.passo, idempotente=not a.nao_idempotente)
    elif a.comando == "fim":
        fim(a.raiz, a.slug, a.fase, a.passo)
    elif a.comando == "revertido":
        revertido(a.raiz, a.slug, a.fase, a.passo)
    else:
        est = reconstruir(a.raiz, a.slug, a.sp) if a.comando == "reconstruir" else estado(a.raiz, a.slug, a.sp)
        if isinstance(est, Corrompido):
            print(f"aviso: estado corrompido em quarentena: {est.quarentena}", file=sys.stderr)
        print(json.dumps(_para_json(est), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
