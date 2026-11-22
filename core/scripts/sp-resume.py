#!/usr/bin/env python3
"""Retoma um SP interrompido na fase certa (`kaizen resume`).

Uso: python -I scripts/sp-resume.py [<slug>] [--from <fase>] [--restart [--sim]] [--raiz R]
     python -I scripts/sp-resume.py <slug> --lock|--unlock [--painel P]   (michi por CLI)
rc: 0 ok / nada a retomar · 1 recusado (EC-043 lock vivo, EC-016/017 pausa antes de `retoma_em`, --restart sem confirmação) · 2 uso inválido (fase, escolha pendente)

Candidato = SP com checkpoint em `<raiz>/.kaizen/estado/` sem lock vivo e fora de Done (EC-027, UC-031).
Ponto de retoma = passo seguinte ao último «fim» do journal (EC-001); passos abertos repetem (idempotentes)
ou revertem (plano do `michi-checkpoint.py restore`, sem --apply). `--restart` arquiva (nunca apaga) o estado (UC-032).
SP pausado pela fila por quota/rede (`motivo` + `retoma_em` no estado do painel) só retoma depois dessa hora.
Antes de retomar corre o pré-voo (`sp-preflight.py`) e mostra os problemas como aviso. Erros no formato de `kf_erros`.
"""
import argparse
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kf_erros  # noqa: E402
import sp_disco  # noqa: E402
import sp_journal  # noqa: E402

FASES = ("grill", "dr", "dp", "da", "gates", "pentest", "review", "docs", "pr", "report", "reflect", "commit")


def _slugs_com_estado(raiz):
    pasta = Path(raiz) / ".kaizen" / "estado"
    if not pasta.is_dir():
        return []
    return sorted(p.name[: -len(".json")] for p in pasta.glob("*.json") if not p.name.endswith(".lock.json"))


def _slugs_em_done(raiz):
    """Nomes dos SPs em Done (um só glob para todos os slugs)."""
    return {p.stem for p in Path(raiz).glob("knowledge/projects/**/sp/Done/*.md")}


def _em_done(raiz, slug):
    return slug in _slugs_em_done(raiz)


def _eventos(raiz, slug):
    jp = sp_journal.caminhos(raiz, slug)[1]
    if not jp.exists():
        return []
    lido = sp_journal._ler_journal(jp)
    return lido[0] if lido else []


def _abertos(eventos):
    """[(fase, passo, idempotente)] dos passos com «inicio» sem «fim»/«revertido», por ordem."""
    abertos = {}
    for e in eventos:
        k = (e["fase"], e["passo"])
        if e["evento"] == "inicio":
            abertos.pop(k, None)
            abertos[k] = bool(e.get("idempotente", True))
        else:
            abertos.pop(k, None)
    return [(f, p, i) for (f, p), i in abertos.items()]


def candidatos(raiz):
    """Slugs interrompidos: estado em disco, lock não vivo, SP fora de Done."""
    cands = [s for s in _slugs_com_estado(raiz) if sp_disco.dono(raiz, s)["estado"] != "vivo"]
    if not cands:
        return []
    feitos = _slugs_em_done(raiz)
    return [s for s in cands if s not in feitos]


def _fase_de_retoma(abertos, ultimo):
    """Primeira fase aberta; sem abertos, a seguinte à do último «fim» (fase concluída não se repete); commit = «concluido»."""
    if abertos:
        return abertos[0][0]
    if not ultimo:
        return FASES[0]
    if ultimo["fase"] not in FASES:
        return ultimo["fase"]
    i = FASES.index(ultimo["fase"])
    return FASES[i + 1] if i + 1 < len(FASES) else "concluido"


def ponto_de_retoma(raiz, slug):
    """Onde retomar: último «fim», passos abertos e a ação (repetir | reverter | nada)."""
    eventos = _eventos(raiz, slug)
    fins = [e for e in eventos if e["evento"] == "fim"]
    abertos = _abertos(eventos)
    ultimo = fins[-1] if fins else None
    acao = "nada" if not abertos else ("repetir" if all(i for _, _, i in abertos) else "reverter")
    return {
        "slug": slug,
        "ultimo_fim": {"fase": ultimo["fase"], "passo": ultimo["passo"]} if ultimo else None,
        "abertos": [{"fase": f, "passo": p, "idempotente": i} for f, p, i in abertos],
        "acao": acao,
        "fase": _fase_de_retoma(abertos, ultimo),
    }


def _msg(o_que, porque, guardado, proximo, ec):
    return kf_erros.erro(ec, o_que, porque, guardado, proximo)


