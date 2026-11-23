"""Orçamento da fila autónoma: tetos de custo por SP e por dia e de falhas seguidas (`orcamento` do kaizen.config.json).

`decidir` devolve `ok` (abaixo de 80 % de todos os tetos), `aviso` (>= 80 % de algum) ou `parar` (algum atingido).
Só métricas (tokens e USD equivalentes à API), nunca conteúdo de conversas. Sem config ou sem teto: sempre `ok`.

Uso: módulo importado por sp_fila_execucao; sem execução direta
rc: n/a
"""
import importlib.util
import sys
from datetime import datetime
from pathlib import Path

AVISO = 0.8
USAGE_DIR = Path(__file__).resolve().parents[2] / "usage"
_TETOS = (("spUsd", "custo do SP", "USD"), ("diaUsd", "custo do dia", "USD"), ("falhasSeguidas", "falhas seguidas", ""))


def decidir(cfg, sp_usd=0.0, dia_usd=0.0, seguidas=0):
    """{estado: ok|aviso|parar, razao, avisos}; `razao` é a do primeiro teto atingido, `avisos` os tetos a >= 80 %."""
    valores = {"spUsd": sp_usd, "diaUsd": dia_usd, "falhasSeguidas": seguidas}
    razao, avisos = "", []
    for chave, nome, unidade in _TETOS:
        teto = (cfg or {}).get(chave)
        if not teto:
            continue
        v = valores[chave]
        fmt = f"{v:.2f}/{teto:.2f} {unidade}" if unidade else f"{v}/{teto}"
        if v >= teto and not razao:
            razao = f"{chave} atingido: {nome} {fmt}"
        elif v >= teto * AVISO:
            avisos.append(f"{chave} a {v / teto:.0%}: {nome} {fmt}")
    return {"estado": "parar" if razao else "aviso" if avisos else "ok", "razao": razao, "avisos": avisos}


def gasto_dia(agora=None, usage_dir=None, claude_root=None):
    """USD equivalentes à API gastos no dia de `agora` (via `usage/kaizen_usage.py`); 0.0 se a medição não existe ou falha."""
    agora = agora or datetime.now()
    pasta = Path(usage_dir or USAGE_DIR)
    ficheiro = pasta / "kaizen_usage.py"
    if not ficheiro.is_file():
        return 0.0
    try:
        spec = importlib.util.spec_from_file_location("kf_orc_usage", ficheiro)
        ku = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("kf_orc_usage", ku)
        spec.loader.exec_module(ku)
        inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0).astimezone()
        recs = ku.ClaudeTranscripts(claude_root).read(inicio)
        preco = ku.Pricing.load(pasta / "prices.json")
        dia = inicio.strftime("%Y-%m-%d")
        return sum(c for r in recs if r["ts"].strftime("%Y-%m-%d") == dia and (c := preco.cost(r)) is not None)
    except (Exception, SystemExit):  # noqa: BLE001 — a medição nunca pode impedir a fila (preços ilegíveis fazem sys.exit)
        return 0.0
