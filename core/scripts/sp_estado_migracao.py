"""Migração do estado antigo `~/.claude/sp-fila-estado.json` (estado único) para uma fila de `sp_painel_estado`.

`sp_painel_estado.migrar_antigo` delega aqui. Só stdlib.

Uso: módulo importado por sp_painel_estado; sem execução direta
rc: n/a
"""
import json
from datetime import datetime
from pathlib import Path

import sp_painel_estado as pe
from sp_disco import guardar

ErroEstado, ILEGIVEL, MAX_PARALELO, FINAIS = pe.ErroEstado, pe.ILEGIVEL, pe.MAX_PARALELO, pe.FINAIS
_LIMITES_ANTIGOS = ("max", "ate", "horas", "usd", "orcamento", "max_falhas", "concorrencia")


def migrar_antigo(path=None, root=None, agora=None):
    """Converte o `~/.claude/sp-fila-estado.json` (estado único) numa fila; devolve o fila-id ou None se não há ficheiro.

    O ficheiro antigo fica onde está (a série `sp-handoff --launch` ainda o usa). Recusa com `ErroEstado`:
    JSON ilegível, formato desconhecido, nomes inválidos, fila já migrada ou sessões que rebentam o teto."""
    path = Path(path) if path else Path.home() / ".claude" / "sp-fila-estado.json"
    try:
        bruto = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as e:
        raise ErroEstado(f"estado antigo {ILEGIVEL}: {path} ({e})") from e
    try:
        antigo = json.loads(bruto)
    except ValueError as e:
        raise ErroEstado(f"estado antigo {ILEGIVEL}: {path} ({e}); corrigir ou apagar à mão") from e
    if not isinstance(antigo, dict) or not ({"sessoes", "lancado"} & set(antigo)):
        raise ErroEstado(f"estado antigo em formato desconhecido: {path} (sem `sessoes` nem `lancado`)")
    sessoes = antigo.get("sessoes") or {}
    if not isinstance(sessoes, dict):
        raise ErroEstado(f"estado antigo em formato desconhecido: {path} (`sessoes` não é um objeto)")
    sessoes = {s: (v if isinstance(v, dict) else {}) for s, v in sessoes.items()}
    listas = {}
    for campo in ("feitos", "falhados"):
        valor = antigo.get(campo) or []
        if not isinstance(valor, list) or not all(isinstance(s, str) for s in valor):
            raise ErroEstado(f"estado antigo em formato desconhecido: {path} (`{campo}` não é uma lista de slugs)")
        listas[campo] = valor
    lancado = antigo.get("lancado")
    if lancado:
        if not isinstance(lancado, str):
            raise ErroEstado(f"estado antigo em formato desconhecido: {path} (`lancado` não é um slug)")
        sessoes.setdefault(lancado, {})
    try:
        modo = "paralelo" if int(antigo.get("concorrencia") or 1) > 1 else "sequencial"
    except (TypeError, ValueError):
        raise ErroEstado(f"estado antigo em formato desconhecido: {path} (`concorrencia` não é um número)") from None
    feitos = [s for s in dict.fromkeys(listas["feitos"]) if s not in sessoes]
    falhados = [s for s in dict.fromkeys(listas["falhados"]) if s not in sessoes and s not in feitos]
    for s in [*sessoes, *feitos, *falhados]:
        pe._slug(s)
    try:
        criada = datetime.fromisoformat(str(antigo.get("inicio")))
    except ValueError:
        criada = agora or datetime.now()
    programa = antigo.get("programa") or None
    fid = pe.fila_id(programa, criada)
    with pe._exclusivo(root) as r:
        d = r / fid
        if d.exists():
            raise ErroEstado(f"estado antigo já migrado: a fila {fid} existe")
        if sessoes and pe._ativos(r) + len(sessoes) > MAX_PARALELO:
            raise ErroEstado(f"migração recusada: {len(sessoes)} sessões em curso passam o teto de {MAX_PARALELO} painéis")
        d.mkdir()
        agora_ts = pe._ts(agora)
        for slug, estado in [*((s, "done") for s in feitos), *((s, "falhou") for s in falhados), *((s, "a-correr") for s in sessoes)]:
            sp = pe._sp_novo(fid, slug, agora)
            info = sessoes.get(slug, {})
            sp.update(estado=estado, msg="migrado de sp-fila-estado.json",
                      worktree=info.get("worktree"), pane=None if info.get("painel") is None else str(info["painel"]),
                      inicio=info.get("inicio") if estado == "a-correr" else None,
                      fim=agora_ts if estado in FINAIS else None)
            guardar(d / f"{slug}.json", sp)
        guardar(d / "fila.json", {"fila": fid, "programa": programa,
                                  "modo": modo,
                                  "limites": {k: antigo[k] for k in _LIMITES_ANTIGOS if antigo.get(k) is not None},
                                  "ordem": [*feitos, *falhados, *sessoes], "criada": criada.isoformat(timespec="seconds"),
                                  "migrada_de": str(path)})
    return fid
