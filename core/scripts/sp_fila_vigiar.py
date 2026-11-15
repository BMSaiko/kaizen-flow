"""Vigiar a fila de painéis pelo LLM: uma linha por transição relevante, só leitura.

`passo(mem, leitura)` é puro: compara o estado lido (SPs, log do vigia, vida do vigia) com o que já saiu e devolve
`(linhas, fim)`; `fim` é None (continua), 0 (fila acabou) ou 1 (vigia morreu com a fila por acabar).
Pensado para `Monitor`: cada linha impressa é uma notificação. Ver `sp-fila-vigiar.py`.

Uso: módulo importado por sp-fila-vigiar.py; sem execução direta
rc: sem execução direta"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_painel_estado as pe  # noqa: E402
import sp_vigia as sv  # noqa: E402
from sp_estado_base import ErroEstado  # noqa: E402

INTERVALO = 10.0
ATENCAO = {"bloqueado": "ATENÇÃO", "falhou": "ATENÇÃO", "pergunta": "DECISÃO DO user"}
RE_MERGE = re.compile(r"^\S+ merge (\S+): (.*)$")
RE_SEGUINTE = re.compile(r"^\S+ seguinte (\S+): (\S+)")
RE_FIM = re.compile(r"^\S+ fila terminada:\s*(.*)$")


def memoria_nova():
    return {"estados": {}, "vistos": set(), "morto_avisado": False}


def _linha_estado(slug, sp):
    estado, msg = sp.get("estado"), sp.get("msg")
    texto = f"{slug}: {estado}" + (f" ({msg})" if msg else "")
    marca = ATENCAO.get(estado)
    return texto + (f" · {marca}" if marca else "")


def _do_log(mem, log):
    """Linhas novas do log do vigia (merge feito, seguinte lançado) e o motivo do fim, se já terminou."""
    linhas, fim = [], None
    for l in (log or "").splitlines():
        m = RE_FIM.match(l)
        if m:
            fim = m.group(1).strip()
            continue
        m = RE_MERGE.match(l)
        if m and "lock ocupado" not in m.group(2):
            chave = ("merge", m.group(1))
            if chave not in mem["vistos"]:
                mem["vistos"].add(chave)
                linhas.append(f"{m.group(1)}: merge feito")
            continue
        m = RE_SEGUINTE.match(l)
        if m and m.group(2) != "fim":
            chave = ("seguinte", m.group(1), m.group(2))
            if chave not in mem["vistos"]:
                mem["vistos"].add(chave)
                linhas.append(f"{m.group(1)}: seguinte {m.group(2)}")
    return linhas, fim


def passo(mem, leitura):
    linhas = []
    for slug, sp in leitura["sps"].items():
        chave = (sp.get("estado"), sp.get("msg"))
        if mem["estados"].get(slug) != chave:
            mem["estados"][slug] = chave
            linhas.append(_linha_estado(slug, sp))
    novas, motivo = _do_log(mem, leitura.get("log"))
    linhas += novas
    if motivo is not None:
        return linhas + [f"fim: {motivo}".rstrip(": ")], 0
    if not leitura.get("fila_existe", True):
        return linhas + ["fim: fila parada ou removida"], 0
    if not leitura.get("vigia_vivo", True):
        if not mem["morto_avisado"]:
            mem["morto_avisado"] = True
            linhas.append("vigia morto com a fila por acabar · ATENÇÃO · relançar: "
                          "python -I scripts/sp-vigia.py <fila>")
        return linhas, 1
    return linhas, None


# --- leitura real --------------------------------------------------------------------------------

def _pasta(fila):
    return pe.raiz() / fila


def ler_fila(fila):
    return pe.ler(fila)


def _vigia_vivo(pidf):
    try:
        return pe.pid_vivo(int(Path(pidf).read_text(encoding="utf-8").strip()))
    except (OSError, ValueError):
        return False


def ler_tudo(fila):
    pasta = _pasta(fila)
    pidf, logf, _ = sv.caminhos(pasta)
    try:
        sps = ler_fila(fila).get("sps", {})
        existe = True
    except (OSError, ValueError, KeyError, ErroEstado):
        sps, existe = {}, False
    try:
        log = logf.read_text(encoding="utf-8", errors="replace")
    except OSError:
        log = ""
    return {"sps": sps, "vigia_vivo": _vigia_vivo(pidf), "log": log, "fila_existe": existe}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Vigia uma fila de painéis do sp-fila (uma linha por transição)")
    ap.add_argument("fila")
    ap.add_argument("--intervalo", type=float, default=INTERVALO)
    ap.add_argument("--uma-vez", action="store_true", help="um só tick (diagnóstico)")
    args = ap.parse_args(argv)
    if not _pasta(args.fila).is_dir():
        print(f"erro: fila de painéis desconhecida: {args.fila}", file=sys.stderr)
        return 1
    mem = memoria_nova()
    while True:
        linhas, fim = passo(mem, ler_tudo(args.fila))
        for l in linhas:
            print(l, flush=True)
        if fim is not None:
            return fim
        if args.uma_vez:
            return 0
        time.sleep(args.intervalo)
