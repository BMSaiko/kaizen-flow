#!/usr/bin/env python3
"""Fila autónoma de SPs: escolhe o próximo SP elegível e lança-o (modo auto, sessão limpa).

Elegível = TODO, `modo: auto`, com `gates:`, dependências em Done, autorizações suficientes. Ordem:
prioridade, depois idade, com `depends_on` a mandar. Nunca faz push/PR: isso é do fecho de cada SP.

Uso:
  python -I scripts/sp-fila.py --dry-run [--max N] [--ate HH:MM] [--projeto P]   # ordem e exclusões
  python -I scripts/sp-fila.py [--max N] [--max-falhas N] [--ate HH:MM] [--projeto P] [--orcamento N]   # arranca a fila (para ao fim de N falhas seguidas, defeito 2)
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
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402
import painel_backend  # noqa: E402
# Módulos irmãos (a CLI e os testes continuam a ver tudo aqui): estado, plano, relatório, execução, paralelo.
from sp_fila_estado import (MAX_DEFEITO, MAX_FALHAS_DEFEITO, NO_WINDOW, ORCAMENTO, REQ_POR_SP, RELATORIOS, ESTADO, USER,  # noqa: E402,F401
                            atualizar, bloqueio, guardar, ler, migrar, run_hidden)
from sp_fila_plano import descendentes, limite, load, plan, render_plan, sem_commit, sp_list  # noqa: E402,F401
from sp_fila_relatorio import gastos, relatorio, render_gastos  # noqa: E402,F401
from sp_fila_execucao import (_custos, _ler_sp, _painel_lancado,  # noqa: E402,F401
                              lancar_seguinte_auto, seguinte, IntegracaoPendente, SlugObrigatorio)
from sp_fila_paralelo import (INATIVIDADE_S, VIGIA_LOG, aviso_vigia, batida_vigia, classificar,
                              contar_tails, estado_vivo, fechar_painel_sessao, garantir_vigia, linha, parar_vigia, registar_incidente, vigiar)

def backend_paineis(repo=None, env=None, which=None, run=None):
    """(backend ou None, config) segundo `painelBackend` do kaizen.config.json; None = sem painéis utilizáveis."""
    cfg = kaizen_engine.load("kaizen_config").painel_backend(Path(repo or Path.cwd()))
    kw = {k: v for k, v in (("env", env), ("which", which), ("run", run)) if v is not None}
    return painel_backend.escolher(cfg, **kw), cfg


def destacar(args, log, popen=subprocess.Popen):
    """Arranca `sp-fila.py <args>` num processo próprio (fora do prazo do Monitor), com a saída em `log`."""
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == "nt" else 0
    saida = open(log, "a", encoding="utf-8")
    return popen([sys.executable, "-I", str(Path(__file__).resolve()), *args], stdin=subprocess.DEVNULL, stdout=saida,
                 stderr=subprocess.STDOUT, creationflags=flags, **({} if os.name == "nt" else {"start_new_session": True}))


AJUDA = """Orquestrador do sp-fila (regras):
- Vigia: `sp-fila.py --vigiar --destacado` (processo próprio; se já houver uma ativa não arma outra) e UM só Monitor `tail -F ~/.claude/sp-fila-vigia.log`; aos 30 min o novo substitui o anterior (parar o antigo primeiro).
- Ao ver um SP «fechado» a vigia fecha o painel e lança o seguinte sozinha (como `--seguinte --slug`), respeitando max, concorrência, ate, orçamento e dependências; se não lança, a razão fica no log (`slug · fila · razão`).
- Cada linha do log = `slug · estado · ação`; só mudanças (bloqueado repete-se a cada 15 min como «AINDA»).
- Relato por linha: ≤3 linhas + TLDR; não narrar avisos repetidos nem reler ecrãs.
- Pergunta/aprovação de painel: `wezterm cli get-text --pane-id N`, um AskUserQuestion («Painel N»), só depois `send-text --no-paste`; nunca aprovar sozinho.
- `--estado-vivo` avisa «SEM VIGIA»/«VIGIA PAROU» (rearmar) e «N Monitores» (deixar só um)."""


def armar_vigia(args, estado):
    """Único caminho para armar a vigia: destaca-a se não está viva (idempotente) e devolve a mensagem."""
    extra = [a for flag, val in (("--intervalo", args.intervalo), ("--inatividade", args.inatividade), ("--estado", args.estado), ("--root", args.root)) for a in (flag, str(val))]
    extra += (["--projeto", args.projeto] if args.projeto else []) + (["--ate", args.ate] if args.ate else [])
    res, pid = garantir_vigia(ler(estado), lambda: destacar(["--vigiar", *extra], VIGIA_LOG), datetime.now())
    if res == "viva":
        return f"vigia já ativo (pid {pid}); log: {VIGIA_LOG}"
    return f"vigia destacado (pid {pid}); acompanhar com o Monitor: `tail -F {VIGIA_LOG}` (re-armar o tail aos 30 min); sem a fila a correr, sai sozinho"


def _ler_ou_erro(path):
    """Estado da fila ou None (com erro claro em stderr) se estiver ilegível."""
    try:
        return ler(path)
    except ValueError as e:
        print(f"erro: estado da fila ilegível ({path}): {e}; `--parar` abandona e apaga-o", file=sys.stderr)
        return None


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
    ap.add_argument("--max", type=int, default=None, help=f"nº máximo de SPs (defeito {MAX_DEFEITO}; em --concorrencia só conta se passado)")
    ap.add_argument("--ate", metavar="HH:MM", help="hora limite")
    ap.add_argument("--concorrencia", type=int, metavar="N", help="modo paralelo (N=1 também: um painel próprio): até N sessões em painéis próprios, sem limite de quota (só o guard de contexto, via handoff)")
    ap.add_argument("--orcamento", type=int, default=ORCAMENTO, help=f"teto opcional de requests totais; cada SP gasta {REQ_POR_SP} (sem ele, sem limite)")
    ap.add_argument("--max-falhas", type=int, default=MAX_FALHAS_DEFEITO, metavar="N", help=f"para a fila após N SPs falhados seguidos (defeito {MAX_FALHAS_DEFEITO}; 0 = sem este limite)")
    ap.add_argument("--projeto")
    ap.add_argument("--programa", metavar="SLUG", help="só a árvore deste SP-mãe; orçamento lido do frontmatter dela")
    ap.add_argument("--root", default=str(sp_list.DEFAULT_ROOT), help=argparse.SUPPRESS)
    ap.add_argument("--estado", default=str(ESTADO), help=argparse.SUPPRESS)
    ap.add_argument("--relatorios", default=str(RELATORIOS), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.max is None and not args.concorrencia:
        args.max = MAX_DEFEITO  # em paralelo None = sem máximo
    estado = Path(args.estado)
    if args.concorrencia is not None and args.concorrencia < 1:
        print(f"erro: --concorrencia exige N >= 1 (recebido {args.concorrencia}); sem a opção a fila corre em série", file=sys.stderr)
        return 1

    if args.ajuda:
        print(AJUDA)
        return 0
    if args.parar:
        try:
            vigia = ler(estado).get("vigia") if estado.exists() else None
        except ValueError:  # corrompido: abandonar na mesma
            vigia = None
        estado.unlink(missing_ok=True)
        print("fila abandonada")
        if vigia:
            print(parar_vigia(vigia)[1])
        return 0
    if args.vigiar and args.destacado:
        if not estado.exists():
            print("erro: sem fila em curso", file=sys.stderr)
            return 1
        print(armar_vigia(args, estado))
        return 0
    if args.vigiar:
        def lido():
            return estado_vivo(_ler_ou_erro(estado) or {"sessoes": {}}, load(args.root, args.projeto), run_hidden, datetime.now(), args.inatividade * 60, backend=backend_paineis()[0]) if estado.exists() else None
        fim = None
        if args.ate:
            h, m = map(int, args.ate.split(":"))
            fim = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
        return vigiar(lido, args.intervalo, time.sleep, lambda m: print(m, flush=True), lambda: fim is not None and datetime.now() >= fim,
                      lambda: batida_vigia(estado), lambda slug: fechar_painel_sessao(estado, slug, run_hidden, backend=backend_paineis()[0]),
                      lancar_seguinte=lambda slug: lancar_seguinte_auto(args.root, estado, Path(args.relatorios), slug),
                      incidente=lambda texto: registar_incidente(estado, texto))
    if args.estado_vivo:
        if not estado.exists():
            print("erro: sem fila em curso", file=sys.stderr)
            return 1
        atual = _ler_ou_erro(estado)
        if atual is None:
            return 1
        for slug, est, motivo in estado_vivo(atual, load(args.root, args.projeto), run_hidden, datetime.now(), args.inatividade * 60, backend=backend_paineis()[0]):
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
        atual = _ler_ou_erro(estado)
        if atual is None:
            return 1
        print(render_gastos(atual, _custos()))
        return 0
    if args.concorrencia and not args.dry_run and not args.seguinte and (esc := backend_paineis())[0] is None:
        print(f"AVISO: {painel_backend.falta(esc[1])}; a fila corre em série (sem --concorrencia)", file=sys.stderr)
        args.concorrencia = None
        if args.max is None:
            args.max = MAX_DEFEITO
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
        print(f"Limites: máx {args.max or 'sem'} SPs · {args.max_falhas or 'sem'} falhas seguidas · "
              f"{'até ' + args.ate if args.ate else 'sem hora limite'} · {args.orcamento or 'sem'} requests")
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
                "max_falhas": max(0, args.max_falhas), "seguidas": 0, "usados": 0, "feitos": [], "falhados": [], "sessoes": {}, "projeto": args.projeto,
                "programa": args.programa, "horas": num("orcamento_horas"), "usd": usd,
                "inicio": datetime.now().isoformat(timespec="seconds")}
        if usd is not None:
            novo["custo_inicio"] = sum(_custos().get(s, 0.0) for s in so)
        guardar(estado, novo)
    try:
        out = seguinte(args.root, estado, Path(args.relatorios), slug=args.slug)
    except (IntegracaoPendente, SlugObrigatorio) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    except ValueError as e:  # estado ilegível (JSON truncado/corrompido): não adivinhar, o user decide
        print(f"erro: estado da fila ilegível ({estado}): {e}; `--parar` abandona e apaga-o", file=sys.stderr)
        return 1
    except TimeoutError as e:  # lock preso: o estado fica intacto (sem «fila vazia» nem falhados); repetir `--seguinte --slug`
        print(f"erro: {e}; o estado não foi alterado, repetir `--seguinte`", file=sys.stderr)
        return 1
    if out["acao"] == "espera":
        print(f"a aguardar · {', '.join(out['sessoes'])}")
    elif out["acao"] == "lancou":
        print(f"lançado · {', '.join(out['slugs'])} · terminar o turno")
        if ler(estado).get("concorrencia"):
            print(armar_vigia(args, estado))
            print(f"VIGIAR · um só Monitor `tail -F {VIGIA_LOG}` · regras: `sp-fila.py --ajuda`")
    else:
        print(f"fila terminada: {out['motivo']}\nrelatório: {out['relatorio']}")
        if out.get("vigia") and "sem vigia" not in out["vigia"]:
            print(out["vigia"])
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-fila", main))
