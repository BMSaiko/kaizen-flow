"""Base do estado do sp-fila: erros, estados, validação de nomes e leitura de JSON de estado. Só stdlib.

Vive à parte para o `sp_painel_estado.py` ficar só com o modelo de estados; este módulo não toca na raiz do estado.

Uso: módulo importado por sp_painel_estado; sem execução direta
rc: n/a
"""
import json
import re
from datetime import datetime
from pathlib import Path

ESTADOS = ("pendente", "a-correr", "pergunta", "done", "bloqueado", "falhou")
ILEGIVEL = "ilegível"
FINAIS = frozenset({"done", "falhou"})
CAMPOS = ("modelo", "worktree", "pane", "fase", "pergunta")
NAO_SP = {"fila.json", "vigia.json"}  # a memória do vigia vive na pasta da fila e não é estado de SP
_NOME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,149}$")
_DISPOSITIVO = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\.|$)", re.IGNORECASE)


class ErroEstado(Exception):
    """Pedido recusado sem escrever (nome inválido, slug desconhecido, transição inválida, JSON ilegível)."""


class SemVaga(ErroEstado):
    """O teto global de painéis ativos está atingido."""


def _nome(valor, que):
    """Um nome (fila ou slug) vira nome de ficheiro: só letras, dígitos, `.`, `_` e `-`, sem `..`."""
    if not isinstance(valor, str) or not _NOME.match(valor) or ".." in valor or valor.endswith("."):
        raise ErroEstado(f"{que} inválido: {valor!r}")
    if _DISPOSITIVO.match(valor):  # Windows: `NUL.json` é o dispositivo, não um ficheiro
        raise ErroEstado(f"{que} inválido: {valor!r} (nome reservado no Windows)")
    return valor


def _slug(valor):
    if _nome(valor, "slug").lower() == "fila":
        raise ErroEstado(f"slug inválido: {valor!r} (reservado)")
    return valor


def fila_id(programa=None, agora=None):
    """Id da fila: o slug da mãe (programa) ou `fila-AAAAMMDD-HHMMSS` na fila sem programa."""
    if programa:
        return _nome(programa, "programa")
    return "fila-" + (agora or datetime.now()).strftime("%Y%m%d-%H%M%S")


def _ts(agora=None):
    return (agora or datetime.now()).isoformat(timespec="seconds")


def _ler_json(path):
    try:
        dados = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, ValueError) as e:
        raise ErroEstado(f"estado {ILEGIVEL}: {path} ({e})") from e
    if not isinstance(dados, dict):
        raise ErroEstado(f"estado {ILEGIVEL}: {path} (não é um objeto JSON)")
    return dados


def _ler_sp(path):
    dados = _ler_json(path)
    if dados.get("estado") not in ESTADOS:
        raise ErroEstado(f"estado {ILEGIVEL}: {path} (estado {dados.get('estado')!r})")
    return dados


def _dirs(r):
    """Pastas de fila dentro da raiz, por ordem de nome."""
    if not r.is_dir():
        return []
    return sorted((d for d in r.iterdir() if d.is_dir() and (d / "fila.json").is_file()), key=lambda d: d.name)


def _ficheiros_sp(d):
    return sorted((p for p in d.glob("*.json") if p.name.lower() not in NAO_SP), key=lambda p: p.name)


def _sp_novo(fid, slug, agora=None):
    return {"slug": slug, "fila": fid, "estado": "pendente", "modelo": None, "worktree": None, "pane": None,
            "inicio": None, "fim": None, "msg": None, "atualizado": _ts(agora), "fase": None, "pergunta": None}


def _campos(campos):
    estranhos = sorted(set(campos) - set(CAMPOS))
    if estranhos:
        raise ErroEstado(f"campo desconhecido: {', '.join(estranhos)} (válidos: {', '.join(CAMPOS)})")
    return {k: (None if v is None else str(v)) for k, v in campos.items()}


def _procurar(r, slug):
    candidatas = []
    for d in _dirs(r):
        p = d / f"{slug}.json"
        if not p.is_file():
            continue
        try:
            acabado = _ler_sp(p)["estado"] in FINAIS
        except (ErroEstado, FileNotFoundError):
            acabado = False
        try:
            criada = str(_ler_json(d / "fila.json").get("criada") or "")
        except (ErroEstado, FileNotFoundError):
            criada = ""
        candidatas.append((not acabado, criada, d.name))
    if not candidatas:
        raise ErroEstado(f"slug desconhecido: {slug} (nenhuma fila o regista)")
    return max(candidatas)[2]
