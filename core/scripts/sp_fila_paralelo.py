"""Sp-fila: modo paralelo (painéis wezterm): classificar sessões, vigia e fecho de painéis."""
import json
import os
import re
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kf_git  # noqa: E402
import painel_backend  # noqa: E402
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
            r = kf_git.run(sessao["worktree"], "log", "-1", "--format=%ct", run=run)
            ult = max(ult, datetime.fromtimestamp(int(r.stdout.strip())))
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return ult


def _norm_caminho(caminho):
    """Caminho comparável: sem `file://`, com `/`, minúsculas e sem barra final (cwd do wezterm vs. worktree registada)."""
    c = unquote(str(caminho)).replace("\\", "/")
    c = re.sub(r"^file://[^/]*/(?=[A-Za-z]:)", "", c)
    c = re.sub(r"^file://[^/]*(?=/)", "", c)
    c = re.sub(r"^/{2,}", "/", c)
    return c.rstrip("/").lower()


def estado_vivo(estado, items, run, agora, inatividade_s=INATIVIDADE_S, backend=None):
    """[(slug, estado, motivo)] por sessão da corrida; só lê o backend de painéis (defeito wezterm), os SPs e o `git log` da worktree."""
    backend = backend or painel_backend.WeztermBackend(run)
    lista = backend.listar()
    paineis = set(lista)
    por_cwd = {_norm_caminho(cwd): id_ for id_, cwd in lista.items() if cwd}
    status = {sp.slug: sp.status for sp, _ in items}
    linhas = []
    for slug, sessao in estado["sessoes"].items():
        if str(sessao.get("painel")) not in paineis and sessao.get("worktree"):  # registo desatualizado: o painel vivo é o que está na worktree
            achado = por_cwd.get(_norm_caminho(sessao["worktree"]))
            if achado:
                sessao = {**sessao, "painel": achado}
        ecra = ""
        if str(sessao.get("painel")) in paineis:
            ecra = backend.ecra(sessao["painel"])
        est, motivo = classificar(sessao, status.get(slug), paineis, ecra, _atividade(sessao, run, estado.get("inicio")), agora, inatividade_s)
        linhas.append((slug, est, motivo))
    return linhas


VIGIA_LOG = Path.home() / ".claude" / "sp-fila-vigia.log"
BATIDA_MAX_S = 180  # heartbeat mais velho que isto = vigia parado (ciclo medido 25-45 s, picos ~2 min com a máquina ocupada)


def batida_vigia(estado_path, agora=datetime.now):
    """Regista `vigia = {pid, ts, incidentes}` no estado; não faz nada se a fila já acabou.

    Preserva os incidentes e junta «vigia parou N min» quando a batida anterior é mais velha que `BATIDA_MAX_S`."""
    def fn(e):
        antes, agora_ = e.get("vigia") or {}, agora()
        incidentes = list(antes.get("incidentes", []))
        if antes.get("ts"):
            idade = (agora_ - datetime.fromisoformat(antes["ts"])).total_seconds()
            if idade > BATIDA_MAX_S and e.get("sessoes"):
                incidentes.append(f"vigia parou {int(idade // 60)} min")
        e["vigia"] = {"pid": os.getpid(), "ts": agora_.isoformat(timespec="seconds"), "incidentes": incidentes}
    try:
        atualizar(estado_path, fn)
    except (OSError, ValueError):
        pass


def registar_incidente(estado_path, texto):
    """Acrescenta `texto` a `estado["vigia"]["incidentes"]` (sem duplicar); alimenta a secção `## Vigia` do relatório."""
    def fn(e):
        vigia = e.setdefault("vigia", {})
        incidentes = vigia.setdefault("incidentes", [])
        if texto not in incidentes:
            incidentes.append(texto)
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


def garantir_vigia(estado, armar, agora):
    """Idempotente: ('viva', pid) se a vigia bate a tempo; senão arma uma (`armar()` devolve o processo) e dá ('armada', pid)."""
    vivo = estado.get("vigia")
    if vivo and not aviso_vigia({"sessoes": {"x": {}}, "vigia": vivo}, agora):
        return "viva", vivo["pid"]
    return "armada", armar().pid

