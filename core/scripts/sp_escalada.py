"""Escalada de modelo: na paragem por `gate-falha`, relança o SP uma vez no nível michi seguinte.

Ordem dos níveis em `.claude/modelos.json` (`michi_modelo`: simples → default → complexo → critico). Escala só
quando o painel acabou em `falhou`/`bloqueado`, o SP tem `## Paragem DA` (escrita pelo `da-stop.py`: só há
paragem DA por gate), `escalar: sim` (defeito por perfil: `normal`/`autonomo` sim, `cauteloso` não), ainda não
foi escalado (linha `- escalado:` no SP) e há nível acima. O relançamento usa a vaga do painel que falhou.
Regras: `.claude/skills/michi/references/michi-perfis.md` (coluna «Escalada»).

Uso: módulo importado por sp_vigia.py; sem execução direta
rc: n/a
"""
import contextlib
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_leitura  # noqa: E402

ESCALAR_POR_PERFIL = {"cauteloso": "nao", "normal": "sim", "autonomo": "sim"}
ESTADOS = ("falhou", "bloqueado")
REPORT = "## Report modo auto"
_PARAGEM = re.compile(r"^## Paragem DA\s*$", re.M)
_CAUSA = re.compile(r"^- Causa:\s*(.+?)\s*$", re.M)
_ESCALADO = re.compile(r"^- escalado: ", re.M)


def escalar_ativo(fm):
    """`escalar:` do SP; sem ele, o defeito do perfil (sem perfil = normal)."""
    v = (fm.get("escalar") or "").strip()
    if v in ("sim", "nao"):
        return v == "sim"
    return ESCALAR_POR_PERFIL.get(fm.get("perfil") or "normal", "sim") == "sim"


def causa_paragem(texto):
    """Causa da última `## Paragem DA` do SP; "" se a secção existe sem causa; None se não há paragem DA."""
    ms = list(_PARAGEM.finditer(texto or ""))
    if not ms:
        return None
    resto = texto[ms[-1].end():]
    fim = re.search(r"^## ", resto, re.M)
    c = _CAUSA.search(resto[:fim.start()] if fim else resto)
    return c.group(1) if c else ""


def ja_escalado(texto):
    return bool(_ESCALADO.search(texto or ""))


def deve_escalar(fm, estado):
    """Decisão pura. `estado`: {estado, paragem (causa|None), escalado (bool), seguinte (nível|None)}."""
    return (estado.get("estado") in ESTADOS and estado.get("paragem") is not None
            and not estado.get("escalado") and bool(estado.get("seguinte")) and escalar_ativo(fm))


def decidir(texto, estado_painel, data=None):
    """(de, para, causa) se o SP deve escalar; None caso contrário. `data`: modelos.json carregado (ordem dos níveis)."""
    import modelos
    fm = sp_leitura.frontmatter(texto or "")
    de = fm.get("michi_modelo") or "default"
    estado = {"estado": estado_painel, "paragem": causa_paragem(texto), "escalado": ja_escalado(texto),
              "seguinte": modelos.proximo_nivel(de, data)}
    if not deve_escalar(fm, estado):
        return None
    return de, estado["seguinte"], estado["paragem"] or "gate-falha"


def linha_report(de, para, causa, agora=None):
    agora = agora or datetime.now()
    return f"- escalado: {de} → {para} ({agora:%Y-%m-%d %H:%M}; causa: {causa})"


def registar_report(path, linha):
    """Acrescenta `linha` a `## Report modo auto` do SP (cria a secção no fim se faltar); mantém o EOL do ficheiro."""
    p = Path(path)
    raw = p.read_bytes()
    eol = b"\r\n" if b"\r\n" in raw else b"\n"
    texto = raw.decode("utf-8")
    nl = eol.decode()
    i = texto.find(REPORT + nl)
    if i < 0:
        sep = "" if texto.endswith(nl) else nl
        texto = f"{texto}{sep}{nl}{REPORT}{nl}{nl}{linha}{nl}"
    else:
        corpo = i + len(REPORT + nl)
        prox = re.search(r"^## ", texto[corpo:], re.M)
        fim = corpo + prox.start() if prox else len(texto)
        bloco = texto[corpo:fim].rstrip("\r\n")
        texto = texto[:corpo] + bloco + nl + linha + nl + (nl if prox else "") + texto[fim:]
    p.write_bytes(texto.encode("utf-8"))


def prompt_escalada(slug, worktree):
    """Prompt do painel relançado: o de sempre + ler `## Paragem DA` antes de retomar."""
    import sp_fila_paineis
    return (sp_fila_paineis.prompt_painel(slug, worktree)
            + " Escalada de modelo: lê primeiro `## Paragem DA` do SP (passo, tentativas, causa) e retoma desse passo.")


def relancar(slug, nivel, sp, fila, backend, run=None, sleep=time.sleep, estado_root=None):
    """Relança o painel do SP no `nivel`, na mesma worktree e na vaga do que falhou.

    `sp`: registo do painel ({pane, worktree, estado}). Devolve {estado: a-correr|falhou, modelo, pane, msg}."""
    import sp_fila_paineis as fp
    import sp_painel_estado as pe
    from painel_backend import enviar_prompt
    wt = sp.get("worktree")
    if not wt:
        return {"estado": "falhou", "msg": "sem worktree para relançar"}
    if sp.get("pane"):
        with contextlib.suppress(Exception):  # painel já fechado
            backend.fechar(sp["pane"])
    cmd = fp.comando_nivel(nivel)
    modelo = cmd[2]
    pe.transitar(slug, "pendente", msg=f"escalada para {nivel}", fila=fila, root=estado_root)
    if not pe.reclamar_vaga(slug, fila=fila, root=estado_root, modelo=modelo):
        pe.transitar(slug, "falhou", msg="escalada sem vaga", fila=fila, root=estado_root)
        return {"estado": "falhou", "modelo": modelo, "msg": "escalada sem vaga"}
    pane = None
    try:
        texto = prompt_escalada(slug, wt)
        interativo = getattr(backend, "interativo", True)
        pane = backend.abrir(cmd if interativo else cmd + [texto], wt)
        f = getattr(backend, "titulo", None)
        if f:
            f(pane, slug)
        if interativo:
            enviar_prompt(backend, pane, texto, run or fp.run_hidden, sleep)
        pe.registar(fila, slug, root=estado_root, pane=str(pane), modelo=modelo)
    except Exception as e:  # noqa: BLE001 — falha do relançamento = falha final do SP
        msg = f"erro na escalada de {slug}: {e}"
        pe.transitar(slug, "falhou", msg=msg, fila=fila, root=estado_root)
        if pane is not None:
            with contextlib.suppress(Exception):
                backend.fechar(pane)
        return {"estado": "falhou", "modelo": modelo, "msg": msg}
    return {"estado": "a-correr", "modelo": modelo, "pane": str(pane), "msg": None}


def registar_fila(estado_path, slug, de, para):
    """Regista a escalada no estado da sp-fila (relatório e `--gastos`) e conta os pedidos do painel novo."""
    from sp_fila_estado import REQ_POR_SP, bloqueio, guardar, ler
    p = Path(estado_path)
    if not p.exists():
        return False
    with bloqueio(p):
        estado = ler(p)
        estado.setdefault("escaladas", []).append({"slug": slug, "de": de, "para": para})
        estado["usados"] = estado.get("usados", 0) + REQ_POR_SP
        guardar(p, estado)
    return True
