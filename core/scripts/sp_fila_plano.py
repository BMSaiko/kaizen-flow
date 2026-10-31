"""Sp-fila: elegibilidade, ordem da fila (plan), limites e orçamento."""
import subprocess
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402
from sp_fila_estado import REQ_POR_SP, USER, run_hidden

sp_list = kaizen_engine.load("sp-list")


def load(root, project=None):
    """[(Sp, frontmatter)] de todos os SPs (incluindo Done, para saber as dependências cumpridas)."""
    items = []
    for sp in sp_list.collect(root, include_done=True):
        if project and sp.project != project:
            continue
        fm = sp_list.parse_frontmatter(sp.path.read_text(encoding="utf-8"))
        items.append((sp, fm))
    return items


def autorizacao(fm):
    """Motivo de exclusão por autorizações insuficientes, ou ''."""
    commit, push, pr = (fm.get(k, "") for k in ("commit", "push", "pr"))
    if push == "pergunta" or pr == "pergunta":
        return f"autorização insuficiente (push/pr «pergunta» precisa do {USER})"
    if push == "auto" and commit == "nunca":
        return "autorização insuficiente (push auto com commit nunca)"
    if pr == "auto" and push != "auto":
        return "autorização insuficiente (pr auto sem push auto)"
    return ""


def estatico(sp, fm):
    if sp.status == "Doing":
        return "já em Doing"
    if sp.kind == "program":
        return "programa (SP-mãe, só agrupador)"
    if fm.get("modo") != "auto":
        return f"modo {fm.get('modo') or 'em falta'} (só `modo: auto`)"
    if "gates" not in fm:
        return "sem gates no frontmatter"
    return autorizacao(fm)


def descendentes(items, mae):
    """Slugs dos SPs na árvore de `mae` (netos incluídos, sem a própria mãe)."""
    arvore, novos = set(), {mae}
    while novos:
        novos = {sp.slug for sp, _ in items if sp.parent in novos and sp.slug not in arvore and sp.slug != mae}
        arvore |= novos
    return arvore


def plan(items, maximo=None, so=None, por_commitar=()):
    """(fila ordenada, [(slug, motivo)]). Função pura, sem FS. `so`: só estes slugs são candidatos; `por_commitar`: slugs fora do HEAD."""
    done = {sp.slug for sp, _ in items if sp.status == "Done"}
    excluidos, cand = [], {}
    for sp, fm in items:
        if sp.status == "Done" or (so is not None and sp.slug not in so):
            continue
        why = estatico(sp, fm) or ("por commitar (SP fora do HEAD; a worktree nasceria sem ele)" if sp.slug in por_commitar else "")
        if why:
            excluidos.append((sp.slug, why))
        else:
            cand[sp.slug] = sp

    def chave(sp):
        return (sp.priority, sp.created is None, sp.created or sp_list.date.min, sp.slug)

    fila, feitos = [], set(done)
    while True:
        prontos = [sp for sp in cand.values() if sp.slug not in feitos and all(d in feitos for d in sp.depends_on)]
        if not prontos:
            break
        sp = min(prontos, key=chave)
        fila.append(sp)
        feitos.add(sp.slug)

    resto = {s: sp for s, sp in cand.items() if s not in feitos}
    bloqueados = {s: [d for d in sp.depends_on if d not in feitos and d not in resto] for s, sp in resto.items()}
    bloqueados = {s: ds for s, ds in bloqueados.items() if ds}
    mudou = True
    while mudou:
        mudou = False
        for s, sp in resto.items():
            if s not in bloqueados and (ds := [d for d in sp.depends_on if d in bloqueados]):
                bloqueados[s], mudou = ds, True
    for s in sorted(resto):
        if s in bloqueados:
            excluidos.append((s, f"dependência em falta ({', '.join(bloqueados[s])})"))
        else:
            excluidos.append((s, "ciclo de dependências"))
    return (fila[:maximo] if maximo else fila), sorted(excluidos)


def limite(estado, agora, custo=0.0):
    """Motivo para parar a fila, ou None. `custo`: USD gasto nesta corrida (só conta com orcamento_usd)."""
    if len(estado["feitos"]) + len(estado["falhados"]) + len(estado.get("sessoes", {})) >= estado["max"]:
        return f"atingido o máximo de {estado['max']} SPs"
    if estado.get("ate"):
        h, m = (int(x) for x in estado["ate"].split(":"))
        if (agora.hour, agora.minute) >= (h, m):
            return f"atingida a hora limite {estado['ate']}"
    if estado.get("horas") is not None:
        gastas = (agora - datetime.fromisoformat(estado["inicio"])).total_seconds() / 3600
        if gastas >= estado["horas"]:
            return f"orçamento de tempo esgotado ({gastas:.1f}/{estado['horas']} h)"
    if estado.get("usd") is not None and custo >= estado["usd"]:
        return f"orçamento de custo esgotado ({custo:.2f}/{estado['usd']} USD)"
    if estado.get("orcamento") is not None and estado["usados"] + REQ_POR_SP > estado["orcamento"]:
        return f"orçamento de requests esgotado ({estado['usados']}/{estado['orcamento']})"
    return None


def render_plan(fila, excluidos):
    linhas = ["Ordem de execução:"]
    linhas += [f"  {i}. {sp.slug} ({sp.project}, {sp.priority}, {sp.created or '?'})" for i, sp in enumerate(fila, 1)] or ["  (vazia)"]
    linhas.append("Excluídos:")
    linhas += [f"  - {slug}: {why}" for slug, why in excluidos] or ["  (nenhum)"]
    return "\n".join(linhas)


def sem_commit(items, run=run_hidden):
    """Slugs dos SPs cujo ficheiro não está no HEAD do repo (só leitura). Sem git ou fora de um repo: nenhum."""
    fora = set()
    for sp, _ in items:
        if sp.status == "Done":
            continue
        try:
            r = run(["git", "-C", str(sp.path.parent), "ls-tree", "--name-only", "HEAD", sp.path.name], capture_output=True, text=True, encoding="utf-8")
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0 and not r.stdout.strip():
            fora.add(sp.slug)
    return fora
