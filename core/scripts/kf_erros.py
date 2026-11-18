#!/usr/bin/env python3
"""Formato único das mensagens de erro do kf e classificador de falhas do modelo (quota, rede, sessão).

Formato (PT, 4 linhas, código do catálogo `docs/catalogo.json` no início):
    EC-NNN O quê: <o que falhou>
      Porquê: <causa>
      Estado guardado: <o que ficou intacto ou gravado>
      Próximo: <comando a correr a seguir>

`classificar_falha(texto, rc)` lê a saída de um harness (Claude Code, Codex) e devolve
`(ec, motivo, retoma_em|None)` para quota/limite de uso (EC-016), rede (EC-017) e sessão/login
expirado (EC-066), ou None numa falha genérica. Deteção só pelo texto: nunca chama a API.

Não confundir com o script `kf-erros.py` (agrupa erros recorrentes do log).

Uso: módulo (`import kf_erros`); sem execução direta
rc: n/a
"""
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
EC_RE = re.compile(r"^EC-\d{3}$")
_EC_EM = re.compile(r"\bEC-\d{3}\b")
ROTULOS = ("O quê", "Porquê", "Estado guardado", "Próximo")
EC_INESPERADO, EC_QUOTA, EC_REDE, EC_SESSAO = "EC-010", "EC-016", "EC-017", "EC-066"
ECS_USADOS = (EC_INESPERADO, EC_QUOTA, EC_REDE, EC_SESSAO)
RETOMA_MIN = 30  # retoma sem hora no texto: agora + este intervalo (KF_RETOMA_MIN muda-o)
CAUDA = 40  # só as últimas linhas contam: um limite antigo no histórico do ecrã não bloqueia


def _uma_linha(texto):
    return " ".join(str(texto).splitlines()).strip()


@dataclass(frozen=True)
class Erro:
    ec: str
    oque: str
    porque: str
    estado: str
    proximo: str

    def __post_init__(self):
        if not isinstance(self.ec, str) or not EC_RE.match(self.ec):
            raise ValueError(f"código EC inválido: {self.ec!r} (forma EC-NNN)")
        for nome in ("oque", "porque", "estado", "proximo"):
            valor = getattr(self, nome)
            if valor is None or not _uma_linha(valor):
                raise ValueError(f"parte vazia na mensagem {self.ec}: {nome}")


def formatar(erro):
    """As 4 partes, uma por linha, com o EC no início da primeira."""
    oque, porque, estado, proximo = (_uma_linha(getattr(erro, n)) for n in ("oque", "porque", "estado", "proximo"))
    return f"{erro.ec} O quê: {oque}\n  Porquê: {porque}\n  Estado guardado: {estado}\n  Próximo: {proximo}"


def erro(ec, oque, porque, estado, proximo):
    """Atalho: `formatar(Erro(...))`."""
    return formatar(Erro(ec, oque, porque, estado, proximo))


def ler(texto):
    """Lê de volta uma mensagem no formato (Erro) ou None se o texto não o tem."""
    linhas = str(texto).split("\n")
    if len(linhas) != 4:
        return None
    m = re.match(r"^(EC-\d{3}) O quê: (.*)$", linhas[0])
    if not m:
        return None
    partes = [m.group(2)]
    for linha, rotulo in zip(linhas[1:], ROTULOS[1:]):
        prefixo = f"  {rotulo}: "
        if not linha.startswith(prefixo):
            return None
        partes.append(linha[len(prefixo):])
    try:
        return Erro(m.group(1), *partes)
    except ValueError:
        return None


def ecs_em(texto):
    """Códigos EC-NNN que aparecem no texto, pela ordem e sem repetidos."""
    vistos = []
    for ec in _EC_EM.findall(str(texto)):
        if ec not in vistos:
            vistos.append(ec)
    return vistos


def caminho_catalogo():
    """`docs/catalogo.json`: $KF_CATALOGO se existir, senão o do repo (core/scripts → ../../docs). None fora do repo."""
    env = os.environ.get("KF_CATALOGO")
    if env and Path(env).is_file():
        return Path(env)
    p = HERE.parent.parent / "docs" / "catalogo.json"
    return p if p.is_file() else None


def ecs_do_catalogo(path=None):
    """Ids EC do catálogo (vazio se não houver ou estiver ilegível)."""
    p = path or caminho_catalogo()
    if p is None:
        return set()
    try:
        dados = json.loads(Path(p).read_text(encoding="utf-8"))
        return {e["id"] for e in dados.get("edge_cases", []) if isinstance(e, dict) and "id" in e}
    except (OSError, ValueError, AttributeError, TypeError):
        return set()


# --- classificador -----------------------------------------------------------

