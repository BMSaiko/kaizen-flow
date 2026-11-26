#!/usr/bin/env python3
"""Fecha um SP numa só chamada: gates -> context-budget -> sp-move done -> COMMIT_*.md.

Pára sem mover o SP se um gate (ou o orçamento de contexto) falhar. Sem gates declarados corre
`test-fast.py fast`; bloqueia (RC 1) se faltar `## Prova de done` ou `## Reflect`, salvo `--sem-prova "motivo"` (fica registado no SP). Bloqueia também (RC 1, sem dispensa) se faltar a fase Docs: `## Docs` não vazia, `Docs: <resumo>` na prova, ou `Docs: skip — <motivo>`. Nunca faz commit nem push.
O COMMIT_*.md lista o stage explícito (um `git add` por caminho, sem o próprio COMMIT_*.md).

Uso:
  python -I scripts/sp-fechar.py <slug> [--project P] [--next] [--msg "assunto"]
                                 [--sem-budget] [--sem-testes] [--sem-commit] [--commit-dir DIR] [--sem-prova "motivo"]
RC 0 = fechado; 1 = gate/orçamento vermelho (SP fica em Doing); 2 = erro de uso.
rc: 0 fechado, 1 verificação falhou (SP continua em Doing), 2 gates inválidos
"""
import argparse
import re
from collections.abc import Callable, Sequence
from typing import Any
import sys as _s
import pathlib as _p
_s.path.insert(0, str(_p.Path(__file__).resolve().parent))
import painel_backend as _painel_backend  # noqa: E402
from painel_backend import run_hidden  # noqa: E402
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kf_git as _kf_git  # noqa: E402
import kaizen_engine  # noqa: E402
import kf_ligados  # noqa: E402
import sp_journal as _sp_journal  # noqa: E402
import wt_redirect  # noqa: E402
from sp_disco import ler_json as _ler_json  # noqa: E402

# Módulos de dependência ainda sem tipos: vistos como Any aqui (o ratchet não os mede).
painel_backend: Any = _painel_backend
kf_git: Any = _kf_git
sp_journal: Any = _sp_journal
ler_json: Any = _ler_json

sp_list: Any = kaizen_engine.load("sp-list")
sp_gates: Any = kaizen_engine.load("sp-gates")
sp_move: Any = kaizen_engine.load("sp-move")
sp_provas: Any = kaizen_engine.load("sp-provas")

HERE = Path(__file__).resolve().parent
SECRETS = (".env", ".key", ".pem", ".p12", ".pfx", "id_rsa", ".kdbx", "secrets.", ".secrets")


class FecharError(Exception):
    pass


def find_doing(root: str | Path, slug: str, project: str | None = None) -> Any:
    found = sp_list.encontrar(sp_list.collect(root, include_done=True), slug, project)
    if not found:
        raise FecharError(f"SP '{slug}' não encontrado; ver scripts/sp-list.py")
    if len(found) > 1:
        raise FecharError(f"SP '{slug}' ambíguo; usar --project")
    if found[0].status != "Doing":
        raise FecharError(f"SP '{slug}' está em {found[0].status}, não em Doing; corre sp-move.py {slug} doing")
    return found[0]


def passo(nome: str, fn: Callable[..., Any], *args: Any) -> Any:
    """Corre um passo com progresso no stderr (início, fim e duração); devolve o resultado de fn."""
    print(f"[sp-fechar] > {nome} ...", file=sys.stderr, flush=True)
    t0 = time.monotonic()
    res = fn(*args)
    rc = res[0] if isinstance(res, tuple) else 0
    print(f"[sp-fechar] {'ok' if not rc else 'FALHA rc=' + str(rc)} {nome} {time.monotonic() - t0:.1f}s",
          file=sys.stderr, flush=True)
    return res


def run_gates(sp: Any) -> tuple[int, str, list[dict[str, Any]]]:
    """Devolve (rc, texto, resultados). rc 0 = verdes ou sem gates."""
    gates = sp_gates.parse_gates(sp.path.read_text(encoding="utf-8"))
    if not gates:
        return 0, "gates: nenhum declarado", []
    bad = sp_gates.problems(gates)
    if bad:
        return 2, "\n".join(bad), []
    results = sp_gates.run(gates)
    ok = all(r["rc"] == 0 for r in results) and len(results) == len(gates)
    return (0 if ok else 1), sp_gates.summary(results), results


