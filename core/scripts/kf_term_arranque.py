"""`kaizen term fila|michi`: seletor de SPs com preview e confirmação antes de lançar em painel novo.

`michi` lista os SPs elegíveis (TODO/Doing, não-mãe, dependências em Done: `sp_list.eligibility`) e lança o michi
do escolhido num painel nomeado pelo slug; `fila` lista os programas com filhos elegíveis e lança o `sp-fila.py
--programa <mãe>` num painel `fila-<mãe>`. O SP é mostrado (preview) antes de perguntar; só «s»/«sim» lança,
tudo o resto cancela sem tocar em nada. `--sim` é a confirmação explícita para uso sem terminal. Sem backend de
painéis imprime o comando equivalente e termina com rc 0.

Uso: python -I scripts/kf_term_arranque.py michi|fila [--slug SP | --programa MÃE] [--sim] [--root DIR]
rc: 0 ok (lançado, cancelado, sem elegíveis ou sem backend), 1 falha a lançar, 2 SP/programa não elegível
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402
import painel_backend as pb  # noqa: E402

sp_list = kaizen_engine.load("sp-list")
PREVIEW_LINHAS = 30
SIM = {"s", "sim", "y", "yes"}


def _todos(root):
    return sp_list.collect(Path(root), include_done=True)


def elegiveis(root):
    """SPs elegíveis (a mesma regra do `sp-list`), Doing antes de TODO."""
    return sp_list.eligibility(_todos(root))[0]


def programas(root):
    """[(mãe, [filhos elegíveis])] só dos SP-mãe com pelo menos um filho elegível."""
    todos = _todos(root)
    eleg = sp_list.eligibility(todos)[0]
    out = []
    for mae in (s for s in todos if s.kind == "program" and s.status != "Done"):
        filhos = [s for s in eleg if s.parent == mae.slug and s.project == mae.project]
        if filhos:
            out.append((mae, filhos))
    return out


def preview(path, max_linhas=PREVIEW_LINHAS):
    """Corpo do SP sem frontmatter, cortado a `max_linhas` (com «…» quando há mais)."""
    linhas = Path(path).read_text(encoding="utf-8").splitlines()
    if linhas and linhas[0].strip() == "---":
        fim = next((i for i, l in enumerate(linhas[1:], 1) if l.strip() == "---"), None)
        linhas = linhas[fim + 1:] if fim is not None else linhas
    while linhas and not linhas[0].strip():
        linhas.pop(0)
    if len(linhas) > max_linhas:
        linhas = linhas[:max_linhas] + ["…"]
    return "\n".join(linhas)


def escolher(opcoes, entrada=input, saida=print):
    """Mostra `opcoes` [(rótulo, caminho)], lê um número e mostra o preview; devolve a opção ou None (q/vazio cancela)."""
    if not opcoes:
        return None
    escrever = saida.write if hasattr(saida, "write") else (lambda t: saida(t.rstrip("\n")))
    for i, (rotulo, _) in enumerate(opcoes, 1):
        escrever(f"{i}) {rotulo}\n")
    while True:
        r = entrada("número (q cancela): ").strip().lower()
        if r in ("", "q"):
            return None
        if r.isdigit() and 1 <= int(r) <= len(opcoes):
            rotulo, caminho = opcoes[int(r) - 1]
            escrever(f"\n--- {rotulo} ---\n{preview(caminho)}\n---\n")
            return opcoes[int(r) - 1]
        escrever(f"inválido: {r}\n")


def confirmar(pergunta, entrada=input, saida=print):
    """Só um «s»/«sim» explícito confirma; vazio ou qualquer outra coisa cancela."""
    return entrada(f"{pergunta} [s/N] ").strip().lower() in SIM


def comando_equivalente(modo, alvo):
    if modo == "fila":
        return f"python -I scripts/sp-fila.py --programa {alvo}"
    return f"claude  # depois: /michi {alvo}"


def spawn_real(backend):
    """spawn(modo, alvo) -> id do painel novo; reutiliza o `michi_handoff_auto` (michi) e o backend (fila)."""
    def spawn(modo, alvo):
        if modo == "michi":
            import michi_handoff_auto as mha
            res = mha.go(alvo, None, backend, mha._spawn_real(backend.nome))
            if not res["ok"]:
                raise pb.BackendError(res["erro"])
            return res["painel"]
        raiz = Path(__file__).resolve().parents[1]
        return backend.abrir([sys.executable, "-I", "scripts/sp-fila.py", "--programa", alvo], str(raiz))
    return spawn


def _nome_painel(modo, alvo):
    return f"fila-{alvo}" if modo == "fila" else alvo


def main(argv=None, root=None, backend="auto", spawn=None, entrada=input, saida=print, aviso_backend=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("modo", choices=("fila", "michi"))
    ap.add_argument("--slug", help="michi: SP a lançar (salta o seletor, ainda confirma)")
    ap.add_argument("--programa", help="fila: SP-mãe (salta o seletor, ainda confirma)")
    ap.add_argument("--sim", action="store_true", help="confirmação explícita (sem terminal)")
    ap.add_argument("--root", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    escrever = saida.write if hasattr(saida, "write") else (lambda t: saida(t.rstrip("\n")))
    root = Path(root or a.root or sp_list.DEFAULT_ROOT)

    if a.modo == "michi":
        opcoes = [(s.slug, s.path) for s in elegiveis(root)]
        pedido = a.slug
    else:
        opcoes = [(m.slug, m.path) for m, _ in programas(root)]
        pedido = a.programa
    if pedido:
        if pedido not in dict(opcoes):
            print(f"erro: {pedido} não elegível (precisa de TODO/Doing, não ser mãe e ter dependências em Done)"
                  if a.modo == "michi" else f"erro: programa {pedido} não elegível (sem filhos elegíveis)", file=sys.stderr)
            return 2
        escolha = (pedido, dict(opcoes)[pedido])
        escrever(f"--- {pedido} ---\n{preview(escolha[1])}\n---\n")
    elif not opcoes:
        escrever("sem SPs elegíveis\n" if a.modo == "michi" else "sem programas com SPs elegíveis\n")
        return 0
    else:
        escolha = escolher(opcoes, entrada, saida)
        if escolha is None:
            escrever("cancelado\n")
            return 0
    alvo = escolha[0]
    if not a.sim and not confirmar(f"lançar {a.modo} de {alvo} num painel novo?", entrada, saida):
        escrever("cancelado\n")
        return 0

    if backend == "auto":
        import kf_term_ls
        backend, aviso_backend = kf_term_ls.backend_por_config()
    if backend is None:
        if aviso_backend:
            print(f"aviso: {aviso_backend}", file=sys.stderr)
        escrever(f"{comando_equivalente(a.modo, alvo)}\n")
        return 0
    try:
        painel = (spawn or spawn_real(backend))(a.modo, alvo)
    except (pb.BackendError, OSError, subprocess.SubprocessError) as e:
        print(f"erro a lançar {a.modo} de {alvo}: {e}", file=sys.stderr)
        return 1
    try:
        backend.titulo(painel, _nome_painel(a.modo, alvo))
    except (pb.BackendError, OSError, subprocess.SubprocessError) as e:
        print(f"aviso: painel {painel} sem título ({e})", file=sys.stderr)
    escrever(f"lançado {a.modo} de {alvo} no painel {painel}\n")
    return 0


if __name__ == "__main__":
    for _f in (sys.stdout, sys.stderr):  # pipe no Windows: sem isto os acentos saem em cp1252
        _f.reconfigure(encoding="utf-8")
    sys.exit(main())
