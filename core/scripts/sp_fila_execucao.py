"""Sp-fila: passo seguinte (registar o SP fechado, respeitar limites, lançar o próximo).

Uso: módulo importado por sp-fila.py; sem execução direta
rc: n/a
"""
import re
import sys
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kf_git  # noqa: E402
import kaizen_config  # noqa: E402
import kaizen_engine  # noqa: E402
import painel_backend  # noqa: E402
import sp_painel_estado as pe  # noqa: E402
from sp_fila_estado import RELATORIOS, REPO, REQ_POR_SP, SCRIPTS, bloqueio, guardar, ler, registar_sessao, run_hidden
import sp_fila_paineis  # noqa: E402
import sp_fila_subagents  # noqa: E402
from sp_fila_plano import aplicar_master, descendentes, limite, limite_paralelo, load, plan, sem_commit
from sp_fila_relatorio import destino_relatorio, escrever_commit_md, progresso, relatorio


def _backend_defeito():
    """Backend de painéis da config (`painelBackend` do kaizen.config.json); None se não houver (os testes trocam-no)."""
    return painel_backend.escolher(kaizen_config.painel_backend(REPO))


def falta_backend():
    """Mensagem de uma linha sobre o backend de painéis em falta."""
    return painel_backend.falta(kaizen_config.painel_backend(REPO))


def seguinte(root, estado_path, rel_dir, run=run_hidden, agora=None, custo_fn=None, slug=None, backend=None):
    """Regista o SP que fechou, respeita os limites e lança o seguinte. Devolve {acao, ...}.

    `slug`: só essa sessão fecha (as outras continuam); sem ele fecham todas as registadas (formato antigo).
    Com sessões ainda em curso não lança nada (`acao: espera`) até haver teto de concorrência.
    `backend`: painéis do modo paralelo (defeito: o da config, resolvido só quando há um SP a lançar)."""
    with ExitStack() as pilha:  # o lock é solto durante o spawn (`_seguinte` fecha-o e volta a prendê-lo) e solto no fim
        pilha.enter_context(bloqueio(estado_path))
        return _seguinte(root, estado_path, rel_dir, run, agora or datetime.now(), custo_fn, slug, pilha, backend)


def _fechar_painel(estado, slug, feito):
    """Liberta a vaga do painel do SP que fechou (done/falhou), se o `sp-estado` do painel ainda não o fez."""
    fila = estado.get("fila_paineis")
    if not fila:
        return
    try:
        if pe.ler(fila, slug)["estado"] not in pe.FINAIS:
            pe.transitar(slug, "done" if feito else "falhou", msg=None if feito else "fechado pela fila sem Done", fila=fila)
    except pe.ErroEstado:  # sem registo ou transição inválida: a fila continua
        pass


class SlugObrigatorio(ValueError):
    """Em modo paralelo `--seguinte` sem `--slug` fecharia sessões ainda vivas."""


class IntegracaoPendente(RuntimeError):
    """Um SP lançado está em Done só na worktree: fechar a fila agora daria um «fila vazia» falso."""


def _done_so_na_worktree(root, slug, run):
    """Caminho da worktree `agent/<nome>` do SP se aí o SP está em Done; None se não houver worktree ou o SP não estiver em Done lá."""
    nome = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")[:31].rstrip("-")  # igual a sb-worktree.name_of (o pacote kf não o inclui)
    r = kf_git.run(root, "worktree", "list", "--porcelain", run=run)
    atual = None
    for linha in (r.stdout or "").splitlines():
        if linha.startswith("worktree "):
            atual = linha[9:].strip()
        elif linha.strip() == f"branch refs/heads/agent/{nome}" and atual and Path(atual).resolve() != Path(root).resolve():
            if any(Path(atual).glob(f"**/sp/Done/{slug}*.md")):
                return atual
    return None


def _ler_sp(sp):
    """Texto do SP onde estiver agora: o `sp-move` pode tê-lo mudado de pasta depois do `load`."""
    for pasta in (sp.path.parent, *(sp.path.parent.parent / n for n in ("Doing", "Done", "TODO"))):
        f = pasta / sp.path.name
        if f.is_file():
            return f.read_text(encoding="utf-8")
    return ""


def _sp_move_na_worktree(root, worktree, alvo):
    """Delega em `sp_fila_paineis.sp_move_na_worktree` (um só sítio para o argv do `sp-move` na worktree)."""
    return sp_fila_paineis.sp_move_na_worktree(root, worktree, alvo)


