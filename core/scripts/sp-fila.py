#!/usr/bin/env python3
"""Fila autónoma de SPs: escolhe o próximo SP elegível e lança-o (modo auto, sessão limpa).

Elegível = TODO, `modo: auto`, com `gates:`, dependências em Done, autorizações suficientes. Ordem:
prioridade, depois idade, com `depends_on` a mandar. Nunca faz push/PR: isso é do fecho de cada SP.

Uso:
  python -I scripts/sp-fila.py --dry-run [--max N] [--ate HH:MM] [--projeto P]   # ordem e exclusões
  python -I scripts/sp-fila.py [--max N] [--max-falhas N] [--ate HH:MM] [--projeto P] [--orcamento N]   # arranca a fila (para ao fim de N falhas seguidas, defeito 2)
  python -I scripts/sp-fila.py [--concorrencia N]   # modo paralelo: plano JSON para até N subagents `Agent` (worktree própria), sem orçamento nem máximo
  python -I scripts/sp-fila.py --ajuda      # regras do agente principal no modo paralelo
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
rc: 0 ok, 1 falha
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Módulos irmãos (a CLI e os testes continuam a ver tudo aqui): estado, plano, relatório, execução, subagents.
from sp_fila_estado import (MAX_DEFEITO, MAX_FALHAS_DEFEITO, NO_WINDOW, ORCAMENTO, REQ_POR_SP, RELATORIOS, ESTADO, USER,  # noqa: E402,F401
                            atualizar, bloqueio, guardar, ler, migrar, run_hidden)
from sp_fila_plano import descendentes, limite, load, plan, render_plan, sem_commit, sp_list  # noqa: E402,F401
from sp_fila_relatorio import gastos, relatorio, render_gastos  # noqa: E402,F401
from sp_fila_execucao import (_custos, _ler_sp,  # noqa: E402,F401
                              seguinte, IntegracaoPendente, SlugObrigatorio)
import sp_fila_subagents  # noqa: E402

AJUDA = """Orquestrador do sp-fila em paralelo (subagents):
- O lançamento imprime um JSON `{"acao": "lancar", "itens": [...]}`: por item, um `Agent` com `prompt` e `description`, `run_in_background: true`, sem `isolation` (a worktree já existe em `worktree`); até N em simultâneo.
- Terminar o turno depois de lançar; cada subagent avisa ao acabar (notificação), sem vigia nem Monitor.
- Fim de cada subagent: ler a última linha `ESTADO:`. `pergunta` → AskUserQuestion ao user com o slug, depois SendMessage ao subagent com a resposta; `done` → `sb-worktree.py merge <slug>` com confirmação do user, depois `sp-fila.py --seguinte --slug <slug>`; `bloqueado`/`falhou` → avisar o user e `--seguinte --slug <slug>`.
- O `--seguinte` imprime o JSON dos próximos a lançar (se houver); repetir até «fila terminada».
- Relato por subagent: ≤3 linhas + TLDR."""


def _resumo_antigo(estado, args):
    """Resumo do estado antigo da fila (sessões e início) para mostrar antes de `--parar` ou de um arranque novo."""
    atual = ler(estado)
    sessoes = atual.get("sessoes") or {}
    linhas = [f"estado antigo: {len(sessoes)} sessão(ões), início {atual.get('inicio', '?')}"]
    linhas += [f"  SP {slug} · worktree {sess.get('worktree', '-')}" for slug, sess in sessoes.items()]
    return "\n".join(linhas)


def _ler_ou_erro(path):
    """Estado da fila ou None (com erro claro em stderr) se estiver ilegível."""
    try:
        return ler(path)
    except ValueError as e:
        print(f"erro: estado da fila ilegível ({path}): {e}; `--parar` abandona e apaga-o", file=sys.stderr)
        return None


OBSOLETA_MIN = 60  # fila arrancada há mais disto, sem SP da corrida em Doing = fila obsoleta


def fila_obsoleta(atual, items, agora, limite_min=OBSOLETA_MIN):
    """Motivo (str) se o estado é de uma fila obsoleta, None se está viva.

    Viva = algum SP da corrida em Doing ou arranque há menos de `limite_min`. Obsoleta = nenhuma das duas.
    Nunca devolve motivo para uma fila viva."""
    sessoes = atual.get("sessoes") or {}
    status = {sp.slug: sp.status for sp, _ in items}
    if any(status.get(s) == "Doing" for s in sessoes):
        return None
    try:
        idade = (agora - datetime.fromisoformat(atual.get("inicio"))).total_seconds() / 60
    except (TypeError, ValueError):
        return "estado sem data legível e sem SP em Doing"
    if idade <= limite_min:
        return None
    return f"arrancada há {int(idade)} min (limite {limite_min}) e nenhum SP em Doing ({len(sessoes)} sessão(ões) registada(s))"


def abandonar_obsoleta(estado, atual, motivo, args, entrada=input, tty=None):
    """Propõe abandonar a fila obsoleta e, confirmado, apaga o estado. True = abandonada."""
    print(f"fila obsoleta ({estado}): {motivo}", file=sys.stderr)
    tty = sys.stdin.isatty() if tty is None else tty
    ok = args.abandonar_obsoleta
    if not ok and tty:
        try:  # no Windows, stdin em NUL diz isatty() True e o input() dá EOF: vale como «não»
            ok = entrada("abandonar e arrancar uma nova? [s/N] ").strip().lower() in ("s", "sim", "y", "yes")
        except EOFError:
            ok = False
    if not ok:
        print("erro: fila obsoleta por abandonar; repetir com `--abandonar-obsoleta` (ou `--parar`)", file=sys.stderr)
        return False
    estado.unlink(missing_ok=True)
    print("fila obsoleta abandonada")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fila autónoma de SPs")
    ap.add_argument("--abandonar-obsoleta", action="store_true", help="ao arrancar: abandona sem perguntar uma fila obsoleta (arrancada há mais de 60 min e nenhum SP em Doing); fila viva nunca é tocada")
    ap.add_argument("--dry-run", action="store_true", help="mostra a ordem e as exclusões, sem lançar")
    ap.add_argument("--seguinte", action="store_true", help="no fecho de um SP da fila: regista e lança o seguinte")
    ap.add_argument("--slug", help="com --seguinte: o SP que fechou (só essa sessão; sem ele fecham todas)")
    ap.add_argument("--gastos", action="store_true", help="mostra o custo (USD) de cada sessão da corrida; só mede, não limita")
    ap.add_argument("--ajuda", action="store_true", help="regras do orquestrador (subagents, perguntas, fecho de cada SP, relato)")
    ap.add_argument("--parar", action="store_true", help="abandona a fila")
    ap.add_argument("--max", type=int, default=None, help=f"nº máximo de SPs (defeito {MAX_DEFEITO}; em --concorrencia só conta se passado)")
    ap.add_argument("--ate", metavar="HH:MM", help="hora limite")
    ap.add_argument("--concorrencia", type=int, metavar="N", help="modo paralelo (N=1 também): até N subagents `Agent` em background, cada um com a sua worktree; imprime o plano em JSON, sem limite de quota")
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
            if estado.exists():
                print(_resumo_antigo(estado, args))
        except ValueError:  # corrompido: abandonar na mesma
            pass
        estado.unlink(missing_ok=True)
        print("fila abandonada")
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
            try:
                atual, motivo = ler(estado), None
                motivo = fila_obsoleta(atual, load(args.root, None), datetime.now())
            except ValueError:  # ilegível: o user decide com `--parar`
                atual = motivo = None
            if motivo and abandonar_obsoleta(estado, atual, motivo, args):
                pass
            elif motivo:
                return 1
        if estado.exists():
            try:
                print(_resumo_antigo(estado, args), file=sys.stderr)
            except ValueError:
                pass
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
        if out.get("itens"):  # paralelo: o agente principal lança um `Agent` por item (regras: `--ajuda`)
            print(f"lançar como subagents · {', '.join(out['slugs'])} · regras: `sp-fila.py --ajuda`")
            print(sp_fila_subagents.plano(out["itens"]))
        else:
            print(f"lançado · {', '.join(out['slugs'])} · terminar o turno")
    else:
        print(f"fila terminada: {out['motivo']}\nrelatório: {out['relatorio']}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-fila", main))