def pausa(slug, painel_root=None):
    """(motivo, retoma_em) se a fila deixou o SP `bloqueado` por quota/rede/sessão; senão None. Nunca levanta."""
    try:
        import sp_painel_estado as pe
        sp = pe.ler(pe.procurar(slug, painel_root), slug, painel_root)
    except Exception:  # noqa: BLE001 — sem fila que o registe: não há pausa
        return None
    ecs = kf_erros.ecs_em(sp.get("motivo") or "")
    if sp.get("estado") != "bloqueado" or not ecs or ecs[0] not in (kf_erros.EC_QUOTA, kf_erros.EC_REDE, kf_erros.EC_SESSAO):
        return None
    return sp["motivo"], sp.get("retoma_em")


def _arquivar(raiz, slug):
    estado_p, jp = sp_journal.caminhos(raiz, slug)
    if not estado_p.exists() and not jp.exists():
        return None
    destino = Path(raiz) / ".kaizen" / "estado" / "arquivo" / f"{slug}-{time.strftime('%Y%m%dT%H%M%S')}-{time.time_ns() % 10**6:06d}"
    destino.mkdir(parents=True, exist_ok=True)
    for p in (estado_p, jp):
        if p.exists():
            shutil.move(str(p), str(destino / p.name))
    return destino


def _msg_ocupado(slug, d):
    idade = f", último heartbeat há {int(time.time() - d['hb'])} s" if isinstance(d.get("hb"), (int, float)) else ""
    return _msg(
        f"SP {slug} já está em curso no painel {d.get('painel') or '?'} (pid {d.get('pid')}{idade})",
        "um SP só admite um dono vivo",
        "intacto",
        f"esperar, ou se o painel já não existe `python -I scripts/sp-resume.py {slug} --unlock` e `kaizen resume {slug}`",
        "EC-043",
    )


def _slug_valido(slug):
    return bool(slug) and slug not in (".", "..") and not any(c in slug for c in ("/", chr(92), ":"))


def _pedido_invalido(slug, from_fase, restart):
    """(2, mensagem) se o pedido é inválido; None se pode seguir."""
    if not _slug_valido(slug):
        return 2, _msg(f"slug inválido «{slug}»", "o slug é um nome de ficheiro (sem /, \\ nem :)", "nada alterado",
                       "`kaizen resume` sem argumentos lista os SPs interrompidos", "EC-067")
    if from_fase is not None and from_fase not in FASES:
        return 2, _msg(f"fase inválida «{from_fase}»", f"fases válidas: {', '.join(FASES)}", "nada alterado",
                       f"`kaizen resume {slug} --from <fase>`", "EC-067")
    if restart and from_fase is not None:
        return 2, _msg("--restart e --from não se combinam", "--restart recomeça sempre em grill", "nada alterado",
                       f"`kaizen resume {slug} --restart` ou `kaizen resume {slug} --from <fase>`", "EC-067")
    return None


def _texto_retoma(slug, ponto, fase, from_fase, antes):
    ult = ponto["ultimo_fim"]
    texto = f"retomar {slug} em {fase}; último passo concluído: {ult['fase'] + '/' + ult['passo'] if ult else 'nenhum'}"
    if from_fase is None and ponto["abertos"]:
        nomes = ", ".join(f"{a['fase']}/{a['passo']}" for a in ponto["abertos"])
        if ponto["acao"] == "repetir":
            texto += f"; repetir (idempotente): {nomes}"
        else:
            texto += (
                f"; reverter antes de repetir: {nomes} — plano: "
                f"`python -I scripts/michi-checkpoint.py restore --slug {slug}` (sem --apply só mostra)"
            )
    if from_fase is not None and antes:
        texto += f"; atenção: passos abertos em fases anteriores ficam por fechar: {', '.join(antes)}"
    return texto


def _recomecar(raiz, slug, confirmar):
    """--restart: arquiva o estado e recomeça do início (pede confirmação)."""
    if confirmar is None or not confirmar():
        return 1, _msg("--restart não confirmado", "arquivar o estado pede confirmação explícita (EOF vale não)",
                       "nada alterado (EC-001)", f"`kaizen resume {slug} --restart --sim`", "EC-006")
    destino = _arquivar(raiz, slug)
    if destino is None:
        return 1, _msg(f"SP {slug} sem estado a arquivar", "não há checkpoint nem journal em .kaizen/estado",
                       "nada alterado (EC-001)", "`kaizen resume` lista os SPs com estado", "EC-050")
    return 0, f"recomeçado do início em {FASES[0]}; estado anterior arquivado em {destino} (UC-032)"


