"""Lê `kaizen.config.json` na raiz do repo; sem ficheiro ou chave, devolve o defeito.

Chaves: `spRoot` (raiz dos SPs) e `docsRoot` (raiz dos DR/DP), relativas à raiz do repo; `desenvolvimento` (método do projeto); `herdr` ({maxPanesPorTab, workspacePorProjeto}); `qualidade.coberturaDiff` (limiar % da cobertura do diff, defeito 85); `qualidade.{bloqueantes,consultivos,fases}` (perfil de gates, ver `qualidade`); `orcamento` ({spUsd, diaUsd, falhasSeguidas}, ver `orcamento`).

Uso: módulo importado pelos scripts sp-* e doc_ops; sem execução direta
rc: n/a
"""
import json
from pathlib import Path

DEFAULT_SP_ROOT = "knowledge/projects/kaizen"
DEFAULT_DOCS_ROOT = "knowledge/projects"
CONFIG_NAME = "kaizen.config.json"
DEFAULT_USER = "user"


def _read(repo):
    try:
        data = json.loads((Path(repo) / CONFIG_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def sp_root(repo):
    return Path(repo) / _read(repo).get("spRoot", DEFAULT_SP_ROOT)


def user_name(repo):
    """Nome com que os avisos tratam o utilizador (`userName`; defeito «user»)."""
    v = _read(repo).get("userName")
    return v if isinstance(v, str) and v.strip() else DEFAULT_USER


def docs_root(repo):
    return Path(repo) / _read(repo).get("docsRoot", DEFAULT_DOCS_ROOT)


PAINEL_BACKENDS = ("auto", "wezterm", "tmux", "herdr", "background")


def painel_backend(repo):
    """Backend dos painéis do modo paralelo (`painelBackend`): auto, wezterm, tmux ou background; inválido = auto."""
    v = _read(repo).get("painelBackend", "auto")
    return v if v in PAINEL_BACKENDS else "auto"


HERDR_DEFEITO = {"maxPanesPorTab": 2, "workspacePorProjeto": True}


def herdr(repo):
    """Config do backend herdr (`herdr.maxPanesPorTab` inteiro >= 1, `herdr.workspacePorProjeto` bool); inválido ou ausente = defeito."""
    raw = _read(repo).get("herdr")
    raw = raw if isinstance(raw, dict) else {}
    n, w = raw.get("maxPanesPorTab"), raw.get("workspacePorProjeto")
    return {"maxPanesPorTab": n if isinstance(n, int) and not isinstance(n, bool) and n >= 1 else HERDR_DEFEITO["maxPanesPorTab"],
            "workspacePorProjeto": w if isinstance(w, bool) else HERDR_DEFEITO["workspacePorProjeto"]}


COBERTURA_DIFF_DEFEITO = 85


def cobertura_diff(repo):
    """Limiar (%) da cobertura das linhas do diff (`qualidade.coberturaDiff`, número 0-100); inválido ou ausente = 85."""
    q = _read(repo).get("qualidade")
    v = q.get("coberturaDiff") if isinstance(q, dict) else None
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 100 else COBERTURA_DIFF_DEFEITO


FASES_PERFIL = ("pentest", "review")


def qualidade(repo):
    """Perfil `qualidade` ({bloqueantes, consultivos, fases}) ou None sem perfil (repo sem a chave: comportamento antigo).

    Há perfil se `qualidade.bloqueantes` ou `qualidade.consultivos` for uma lista. Entradas não-string/vazias e
    duplicados caem; `fases` (pentest|review exigidas pelo `pr_fechar`) tem defeito as duas.
    """
    q = _read(repo).get("qualidade")
    if not isinstance(q, dict) or not any(isinstance(q.get(k), list) for k in ("bloqueantes", "consultivos")):
        return None

    def cmds(k):
        vistos = []
        for c in q.get(k) if isinstance(q.get(k), list) else []:
            if isinstance(c, str) and c.strip() and c.strip() not in vistos:
                vistos.append(c.strip())
        return vistos

    bloq = cmds("bloqueantes")
    fases = q.get("fases")
    fases = [f for f in FASES_PERFIL if f in fases] if isinstance(fases, list) else list(FASES_PERFIL)
    return {"bloqueantes": bloq, "consultivos": [c for c in cmds("consultivos") if c not in bloq], "fases": fases}


FALHAS_SEGUIDAS_DEFEITO = 3


def orcamento(repo):
    """Orçamento da fila ({spUsd, diaUsd, falhasSeguidas}) ou None sem a chave `orcamento` (comportamento antigo).

    `spUsd`/`diaUsd`: número > 0, senão None (sem esse teto); `falhasSeguidas`: inteiro >= 1, defeito 3."""
    o = _read(repo).get("orcamento")
    if not isinstance(o, dict):
        return None

    def usd(k):
        v = o.get(k)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None

    f = o.get("falhasSeguidas")
    return {"spUsd": usd("spUsd"), "diaUsd": usd("diaUsd"),
            "falhasSeguidas": f if isinstance(f, int) and not isinstance(f, bool) and f >= 1 else FALHAS_SEGUIDAS_DEFEITO}


PROTEGIDOS_DEFEITO = ("MEMORY.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursor/rules/kaizen-flow.mdc")


def protected_files(repo: str | Path) -> list[str]:
    """Ficheiros de contexto protegidos (`protectedFiles`, lista de caminhos relativos); ausente ou inválido = defeito.

    Só se acrescenta/substitui por lista de strings não vazias; lista vazia desliga a guarda."""
    v = _read(repo).get("protectedFiles")
    if not isinstance(v, list):
        return list(PROTEGIDOS_DEFEITO)
    return [x.strip().replace("\\", "/") for x in v if isinstance(x, str) and x.strip()]


HOOKS_NAME = "kaizen-hooks.json"
EVENTS = ("sp.created", "sp.moved", "michi.phase.start", "michi.phase.end",
          "michi.gate.failed", "michi.commit", "michi.closed")


def hooks(repo):
    """Hooks válidos de `kaizen-hooks.json` (lista `hooks`); entradas inválidas são descartadas."""
    try:
        data = json.loads((Path(repo) / HOOKS_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    raw = data.get("hooks") if isinstance(data, dict) else None
    out = []
    for h in raw if isinstance(raw, list) else []:
        if not isinstance(h, dict) or h.get("event") not in EVENTS:
            continue
        cmd = h.get("cmd")
        if not isinstance(cmd, str) or not cmd.strip():
            continue
        modo = h.get("modo", "informativo")
        timeout = h.get("timeout", 10)
        cond = h.get("if", {})
        if modo not in ("bloqueante", "informativo") or isinstance(timeout, bool) \
                or not isinstance(timeout, (int, float)) or timeout <= 0 or not isinstance(cond, dict):
            continue
        if h.get("enabled", True) is not True:
            continue
        out.append({"event": h["event"], "cmd": cmd, "modo": modo, "timeout": timeout, "if": cond})
    return out


# Autorizações por destino (tabela única). Projeto não listado = vault.
DESTINOS_DEFEITO = {
    "vault": {"commit": "auto", "push": "auto", "pr": "nunca", "merge": "nunca"},
    "kaizen-flow": {"commit": "auto", "push": "auto", "pr": "auto", "merge": "auto"},
    "repo": {"commit": "auto", "push": "auto", "pr": "auto", "merge": "nunca"},
}
PROJETO_DESTINO = {"kaizenflow": "kaizen-flow", "kaizen-flow": "kaizen-flow", "atlas": "repo", "foodlister": "repo"}


def destino(repo, project):
    """Destino do `project` (vault|kaizen-flow|repo): `destinos` em kaizen.config.json sobrepõe a tabela; defeito vault."""
    over = _read(repo).get("destinos")
    if isinstance(over, dict) and over.get(project) in DESTINOS_DEFEITO:
        return over[project]
    return PROJETO_DESTINO.get(project, "vault")


def autorizacoes(repo, project):
    """Autorizações commit/push/pr/merge por defeito do destino do `project` (cópia)."""
    return dict(DESTINOS_DEFEITO[destino(repo, project)])


# Método de desenvolvimento do projeto (chave `desenvolvimento`).
METODOS = {
    "worktree-pr": {"commit": "auto", "push": "auto", "pr": "auto", "pr_vigia": True,
                    "pr_merge": "auto-se-verde"},
    "worktree-merge": {"commit": "auto", "push": "nunca", "pr": "nunca", "pr_vigia": False,
                       "pr_merge": "nunca"},
    "direto": {"commit": "pergunta", "push": "pergunta", "pr": "pergunta", "pr_vigia": False,
               "pr_merge": "pergunta"},
}
AUTH_VALORES = ("auto", "pergunta", "nunca")
PR_MERGE_VALORES = ("auto-se-verde", "pergunta", "nunca")
MERGE_ESTRATEGIAS = ("squash", "merge", "rebase")


def desenvolvimento(repo):
    """Método do projeto já resolvido (defeitos do método + sobreposições válidas) ou None sem método válido."""
    raw = _read(repo).get("desenvolvimento")
    if not isinstance(raw, dict) or raw.get("metodo") not in METODOS:
        return None
    out = {"metodo": raw["metodo"], "ramo_principal": "main", "merge_estrategia": "squash",
           **METODOS[raw["metodo"]]}
    rp = raw.get("ramo_principal")
    if isinstance(rp, str) and rp.strip():
        out["ramo_principal"] = rp.strip()
    for k in ("commit", "push", "pr"):
        if raw.get(k) in AUTH_VALORES:
            out[k] = raw[k]
    if isinstance(raw.get("pr_vigia"), bool):
        out["pr_vigia"] = raw["pr_vigia"]
    if raw.get("pr_merge") in PR_MERGE_VALORES:
        out["pr_merge"] = raw["pr_merge"]
    if raw.get("merge_estrategia") in MERGE_ESTRATEGIAS:
        out["merge_estrategia"] = raw["merge_estrategia"]
    return out


def metodo_autorizacoes(repo, ramo):
    """Autorizações commit/push/pr do método, ou None sem método.

    Guarda: com `ramo` igual ao `ramo_principal` (ou master/main) os `auto` voltam a `pergunta`.
    """
    d = desenvolvimento(repo)
    if d is None:
        return None
    no_principal = not ramo or ramo in (d["ramo_principal"], "main", "master")
    out = {}
    for k in ("commit", "push", "pr"):
        v = d[k]
        out[k] = "pergunta" if v == "auto" and no_principal else v
    return out