def _mae_na_worktree(mae, run):
    """Ficheiro da mãe na worktree dela (`ensure`): o `## Progresso` nunca suja master (a prova real apanhou-o lá).

    Fora do repo (testes) é o próprio ficheiro; se o `ensure` falhar, None (sem progresso, master intacto)."""
    try:
        rel = Path(mae.path).resolve().relative_to(REPO.resolve())
    except ValueError:
        return mae.path
    try:
        wt = Path(sp_fila_subagents.lancar(mae.slug, run=run)["worktree"])
    except RuntimeError as e:
        print(f"aviso: sem `## Progresso` na mãe ({e})", file=sys.stderr)
        return None
    return wt / rel


def _seguinte(root, estado_path, rel_dir, run, agora, custo_fn, slug, pilha, backend=None):
    estado = ler(estado_path)
    if not slug and estado.get("concorrencia") and estado["sessoes"]:
        raise SlugObrigatorio("em modo paralelo `--seguinte` exige `--slug <SP que fechou>`; sem ele fecharia sessões ainda vivas")
    items = load(root, estado.get("projeto"))
    if estado.get("concorrencia"):  # worktrees atrasadas: o estado dos SPs é o de master
        aplicar_master(items)
    so = descendentes(items, estado["programa"]) if estado.get("programa") else None
    for fechada in ([slug] if slug else list(estado["sessoes"])):
        sp = next((s for s, _ in items if s.slug == fechada), None)
        if fechada in estado["sessoes"] and (sp is None or sp.status != "Done"):
            wt = _done_so_na_worktree(root, fechada, run)
            if wt:
                raise IntegracaoPendente(f"{fechada} está em Done só na worktree ({wt}), não em master; "
                                         f"integrar com `python -I scripts/sb-worktree.py merge {fechada}` e repetir `--seguinte`")
    for fechada in ([slug] if slug else list(estado["sessoes"])):
        if fechada not in estado["sessoes"]:
            continue
        sp = next((s for s, _ in items if s.slug == fechada), None)
        feito = sp is not None and sp.status == "Done"
        (estado["feitos"] if feito else estado["falhados"]).append(fechada)
        estado["seguidas"] = 0 if feito else estado.get("seguidas", 0) + 1
        del estado["sessoes"][fechada]
        _fechar_painel(estado, fechada, feito)
    # Paralelo (--concorrencia N): sem orçamento; só `--ate` e `--max` explícito; o único travão é o guard de contexto, que continua a sessão por handoff.
    teto = estado.get("concorrencia") or 1
    paralelo = bool(estado.get("concorrencia"))  # um só critério: com `concorrencia` (mesmo 1) lança num painel
    if len(estado["sessoes"]) >= teto:
        guardar(estado_path, estado)
        return {"acao": "espera", "sessoes": list(estado["sessoes"])}
    fila, excluidos = plan(items, so=so, por_commitar=sem_commit(items))
    # Sequencial: um filho que não chega a Done pára a cadeia (nada mais é lançado; o resto fica por correr).
    parada = (f"cadeia parada: {', '.join(estado['falhados'])} não chegou a Done"
              if estado.get("modo") == "sequencial" and estado["falhados"] else None)
    done = {sp.slug for sp, _ in items if sp.status == "Done"}
    custo = 0.0
    if estado.get("usd") is not None and not paralelo:
        custos = (custo_fn or _custos)()
        custo = sum(custos.get(s, 0.0) for s in so) - estado.get("custo_inicio", 0.0)
    lancados, itens, pendentes, motivo = [], [], [], None
    # Único decisor: nunca lançar SP já iniciado (Doing), nem um que a fila já lançou/fechou ou reservou (outro `--seguinte` corre enquanto o spawn tem o lock solto).
    for alvo in (sp for sp in ([] if parada else fila) if sp.status == "TODO" and all(d in done for d in sp.depends_on)):
        if alvo.slug in set(estado["sessoes"]) | set(estado["feitos"]) | set(estado["falhados"]):
            continue
        motivo = limite_paralelo(estado, agora) if paralelo else limite(estado, agora, custo)
        if motivo or len(estado["sessoes"]) >= teto:
            break
        if paralelo:
            backend = backend or _backend_defeito()
            if backend is None:
                motivo = falta_backend()
                break
            if not estado.get("fila_paineis"):
                estado["fila_paineis"] = sp_fila_paineis.garantir_fila(estado)
        doing = alvo.path.parent.parent / "Doing" / alvo.path.name
        inicio = agora.isoformat(timespec="seconds")
        registar_sessao(estado, alvo.slug, inicio, requests=REQ_POR_SP, reserva=True)  # reservar o slug antes de soltar o lock
        guardar(estado_path, estado)
        pilha.close()
        erro, item = None, None
        if paralelo:  # painel: vaga global, `ensure`, Doing só na worktree do filho (nunca o `sp-move` do orquestrador), painel com o modelo do SP
            try:
                item = sp_fila_paineis.lancar([alvo], estado["fila_paineis"], backend, run=run, root=root)[0]
            except Exception as e:  # noqa: BLE001 — registo das filas ilegível ou inválido: falha só este SP
                item = {"slug": alvo.slug, "estado": "falhou", "msg": f"erro a lançar {alvo.slug}: {e}"}
            if item["estado"] == "falhou":
                erro = item["msg"]
        else:
            r = run([sys.executable, "-I", str(SCRIPTS / "sp-move.py"), "--root", str(root), "--project", alvo.project, alvo.slug, "doing"],
                    capture_output=True, text=True, encoding="utf-8")
            if r.returncode != 0:
                erro = f"erro a lançar {alvo.slug}: {(r.stderr or r.stdout).strip()}"
            if not erro:
                r = run([sys.executable, "-I", str(SCRIPTS / "sp-handoff.py"), "--launch", str(doing), "--auto"], capture_output=True, text=True, encoding="utf-8")
                if r.returncode != 0:
                    erro = f"erro a lançar {alvo.slug}: {(r.stderr or r.stdout).strip()}"
        pilha.enter_context(bloqueio(estado_path))
        estado = ler(estado_path)  # outros `--seguinte` podem ter alterado o estado durante o spawn
        if item and item["estado"] == "pendente":  # sem vaga global: tira a reserva, não é falha; nada mais abre agora
            estado["sessoes"].pop(alvo.slug, None)
            pendentes.append(alvo.slug)
            motivo = None
            guardar(estado_path, estado)
            break
        if erro:
            motivo = erro
            estado["sessoes"].pop(alvo.slug, None)
            estado["falhados"].append(alvo.slug)
            estado["seguidas"] = estado.get("seguidas", 0) + 1
        else:
            registar_sessao(estado, alvo.slug, agora.isoformat(timespec="seconds"), requests=REQ_POR_SP,
                            **({"worktree": item["worktree"], "painel": True} if item else {}))
            estado["usados"] += REQ_POR_SP
            lancados.append(alvo)
            if item:
                itens.append(item)
            motivo = None
        guardar(estado_path, estado)
    if pendentes and not lancados:
        guardar(estado_path, estado)
        return {"acao": "espera", "sessoes": list(estado["sessoes"]), "pendentes": pendentes}
    if not lancados and not estado["sessoes"]:
        motivo = parada or motivo or (limite_paralelo(estado, agora) if paralelo else limite(estado, agora, custo)) or "fila vazia"
        sps = {sp.slug: (sp.status, _ler_sp(sp)) for sp, _ in items
               if sp.slug in estado["feitos"] + estado["falhados"]}
        rel_dir, wt_slug = destino_relatorio(rel_dir, agora, run)
        path = relatorio(estado, fila, excluidos, motivo, rel_dir, run, agora, _custos_seguros(custo_fn), sps)
        if wt_slug:
            escrever_commit_md(path.parents[len(RELATORIOS.relative_to(REPO).parts)], path, agora)
        if estado.get("programa"):
            mae = next((sp for sp, _ in items if sp.slug == estado["programa"]), None)
            alvo_mae = _mae_na_worktree(mae, run) if mae is not None else None
            if alvo_mae is not None:
                progresso(alvo_mae, estado, fila, motivo, agora)
        Path(estado_path).unlink()
        # Programa com a árvore toda em Done (em master): o principal fecha a mãe na worktree dela.
        fechar = estado.get("programa") if so and all(sp.status == "Done" for sp, _ in items if sp.slug in so) else None
        return {"acao": "fim", "motivo": motivo, "relatorio": str(path), "fechar_mae": fechar}
    guardar(estado_path, estado)
    if not lancados:
        return {"acao": "espera", "sessoes": list(estado["sessoes"])}
    alvo = lancados[0]
    return {"acao": "lancou", "slug": alvo.slug, "slugs": [sp.slug for sp in lancados], "itens": itens,
            "caminho": str(alvo.path.parent.parent / "Doing" / alvo.path.name)}


def _custos_seguros(custo_fn=None):
    try:
        return (custo_fn or _custos)()
    except Exception:  # a medição nunca pode impedir o fecho da fila
        return {}


def _custos():
    return kaizen_engine.load("sp-metricas").custo_por_slug()