_QUOTA = re.compile(
    # «limit reached» só com qualificador de quota ou com hora de reset: «Context/max turns limit reached» não é quota
    r"usage limit|\b(?:5-hour|weekly|session|daily|opus|sonnet)\s+limit reached"
    r"|limit reached[^\n]{0,40}\b(?:resets?|try again)|limit reached\|\d{9,11}|rate[ _-]?limit|too many requests|overloaded|insufficient_quota|quota exceeded"
    r"|exceeded your current quota|hit your (?:usage )?limit|\b(?:error|status|http|code)\b[^\n]{0,30}\b(?:429|529)\b",
    re.I,
)
_SESSAO = re.compile(
    r"oauth token has expired|invalid api key|not logged in|please run /login|authentication_error"
    r"|token could not be refreshed|session (?:has )?expired|(?:sign|log) in again|codex login\b",
    re.I,
)
_REDE = re.compile(
    r"ENOTFOUND|ECONNRESET|ECONNREFUSED|ETIMEDOUT|EAI_AGAIN|getaddrinfo|could not resolve host|network (?:error|is unreachable)"
    r"|connection (?:error|reset|refused|timed out)|request timed out|operation timed out|stream disconnected|fetch failed",
    re.I,
)
_EPOCH = re.compile(r"limit reached\|(\d{9,11})", re.I)
_HORA = re.compile(r"(?:resets?|try again at)\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*([ap])?\.?m?\b", re.I)
_DURACAO = re.compile(r"try again in\s+((?:\d+\s*(?:days?|hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b[\s,]*(?:and\s+)?)+)", re.I)
_UNIDADE = re.compile(r"(\d+)\s*(days?|hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b", re.I)


def _intervalo(intervalo_min):
    if intervalo_min is not None:
        return int(intervalo_min)
    try:
        return max(1, int(os.environ.get("KF_RETOMA_MIN", RETOMA_MIN)))
    except ValueError:
        return RETOMA_MIN


def _iso(dt):
    return dt.replace(microsecond=0).isoformat(timespec="seconds")


def retoma_padrao(agora=None, intervalo_min=None):
    """Hora de retoma quando o texto não a dá: agora + intervalo (KF_RETOMA_MIN, defeito 30 min)."""
    return _iso((agora or datetime.now()) + timedelta(minutes=_intervalo(intervalo_min)))


def _hora_no_texto(texto, agora):
    m = _EPOCH.search(texto)
    if m:
        try:
            return datetime.fromtimestamp(int(m.group(1)))
        except (OverflowError, OSError, ValueError):
            pass
    m = _DURACAO.search(texto)
    if m:
        total = timedelta()
        for n, u in _UNIDADE.findall(m.group(1)):
            u = u.lower()
            mult = {"d": "days", "h": "hours", "m": "minutes", "s": "seconds"}[u[0]]
            if u.startswith("mi") or u == "m":
                mult = "minutes"
            total += timedelta(**{mult: int(n)})
        if total:
            return agora + total
    m = _HORA.search(texto)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
        if ap == "p" and h < 12:
            h += 12
        elif ap == "a" and h == 12:
            h = 0
        if h < 24 and mi < 60 and (ap or m.group(2)):
            alvo = agora.replace(hour=h, minute=mi, second=0, microsecond=0)
            return alvo if alvo > agora else alvo + timedelta(days=1)
    return None


def classificar_falha(texto, rc=None, agora=None, intervalo_min=None):
    """(ec, motivo, retoma_em ISO local | None) para quota/rede/sessão; None numa falha genérica. Nunca levanta."""
    try:
        linhas = [l for l in str(texto or "").splitlines() if l.strip()][-CAUDA:]
        cauda = "\n".join(linhas)
        if not cauda:
            return None
        agora = agora or datetime.now()
        for ec, padrao, motivo in ((EC_QUOTA, _QUOTA, "quota/limite de uso do modelo"),
                                   (EC_SESSAO, _SESSAO, "sessão/login do modelo expirado"),
                                   (EC_REDE, _REDE, "rede indisponível")):
            m = padrao.search(cauda)
            if not m:
                continue
            linha = next((l for l in linhas if padrao.search(l)), m.group(0))
            detalhe = _uma_linha(linha)[:160]
            if ec == EC_SESSAO:
                return ec, f"{motivo}: {detalhe}", None
            alvo = _hora_no_texto(cauda, agora) if ec == EC_QUOTA else None
            return ec, f"{motivo}: {detalhe}", _iso(alvo) if alvo else retoma_padrao(agora, intervalo_min)
        return None
    except Exception:  # noqa: BLE001 — classificar nunca parte quem chama
        return None


def ja_passou(retoma_em, agora=None):
    """True se `retoma_em` (ISO) já passou, falta ou é ilegível (não bloqueia por um valor estragado)."""
    if not retoma_em:
        return True
    try:
        return datetime.fromisoformat(str(retoma_em)) <= (agora or datetime.now())
    except (ValueError, TypeError):
        return True
