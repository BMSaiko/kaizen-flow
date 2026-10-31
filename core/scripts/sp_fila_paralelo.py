"""Sp-fila: modo paralelo (painéis wezterm): classificar sessões, vigia e fecho de painéis."""
import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sp_fila_estado import USER, atualizar, ler


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
    c = re.sub(r"^file://[^/]*/(?=[A-Za-z]:)", "", c)
    c = re.sub(r"^file://[^/]*(?=/)", "", c)
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


def contar_tails(run=subprocess.run):
    """Nº de `tail` a seguir o log da vigia (mais de 1 = Monitores duplicados, linhas repetidas); 0 se não der para ver."""
    cmd = (["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Process -Filter \"Name like 'tail%'\").CommandLine"]
           if os.name == "nt" else ["ps", "-eo", "args"])
    try:
        saida = run(cmd, capture_output=True, text=True, encoding="utf-8").stdout or ""
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0
    return sum(1 for l in saida.splitlines() if "sp-fila-vigia" in l and re.match(r'^\W*(?:.*[\\/])?tail(?:\.exe)?"?\s', l))