def pacote_de_provas(sp: Any, resultados: list[dict[str, Any]], cwd: str | Path) -> tuple[int, list[str]]:
    """Gera `sp/proofs/<slug>/provas.json` e valida-o. Devolve (rc, linhas); só SPs de 2026-11-13 em diante."""
    if not sp_provas.exige_pacote(sp):
        return 0, []
    pasta, d = sp_provas.gravar(sp, cwd, None, resultados)
    probs = sp_provas.validar(d, sp_provas.com_ui(sp), pasta)
    if probs:
        return 1, [f"PACOTE: {p}" for p in probs] + [f"{sp.slug}: pacote de provas inválido (anexar com sp-provas.py --imagem, ou --sem-prova \"motivo\")"]
    return 0, [f"PROVAS: {pasta / 'provas.json'}"]


def run_budget() -> tuple[int, str]:
    # opcional: o pacote kaizen-flow não leva o script do orçamento (glob evita referência dura)
    script = next(iter(HERE.glob("context-budg*.py")), None)
    if script is None:
        return 0, "context-budget: ausente (ignorado)"
    r = run_hidden([sys.executable, "-I", str(script)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-3:])
    return r.returncode, f"context-budget rc={r.returncode}\n{tail}"


def run_fast() -> tuple[int, str]:
    """test-fast.py fast quando o SP não declara gates. Opcional: o pacote kaizen-flow pode não o levar."""
    script = HERE / "test-fast.py"
    if not script.exists():
        return 0, "test-fast: ausente (ignorado)"
    r = run_hidden([sys.executable, "-I", str(script), "fast"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-8:])
    return r.returncode, f"test-fast rc={r.returncode}\n{tail}"


def avisos(sp_text: str) -> list[str]:
    """Faltas (bloqueiam o fecho sem --sem-prova) se faltar a prova de done ou o Reflect de fase/final."""
    def body(title: str) -> str:
        m = re.search(rf"^## {title}[^\n]*\n(.*?)(?=^## |\Z)", sp_text, re.S | re.M)
        return m.group(1) if m else ""
    out = []
    if not body("Prova de done").strip():
        out.append("FALTA: sem '## Prova de done' no SP (registar a prova como cliente final)")
    if not re.search(r"^[ \t]*(?:[-*][ \t]+)?Reflect \S", body("Reflect"), re.M):
        out.append("FALTA: sem linhas 'Reflect <fase>:' no SP (correr /reflect fase|final)")
    return out


def falta_docs(sp_text: str) -> list[str]:
    """Lista de faltas (vazia = ok) da fase Docs. Aceita `## Docs` não vazia, `Docs: <algo>` na
    `## Prova de done`, ou `Docs: skip — <motivo>` com motivo. `Docs: skip` sem motivo não conta."""
    def body(title: str) -> str:
        m = re.search(rf"^## {title}[^\n]*\n(.*?)(?=^## |\Z)", sp_text, re.S | re.M)
        return m.group(1) if m else ""
    skip = re.search(r"^Docs:\s*skip\b(.*)$", body("Prova de done"), re.M | re.I)
    if skip:
        motivo = skip.group(1).strip(" \t—–-:")
        return [] if motivo else ["FALTA: 'Docs: skip' sem motivo (escrever 'Docs: skip — <motivo>')"]
    if body("Docs").strip() or re.search(r"^Docs:\s*\S", body("Prova de done"), re.M):
        return []
    return ["FALTA: sem prova da fase Docs (registar '## Docs' ou 'Docs: skip — <motivo>')"]


def registar_dispensa(path: Path, motivo: str) -> None:
    """Acrescenta ao SP a dispensa consciente de prova/reflect (bytes: preserva CRLF)."""
    nl = "\r\n" if b"\r\n" in path.read_bytes() else "\n"
    linha = nl + "## Dispensa de prova/reflect" + nl + nl + f"{datetime.now():%Y-%m-%d}: {motivo}" + nl
    with open(path, "ab") as fh:
        fh.write(linha.encode("utf-8"))


