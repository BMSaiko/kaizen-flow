#!/usr/bin/env python3
"""Fila autónoma de SPs: escolhe o próximo SP elegível e lança-o (modo auto, sessão limpa).

Elegível = TODO, `modo: auto`, com `gates:`, dependências em Done, autorizações suficientes. Ordem:
prioridade, depois idade, com `depends_on` a mandar. Nunca faz push/PR: isso é do fecho de cada SP.

Uso:
  python -I scripts/sp-fila.py --dry-run [--max N] [--ate HH:MM] [--projeto P]   # ordem e exclusões
  python -I scripts/sp-fila.py [--max N] [--ate HH:MM] [--projeto P] [--orcamento N]   # arranca a fila
  python -I scripts/sp-fila.py [--concorrencia N]   # modo paralelo: até N painéis via sp-handoff --spawn, sem orçamento nem máximo
  python -I scripts/sp-fila.py --programa <slug-mãe> [--max N]   # só a árvore da mãe; orçamento lido dela
  python -I scripts/sp-fila.py --seguinte [--slug S]   # no fecho de cada SP da fila: regista e lança o seguinte
  python -I scripts/sp-fila.py --gastos     # custo USD por sessão da corrida (só medição)
  python -I scripts/sp-fila.py --parar       # abandona a fila (apaga o estado)

O estado vive em `~/.claude/sp-fila-estado.json` (uma entrada por sessão em `sessoes`, escrita atómica e
bloqueio `.lock`; o formato antigo com `lancado` migra sozinho); no fim (fila vazia, limite ou erro) escreve o
relatório em `knowledge/infra/reports/sp-fila/` e apaga o estado. Um SP lançado que não chegou a Done
conta como falhado: os dependentes ficam de fora e só continuam os independentes.

Orçamento por programa: o SP-mãe pode ter `orcamento_horas`, `orcamento_usd`, `orcamento_requests` no
frontmatter. Contam por corrida (retomar = nova corrida): tempo desde o arranque, custo USD das sessões
`/michi` da árvore (sp-metricas.custo_por_slug) e requests. Ao parar acrescenta `## Progresso (sessão <data>)`
à mãe (feitos, falhados, por correr) além do relatório.
"""
import argparse
import json
from urllib.parse import unquote
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402

sp_list = kaizen_engine.load("sp-list")
REPO = Path(__file__).resolve().parent.parent
_cfg = kaizen_engine.load("kaizen_config")
USER = _cfg.user_name(REPO)
SCRIPTS = Path(__file__).resolve().parent
ESTADO = Path.home() / ".claude" / "sp-fila-estado.json"
RELATORIOS = REPO / "knowledge" / "infra" / "reports" / "sp-fila"
REQ_POR_SP = 50  # unidade de contagem do teto opt-in (--orcamento / orcamento_requests); por defeito sem limite
ORCAMENTO = None  # sem limite de requests
MAX_DEFEITO = 5
LOCK_VELHO_S = 60  # um bloqueio mais antigo é de uma sessão morta


NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_hidden(*args, **kwargs):
    """subprocess.run sem janela de consola no Windows: o vigia chama wezterm/git a cada ciclo e as janelas piscavam."""
    kwargs.setdefault("creationflags", NO_WINDOW)
    return subprocess.run(*args, **kwargs)


@contextmanager
def bloqueio(path, espera=15.0):
    """Exclusão mútua entre sessões sobre `path`: ficheiro `<path>.lock` criado com O_CREAT|O_EXCL."""
    lock = Path(f"{path}.lock")
    limite_t = time.monotonic() + espera
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except (FileExistsError, PermissionError):  # Windows: PermissionError se o dono está a apagar o .lock
            try:
                if time.time() - lock.stat().st_mtime > LOCK_VELHO_S:
                    lock.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.monotonic() > limite_t:
                raise TimeoutError(f"estado bloqueado há demasiado tempo: {lock}")
            time.sleep(0.02)
    try:
        yield
    finally:
        for tentativa in range(100):
            try:
                lock.unlink(missing_ok=True)
                break
            except PermissionError:  # Windows: antivírus/indexador seguram o .lock; largar sem o apagar bloquearia os outros
                if tentativa == 99:
                    raise
                time.sleep(0.02)


def migrar(estado):
    """Formato antigo (`lancado`: um slug) → `sessoes`: {slug: {inicio, ...}} (uma entrada por SP em curso)."""
    antigo = estado.pop("lancado", None)
    estado.setdefault("sessoes", {})
    if antigo:
        estado["sessoes"].setdefault(antigo, {})
    return estado


def ler(path):
    return migrar(json.loads(Path(path).read_text(encoding="utf-8")))


