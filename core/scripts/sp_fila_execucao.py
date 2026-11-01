"""Sp-fila: passo seguinte (registar o SP fechado, respeitar limites, lançar o próximo)."""
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402
from sp_fila_estado import REQ_POR_SP, SCRIPTS, bloqueio, guardar, ler, run_hidden
from sp_fila_plano import descendentes, falhas, limite, load, plan, sem_commit
from sp_fila_relatorio import progresso, relatorio


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
        feito = sp is not None and sp.status == "Done"
        (estado["feitos"] if feito else estado["falhados"]).append(fechada)
        estado["seguidas"] = 0 if feito else estado.get("seguidas", 0) + 1
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
        motivo = falhas(estado) if paralelo else limite(estado, agora, custo)
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
                estado["seguidas"] = estado.get("seguidas", 0) + 1
                break
        else:
            estado["sessoes"][alvo.slug] = {"inicio": agora.isoformat(timespec="seconds"), "requests": REQ_POR_SP,
                                            **_painel_lancado(alvo.slug, r.stdout)}
            estado["usados"] += REQ_POR_SP
            lancados.append(alvo)
            motivo = None
    if not lancados and not estado["sessoes"]:
        motivo = motivo or (falhas(estado) if paralelo else limite(estado, agora, custo)) or "fila vazia"
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


def _custos_seguros(custo_fn=None):
    try:
        return (custo_fn or _custos)()
    except Exception:  # a medição nunca pode impedir o fecho da fila
        return {}


def _custos():
    return kaizen_engine.load("sp-metricas").custo_por_slug()
