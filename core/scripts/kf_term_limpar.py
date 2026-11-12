"""`kaizen term limpar|retomar`: fechar painéis e estado órfãos; reabrir o painel de SPs em Doing sem painel.

`limpar` faz dry-run por defeito: mostra o que fecharia e o que protege. Só com `--apply` (e confirmação «s»/«sim»,
ou `--sim` sem terminal) executa. Ações: `fechar-painel` (SP `done` com painel vivo e worktree limpa), `estado-orfao`
(SP ativo cujo painel morreu passa a `bloqueado`) e `remover-fila` (fila só com SPs `done` e sem painéis).
Nunca fecha: o painel onde corre o comando, painéis de SPs ativos, SPs `falhou`/pendentes, painéis cuja worktree
está suja ou não se consegue verificar. Sem backend de painéis não há nada a decidir (rc 0, aviso).

`retomar` lista os SPs em Doing (não-mãe) sem painel vivo, mostra os handoffs pendentes de cada um, pede
confirmação e reabre o michi numa worktree nova (`michi_handoff_auto.go`).

Uso: python -I scripts/kf_term_limpar.py limpar [--apply] [--sim] | retomar [--slug SP] [--sim]
rc: 0 ok (inclui dry-run, cancelado, nada a fazer, sem backend), 1 falha a executar, 2 argumento inválido
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402
import painel_backend as pb  # noqa: E402
import sp_painel_estado as pe  # noqa: E402

sp_list = kaizen_engine.load("sp-list")
SIM = {"s", "sim", "y", "yes"}
ERROS = (pb.BackendError, OSError, subprocess.SubprocessError, pe.ErroEstado)


def painel_proprio(env=None):
    """Id do painel onde corre este processo (WezTerm ou tmux); None se não corre num painel."""
    env = os.environ if env is None else env
    return env.get("WEZTERM_PANE") or env.get("TMUX_PANE") or None


def worktree_suja(caminho, run=subprocess.run):
    """True se há alterações por guardar; False se limpa ou se a worktree já não existe; None se não se consegue ver."""
    if not caminho:
        return False
    if not Path(caminho).is_dir():
        return False
    try:
        r = run(["git", "-C", str(caminho), "status", "--porcelain"], capture_output=True, text=True,
                encoding="utf-8", timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return bool(r.stdout.strip()) if r.returncode == 0 else None


def _id(valor):
    return None if valor in (None, "") else str(valor)


def planear(filas, vivos, proprio=None, suja=worktree_suja):
    """(ações, protegidos). `vivos`: ids dos painéis vivos. Cada ação: {acao, alvo, slug, fila, motivo}."""
    acoes, protegidos = [], []
    for f in filas:
        presos = 0
        for sp in f["sps"]:
            slug, estado, pane = sp.get("slug"), sp.get("estado"), _id(sp.get("pane"))
            vivo = pane is not None and pane in vivos
            base = {"slug": slug, "fila": f["fila"], "alvo": pane}
            if estado == pe.ILEGIVEL:
                protegidos.append({**base, "motivo": "estado ilegível"})
                presos += 1
            elif estado in pe.ATIVOS and not vivo:
                acoes.append({**base, "acao": "estado-orfao", "motivo": f"{estado} sem painel vivo → bloqueado"})
            elif not vivo:
                continue
            elif pane == proprio:
                protegidos.append({**base, "motivo": "painel onde corre o comando"})
                presos += 1
            elif estado in pe.ATIVOS:
                protegidos.append({**base, "motivo": f"SP {estado}"})
                presos += 1
            elif estado != "done":
                protegidos.append({**base, "motivo": f"SP {estado} (rever antes de fechar)"})
                presos += 1
            else:
                s = suja(sp.get("worktree"))
                if s is False:
                    acoes.append({**base, "acao": "fechar-painel", "motivo": "SP done, worktree limpa"})
                else:
                    protegidos.append({**base, "motivo": "worktree suja" if s else "worktree não verificada"})
                    presos += 1
        sps = f["sps"]
        if sps and not presos and all(sp.get("estado") == "done" for sp in sps):
            acoes.append({"acao": "remover-fila", "alvo": None, "slug": None, "fila": f["fila"],
                          "motivo": "todos os SPs done e sem painéis a proteger"})
    return acoes, protegidos


def descrever(a):
    if a["acao"] == "remover-fila":
        return f"remover-fila   fila {a['fila']}  ({a['motivo']})"
    return f"{a['acao']:<14} {a['slug']}  painel {a['alvo'] or '-'}  ({a['motivo']})"


def executar(acoes, backend, root=None):
    """Aplica as ações pela ordem fechar → órfãos → filas; devolve (feitas, falhas [(ação, erro)])."""
    ordem = {"fechar-painel": 0, "estado-orfao": 1, "remover-fila": 2}
    feitas, falhas = [], []
    for a in sorted(acoes, key=lambda x: ordem[x["acao"]]):
        try:
            if a["acao"] == "fechar-painel":
                backend.fechar(a["alvo"])
            elif a["acao"] == "estado-orfao":
                pe.transitar(a["slug"], "bloqueado", msg="painel morto (kaizen term limpar)", fila=a["fila"], root=root)
            else:
                pe.remover_fila(a["fila"], root=root)
            feitas.append(a)
        except ERROS as e:
            falhas.append((a, str(e)))
    return feitas, falhas


def confirmar(pergunta, entrada=input):
    return entrada(f"{pergunta} [s/N] ").strip().lower() in SIM


def limpar(a, root, backend, aviso, entrada, escrever, proprio, suja):
    if backend is None:
        print(f"aviso: {aviso or 'sem backend de painéis'}; nada a limpar sem saber que painéis vivem", file=sys.stderr)
        return 0
    import kf_term_ls
    vivos, erro = kf_term_ls._vivos(backend)
    if vivos is None:
        print(f"aviso: {erro}; nada a limpar", file=sys.stderr)
        return 0
    acoes, protegidos = planear(pe.filas(root), vivos, proprio, suja)
    for p in protegidos:
        escrever(f"protegido      {p['slug']}  painel {p['alvo'] or '-'}  ({p['motivo']})\n")
    if not acoes:
        escrever("nada a limpar\n")
        return 0
    for x in acoes:
        escrever(descrever(x) + "\n")
    if not a.apply:
        escrever(f"dry-run: {len(acoes)} ação(ões); use --apply para executar\n")
        return 0
    if not a.sim and not confirmar(f"executar as {len(acoes)} ações acima?", entrada):
        escrever("cancelado\n")
        return 0
    feitas, falhas = executar(acoes, backend, root)
    escrever(f"feito: {len(feitas)} ação(ões)\n")
    for x, e in falhas:
        print(f"erro: {descrever(x)}: {e}", file=sys.stderr)
    return 1 if falhas else 0


def _handoffs(slug, pasta):
    """Handoffs pendentes do SP: `<pasta>/*-<slug>.md` (o handoff.py grava `<data>-<HHMM>-<slug>.md`)."""
    if not pasta or not Path(pasta).is_dir():
        return []
    return sorted(str(p) for p in Path(pasta).glob(f"*-{slug}.md") if p.is_file())


def candidatos(root_sp, filas, vivos):
    """SPs em Doing (não-mãe) sem painel vivo registado, pela ordem do `sp-list`."""
    painel = {sp.get("slug"): _id(sp.get("pane")) for f in filas for sp in f["sps"]}
    return [s for s in sp_list.collect(Path(root_sp), include_done=False)
            if s.status == "Doing" and s.kind != "program" and not (painel.get(s.slug) in vivos)]


def spawn_real(backend):
    import michi_handoff_auto as mha
    return mha._spawn_real(backend.nome)


def retomar(a, root_sp, root_estado, backend, aviso, entrada, escrever, pasta_handoffs, spawn=None):
    if backend is None:
        print(f"aviso: {aviso or 'sem backend de painéis'}; sem painel para reabrir", file=sys.stderr)
        return 0
    import kf_term_ls
    vivos, erro = kf_term_ls._vivos(backend)
    if vivos is None:
        print(f"aviso: {erro}; não sei que painéis vivem", file=sys.stderr)
        return 0
    cands = candidatos(root_sp, pe.filas(root_estado), vivos)
    if a.slug:
        cands = [s for s in cands if s.slug == a.slug]
        if not cands:
            print(f"erro: {a.slug} não está em Doing sem painel vivo", file=sys.stderr)
            return 2
    if not cands:
        escrever("nada a retomar\n")
        return 0
    for i, s in enumerate(cands, 1):
        hs = _handoffs(s.slug, pasta_handoffs)
        escrever(f"{i}) {s.slug}" + (f"  handoff: {hs[-1]}" if hs else "  (sem handoff pendente)") + "\n")
    if len(cands) > 1 and not a.slug:
        r = entrada("número (q cancela): ").strip().lower()
        if not (r.isdigit() and 1 <= int(r) <= len(cands)):
            escrever("cancelado\n")
            return 0
        alvo = cands[int(r) - 1]
    else:
        alvo = cands[0]
    if not a.sim and not confirmar(f"reabrir o michi de {alvo.slug} num painel novo?", entrada):
        escrever("cancelado\n")
        return 0
    import michi_handoff_auto as mha
    res = mha.go(alvo.slug, None, backend, spawn or spawn_real(backend))
    if not res["ok"]:
        print(f"erro a reabrir {alvo.slug}: {res['erro']}", file=sys.stderr)
        return 1
    try:
        backend.titulo(res["painel"], alvo.slug)
    except ERROS as e:
        print(f"aviso: painel {res['painel']} sem título ({e})", file=sys.stderr)
    escrever(f"reaberto {alvo.slug} no painel {res['painel']}\n")
    return 0


def main(argv=None, root=None, root_sp=None, backend="auto", aviso=None, entrada=input, saida=print, proprio=False,
         suja=worktree_suja, pasta_handoffs=None, spawn=None):
    ap = argparse.ArgumentParser(prog="kaizen term", description=__doc__.splitlines()[0])
    ap.add_argument("modo", choices=("limpar", "retomar"))
    ap.add_argument("--apply", action="store_true", help="limpar: executar (por defeito só mostra)")
    ap.add_argument("--sim", action="store_true", help="confirmação explícita (sem terminal)")
    ap.add_argument("--slug", help="retomar: SP a reabrir (salta o seletor, ainda confirma)")
    a = ap.parse_args(argv)
    if a.modo == "retomar" and a.apply or a.modo == "limpar" and a.slug:
        print("erro: --apply é só de limpar; --slug é só de retomar", file=sys.stderr)
        return 2
    escrever = saida.write if hasattr(saida, "write") else (lambda t: saida(t.rstrip("\n")))
    if backend == "auto":
        import kf_term_ls
        backend, aviso = kf_term_ls.backend_por_config()
    if proprio is False:
        proprio = painel_proprio()
    if a.modo == "limpar":
        return limpar(a, root, backend, aviso, entrada, escrever, proprio, suja)
    if pasta_handoffs is None:
        try:
            import handoff
            pasta_handoffs = handoff.HANDOFFS_DIR
        except Exception:  # noqa: BLE001 - sem handoffs configurados: só não os mostra
            pasta_handoffs = None
    return retomar(a, root_sp or sp_list.DEFAULT_ROOT, root, backend, aviso, entrada, escrever, pasta_handoffs, spawn)


if __name__ == "__main__":
    for _f in (sys.stdout, sys.stderr):  # pipe no Windows: sem isto os acentos saem em cp1252
        _f.reconfigure(encoding="utf-8")
    sys.exit(main())
