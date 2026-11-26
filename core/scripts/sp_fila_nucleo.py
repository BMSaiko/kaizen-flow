"""Núcleo herdr do sp-fila: subcomandos `run|status|watch|stop|resume|gastos`, motor `--motor herdr` e retoma idempotente.

Fica por cima de `herdr_ops`/`HerdrBackend` e do estado existente (formato retrocompatível): `traduzir` converte o
subcomando nas flags antigas (que continuam a funcionar), `backend_herdr` dá o backend do motor novo e `retomar`
reconcilia o estado com os painéis vivos do herdr (re-adota vivos, marca mortos como falhou, nunca relança worktrees).

Uso: módulo importado por sp-fila.py; sem execução direta
rc: n/a
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import herdr_ops  # noqa: E402
import painel_backend  # noqa: E402
import sp_painel_estado as pe  # noqa: E402

SUBCOMANDOS = ("run", "status", "watch", "stop", "resume", "gastos")
MOTORES = ("herdr", "antigo")
MOTOR_ATUAL = "antigo"  # fixado por sp-fila.py a cada arranque


def motor_defeito(which=shutil.which):
    """`herdr` se o CLI existir; senão `antigo` (fallback mínimo: WezTerm/tmux/background da config)."""
    return "herdr" if which("herdr") else "antigo"
HERDR_RUN = None  # os testes trocam-no pelo FakeHerdr; None = CLI real
RUN = None  # idem para o `run` do `seguinte` (worktree, git, sp-move)

_ANTIGO = {"stop": ["--parar"], "gastos": ["--gastos"]}


def traduzir(argv):
    """(subcomando, argv nas flags antigas). Sem subcomando = `run` (as flags de sempre continuam a valer)."""
    argv = list(argv)
    if argv and argv[0] in SUBCOMANDOS:
        return argv[0], _ANTIGO.get(argv[0], []) + argv[1:] if argv[0] in _ANTIGO else argv[1:]
    return "run", argv


def backend_herdr():
    """Backend de painéis do motor herdr."""
    return painel_backend.HerdrBackend(run=HERDR_RUN or painel_backend.run_hidden)


def ops_herdr():
    return herdr_ops.HerdrOps(run=HERDR_RUN or painel_backend.run_hidden)


def retomar(estado, ops=None, root=None):
    """Reconcilia `estado` (dict da fila) com o herdr. Devolve {adotados, mortos, vigia} e altera `estado` em memória.

    Idempotente: viva = o `pane` registado ainda existe; morta = o SP ativo cujo painel desapareceu passa a `falhou`
    (liberta a vaga) e a `falhados`. Não toca em worktrees nem lança agentes: o que sobra volta a andar com `run`/`--seguinte`."""
    ops = ops or ops_herdr()
    fila = estado.get("fila_paineis")
    vivos = {p.get("pane_id") for p in ops.paineis()}
    adotados, mortos = [], []
    for slug in list(estado.get("sessoes") or {}):
        try:
            reg = pe.ler(fila, slug, root=root) if fila else {}
        except pe.ErroEstado:
            reg = {}
        pane = reg.get("pane")
        if pane and pane in vivos:
            adotados.append(slug)
            continue
        if reg.get("estado") in pe.FINAIS and reg.get("estado") == "done":
            continue  # terminou: o `--seguinte` fecha-o
        if fila and reg.get("estado") in pe.ATIVOS:
            pe.transitar(slug, "falhou", msg="painel morto na retoma", fila=fila, root=root)
        mortos.append(slug)
        estado["sessoes"].pop(slug, None)
        if slug not in estado.setdefault("falhados", []):
            estado["falhados"].append(slug)
    return {"adotados": adotados, "mortos": mortos}
