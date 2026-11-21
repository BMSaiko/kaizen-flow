#!/usr/bin/env python3
"""Fila autónoma de SPs: escolhe o próximo SP elegível e lança-o (modo auto, sessão limpa).

Elegível = TODO, `modo: auto`, com `gates:`, dependências em Done, autorizações suficientes. Ordem:
prioridade, depois idade, com `depends_on` a mandar. Nunca faz push/PR: isso é do fecho de cada SP.

Uso:
  python -I scripts/sp-fila.py --dry-run [--max N] [--ate HH:MM] [--projeto P]   # ordem e exclusões
  python -I scripts/sp-fila.py [--max N] [--max-falhas N] [--ate HH:MM] [--projeto P] [--orcamento N]   # arranca a fila (para ao fim de N falhas seguidas, defeito 2)
  python -I scripts/sp-fila.py [--concorrencia N]   # modo paralelo: abre até N painéis `claude` (worktree e modelo do SP), sem orçamento nem máximo
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
# Módulos irmãos (a CLI e os testes continuam a ver tudo aqui): estado, plano, relatório, execução, painéis.
from sp_fila_estado import (MAX_DEFEITO, MAX_FALHAS_DEFEITO, ORCAMENTO, REQ_POR_SP, RELATORIOS, ESTADO, USER,  # noqa: E402,F401
                            atualizar, bloqueio, guardar, ler, migrar, run_hidden)
from sp_fila_plano import descendentes, limite, load, plan, render_plan, sem_commit, sp_list  # noqa: E402,F401
from sp_fila_relatorio import gastos, relatorio, render_gastos  # noqa: E402,F401
from sp_fila_execucao import (_custos, _ler_sp,  # noqa: E402,F401
                              seguinte, IntegracaoPendente, SlugObrigatorio)
import sp_fila_estado  # noqa: E402
from sp_fila_estado import estado_de  # noqa: E402
import sp_fila_execucao  # noqa: E402
import sp_fila_paineis  # noqa: E402
import sp_vigia  # noqa: E402
import kf_erros  # noqa: E402
import contextlib


def _erro(ec, oque, porque, estado, proximo):
    """Recusa no formato único (kf_erros): EC · o quê · porquê · estado guardado · próximo comando."""
    print(kf_erros.erro(ec, oque, porque, estado, proximo), file=sys.stderr)

MAX_PARALELO = 3  # teto de painéis michi abertos em simultâneo, somando todas as filas (paralelo e `--concorrencia`)
MODOS = ("sequencial", "paralelo")

AJUDA = """Orquestrador do sp-fila em paralelo (painéis):
- Modo: com `--programa <mãe>` vem de `execucao:` da mãe (vazio → perguntar ao user «sequencial ou paralelo?» e gravar com `sp-execucao.py <mãe> <modo>`); sequencial = 1 painel de cada vez, paralelo = até 3 (`MAX_PARALELO`, total das filas).
- O lançamento abre os painéis sozinho (`sp_fila_paineis.lancar`): por SP, worktree própria, separador com o slug, `claude --model <modelo do SP>` e `/michi --auto <SP>`; imprime «lançado em painéis» com slug · modelo · worktree. Sem vaga: o SP fica `pendente` e sai «sem vaga de painel». `--dry-run --concorrencia N` mostra os painéis previstos sem abrir nada.
- Terminar o turno depois de lançar. Cada painel grava o seu estado com `sp-estado.py <slug> <estado> --msg "<resumo>"`; `sp-estado.py --listar` mostra todas as filas e SPs pelo nome.
- Estado de cada SP: `pergunta` → AskUserQuestion ao user com o slug e a msg, a resposta segue no painel desse SP; `done` → `sb-worktree.py merge <slug>` com confirmação do user, depois `sp-fila.py --seguinte --slug <slug>`; `bloqueado`/`falhou` → avisar o user e `--seguinte --slug <slug>`.
- Merge antes do `--seguinte` (lê master). O `--seguinte` fecha o painel do SP, liberta a vaga e abre os próximos (se houver) sem perguntar; repetir até «fila terminada». `fechar-mae: <mãe>` = fechar a mãe na worktree dela.
- Relato por SP: ≤3 linhas + TLDR."""


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
        _erro("EC-045", f"estado da fila ilegível ({path}): {e}", "o JSON da fila está truncado ou corrompido",
              "ficheiro intacto (nada adivinhado)", "`sp-fila.py --parar` abandona e apaga-o")
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


def _limpar_paineis(fid):
    """A fila de painéis da corrida também sai (vagas livres, `sp-estado.py --listar` limpo); o vigia primeiro:
    não pode agir sobre uma fila a meio de ser apagada, nem sobre a fila nova que reutilize o mesmo id."""
    if not fid:
        return
    try:
        pid = sp_vigia.parar(sp_vigia.caminhos(sp_fila_paineis.pe.raiz() / fid)[0],
                             sp_fila_paineis.pe.pid_vivo, sp_vigia.matar_pid)
        if pid:
            print(f"vigia {pid} terminado")
    except Exception as e:  # noqa: BLE001
        print(f"aviso: vigia de {fid} não terminado: {e}", file=sys.stderr)
    try:
        sp_fila_paineis.pe.remover_fila(fid)
    except Exception as e:  # noqa: BLE001
        print(f"aviso: fila de painéis {fid} não removida: {e}", file=sys.stderr)


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
        _erro("EC-038", "fila obsoleta por abandonar", motivo, "fila intacta",
              "repetir com `--abandonar-obsoleta` (ou `--parar`)")
        return False
    _limpar_paineis((atual or {}).get("fila_paineis"))  # sem isto o vigia velho fecha a fila nova com o mesmo id
    estado.unlink(missing_ok=True)
    print("fila obsoleta abandonada")
    return True


def _arrancar_vigia(estado):
    """Paralelo: o vigia da fila de painéis corre destacado (merge, avisos, seguinte); um só por fila."""
    try:
        fid = ler(estado).get("fila_paineis")
        if not fid:
            return None
        pasta = sp_fila_paineis.pe.raiz() / fid
        pidf = sp_vigia.caminhos(pasta)[0]
        try:
            if sp_fila_paineis.pe.pid_vivo(int(pidf.read_text(encoding="utf-8").strip())):
                return None  # `--seguinte` com vigia já vivo
        except (OSError, ValueError):
            pass
        p = sp_vigia.arrancar(fid, Path(__file__).resolve().parent / "sp-vigia.py")
        print(f"vigia · pid {p.pid} · log {sp_vigia.caminhos(pasta)[1]}")
        return p
    except Exception as e:  # noqa: BLE001 — sem vigia a fila segue (avisos e merge pelo utilizador)
        print(f"aviso: vigia não arrancou: {e}", file=sys.stderr)
        return None


def _parser():
    ap = argparse.ArgumentParser(description="Fila autónoma de SPs")
    ap.add_argument("--abandonar-obsoleta", action="store_true", help="ao arrancar: abandona sem perguntar uma fila obsoleta (arrancada há mais de 60 min e nenhum SP em Doing); fila viva nunca é tocada")
    ap.add_argument("--dry-run", action="store_true", help="mostra a ordem e as exclusões, sem lançar")
    ap.add_argument("--seguinte", action="store_true", help="no fecho de um SP da fila: regista e lança o seguinte")
    ap.add_argument("--slug", help="com --seguinte: o SP que fechou (só essa sessão; sem ele fecham todas)")
    ap.add_argument("--gastos", action="store_true", help="mostra o custo (USD) de cada sessão da corrida; só mede, não limita")
    ap.add_argument("--ajuda", action="store_true", help="regras do orquestrador (painéis, perguntas, fecho de cada SP, relato)")
    ap.add_argument("--parar", action="store_true", help="abandona a fila")
    ap.add_argument("--max", type=int, default=None, help=f"nº máximo de SPs (defeito {MAX_DEFEITO}; em --concorrencia só conta se passado)")
    ap.add_argument("--ate", metavar="HH:MM", help="hora limite")
    ap.add_argument("--concorrencia", type=int, metavar="N", help="modo paralelo (N=1 também): abre até N painéis `claude`, cada um com a sua worktree e o modelo do SP; sem limite de quota")
    ap.add_argument("--orcamento", type=int, default=ORCAMENTO, help=f"teto opcional de requests totais; cada SP gasta {REQ_POR_SP} (sem ele, sem limite)")
    ap.add_argument("--max-falhas", type=int, default=MAX_FALHAS_DEFEITO, metavar="N", help=f"para a fila após N SPs falhados seguidos (defeito {MAX_FALHAS_DEFEITO}; 0 = sem este limite)")
    ap.add_argument("--projeto")
    ap.add_argument("--programa", metavar="SLUG", help="só a árvore deste SP-mãe; orçamento lido do frontmatter dela")
    ap.add_argument("--root", default=str(sp_list.DEFAULT_ROOT), help=argparse.SUPPRESS)
    ap.add_argument("--estado", default=str(ESTADO), help=argparse.SUPPRESS)
    ap.add_argument("--relatorios", default=str(RELATORIOS), help=argparse.SUPPRESS)
    return ap


def _concorrencia_invalida(args):
    """Rejeita `--concorrencia` fora de 1..MAX_PARALELO; True se já escreveu o erro."""
    if args.concorrencia is not None and args.concorrencia < 1:
        _erro("EC-067", f"--concorrencia exige N >= 1 (recebido {args.concorrencia})", "sem a opção a fila corre em série",
              "nada alterado", f"repetir com `--concorrencia 1..{MAX_PARALELO}` ou sem a opção")
        return True
    if args.concorrencia is not None and args.concorrencia > MAX_PARALELO:
        _erro("EC-067", f"--concorrencia máx. {MAX_PARALELO} painéis em simultâneo (recebido {args.concorrencia})",
              "o teto de painéis é global a todas as filas", "nada alterado", f"repetir com `--concorrencia {MAX_PARALELO}`")
        return True
    return False


def _cmd_parar(args, estado):
    """`--parar`: abandona a fila."""
    fid = None
    try:
        if estado.exists():
            print(_resumo_antigo(estado, args))
            fid = ler(estado).get("fila_paineis")
    except ValueError:  # corrompido: abandonar na mesma
        pass
    _limpar_paineis(fid)
    estado.unlink(missing_ok=True)
    print("fila abandonada")
    return 0


def _cmd_gastos(args, estado):
    """`--gastos`: custo de cada sessão da corrida."""
    if not estado.exists() and estado.with_name("ultima.json").exists():
        estado = estado.with_name("ultima.json")  # fila já terminada: os gastos ficam consultáveis
    if not estado.exists():
        _erro("EC-067", "sem fila em curso", "não há estado de fila nem a última fila terminada", "nada alterado",
              "arrancar com `sp-fila.py`")
        return 1
    atual = _ler_ou_erro(estado)
    if atual is None:
        return 1
    print(render_gastos(atual, _custos()))
    return 0


def _novo_estado(args, mae, modo, so):
    """Estado inicial de uma fila nova."""
    fm = mae[1] if mae else {}
    def num(k):
        return float(fm[k]) if fm.get(k) not in (None, "") else None
    usd = num("orcamento_usd")
    novo = {"max": args.max, "concorrencia": max(1, args.concorrencia or 0) if args.concorrencia else None, "ate": args.ate, "orcamento": int(num("orcamento_requests") or args.orcamento or 0) or None,
            "max_falhas": max(0, args.max_falhas), "seguidas": 0, "usados": 0, "modo": modo, "feitos": [], "falhados": [], "sessoes": {}, "projeto": args.projeto,
            "programa": args.programa, "horas": num("orcamento_horas"), "usd": usd,
            "inicio": datetime.now().isoformat(timespec="seconds")}
    if usd is not None:
        novo["custo_inicio"] = sum(_custos().get(s, 0.0) for s in so)
    return novo


def _imprimir(out, estado):
    """Mostra o que `seguinte` decidiu."""
    if out["acao"] == "espera":
        print(f"a aguardar · {', '.join(out['sessoes'])}")
        if out.get("pendentes"):
            print(f"sem vaga de painel (máx. {MAX_PARALELO} no total das filas) · pendentes: {', '.join(out['pendentes'])}")
    elif out["acao"] == "lancou":
        if out.get("itens"):  # paralelo: um painel por SP, já aberto com o modelo do SP
            print(f"lançado em painéis · {', '.join(out['slugs'])} · terminar o turno")
            for i in out["itens"]:
                print(f"  {i['slug']} · {i.get('modelo') or '?'} · {i.get('worktree') or '?'}")
            _arrancar_vigia(estado)
        else:
            print(f"lançado · {', '.join(out['slugs'])} · terminar o turno")
    else:
        print(f"fila terminada: {out['motivo']}\nrelatório: {out['relatorio']}")
        if out.get("fechar_mae"):
            m = out["fechar_mae"]
            print(f"fechar-mae: {m} · `sb-worktree.py ensure {m}` → `sp-move.py {m} done` → commit → `sb-worktree.py merge {m}`")


def _cmd_dry_run(args, items, so):
    """`--dry-run`: mostra o plano, os painéis previstos e os limites, sem criar estado."""
    fila, excluidos = plan(items, args.max, so, sem_commit(items))
    print(render_plan(fila, excluidos))
    if args.concorrencia:  # o que o lançador de painéis abriria (slug · modelo · worktree), sem abrir nada
        print("Painéis previstos:")
        print(sp_fila_paineis.render_dry_run(sp_fila_paineis.plano_dry_run(fila, maximo=args.concorrencia)))
    print(f"Limites: máx {args.max or 'sem'} SPs · {args.max_falhas or 'sem'} falhas seguidas · "
          f"{'até ' + args.ate if args.ate else 'sem hora limite'} · {args.orcamento or 'sem'} requests")
    return 0


def _preparar_estado(args, estado, mae, modo, so):
    """`--seguinte` exige fila em curso; senão cria o estado novo. Devolve o rc se não pode avançar, ou None."""
    if args.seguinte:
        if not estado.exists():
            _erro("EC-067", "sem fila em curso", "`--seguinte` só continua uma fila arrancada", "nada alterado",
                  "arrancar com `sp-fila.py`")
            return 1
    else:
        if estado.exists():
            try:
                atual = ler(estado)
                motivo = fila_obsoleta(atual, load(args.root, None), datetime.now())
            except ValueError:  # ilegível: o user decide com `--parar`
                atual = motivo = None
            if motivo and abandonar_obsoleta(estado, atual, motivo, args):
                pass
            elif motivo:
                return 1
        if estado.exists():
            with contextlib.suppress(ValueError):
                print(_resumo_antigo(estado, args), file=sys.stderr)
            _erro("EC-067", f"fila já em curso ({estado})", "só há uma fila por estado", "fila em curso intacta",
                  "`--seguinte` continua, `--parar` abandona")
            return 1
        if args.concorrencia and sp_fila_execucao._backend_defeito() is None:
            _erro("EC-036", sp_fila_execucao.falta_backend(), "a fila em paralelo abre painéis num multiplexador",
                  "nenhum estado criado", "instalar/abrir o WezTerm, tmux ou herdr, ou correr sem `--concorrencia`")
            return 1
        estado.parent.mkdir(parents=True, exist_ok=True)
        novo = _novo_estado(args, mae, modo, so)
        guardar(estado, novo)
    return None


def _resolver_programa(args, max_dado):
    """Carrega os SPs e, com `--programa`, a mãe e o modo da fila (`execucao:`). Devolve (items, mae, modo, rc); rc != None = erro."""
    items = load(args.root, args.projeto)
    mae = modo = None
    if args.programa:
        mae = next(((sp, fm) for sp, fm in items if sp.slug == args.programa), None)
        if mae is None:
            _erro("EC-067", f"SP-mãe desconhecido: {args.programa}", "nenhum SP em TODO/Doing tem esse slug", "nada alterado",
                  "`sp-list.py` para ver os slugs")
            return items, mae, modo, 1
        args.projeto = mae[0].project
        items = load(args.root, args.projeto)
    if mae and not args.dry_run and not args.seguinte:  # o modo é da mãe (`execucao:`), nunca escolhido pela fila
        modo = str(mae[1].get("execucao") or "").strip()
        if modo not in MODOS:
            _erro("EC-067", f"modo por escolher: sp-execucao.py {args.programa} sequencial|paralelo",
                  "o modo da fila é da mãe (`execucao:`), nunca escolhido pela fila", "nada alterado",
                  f"`python -I scripts/sp-execucao.py {args.programa} sequencial|paralelo`")
            return items, mae, modo, 1
        args.concorrencia = 1 if modo == "sequencial" else min(args.concorrencia or MAX_PARALELO, MAX_PARALELO)
        args.max = max_dado
    return items, mae, modo, None


def main(argv=None):
    args = _parser().parse_args(argv)
    max_dado = args.max
    if args.max is None and not args.concorrencia:
        args.max = MAX_DEFEITO  # em paralelo None = sem máximo
    estado = Path(args.estado)
    if args.estado == str(ESTADO):  # defeito: o estado é da mãe (`--programa`) ou onde está o SP (`--seguinte --slug`)
        if args.programa:
            estado = estado_de(args.programa)
        elif args.seguinte or args.gastos or args.parar:
            estado = sp_fila_estado.localizar(args.slug) or estado
    if _concorrencia_invalida(args):
        return 1

    if args.ajuda:
        print(AJUDA)
        return 0
    if args.parar:
        return _cmd_parar(args, estado)
    if args.gastos:
        return _cmd_gastos(args, estado)
    items, mae, modo, rc = _resolver_programa(args, max_dado)
    if rc is not None:
        return rc
    so = descendentes(items, args.programa) if args.programa else None
    if args.dry_run:
        return _cmd_dry_run(args, items, so)
    rc = _preparar_estado(args, estado, mae, modo, so)
    if rc is not None:
        return rc
    try:
        out = seguinte(args.root, estado, Path(args.relatorios), slug=args.slug)
    except (IntegracaoPendente, SlugObrigatorio) as e:
        _erro("EC-067", str(e), "o pedido à fila não pode avançar assim", "estado da fila intacto",
              "seguir a indicação acima e repetir `--seguinte`")
        return 1
    except ValueError as e:  # estado ilegível (JSON truncado/corrompido): não adivinhar, o user decide
        _erro("EC-045", f"estado da fila ilegível ({estado}): {e}", "o JSON da fila está truncado ou corrompido",
              "ficheiro intacto (nada adivinhado)", "`sp-fila.py --parar` abandona e apaga-o")
        return 1
    except TimeoutError as e:  # lock preso: o estado fica intacto (sem «fila vazia» nem falhados); repetir `--seguinte --slug`
        _erro("EC-042", str(e), "outro processo tem o lock da fila", "o estado não foi alterado", "repetir `--seguinte`")
        return 1
    _imprimir(out, estado)
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-fila", main))