def guardar(path, estado):
    """Escrita atómica: ficheiro temporário + os.replace (um leitor nunca vê JSON a meio)."""
    tmp = Path(f"{path}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    for tentativa in range(500):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows: um leitor sem bloqueio (painel, estado-vivo) tem o destino aberto
            if tentativa == 499:
                raise
            time.sleep(0.02)


def atualizar(path, fn):
    """Ler-alterar-escrever o estado sob bloqueio; `fn(estado)` altera-o no sítio."""
    with bloqueio(path):
        estado = ler(path)
        fn(estado)
        guardar(path, estado)
        return estado


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


def gastos(estado, custos):
    """[(slug, USD)] das sessões da corrida (em curso, feitas e falhadas) e o total. Só mede, nunca limita."""
    slugs = [*estado.get("sessoes", {}), *estado.get("feitos", []), *estado.get("falhados", [])]
    linhas = [(s, custos.get(s, 0.0)) for s in dict.fromkeys(slugs)]
    return linhas, sum(c for _, c in linhas)


def render_gastos(estado, custos):
    linhas, total = gastos(estado, custos)
    corpo = [f"  {s}: {c:.2f}" for s, c in linhas] or ["  (nenhuma sessão)"]
    return "\n".join(["Gasto por sessão (USD equivalente API, só medição):", *corpo, f"  total: {total:.2f}"])


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


def commits_desde(inicio, run):
    out = run(["git", "-C", str(REPO), "log", f"--since={inicio}", "--format=%h %s"], capture_output=True,
              text=True, encoding="utf-8").stdout or ""
    return [ln for ln in out.splitlines() if ln.strip()]


def reflect_lacunas(slug, texto):
    """Linhas `Reflect ...` do SP com gap (as «sem patch» não contam), prefixadas pelo slug."""
    return [f"{slug}: {l.strip()}" for l in texto.splitlines()
            if l.startswith("Reflect ") and not l.rstrip(". ").endswith("sem patch")]


def relatorio(estado, fila, excluidos, motivo, rel_dir, run, agora, custos=None, sps=None):
    rel_dir.mkdir(parents=True, exist_ok=True)
    path = rel_dir / f"fila-{agora:%Y-%m-%d-%H%M}.md"
    commits = commits_desde(estado["inicio"], run)
    listar = lambda xs: [f"- {x}" for x in xs] or ["- nenhum"]
    linhas = ["---", "type: report", "tags: [sp-fila]", f"date: {agora:%Y-%m-%d}", "---",
              f"# Fila de SPs ({agora:%Y-%m-%d %H:%M})", "", f"Fim: {motivo}.", "",
              "## Feitos", *listar(estado["feitos"]), "", "## Falhados", *listar(estado["falhados"]), "",
              "## Saltados", *listar(f"{s}: {w}" for s, w in excluidos), "", "## Gasto", *listar(
                  f"{s}: {c:.2f} USD" for s, c in gastos(estado, custos or {})[0]), "", "## Commits", *listar(commits), "",
              "## Reflect (lacunas)", *listar(l for s, (_, t) in (sps or {}).items() for l in reflect_lacunas(s, t)), "",
              "## Falhas", *listar(f"{s}: não chegou a Done (fase {sps[s][0]})" if s in (sps or {}) else f"{s}: não chegou a Done"
                                   for s in estado["falhados"]), "",
              "## Próximos passos"]
    passos = [f"inspecionar o SP falhado `{s}` (continua em Doing) e correr `/michi` à mão" for s in estado["falhados"]]
    passos += [f"por correr: `{sp.slug}`" for sp in fila if sp.slug not in estado["falhados"]]
    passos += ["rever os saltados e, se fizer sentido, dar-lhes `modo: auto` e `gates:`"] if excluidos else []
    linhas += listar(passos) + [""]
    path.write_text("\n".join(linhas), encoding="utf-8")
    return path


def progresso(mae_path, estado, fila, motivo, agora):
    """Acrescenta `## Progresso (sessão <data>)` à mãe: feitos, falhados, por correr."""
    listar = lambda xs: [f"- {x}" for x in xs] or ["- nenhum"]
    porcorrer = [sp.slug for sp in fila if sp.slug not in estado["falhados"]]
    linhas = ["", f"## Progresso (sessão {agora:%Y-%m-%d %H:%M})", "", f"Paragem: {motivo}.", "", "Feitos:",
              *listar(estado["feitos"]), "", "Falhados:", *listar(estado["falhados"]), "", "Por correr:",
              *listar(porcorrer), ""]
    with Path(mae_path).open("a", encoding="utf-8") as f:
        f.write("\n".join(linhas))


def seguinte(root, estado_path, rel_dir, run=run_hidden, agora=None, custo_fn=None, slug=None):
    """Regista o SP que fechou, respeita os limites e lança o seguinte. Devolve {acao, ...}.

    `slug`: só essa sessão fecha (as outras continuam); sem ele fecham todas as registadas (formato antigo).
    Com sessões ainda em curso não lança nada (`acao: espera`) até haver teto de concorrência."""
    with bloqueio(estado_path):
        return _seguinte(root, estado_path, rel_dir, run, agora or datetime.now(), custo_fn, slug)


def _ler_sp(sp):
    """Texto do SP onde estiver agora: o `sp-move` pode tê-lo mudado de pasta depois do `load`."""
    for pasta in (sp.path.parent, *(sp.path.parent.parent / n for n in ("Doing", "Done", "TODO"))):
        f = pasta / sp.path.name
        if f.is_file():
            return f.read_text(encoding="utf-8")
    return ""


def _cwd_neutro(root):
    """Checkout principal (master): `sp-move doing` aí não reclama o SP para o agente do worktree que orquestra; quem reclama é o `sb-worktree ensure` do spawn."""
    r = run_hidden(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"], capture_output=True, text=True)
    return Path(r.stdout.strip()).parent if r.returncode == 0 and r.stdout.strip() else None


def _seguinte(root, estado_path, rel_dir, run, agora, custo_fn, slug):
    estado = ler(estado_path)
    items = load(root, estado.get("projeto"))
    so = descendentes(items, estado["programa"]) if estado.get("programa") else None
    for fechada in ([slug] if slug else list(estado["sessoes"])):
        if fechada not in estado["sessoes"]:
            continue
        sp = next((s for s, _ in items if s.slug == fechada), None)
        (estado["feitos"] if sp is not None and sp.status == "Done" else estado["falhados"]).append(fechada)
        del estado["sessoes"][fechada]
    # Paralelo (--concorrencia N): sem orçamento nem máximo; o único travão é o guard de contexto, que continua a sessão por handoff.
    paralelo = bool(estado.get("concorrencia"))
    teto = estado.get("concorrencia") or 1
    if len(estado["sessoes"]) >= teto:
        guardar(estado_path, estado)
        return {"acao": "espera", "sessoes": list(estado["sessoes"])}
    fila, excluidos = plan(items, so=so, por_commitar=sem_commit(items))
    done = {sp.slug for sp, _ in items if sp.status == "Done"}
    custo = 0.0
    if estado.get("usd") is not None and not paralelo:
        custos = (custo_fn or _custos)()
        custo = sum(custos.get(s, 0.0) for s in so) - estado.get("custo_inicio", 0.0)
    lancados, motivo = [], None
    for alvo in (sp for sp in fila if all(d in done for d in sp.depends_on)):
        motivo = None if paralelo else limite(estado, agora, custo)
        if motivo or len(estado["sessoes"]) >= teto:
            break
        doing = alvo.path.parent.parent / "Doing" / alvo.path.name
        arranque = ([sys.executable, "-I", str(SCRIPTS / "sp-handoff.py"), "--spawn", alvo.slug, "--sem-registo"] if teto > 1
                    else [sys.executable, "-I", str(SCRIPTS / "sp-handoff.py"), "--launch", str(doing), "--auto"])
        cwd = _cwd_neutro(root) if teto > 1 else None
        for argv in ([sys.executable, "-I", str(SCRIPTS / "sp-move.py"), "--root", str(root), "--project", alvo.project, alvo.slug, "doing"], arranque):
            r = run(argv, capture_output=True, text=True, encoding="utf-8", cwd=cwd if argv[2].endswith("sp-move.py") else None)
            if r.returncode != 0:
                motivo = f"erro a lançar {alvo.slug}: {(r.stderr or r.stdout).strip()}"
                estado["falhados"].append(alvo.slug)
                break
        else:
            estado["sessoes"][alvo.slug] = {"inicio": agora.isoformat(timespec="seconds"), "requests": REQ_POR_SP,
                                            **_painel_lancado(alvo.slug, r.stdout)}
            estado["usados"] += REQ_POR_SP
            lancados.append(alvo)
            motivo = None
    if not lancados and not estado["sessoes"]:
        motivo = motivo or (None if paralelo else limite(estado, agora, custo)) or "fila vazia"
        sps = {sp.slug: (sp.status, _ler_sp(sp)) for sp, _ in items
               if sp.slug in estado["feitos"] + estado["falhados"]}
        path = relatorio(estado, fila, excluidos, motivo, rel_dir, run, agora, _custos_seguros(custo_fn), sps)
        if estado.get("programa"):
            mae = next((sp for sp, _ in items if sp.slug == estado["programa"]), None)
            if mae is not None:
                progresso(mae.path, estado, fila, motivo, agora)
        Path(estado_path).unlink()
        return {"acao": "fim", "motivo": motivo, "relatorio": str(path)}
    guardar(estado_path, estado)
    if not lancados:
        return {"acao": "espera", "sessoes": list(estado["sessoes"])}
    alvo = lancados[0]
    return {"acao": "lancou", "slug": alvo.slug, "slugs": [sp.slug for sp in lancados],
            "caminho": str(alvo.path.parent.parent / "Doing" / alvo.path.name)}


def _painel_lancado(slug, saida):
    """{painel, worktree} lidos da linha `<slug>: painel <id> em <worktree>` do `sp-handoff --spawn`; {} se não houver."""
    m = re.search(rf"^{re.escape(slug)}: painel (\S+) em (.+)$", saida or "", re.MULTILINE)
    return {"painel": m.group(1), "worktree": m.group(2).strip()} if m and m.group(1) != "-" else {}


INATIVIDADE_S = 600  # sem ecrã novo nem commit há mais disto = sessão bloqueada
ARRANQUE_S = 120  # até aqui, sem prompt do Claude Code (ou sem painel registado) = sessão ainda a arrancar
TURNO_ACABADO = re.compile(r"\bdone \d{1,2}:\d{2}\b")  # linha «done HH:MM» que o Claude Code deixa quando o turno acaba
PERGUNTAS = ("Do you want to", "(y/n)", "Esc to cancel", "Enter to confirm")  # prompts que esperam resposta do utilizador
VIVO = re.compile(r"esc to interrupt|^\s*[✻✶✳✢✽·*]\s+\S+…", re.MULTILINE | re.IGNORECASE)  # spinner do Claude Code: o painel está a trabalhar
REAVISO_S = 900  # «bloqueado» repetido só a cada 15 min enquanto nada mudar


def _resumo_pedido(ecra):
    """Uma linha `comando — motivo` do bloco de permissão (as linhas entre o cabeçalho da ferramenta e «Do you want to»); '' se não houver."""
    linhas = [ln.strip() for ln in ecra.splitlines()]
    fim = next((i for i, ln in enumerate(linhas) if "Do you want to" in ln), None)
    if fim is None:
        return ""
    bloco = []
    for ln in reversed(linhas[:fim]):
        if not ln:
            if bloco:
                break
            continue
        bloco.append(ln)
    bloco.reverse()
    if len(bloco) > 1 and len(bloco[0].split()) <= 3:  # cabeçalho tipo «Bash command», «Edit file»
        bloco = bloco[1:]
    return " — ".join(bloco[:2])


def classificar(sessao, sp_status, paineis, ecra, atividade, agora, inatividade_s=INATIVIDADE_S):
    """(estado, motivo) de uma sessão: fechado (SP Done), morto (sem painel vivo), bloqueado (pergunta pendente ou inativa) ou a correr."""
    if sp_status == "Done":
        return "fechado", "SP em Done"
    painel = sessao.get("painel")
    idade = (agora - datetime.fromisoformat(sessao["inicio"]).replace(tzinfo=None)).total_seconds() if sessao.get("inicio") else None
    recente = idade is not None and idade < ARRANQUE_S
    if painel is None or str(painel) not in paineis:
        return ("a arrancar", "painel ainda não aberto") if recente else ("morto", "painel inexistente")
    if recente and "❯" not in ecra:
        return "a arrancar", "Claude Code ainda sem prompt"
    if any(p in ecra for p in PERGUNTAS):
        pergunta = next((ln.strip() for ln in ecra.splitlines() if any(p in ln for p in PERGUNTAS)), "")
        if "Do you want to" in ecra and re.search(r"^\s*(?:❯\s*)?1\.\s*Yes", ecra, re.MULTILINE):  # pedido de permissão de uma ferramenta
            return "bloqueado", f"precisa de aprovação do {USER}: {(_resumo_pedido(ecra) or pergunta)[:120]}"
        return "bloqueado", f"à espera de resposta: {pergunta[:80]}"
    ultimas = "\n".join([ln for ln in ecra.splitlines() if ln.strip()][-14:])
    if VIVO.search(ultimas):  # spinner visível: a trabalhar, por muito que o SP e a worktree estejam quietos
        return "a correr", ""
    if TURNO_ACABADO.search(ultimas):
        return "parada sem fechar", "turno acabado e SP ainda em Doing"
    parado = (agora - atividade).total_seconds()
    if parado > inatividade_s:
        return "bloqueado", f"inativa há {int(parado // 60)} min"
    return "a correr", ""


def _atividade(sessao, run, inicio_fila=None):
    """Instante mais recente entre o início da sessão (ou da fila, em formato antigo) e o último commit da worktree (só leitura)."""
    ult = datetime.fromisoformat(sessao.get("inicio") or inicio_fila or "1970-01-01T00:00:00").replace(tzinfo=None)
    if sessao.get("worktree"):
        try:
            r = run(["git", "-C", sessao["worktree"], "log", "-1", "--format=%ct"], capture_output=True, text=True, encoding="utf-8")
            ult = max(ult, datetime.fromtimestamp(int(r.stdout.strip())))
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return ult


def _norm_caminho(caminho):
    """Caminho comparável: sem `file://`, com `/`, minúsculas e sem barra final (cwd do wezterm vs. worktree registada)."""
    c = unquote(str(caminho)).replace("\\", "/")
    c = re.sub(r"^file://(?:[^/]*)/(?=[A-Za-z]:)", "", c)
    return c.rstrip("/").lower()


def estado_vivo(estado, items, run, agora, inatividade_s=INATIVIDADE_S):
    """[(slug, estado, motivo)] por sessão da corrida; só lê `wezterm cli list|get-text`, os SPs e o `git log` da worktree."""
    try:
        lista = json.loads(run(["wezterm", "cli", "list", "--format", "json"], capture_output=True, text=True, encoding="utf-8").stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        lista = []
    paineis = {str(p["pane_id"]) for p in lista}
    por_cwd = {_norm_caminho(p.get("cwd")): str(p["pane_id"]) for p in lista if p.get("cwd")}
    status = {sp.slug: sp.status for sp, _ in items}
    linhas = []
    for slug, sessao in estado["sessoes"].items():
        if str(sessao.get("painel")) not in paineis and sessao.get("worktree"):  # registo desatualizado: o painel vivo é o que está na worktree
            achado = por_cwd.get(_norm_caminho(sessao["worktree"]))
            if achado:
                sessao = {**sessao, "painel": achado}
        ecra = ""
        if str(sessao.get("painel")) in paineis:
            ecra = run(["wezterm", "cli", "get-text", "--pane-id", str(sessao["painel"])], capture_output=True, text=True, encoding="utf-8").stdout
        est, motivo = classificar(sessao, status.get(slug), paineis, ecra, _atividade(sessao, run, estado.get("inicio")), agora, inatividade_s)
        linhas.append((slug, est, motivo))
    return linhas


VIGIA_LOG = Path.home() / ".claude" / "sp-fila-vigia.log"
BATIDA_MAX_S = 180  # heartbeat mais velho que isto = vigia parado (ciclo medido 25-45 s, picos ~2 min com a máquina ocupada)


def batida_vigia(estado_path, agora=datetime.now):
    """Regista `vigia = {pid, ts}` no estado; não faz nada se a fila já acabou."""
    def fn(e):
        e["vigia"] = {"pid": os.getpid(), "ts": agora().isoformat(timespec="seconds")}
    try:
        atualizar(estado_path, fn)
    except (OSError, ValueError):
        pass


def aviso_vigia(estado, agora):
    """Aviso (str) quando há sessões em curso e o vigia não existe ou deixou de bater; None se está tudo coberto."""
    if not estado.get("sessoes"):
        return None
    vigia = estado.get("vigia")
    if not vigia:
        return "AVISO: SEM VIGIA com sessões a correr; arrancar já `python -I scripts/sp-fila.py --vigiar --destacado`"
    idade = (agora - datetime.fromisoformat(vigia["ts"])).total_seconds()
    if idade > BATIDA_MAX_S:
        return f"AVISO: o VIGIA PAROU (última batida há {int(idade // 60)} min {int(idade % 60)} s); rearmar com `python -I scripts/sp-fila.py --vigiar --destacado`"
    return None


def destacar(args, log, popen=subprocess.Popen):
    """Arranca `sp-fila.py <args>` num processo próprio (fora do prazo do Monitor), com a saída em `log`."""
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == "nt" else 0
    saida = open(log, "a", encoding="utf-8")
    return popen([sys.executable, "-I", str(Path(__file__).resolve()), *args], stdin=subprocess.DEVNULL, stdout=saida,
                 stderr=subprocess.STDOUT, creationflags=flags, **({} if os.name == "nt" else {"start_new_session": True}))


_AVISO = {"a arrancar": "arrancou", "a correr": "a correr", "fechado": "terminou", "morto": "morreu", "parada sem fechar": "PARADA SEM FECHAR"}


def linha(slug, estado, acao=""):
    """Formato único e curto de uma linha do orquestrador: `slug · estado · ação` (ação numa só linha, sem excesso)."""
    return " · ".join([slug, estado] + ([" ".join(acao.split())] if acao and acao.split() else []))


def _chave(est, motivo):
    """Identidade de um estado para deduplicar: «inativa há N min» é o mesmo estado ao longo dos minutos."""
    return (est, re.sub(r"\d+", "N", motivo) if motivo.startswith("inativa há") else motivo)


def vigiar(ler_estado, intervalo_s, espera, saida, passou_o_fim=lambda: False, batida=lambda: None, fechar_painel=lambda slug: None, relogio=time.monotonic, lancar_seguinte=lambda slug: (False, "")):
    """Repete `ler_estado()` ([(slug, estado, motivo)] ou None se a fila acabou) e emite só as mudanças por sessão.

    «bloqueado» por inatividade (ou outro igual) só se repete a cada `REAVISO_S`; qualquer outra transição emite logo.

    `fechar_painel(slug)` corre uma vez quando a sessão passa a «fechado» (SP em Done): o painel já não faz falta.
    `lancar_seguinte(slug)` corre logo a seguir e devolve `(lançou, razão)`: a razão vai numa linha `slug · fila · razão`;
    se lançou, a vigia continua (o estado já tem a sessão nova) em vez de sair por «todas fechadas».

    Sai (0) quando todas as sessões estão fechadas, mortas ou paradas sem fechar, quando a fila desaparece ou quando `passou_o_fim()` (--ate)."""
    ultimo, quando = {}, {}
    while True:
        relancou = False
        batida()  # heartbeat: prova no estado que o vigia está vivo
        linhas = ler_estado()
        if not linhas:
            return 0
        for slug, est, motivo in linhas:
            chave, agora = _chave(est, motivo), relogio()
            if ultimo.get(slug) == chave and (est != "bloqueado" or agora - quando[slug] < REAVISO_S):
                continue
            repetido = ultimo.get(slug) == chave
            ultimo[slug], quando[slug] = chave, agora
            razao = ""
            if est == "fechado":
                fechar_painel(slug)
                lancou, razao = lancar_seguinte(slug)
                relancou = relancou or lancou
            nome = (f"PRECISA DE APROVAÇÃO DO {USER.upper()}" if motivo.startswith("precisa de aprovação") else "À ESPERA DE RESPOSTA")                 if est == "bloqueado" and motivo.startswith(("à espera", "precisa de aprovação")) else _AVISO.get(est, est)
            saida(linha(slug, ("AINDA " if repetido else "") + nome, motivo))
            if est == "fechado" and razao:
                saida(linha(slug, "fila", razao))
        if not relancou and all(est in ("fechado", "morto", "parada sem fechar") for _, est, _ in linhas):  # parada: já reportada, precisa do utilizador
            return 0
        if passou_o_fim():
            saida("vigilância terminada: hora limite (--ate)")
            return 0
        espera(intervalo_s)


def fechar_painel_sessao(estado, slug, run):
    """Fecha o painel wezterm da sessão `slug` (registo no estado); o painel vivo é achado pela worktree se o id estiver velho."""
    sessao = ler(estado).get("sessoes", {}).get(slug) or {}
    try:
        lista = json.loads(run(["wezterm", "cli", "list", "--format", "json"], capture_output=True, text=True, encoding="utf-8").stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    ids = {str(p["pane_id"]) for p in lista}
    painel = str(sessao.get("painel"))
    if painel not in ids and sessao.get("worktree"):
        painel = next((str(p["pane_id"]) for p in lista if p.get("cwd") and _norm_caminho(p["cwd"]) == _norm_caminho(sessao["worktree"])), painel)
    if painel not in ids:
        return False
    run(["wezterm", "cli", "kill-pane", "--pane-id", painel], capture_output=True, text=True)
    return True


def lancar_seguinte_auto(root, estado, rel_dir, slug, seguinte_fn=seguinte):
    """`--seguinte --slug <slug>` por dentro: (lançou, razão numa linha). Nunca levanta: a vigia não pode morrer por isto."""
    try:
        out = seguinte_fn(root, estado, rel_dir, slug=slug)
    except Exception as e:
        return False, f"erro a lançar o seguinte: {e}"
    if out["acao"] == "lancou":
        return True, "lançou " + ", ".join(out["slugs"])
    if out["acao"] == "espera":
        return False, "a aguardar · " + ", ".join(out["sessoes"])
    return False, f"fila terminada: {out['motivo']}"


def contar_tails(run=subprocess.run):
    """Nº de `tail` a seguir o log da vigia (mais de 1 = Monitores duplicados, linhas repetidas); 0 se não der para ver."""
    cmd = (["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Process -Filter \"Name like 'tail%'\").CommandLine"]
           if os.name == "nt" else ["ps", "-eo", "args"])
    try:
        saida = run(cmd, capture_output=True, text=True, encoding="utf-8").stdout or ""
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0
    return sum(1 for l in saida.splitlines() if "sp-fila-vigia" in l and re.match(r'^\W*(?:.*[\\/])?tail(?:\.exe)?"?\s', l))


def _custos_seguros(custo_fn=None):
    try:
        return (custo_fn or _custos)()
    except Exception:  # a medição nunca pode impedir o fecho da fila
        return {}


def _custos():
    return kaizen_engine.load("sp-metricas").custo_por_slug()


AJUDA = """Orquestrador do sp-fila (regras):
- Vigia: `sp-fila.py --vigiar --destacado` (processo próprio; se já houver uma ativa não arma outra) e UM só Monitor `tail -F ~/.claude/sp-fila-vigia.log`; aos 30 min o novo substitui o anterior (parar o antigo primeiro).
- Ao ver um SP «fechado» a vigia fecha o painel e lança o seguinte sozinha (como `--seguinte --slug`), respeitando max, concorrência, ate, orçamento e dependências; se não lança, a razão fica no log (`slug · fila · razão`).
- Cada linha do log = `slug · estado · ação`; só mudanças (bloqueado repete-se a cada 15 min como «AINDA»).
- Relato por linha: ≤3 linhas + TLDR; não narrar avisos repetidos nem reler ecrãs.
- Pergunta/aprovação de painel: `wezterm cli get-text --pane-id N`, um AskUserQuestion («Painel N»), só depois `send-text --no-paste`; nunca aprovar sozinho.
- `--estado-vivo` avisa «SEM VIGIA»/«VIGIA PAROU» (rearmar) e «N Monitores» (deixar só um)."""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fila autónoma de SPs")
    ap.add_argument("--dry-run", action="store_true", help="mostra a ordem e as exclusões, sem lançar")
    ap.add_argument("--seguinte", action="store_true", help="no fecho de um SP da fila: regista e lança o seguinte")
    ap.add_argument("--slug", help="com --seguinte: o SP que fechou (só essa sessão; sem ele fecham todas)")
    ap.add_argument("--gastos", action="store_true", help="mostra o custo (USD) de cada sessão da corrida; só mede, não limita")
    ap.add_argument("--estado-vivo", action="store_true", help="classifica cada sessão da corrida (a correr, fechado, bloqueado, morto); só lê")
    ap.add_argument("--vigiar", action="store_true", help="repete o --estado-vivo e imprime só as mudanças (arrancou, à espera de resposta, terminou); sai quando todas acabam; só lê")
    ap.add_argument("--destacado", action="store_true", help="com --vigiar: corre o vigia num processo próprio (sobrevive ao Monitor) e escreve em ~/.claude/sp-fila-vigia.log")
    ap.add_argument("--intervalo", type=int, default=20, metavar="S", help="com --vigiar: segundos entre leituras")
    ap.add_argument("--inatividade", type=int, default=INATIVIDADE_S // 60, metavar="MIN", help="com --estado-vivo: minutos sem atividade até «bloqueado»")
    ap.add_argument("--ajuda", action="store_true", help="regras do orquestrador (vigia, Monitor, perguntas dos painéis, relato)")
    ap.add_argument("--parar", action="store_true", help="abandona a fila")
    ap.add_argument("--max", type=int, default=MAX_DEFEITO, help=f"nº máximo de SPs (defeito {MAX_DEFEITO})")
    ap.add_argument("--ate", metavar="HH:MM", help="hora limite")
    ap.add_argument("--concorrencia", type=int, metavar="N", help="modo paralelo: até N sessões em painéis próprios, sem limite de quota (só o guard de contexto, via handoff)")
    ap.add_argument("--orcamento", type=int, default=ORCAMENTO, help=f"teto opcional de requests totais; cada SP gasta {REQ_POR_SP} (sem ele, sem limite)")
    ap.add_argument("--projeto")
    ap.add_argument("--programa", metavar="SLUG", help="só a árvore deste SP-mãe; orçamento lido do frontmatter dela")
    ap.add_argument("--root", default=str(sp_list.DEFAULT_ROOT), help=argparse.SUPPRESS)
    ap.add_argument("--estado", default=str(ESTADO), help=argparse.SUPPRESS)
    ap.add_argument("--relatorios", default=str(RELATORIOS), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    estado = Path(args.estado)

    if args.ajuda:
        print(AJUDA)
        return 0
    if args.parar:
        estado.unlink(missing_ok=True)
        print("fila abandonada")
        return 0
    if args.vigiar and args.destacado:
        if not estado.exists():
            print("erro: sem fila em curso", file=sys.stderr)
            return 1
        vivo = ler(estado).get("vigia")
        if vivo and not aviso_vigia({"sessoes": {"x": {}}, "vigia": vivo}, datetime.now()):
            print(f"vigia já ativo (pid {vivo['pid']}); log: {VIGIA_LOG}")
            return 0
        extra = [a for flag, val in (("--intervalo", args.intervalo), ("--inatividade", args.inatividade), ("--estado", args.estado), ("--root", args.root)) for a in (flag, str(val))]
        extra += (["--projeto", args.projeto] if args.projeto else []) + (["--ate", args.ate] if args.ate else [])
        proc = destacar(["--vigiar", *extra], VIGIA_LOG)
        print(f"vigia destacado (pid {proc.pid}); acompanhar com o Monitor: `tail -F {VIGIA_LOG}` (re-armar o tail aos 30 min); sem a fila a correr, sai sozinho")
        return 0
    if args.vigiar:
        def lido():
            return estado_vivo(ler(estado), load(args.root, args.projeto), run_hidden, datetime.now(), args.inatividade * 60) if estado.exists() else None
        fim = None
        if args.ate:
            h, m = map(int, args.ate.split(":"))
            fim = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
        return vigiar(lido, args.intervalo, time.sleep, lambda m: print(m, flush=True), lambda: fim is not None and datetime.now() >= fim,
                      lambda: batida_vigia(estado), lambda slug: fechar_painel_sessao(estado, slug, run_hidden),
                      lancar_seguinte=lambda slug: lancar_seguinte_auto(args.root, estado, Path(args.relatorios), slug))
    if args.estado_vivo:
        if not estado.exists():
            print("erro: sem fila em curso", file=sys.stderr)
            return 1
        atual = ler(estado)
        for slug, est, motivo in estado_vivo(atual, load(args.root, args.projeto), run_hidden, datetime.now(), args.inatividade * 60):
            print(linha(slug, est, motivo))
        if aviso := aviso_vigia(atual, datetime.now()):
            print(aviso)
        if (n := contar_tails()) > 1:
            print(f"AVISO: {n} Monitores `tail` sobre o log da vigia (linhas duplicadas); parar os antigos e deixar só um")
        return 0
    if args.gastos:
        if not estado.exists():
            print("erro: sem fila em curso", file=sys.stderr)
            return 1
        print(render_gastos(ler(estado), _custos()))
        return 0
    items = load(args.root, args.projeto)
    mae = None
    if args.programa:
        mae = next(((sp, fm) for sp, fm in items if sp.slug == args.programa), None)
        if mae is None:
            print(f"erro: SP-mãe desconhecido: {args.programa}", file=sys.stderr)
            return 1
        args.projeto = mae[0].project
        items = load(args.root, args.projeto)
    so = descendentes(items, args.programa) if args.programa else None
    if args.dry_run:
        fila, excluidos = plan(items, args.max, so, sem_commit(items))
        print(render_plan(fila, excluidos))
        return 0
    if args.seguinte:
        if not estado.exists():
            print("erro: sem fila em curso (arrancar com `sp-fila.py`)", file=sys.stderr)
            return 1
    else:
        if estado.exists():
            print(f"erro: fila já em curso ({estado}); `--seguinte` continua, `--parar` abandona", file=sys.stderr)
            return 1
        estado.parent.mkdir(parents=True, exist_ok=True)
        fm = mae[1] if mae else {}
        num = lambda k: float(fm[k]) if fm.get(k) not in (None, "") else None
        usd = num("orcamento_usd")
        novo = {"max": args.max, "concorrencia": max(1, args.concorrencia or 0) if args.concorrencia else None, "ate": args.ate, "orcamento": int(num("orcamento_requests") or args.orcamento or 0) or None,
                "usados": 0, "feitos": [], "falhados": [], "sessoes": {}, "projeto": args.projeto,
                "programa": args.programa, "horas": num("orcamento_horas"), "usd": usd,
                "inicio": datetime.now().isoformat(timespec="seconds")}
        if usd is not None:
            novo["custo_inicio"] = sum(_custos().get(s, 0.0) for s in so)
        guardar(estado, novo)
    out = seguinte(args.root, estado, Path(args.relatorios), slug=args.slug)
    if out["acao"] == "espera":
        print(f"a aguardar · {', '.join(out['sessoes'])}")
    elif out["acao"] == "lancou":
        print(f"lançado · {', '.join(out['slugs'])} · terminar o turno")
        if ler(estado).get("concorrencia"):
            print("VIGIAR · `sp-fila.py --vigiar --destacado` + um só Monitor `tail -F` ao log · regras: `sp-fila.py --ajuda`")
    else:
        print(f"fila terminada: {out['motivo']}\nrelatório: {out['relatorio']}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
