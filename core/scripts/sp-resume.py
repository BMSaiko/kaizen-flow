#!/usr/bin/env python3
"""Retoma um SP interrompido na fase certa (`kaizen resume`).

Uso: python -I scripts/sp-resume.py [<slug>] [--from <fase>] [--restart [--sim]] [--raiz R]
     python -I scripts/sp-resume.py <slug> --lock|--unlock [--painel P]   (michi por CLI)
rc: 0 ok / nada a retomar · 1 recusado (EC-043 lock vivo, ou --restart sem confirmação) · 2 uso inválido (fase, escolha pendente)

Candidato = SP com checkpoint em `<raiz>/.kaizen/estado/` sem lock vivo e fora de Done (EC-027, UC-031).
Ponto de retoma = passo seguinte ao último «fim» do journal (EC-001); passos abertos repetem (idempotentes)
ou revertem (plano do `michi-checkpoint.py restore`, sem --apply). `--restart` arquiva (nunca apaga) o estado (UC-032).
"""
import argparse
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_disco  # noqa: E402
import sp_journal  # noqa: E402

FASES = ("grill", "dr", "dp", "da", "gates", "pentest", "review", "docs", "pr", "report", "reflect", "commit")


def _slugs_com_estado(raiz):
    pasta = Path(raiz) / ".kaizen" / "estado"
    if not pasta.is_dir():
        return []
    return sorted(p.name[: -len(".json")] for p in pasta.glob("*.json") if not p.name.endswith(".lock.json"))


def _em_done(raiz, slug):
    return any(Path(raiz).glob(f"knowledge/projects/**/sp/Done/{slug}.md"))


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
    return [s for s in _slugs_com_estado(raiz) if sp_disco.dono(raiz, s)["estado"] != "vivo" and not _em_done(raiz, s)]


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
        "fase": abertos[0][0] if abertos else (ultimo["fase"] if ultimo else FASES[0]),
    }


def _msg(o_que, porque, guardado, proximo, ec):
    return f"{o_que} · {porque} · estado guardado: {guardado} · próximo comando: {proximo} [{ec}]"


def _arquivar(raiz, slug):
    estado_p, jp = sp_journal.caminhos(raiz, slug)
    destino = Path(raiz) / ".kaizen" / "estado" / "arquivo" / f"{slug}-{time.strftime('%Y%m%dT%H%M%S')}-{time.time_ns() % 10**6:06d}"
    destino.mkdir(parents=True, exist_ok=True)
    for p in (estado_p, jp):
        if p.exists():
            shutil.move(str(p), str(destino / p.name))
    return destino


def resume(raiz, slug, from_fase=None, restart=False, confirmar=None, painel=None):
    """Devolve (rc, mensagem). `confirmar` é um callable sem argumentos (True = confirmado)."""
    if from_fase is not None and from_fase not in FASES:
        return 2, f"fase inválida «{from_fase}»; fases válidas: {', '.join(FASES)}"
    d = sp_disco.dono(raiz, slug)
    if d["estado"] == "vivo":
        return 1, _msg(
            f"SP {slug} já está em curso no painel {d.get('painel') or '?'} (pid {d.get('pid')})",
            "um SP só admite um dono vivo",
            "intacto",
            f"esperar ou fechar esse painel e correr `kaizen resume {slug}`",
            "EC-043",
        )
    if restart:
        if confirmar is None or not confirmar():
            return 1, f"--restart não confirmado: nada alterado (EC-001). Confirmar com `kaizen resume {slug} --restart --sim`."
        destino = _arquivar(raiz, slug)
        return 0, f"recomeçado do início em {FASES[0]}; estado anterior arquivado em {destino} (UC-032)"
    ponto = ponto_de_retoma(raiz, slug)
    fase = ponto["fase"]
    if from_fase is not None:
        idx = FASES.index(from_fase)
        for a in ponto["abertos"]:
            if a["fase"] in FASES and FASES.index(a["fase"]) >= idx:
                sp_journal.revertido(raiz, slug, a["fase"], a["passo"])
        fase = from_fase
        ponto = ponto_de_retoma(raiz, slug)
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
    return 0, texto + " (EC-001, EC-027, UC-031)"


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
    if a.lock:
        try:
            sp_disco.tomar_lock(a.raiz, a.slug, a.painel, pid=None)
        except sp_disco.LockOcupado as e:
            print(resume(a.raiz, a.slug)[1], file=sys.stderr)
            return 1
        print(f"lock de {a.slug} tomado")
        return 0
    if a.unlock:
        print("lock libertado" if sp_disco.libertar_lock(a.raiz, a.slug, pid=None) else "sem lock próprio a libertar")
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
    rc, texto = resume(a.raiz, slug, a.from_fase, a.restart, (lambda: True) if a.sim else _perguntar, a.painel)
    print(texto, file=sys.stderr if rc else sys.stdout)
    return rc


if __name__ == "__main__":
    sys.exit(main())