VIGIA_TAIL = f"tail -n 0 -F {VIGIA_LOG}"  # só linhas novas: nunca o histórico de filas anteriores
AVISO_TAIL = f"parar o Monitor `{VIGIA_TAIL}` antigo (já não há vigia a escrever)"


def _comando_pid(pid, run=subprocess.run):
    """Linha de comandos do processo `pid`; "" se não existe ou não dá para ver."""
    cmd = (["powershell", "-NoProfile", "-Command", f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"]
           if os.name == "nt" else ["ps", "-p", str(int(pid)), "-o", "args="])
    try:
        return (run(cmd, capture_output=True, text=True, encoding="utf-8").stdout or "").strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""


def parar_vigia(vigia, run=subprocess.run, matar=os.kill, eu=os.getpid):
    """Termina o processo da vigia registada (`estado["vigia"]`) e devolve (parou, mensagem numa linha).

    Só mata o pid registado e só se a linha de comandos for mesmo `sp-fila ... --vigiar` (pid morto ou reutilizado
    por outro processo: não toca em nada). Nunca se mata a si próprio: a vigia que fecha a fila sai sozinha."""
    try:
        pid = int((vigia or {}).get("pid"))
    except (TypeError, ValueError):
        return False, "sem vigia registada"
    if pid == eu():
        return False, "a vigia sai sozinha"
    comando = _comando_pid(pid, run)
    if "sp-fila" not in comando or "--vigiar" not in comando:
        return False, f"pid {pid} já não é a vigia (nada a parar)"
    try:
        matar(pid, signal.SIGTERM)
    except OSError as e:
        return False, f"não consegui parar a vigia (pid {pid}): {e}"
    return True, f"vigia parada (pid {pid}); {AVISO_TAIL}"


_AVISO = {"a arrancar": "arrancou", "a correr": "a correr", "fechado": "terminou", "morto": "morreu", "parada sem fechar": "PARADA SEM FECHAR"}


def linha(slug, estado, acao=""):
    """Formato único e curto de uma linha do orquestrador: `slug · estado · ação` (ação numa só linha, sem excesso)."""
    return " · ".join([slug, estado] + ([" ".join(acao.split())] if acao and acao.split() else []))


def _chave(est, motivo):
    """Identidade de um estado para deduplicar: «inativa há N min» é o mesmo estado ao longo dos minutos."""
    return (est, re.sub(r"\d+", "N", motivo) if motivo.startswith("inativa há") else motivo)


def vigiar(ler_estado, intervalo_s, espera, saida, passou_o_fim=lambda: False, batida=lambda: None, fechar_painel=lambda slug: None, relogio=time.monotonic, lancar_seguinte=lambda slug: (False, ""), incidente=lambda texto: None):
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
            if est in ("morto", "parada sem fechar"):
                incidente(f"{slug}: {'morto' if est == 'morto' else 'PARADA SEM FECHAR'}")
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



def painel_da_sessao(sessao, lista):
    """Id do painel vivo da sessão: o registado, ou (id velho) o que está na worktree; None se não há painel vivo. `lista` = {id: cwd} do backend."""
    painel = str(sessao.get("painel"))
    if painel not in lista and sessao.get("worktree"):
        painel = next((id_ for id_, cwd in lista.items() if cwd and _norm_caminho(cwd) == _norm_caminho(sessao["worktree"])), painel)
    return painel if painel in lista else None


def nome_painel(estado, painel_id):
    """Nome do painel `painel_id` para texto ao user: o título (ou slug) da sessão que o regista, com sufixo -2, -3 se outro id já usa o mesmo nome; «painel sem nome» se o id não está no mapa. Nunca devolve o id."""
    antes = {}
    for slug, sessao in (estado.get("sessoes") or {}).items():
        base = sessao.get("titulo") or slug
        if sessao.get("painel") is not None and str(sessao["painel"]) == str(painel_id):
            n = antes.get(base, 0) + 1
            return base if n == 1 else f"{base}-{n}"
        antes[base] = antes.get(base, 0) + 1
    return "painel sem nome"


def fechar_painel_sessao(estado, slug, run, backend=None):
    """Fecha o painel da sessão `slug` (registo no estado) pelo backend (defeito wezterm); o painel vivo é achado pela worktree se o id estiver velho."""
    backend = backend or painel_backend.WeztermBackend(run)
    sessao = ler(estado).get("sessoes", {}).get(slug) or {}
    painel = painel_da_sessao(sessao, backend.listar())
    return backend.fechar(painel) if painel is not None else False


def ecra_sessao(estado, slug, run, backend=None):
    """(ok, texto) com o ecrã do painel da sessão `slug`, sob o cabeçalho «Painel <slug>»; o user vê o nome, nunca o id."""
    backend = backend or painel_backend.WeztermBackend(run)
    sessao = ler(estado).get("sessoes", {}).get(slug)
    if sessao is None:
        return False, f"Painel {slug}: sem sessão registada na fila"
    painel = painel_da_sessao(sessao, backend.listar())
    if painel is None:
        return False, f"Painel {slug}: sem painel vivo"
    return True, f"Painel {slug}" + chr(10) + backend.ecra(painel)


def enviar_sessao(estado, slug, texto, run, backend=None):
    """(ok, texto) ao enviar `texto` + Enter ao painel da sessão `slug`; só envia a um painel vivo achado como em `ecra_sessao`; o user vê o nome, nunca o id."""
    backend = backend or painel_backend.WeztermBackend(run)
    sessao = ler(estado).get("sessoes", {}).get(slug)
    if sessao is None:
        return False, f"Painel {slug}: sem sessão registada na fila"
    painel = painel_da_sessao(sessao, backend.listar())
    if painel is None:
        return False, f"Painel {slug}: sem painel vivo"
    if not backend.enviar(painel, texto):
        return False, f"Painel {slug}: não deu para enviar"
    return True, f"Painel {slug}: enviado"


def contar_tails(run=subprocess.run):
    """Nº de `tail` a seguir o log da vigia (mais de 1 = Monitores duplicados, linhas repetidas); 0 se não der para ver."""
    cmd = (["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Process -Filter \"Name like 'tail%'\").CommandLine"]
           if os.name == "nt" else ["ps", "-eo", "args"])
    try:
        saida = run(cmd, capture_output=True, text=True, encoding="utf-8").stdout or ""
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0
    return sum(1 for l in saida.splitlines() if "sp-fila-vigia" in l and re.match(r'^\W*(?:.*[\\/])?tail(?:\.exe)?"?\s', l))


def resumo_arranque(estado, agora, vivos=()):
    """Linhas do estado antigo da fila (SP, painéis, aprovações pendentes, idade da vigia) para mostrar antes de aceitar `--parar` ou um arranque novo."""
    sessoes = estado.get("sessoes") or {}
    estados = {s: (e, m) for s, e, m in vivos}
    linhas = [f"estado antigo: {len(sessoes)} sessão(ões), início {estado.get('inicio', '?')}"]
    for slug, sess in sessoes.items():
        est, motivo = estados.get(slug, ("?", ""))
        linhas.append(f"  SP {slug} · painel {sess.get('painel', '-')} · {est}" + (f" · {motivo}" if motivo else ""))
    pendentes = [s for s, (e, m) in estados.items() if m.startswith(("precisa de aprovação", "à espera"))]
    linhas.append(f"  aprovações pendentes: {', '.join(pendentes) if pendentes else 'nenhuma'}")
    vigia = estado.get("vigia")
    if vigia:
        idade = int((agora - datetime.fromisoformat(vigia["ts"])).total_seconds())
        linhas.append(f"  vigia: última batida há {idade // 60} min {idade % 60} s" + (" (PARADA)" if idade > BATIDA_MAX_S else ""))
    else:
        linhas.append("  vigia: nunca armada")
    return "\n".join(linhas)