def resume(raiz, slug, from_fase=None, restart=False, confirmar=None, agora=None, painel_root=None):
    """Devolve (rc, mensagem). `confirmar` é um callable sem argumentos (True = confirmado)."""
    erro = _pedido_invalido(slug, from_fase, restart)
    if erro:
        return erro
    d = sp_disco.dono(raiz, slug)
    if d["estado"] == "vivo":
        return 1, _msg_ocupado(slug, d)
    p = pausa(slug, painel_root)
    if p and p[1] and not kf_erros.ja_passou(p[1], agora):
        ec = kf_erros.ecs_em(p[0])[0]
        return 1, _msg(f"SP {slug} em pausa até {p[1]}", p[0], "checkpoint e journal intactos",
                       f"esperar até {p[1]} (a fila retoma sozinha se o painel estiver vivo) e `kaizen resume {slug}`", ec)
    if restart:
        return _recomecar(raiz, slug, confirmar)
    estado_p, jp = sp_journal.caminhos(raiz, slug)
    if not estado_p.exists() and not jp.exists():
        return 1, _msg(f"SP {slug} sem estado a retomar", "não há checkpoint nem journal em .kaizen/estado",
                       "nada alterado (EC-001)", f"`/michi {slug}` arranca-o do início", "EC-050")
    if _em_done(raiz, slug):
        return 1, _msg(f"SP {slug} já está em Done", "um SP fechado não se retoma", "nada alterado (EC-001)",
                       "`kaizen resume` lista os SPs interrompidos", "EC-067")
    ponto = ponto_de_retoma(raiz, slug)
    fase = ponto["fase"]
    antes = []
    if from_fase is not None:
        idx = FASES.index(from_fase)
        for a in ponto["abertos"]:
            if a["fase"] in FASES and FASES.index(a["fase"]) >= idx:
                sp_journal.revertido(raiz, slug, a["fase"], a["passo"])
        fase = from_fase
        antes = [f"{a['fase']}/{a['passo']}" for a in ponto["abertos"] if a["fase"] in FASES and FASES.index(a["fase"]) < idx]
        ponto = ponto_de_retoma(raiz, slug)
    return 0, _texto_retoma(slug, ponto, fase, from_fase, antes) + " (EC-001, EC-027, UC-031)"


def _perguntar():
    try:
        return input("Arquivar o estado e recomeçar do início? [s/N] ").strip().lower() in ("s", "sim", "y", "yes")
    except EOFError:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="Retoma um SP interrompido (kaizen resume)")
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--raiz", default=".", help="raiz da worktree (defeito: cwd)")
    ap.add_argument("--from", dest="from_fase", metavar="FASE", help="recomeçar nesta fase: " + ", ".join(FASES))
    ap.add_argument("--restart", action="store_true", help="arquivar o estado e recomeçar (pede confirmação)")
    ap.add_argument("--sim", action="store_true", help="confirma --restart sem perguntar")
    ap.add_argument("--lock", action="store_true", help="toma o lock do SP (dono sem processo; michi por CLI)")
    ap.add_argument("--unlock", action="store_true", help="liberta o lock tomado com --lock")
    ap.add_argument("--painel")
    a = ap.parse_args(argv)
    if (a.lock or a.unlock) and not a.slug:
        ap.error("--lock/--unlock precisam de <slug>")
    if (a.lock or a.unlock) and not _slug_valido(a.slug):
        print(resume(a.raiz, a.slug)[1], file=sys.stderr)
        return 2
    if a.lock:
        try:
            sp_disco.tomar_lock(a.raiz, a.slug, a.painel, pid=None)
        except sp_disco.LockOcupado as e:
            print(_msg_ocupado(a.slug, e.dono), file=sys.stderr)
            return 1
        print(f"lock de {a.slug} tomado")
        return 0
    if a.unlock:
        print("lock libertado" if sp_disco.libertar_lock(a.raiz, a.slug, pid=None, painel=a.painel) else "sem lock próprio a libertar")
        return 0
    slug = a.slug
    if not slug:
        cands = candidatos(a.raiz)
        if not cands:
            print("nada a retomar")
            return 0
        if len(cands) > 1:
            print("vários SPs interrompidos; escolhe um com `kaizen resume <slug>`:")
            for c in cands:
                print(f"  {c}")
            return 2
        slug = cands[0]
    rc, texto = resume(a.raiz, slug, a.from_fase, a.restart, (lambda: True) if a.sim else _perguntar)
    print(texto, file=sys.stderr if rc else sys.stdout)
    if rc == 0 and not a.restart:
        _preflight(a.raiz, slug)
    return rc


def _preflight(raiz, slug):
    """Pré-voo antes de retomar: só avisa (sem o órfão do próprio SP); nunca muda o rc do resume."""
    try:
        from sp_carregar import carregar
        pf = carregar(Path(__file__).resolve().with_name("sp-preflight.py"), "sp_preflight")
        probs = pf.diagnosticar(slug, repo=raiz, ignorar_orfao=True)
    except Exception:  # noqa: BLE001 — fora de git ou sem o pré-voo: retomar na mesma
        return
    for p in probs:
        print(f"aviso do pré-voo:\n{p.texto()}", file=sys.stderr)


if __name__ == "__main__":
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-resume", main))
