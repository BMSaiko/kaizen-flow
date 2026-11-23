"""Reação do vigia a `bloqueado`/`pergunta` recuperáveis (sem LLM): classifica a causa por regras e responde só ao que o SP cobre.

`causa(texto)` → "irreversivel" | "contexto" | "autorizacao" | "restricao" | None (regras sobre `msg`/`motivo`/ecrã).
`coberta(sp_texto, texto)` → cláusula do SP que autoriza explicitamente cada ação do `texto`, ou None.
`reagir(ctx, mem, sp)` aplica a reação (no máximo `MAX_REACOES` por SP, depois escala ao BMS): contexto → retoma no mesmo
painel; autorização/restrição coberta → confirmação ao painel e `a-correr`; o resto fica como está (só aviso do vigia).
Ações irreversíveis ou sensíveis nunca são respondidas.

Uso: módulo importado por sp_vigia.py; sem execução direta
rc: sem execução direta"""
import re

MAX_REACOES = 2
ECRA_LINHAS = 15

IRREVERSIVEL = re.compile(
    r"--force\b|push\s+-f\b|reset\s+--hard|\bnpm\s+publish\b|\bpublish\b|\btag\b|\.env\b|secret|segredo|credencia|"
    r"\.pem\b|\.key\b|id_rsa|alargar\s+(?:as\s+)?restri|rm\s+-rf|delete\s+branch|apagar\s+branch|\bforce\b", re.I)
CONTEXTO = re.compile(r"context-guard|\bcontexto\b|context\s+(?:window|limit)|limite\s+de\s+contexto", re.I)
AUTORIZACAO = re.compile(r"autoriza|permiss|permission|not\s+allowed|n[ãa]o\s+permitid|\bapprov", re.I)
RESTRICAO = re.compile(r"restri[çc]|proibid|constraint|forbidden", re.I)

# ação → termos que a identificam no motivo e no texto do SP
ACOES = {
    "worktree": ("worktree",),
    "branch": ("branch", "ramo"),
    "pr": ("pr", "pull request"),
    "merge": ("merge",),
    "push": ("push",),
    "commit": ("commit",),
    "instalar": ("npm install", "pip install", "instalar", "install"),
}
PERMISSIVA = re.compile(r"autoriza|permit", re.I)
RESTRITIVA = re.compile(r"\bnunca\b|\bnever\b|proibid|\bsem\b|n[ãa]o\s+(?:fazer|usar|criar)", re.I)


def _tem(termo, texto):
    return re.search(rf"(?<![\w-]){re.escape(termo)}(?![\w-])", texto, re.I) is not None


def acoes_em(texto):
    """Ações da tabela `ACOES` mencionadas no `texto`."""
    return [a for a, termos in ACOES.items() if any(_tem(t, texto) for t in termos)]


def causa(texto):
    """Causa do bloqueio/pergunta; irreversível ganha sempre (nunca se responde)."""
    if not texto:
        return None
    if IRREVERSIVEL.search(texto):
        return "irreversivel"
    if CONTEXTO.search(texto):
        return "contexto"
    if AUTORIZACAO.search(texto):
        return "autorizacao"
    if RESTRICAO.search(texto):
        return "restricao"
    return None


def _clausulas(sp_texto):
    """(permissivas, restritivas): cláusulas de `restricoes`/`permitir` (frontmatter) e linhas de `## Decisões`."""
    import sp_leitura
    fm = sp_leitura.frontmatter(sp_texto)
    fontes = []
    for chave in ("restricoes", "permitir"):
        valor = fm.get(chave) or ""
        partes = [p.strip() for p in valor.split(";") if p.strip()]
        fontes += [(p, chave == "permitir") for p in partes]
    dec = re.search(r"^## Decis[õo]es\s*$(.*?)(?=^## |\Z)", sp_texto, re.M | re.S)
    if dec:
        fontes += [(l.strip().lstrip("-*").strip(), False) for l in dec.group(1).splitlines() if l.strip()]
    perm, restr = [], []
    for clausula, sempre in fontes:
        if RESTRITIVA.search(clausula) and not (sempre or PERMISSIVA.search(clausula)):
            restr.append(clausula)
        elif sempre or PERMISSIVA.search(clausula):
            perm.append(clausula)
    return perm, restr