def changed_paths(cwd: str | Path) -> list[str]:
    """Caminhos alterados/novos segundo o git, sem COMMIT_*.md nem segredos. Vazio fora de repo git."""
    r = run_hidden(["git", "-C", str(cwd), "status", "--porcelain", "-uall"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return []
    paths = []
    for line in r.stdout.splitlines():
        if line[:2] == "D ":  # apagamento já em stage (ex.: origem de um rename): `git add` falharia
            continue
        p = line[3:].split(" -> ")[-1].strip().strip('"')
        name = Path(p).name
        if name.startswith("COMMIT_") or any(s in name for s in SECRETS):
            continue
        paths.append(p)
    return sorted(set(paths))


PROJETO_KF = "kaizenflow"


def kf_por_sincronizar(cwd: str | Path, tudo: bool = False) -> str:
    """Mensagem de bloqueio se o diff altera ficheiros do motor cuja cópia no pacote kaizen-flow difere; senão ''.
    `tudo` (SP do projeto kaizenflow): o sync é obrigatório, compara todos os ficheiros ligados e não só os tocados."""
    core = kf_ligados.core_dir()
    if core is None:
        return ""
    nomes = None if tudo else kf_ligados.tocados(changed_paths(cwd), core)
    difs = kf_ligados.fora_de_sincronia(Path(cwd) / "scripts", core, nomes)
    if not difs:
        return ""
    return f"kaizen-flow fora de sincronia ({', '.join(difs)}): correr /kaizen-sync e repetir o fecho"


def write_commit(cwd: str | Path, slug: str, subject: str, paths: Sequence[str]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(cwd) / f"COMMIT_{stamp}.md"
    stage = "\n".join(f"git add {p}" for p in paths)
    out.write_text(
        f"## Mensagem\n\n```\n{subject}\n\nFecha o SP {slug} (gates verdes, sp-fechar.py).\n```\n\n"
        f"## Stage\n\n```\n{stage}\n```\n\n"
        f"## Fora do commit\n\nNada além do que o git status mostrava; rever antes de confirmar.\n",
        encoding="utf-8")
    return out


def worktree_hint(cwd: str | Path, slug: str) -> str | None:
    """Se `cwd` é uma worktree (não o checkout principal), o passo que falta depois do commit."""
    def git(*a: str) -> str | None:
        r = kf_git.run(cwd, *a, run=run_hidden)
        return r.stdout.strip() if r.returncode == 0 else None
    gd, common = git("rev-parse", "--path-format=absolute", "--git-dir"), git("rev-parse", "--path-format=absolute", "--git-common-dir")
    if not gd or not common or gd == common:
        return None
    return (f"WORKTREE: depois do commit: python -I scripts/sb-worktree.py merge {slug} && "
            f"python -I scripts/sb-worktree.py clean {slug}")


FILA_ESTADO = Path.home() / ".claude" / "sp-fila-estado.json"


def em_fila(slug: str, estado: Path | None = None) -> bool:
    """True se `slug` é uma sessão lançada pela fila (consta de `sessoes` no estado)."""
    if estado is None:  # estados por mãe (`~/.claude/sp-fila/<mãe>/fila.json`) e o único antigo
        base = Path.home() / ".claude" / "sp-fila"
        cands = sorted(base.glob("*/fila.json")) if base.is_dir() else []
        return any(em_fila(slug, c) for c in [*cands, FILA_ESTADO])
    try:
        return slug in ler_json(estado, {}).get("sessoes", {})
    except AttributeError:
        return False


@dataclass(frozen=True)
class CaminhosFila:
    """Raízes do estado da fila (injetáveis nos testes); `None` = defeito do módulo dono."""
    estado_root: object = None
    base: object = None
    legado: object = None


def _gravar_estado(slug: str, caminhos: "CaminhosFila | None" = None) -> tuple[list[str], Any]:
    """Grava `done` na fila do SP (mãe: `sessoes` → `feitos`; painéis: `done`, também vindo de `bloqueado`).

    Devolve (linhas, pane a fechar ou None); fora da fila: ([], None)."""
    import sp_fila_estado as _fe
    import sp_painel_estado as _pe
    fe: Any = _fe
    pe: Any = _pe
    c = caminhos or CaminhosFila()
    estado_root = c.estado_root
    caminho = fe.localizar(slug, base=c.base, legado=c.legado)
    if caminho is None:
        return [], None
    dados = {}

    def _mover(estado: dict[str, Any]) -> None:
        dados["fila"] = estado.get("fila_paineis")
        if estado["sessoes"].pop(slug, None) is not None and slug not in estado["feitos"]:
            estado["feitos"].append(slug)

    fe.atualizar(caminho, _mover)
    linhas, pane = [f"{slug}: fila — sessão passa a feita"], None
    fila = dados["fila"]
    if not fila:
        return linhas, None
    try:
        pane = pe.ler(fila, slug, root=estado_root).get("pane")
        pe.transitar(slug, "done", fila=fila, root=estado_root, forcar_done=True)
        linhas[0] = f"{slug}: fila {fila} gravada em done"
    except pe.ErroEstado as exc:
        linhas.append(f"aviso: estado da fila não gravado ({exc})")
    return linhas, pane


def limpar_estado(slug: str, *raizes: str | Path | None) -> list[str]:
    """Apaga o checkpoint e o journal do SP fechado (`.kaizen/estado/<slug>.*`) em cada raiz; devolve as linhas."""
    apagados = []
    for raiz in dict.fromkeys(str(r) for r in raizes if r):
        for f in sp_journal.caminhos(raiz, slug):
            if f.exists():
                try:
                    f.unlink()
                    apagados.append(f.name)
                except OSError as exc:
                    apagados.append(f"{f.name} (falhou: {exc})")
    return [f"ESTADO: limpo {', '.join(apagados)}"] if apagados else []


def _fechar_pane(pane: Any, backend: Any, emitir: Callable[[list[str]], None] | None = None,
                 linhas: Sequence[str] = ()) -> list[str] | None:
    """Fecha o pane do SP por último (pode ser o do próprio `sp-fechar`): `emitir(linhas)` antes; falha = linha de aviso."""
    if not pane:
        return None
    if backend is None:
        return [f"aviso: sem backend de painéis, pane {pane} fica aberto"]
    if emitir:
        emitir(list(linhas))
    try:
        backend.fechar(pane)
    except Exception as exc:  # noqa: BLE001 — fechar o pane nunca muda o rc
        return [f"aviso: pane {pane} não fechado ({exc})"]
    return None


def gravar_done_fila(slug: str, backend: Any = None, caminhos: "CaminhosFila | None" = None,
                     emitir: Callable[[list[str]], None] | None = None) -> list[str]:
    """Estado da fila em `done` e pane fechado (injetável nos testes); devolve as linhas, vazias fora da fila."""
    linhas, pane = _gravar_estado(slug, caminhos)
    return [*linhas, *(_fechar_pane(pane, backend, emitir, linhas) or [])]


def filhos_da_mae(sps: Sequence[Any], kid: Any) -> list[str]:
    """Slugs em `children:` do frontmatter da mãe de `kid` (vazio se a mãe não existe ou não os lista)."""
    mae = next((s for s in sps if s.slug == kid.parent and s.project == kid.project), None)
    if not mae:
        return []
    texto = mae.path.read_text(encoding="utf-8").replace("\r\n", "\n")
    fim = texto.find("\n---", 4)
    return re.findall(r"^\s+- slug:\s*(\S+)", texto[:fim] if fim > 0 else texto, flags=re.M)


def seguinte(root: str | Path, slug: str, project: str | None = None, fila: bool = False) -> str:
    """Linha com o passo seguinte de um filho fechado: próximo elegível, fecho da mãe, ou '' (SP sem mãe).

    Em fila só o driver lança o seguinte: a sessão regista e reporta (`sp-fila.py --seguinte --slug`)."""
    if fila:
        return f"FILA: {slug} feito; só reportar e fechar, o driver lança o seguinte (sp-fila.py --seguinte --slug {slug})"
    sps = sp_list.collect(root, include_done=True)
    kid = next((s for s in sps if s.slug == slug and (not project or s.project == project)), None)
    if not kid or not kid.parent:
        return ""
    irmaos = [s for s in sps if s.project == kid.project and s.parent == kid.parent and s.slug != slug]
    feitos = {s.slug for s in irmaos if s.status == "Done"} | {slug}
    prontos = [s for s in irmaos if s.status == "TODO" and all(d in feitos for d in s.depends_on)]
    if prontos:
        return f"PRÓXIMO FILHO: {prontos[0].slug} (manual: AskUserQuestion «abrir?»; auto: sp-fechar --next)"
    # irmãos listados em `children` da mãe mas não vistos (ramo atrás de master): contam como por fechar
    vistos = {s.slug for s in irmaos} | {slug}
    invisiveis = [c for c in filhos_da_mae(sps, kid) if c not in vistos]
    if invisiveis:
        return (f"SEGUINTE: {kid.parent} lista filhos que este ramo não vê ({', '.join(invisiveis)}); "
                f"`git merge master` e repetir antes de fechar a mãe")
    if all(s.status == "Done" for s in irmaos):
        return (f"ÚLTIMO FILHO: fechar a mãe {kid.parent} numa worktree, nunca no checkout principal: "
                f"sb-worktree.py ensure {kid.parent} → sp-move.py {kid.parent} done → commit → sb-worktree.py merge {kid.parent} "
                f"(manual: AskUserQuestion «fechar?»; auto: fechar sozinho)")
    return f"SEGUINTE: nenhum filho elegível de {kid.parent} (os restantes dependem de SPs por fechar)"


def _verificar(sp: Any, slug: str, testes: bool, sem_prova: str | None,
               commit_dir: str | Path) -> tuple[int | None, list[str]]:
    """Gates, test-fast, Docs, prova/reflect e pacote de provas. Devolve (rc, linhas); rc None = pode fechar."""
    lines = []
    rc, text, resultados = passo("gates", run_gates, sp)
    lines.append(text)
    if rc:
        return rc, [*lines, f"{slug}: gate vermelho, SP continua em Doing"]
    if testes and not sp_gates.parse_gates(sp.path.read_text(encoding="utf-8")):
        rc, text = passo("test-fast", run_fast)
        lines.append(text)
        if rc:
            return 1, [*lines, f"{slug}: test-fast vermelho, SP continua em Doing"]
    docs = falta_docs(sp.path.read_text(encoding="utf-8"))
    if docs:  # --sem-prova não dispensa Docs
        return 1, lines + docs + [f"{slug}: SP continua em Doing (registar a fase Docs; --sem-prova não a dispensa)"]
    faltas = avisos(sp.path.read_text(encoding="utf-8"))
    if faltas and not sem_prova:
        return 1, lines + faltas + [f"{slug}: sem prova/reflect, SP continua em Doing (registar, ou --sem-prova \"motivo\")"]
    if faltas:
        registar_dispensa(sp.path, sem_prova or "")
        lines += [f.replace("AVISO", "DISPENSADO") for f in faltas]
    if not sem_prova:
        rc, extra = passo("pacote de provas", pacote_de_provas, sp, resultados, commit_dir)
        lines += extra
        if rc:
            return 1, lines
    return None, lines


def _linha_commit(commit_dir: str | Path, slug: str, msg: str | None) -> str:
    paths = changed_paths(commit_dir)
    if not paths:
        return "COMMIT: nada para stage (sem alterações ou fora de repo git)"
    return f"COMMIT: {write_commit(commit_dir, slug, msg or f'vault: fecha {slug}', paths)}"


def _bloqueado(sp: Any, lines: list[str], commit: bool, budget: bool, commit_dir: str | Path) -> bool:
    """Acrescenta a `lines` o motivo e devolve True se o fecho não pode avançar (sync/orçamento)."""
    if commit:
        bloqueio = kf_por_sincronizar(commit_dir, tudo=sp.project == PROJETO_KF)
        if bloqueio:
            lines += [bloqueio, f"{sp.slug}: kaizen-flow por sincronizar, SP continua em Doing"]
            return True
    if budget:
        rc, text = passo("context-budget", run_budget)
        lines.append(text)
        if rc:
            lines.append(f"{sp.slug}: orçamento de contexto excedido, SP continua em Doing")
            return True
    return False


def fechar(root: str | Path, slug: str, project: str | None = None, nxt: bool = False, msg: str | None = None,
           budget: bool = True, commit: bool = True, commit_dir: str | Path = ".", testes: bool = True,
           sem_prova: str | None = None, backend: Any = None, emitir: Callable[[list[str]], None] | None = None,
           estado_root: Any = None) -> tuple[int, list[str]]:
    """Corre o fecho. Devolve (rc, linhas). Sessão da fila: grava `done` na fila e, com `backend`, fecha o pane no fim (`emitir` imprime antes)."""
    t_total = time.monotonic()
    sp = find_doing(root, slug, project)
    slug = sp.slug  # o resto (sp_move, seguinte, COMMIT) usa o slug completo, não o `ref` curto
    rc, lines = _verificar(sp, slug, testes, sem_prova, commit_dir)
    if rc is not None:
        return rc, lines
    if _bloqueado(sp, lines, commit, budget, commit_dir):
        return 1, lines
    fila = em_fila(slug)
    if nxt and fila:
        return 1, [*lines, f"{slug}: sessão da fila, --next não se aplica (o driver lança o seguinte)"]
    pane = None
    if nxt:
        lines.append(sp_move.advance(root, slug, sp.project))
    else:
        lines.append(sp_move.move(root, slug, "done", sp.project))
        lines += limpar_estado(slug, root, commit_dir)
        linhas_fila, pane = _gravar_estado(slug, CaminhosFila(estado_root)) if fila else ([], None)
        lines += linhas_fila
    prox = "" if nxt else seguinte(root, slug, sp.project, fila)
    if prox:
        lines.append(prox)
    if commit:
        lines.append(_linha_commit(commit_dir, slug, msg))
    hint = worktree_hint(commit_dir, slug)
    if hint:
        lines.append(hint)
    print(f"[sp-fechar] total {time.monotonic() - t_total:.1f}s", file=sys.stderr, flush=True)
    if not nxt and pane:
        lines += _fechar_pane(pane, backend, emitir, lines) or []
    return 0, lines


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fecha um SP: gates, orçamento, Done e COMMIT_*.md")
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--slug", dest="slug_opt", help="alias de slug posicional")
    ap.add_argument("--project")
    ap.add_argument("--next", action="store_true", help="abre o próximo filho elegível do programa")
    ap.add_argument("--msg", help="assunto do commit (defeito: vault: fecha <slug>)")
    ap.add_argument("--sem-budget", action="store_true")
    ap.add_argument("--sem-testes", action="store_true", help="não correr test-fast quando o SP não tem gates")
    ap.add_argument("--sem-commit", action="store_true")
    ap.add_argument("--sem-prova", metavar="MOTIVO", help="dispensa consciente de '## Prova de done'/Reflect; fica registada no SP")
    ap.add_argument("--commit-dir", default=".", help="repo onde gerar o COMMIT_*.md (defeito: cwd)")
    ap.add_argument("--root", default=str(sp_list.DEFAULT_ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    args.slug = args.slug_opt or args.slug
    if not args.slug:
        ap.error("falta o slug (posicional ou --slug); ver scripts/sp-list.py")
    args.slug = sp_list.normalize_ref(args.root, args.slug)
    if argv is None and args.root == str(sp_list.DEFAULT_ROOT):
        rc = wt_redirect.redirect(__file__, args.slug, sys.argv[1:])
        if rc is not None:
            return rc
    impresso: list[int] = []

    def emitir(linhas: list[str]) -> None:  # o pane pode ser o deste processo: as linhas saem antes de ele fechar
        print("\n".join(linhas), flush=True)
        impresso.append(1)
    try:
        backend = painel_backend.escolher_por_config("auto") if em_fila(args.slug) else None
        rc, lines = fechar(args.root, args.slug, args.project, args.next, args.msg,
                           not args.sem_budget, not args.sem_commit, args.commit_dir,
                           not args.sem_testes, args.sem_prova, backend=backend, emitir=emitir)
    except (FecharError, sp_move.SpMoveError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    if impresso:  # o `emitir` já imprimiu tudo menos o que veio depois do fecho do pane
        lines = lines[-1:] if lines and lines[-1].startswith("aviso: pane") else []
    if lines:
        print("\n".join(lines))
    return rc


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-fechar", main))