def coberta(sp_texto, texto):
    """Cláusulas que autorizam, sem ambiguidade, todas as ações do `texto`; None se há ação não coberta ou nenhuma ação."""
    acoes = acoes_em(texto)
    if not acoes:
        return None
    perm, restr = _clausulas(sp_texto)
    achadas = []
    for a in acoes:
        termos = ACOES[a]
        if any(_tem(t, c) for c in restr for t in termos):
            return None
        c = next((c for c in perm if any(_tem(t, c) for t in termos)), None)
        if c is None:
            return None
        achadas.append(c)
    return achadas


def _ecra(ctx, sp):
    ler = getattr(ctx.backend, "ecra", None)
    if ler is None or not sp.get("pane"):
        return ""
    try:
        texto = ler(sp["pane"]) or ""
    except Exception:  # noqa: BLE001 — sem ecrã, classifica só pelo estado
        return ""
    return "\n".join([l for l in str(texto).splitlines() if l.strip()][-ECRA_LINHAS:])


def _registar(ctx, sp, linha):
    ctx.log(linha)
    try:
        ctx.registar_reacao(sp, linha)
    except Exception as e:  # noqa: BLE001 — o registo no SP nunca pára o vigia
        ctx.log(f"registo da reação falhou: {e}")


def reagir(ctx, mem, sp):
    """Reage a `bloqueado`/`pergunta` por contexto ou autorização/restrição coberta. True se atuou (SP volta a `a-correr`)."""
    slug, pane = sp["slug"], sp.get("pane")
    base = f"{sp.get('msg') or ''}\n{sp.get('motivo') or ''}"
    tipo = causa(base)
    texto = base
    if tipo is None:
        texto = base + "\n" + _ecra(ctx, sp)
        tipo = causa(texto) if sp.get("estado") == "pergunta" else None
    if tipo is None or tipo == "irreversivel" or not pane:
        return False
    if ctx.backend.estado(pane) == "morto":
        return False
    reacoes = mem.setdefault("reacoes", {})
    n = reacoes.get(slug, 0)
    if n >= MAX_REACOES:
        if slug not in mem.setdefault("escalados_bms", []):
            mem["escalados_bms"].append(slug)
            _registar(ctx, sp, f"- vigia: {MAX_REACOES} reações esgotadas ({tipo}); escalado ao BMS")
        return False
    if tipo == "contexto":
        return _contexto(ctx, mem, sp, reacoes, n)
    sp_texto = ctx.texto_sp(sp) or ""
    achadas = coberta(sp_texto, texto)
    if not achadas:
        return False
    return _confirmar(ctx, mem, sp, reacoes, n, tipo, achadas)


def _transitar_a_correr(ctx, sp):
    try:
        ctx.retomar(sp["slug"], "vigia: reação automática")
    except Exception as e:  # noqa: BLE001 — sem vaga ou estado mudado: tenta no tick seguinte
        ctx.log(f"reação {sp['slug']} adiada: {e}")
        return False
    return True


def _contexto(ctx, mem, sp, reacoes, n):
    slug = sp["slug"]
    if not _transitar_a_correr(ctx, sp):
        return False
    reacoes[slug] = n + 1
    ok = False
    try:
        ok = bool(ctx.retomar_contexto(sp))
    except Exception as e:  # noqa: BLE001 — a falha conta como reação e fica registada
        ctx.log(f"retoma de contexto {slug} falhou: {e}")
    if not ok:
        ctx.pausar(slug, "contexto: handoff no painel falhou", "contexto", None)
    mem["avisos"].pop(slug, None)
    _registar(ctx, sp, f"- vigia: contexto → handoff no mesmo painel ({'ok' if ok else 'falhou'}; reação {n + 1}/{MAX_REACOES})")
    return ok


def _confirmar(ctx, mem, sp, reacoes, n, tipo, achadas):
    slug, pane = sp["slug"], sp["pane"]
    clausula = achadas[0]
    texto = f"Autorizado pelo SP ({clausula[:160]}). Continua."
    texto = re.sub(r"[\x00-\x1f\x7f]", " ", texto)
    if not _transitar_a_correr(ctx, sp):
        return False
    reacoes[slug] = n + 1
    if not ctx.backend.enviar(pane, texto):
        ctx.pausar(slug, sp.get("msg") or "", sp.get("motivo"), None)
        _registar(ctx, sp, f"- vigia: {tipo} coberta pelo SP, envio falhou; volta a bloqueado")
        return False
    mem["avisos"].pop(slug, None)
    _registar(ctx, sp, f"- vigia: {tipo} coberta pelo SP ({clausula[:80]}) → confirmação enviada (reação {n + 1}/{MAX_REACOES})")
    return True
