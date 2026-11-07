#!/usr/bin/env python3
"""Fecha um SP numa só chamada: gates -> context-budget -> sp-move done -> COMMIT_*.md.

Pára sem mover o SP se um gate (ou o orçamento de contexto) falhar. Sem gates declarados corre
`test-fast.py fast`; bloqueia (RC 1) se faltar `## Prova de done` ou `## Reflect`, salvo `--sem-prova "motivo"` (fica registado no SP). Nunca faz commit nem push.
O COMMIT_*.md lista o stage explícito (um `git add` por caminho, sem o próprio COMMIT_*.md).

Uso:
  python -I scripts/sp-fechar.py <slug> [--project P] [--next] [--msg "assunto"]
                                 [--sem-budget] [--sem-testes] [--sem-commit] [--commit-dir DIR] [--sem-prova "motivo"]
RC 0 = fechado; 1 = gate/orçamento vermelho (SP fica em Doing); 2 = erro de uso.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kf_git  # noqa: E402
import kaizen_engine  # noqa: E402
import kf_ligados  # noqa: E402
import wt_redirect  # noqa: E402

sp_list = kaizen_engine.load("sp-list")
sp_gates = kaizen_engine.load("sp-gates")
sp_move = kaizen_engine.load("sp-move")

HERE = Path(__file__).resolve().parent
SECRETS = (".env", ".key", ".pem", ".p12", ".pfx", "id_rsa", ".kdbx", "secrets.", ".secrets")


class FecharError(Exception):
    pass


def find_doing(root, slug, project=None):
    found = [sp for sp in sp_list.collect(root, include_done=True)
             if sp.slug == slug and (not project or sp.project == project)]
    if not found:
        raise FecharError(f"SP '{slug}' não encontrado; ver scripts/sp-list.py")
    if len(found) > 1:
        raise FecharError(f"SP '{slug}' ambíguo; usar --project")
    if found[0].status != "Doing":
        raise FecharError(f"SP '{slug}' está em {found[0].status}, não em Doing; corre sp-move.py {slug} doing")
    return found[0]


def passo(nome, fn, *args):
    """Corre um passo com progresso no stderr (início, fim e duração); devolve o resultado de fn."""
    print(f"[sp-fechar] > {nome} ...", file=sys.stderr, flush=True)
    t0 = time.monotonic()
    res = fn(*args)
    rc = res[0] if isinstance(res, tuple) else 0
    print(f"[sp-fechar] {'ok' if not rc else 'FALHA rc=' + str(rc)} {nome} {time.monotonic() - t0:.1f}s",
          file=sys.stderr, flush=True)
    return res


def run_gates(sp):
    """Devolve (rc, texto). rc 0 = verdes ou sem gates."""
    gates = sp_gates.parse_gates(sp.path.read_text(encoding="utf-8"))
    if not gates:
        return 0, "gates: nenhum declarado"
    bad = sp_gates.problems(gates)
    if bad:
        return 2, "\n".join(bad)
    results = sp_gates.run(gates)
    ok = all(r["rc"] == 0 for r in results) and len(results) == len(gates)
    return (0 if ok else 1), sp_gates.summary(results)


def run_budget():
    # opcional: o pacote kaizen-flow não leva o script do orçamento (glob evita referência dura)
    script = next(iter(HERE.glob("context-budg*.py")), None)
    if script is None:
        return 0, "context-budget: ausente (ignorado)"
    r = subprocess.run([sys.executable, "-I", str(script)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-3:])
    return r.returncode, f"context-budget rc={r.returncode}\n{tail}"


def run_fast():
    """test-fast.py fast quando o SP não declara gates. Opcional: o pacote kaizen-flow pode não o levar."""
    script = HERE / "test-fast.py"
    if not script.exists():
        return 0, "test-fast: ausente (ignorado)"
    r = subprocess.run([sys.executable, "-I", str(script), "fast"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-8:])
    return r.returncode, f"test-fast rc={r.returncode}\n{tail}"


def avisos(sp_text):
    """Faltas (bloqueiam o fecho sem --sem-prova) se faltar a prova de done ou o Reflect de fase/final."""
    def body(title):
        m = re.search(rf"^## {title}[^\n]*\n(.*?)(?=^## |\Z)", sp_text, re.S | re.M)
        return m.group(1) if m else ""
    out = []
    if not body("Prova de done").strip():
        out.append("FALTA: sem '## Prova de done' no SP (registar a prova como cliente final)")
    if not re.search(r"^Reflect \S", body("Reflect"), re.M):
        out.append("FALTA: sem linhas 'Reflect <fase>:' no SP (correr /reflect fase|final)")
    return out


def registar_dispensa(path, motivo):
    """Acrescenta ao SP a dispensa consciente de prova/reflect (bytes: preserva CRLF)."""
    nl = "\r\n" if b"\r\n" in path.read_bytes() else "\n"
    linha = nl + "## Dispensa de prova/reflect" + nl + nl + f"{datetime.now():%Y-%m-%d}: {motivo}" + nl
    with open(path, "ab") as fh:
        fh.write(linha.encode("utf-8"))


def changed_paths(cwd):
    """Caminhos alterados/novos segundo o git, sem COMMIT_*.md nem segredos. Vazio fora de repo git."""
    r = subprocess.run(["git", "-C", str(cwd), "status", "--porcelain", "-uall"],
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


def kf_por_sincronizar(cwd):
    """Mensagem de bloqueio se o diff altera ficheiros do motor cuja cópia no pacote kaizen-flow difere; senão ''."""
    core = kf_ligados.core_dir()
    if core is None:
        return ""
    nomes = kf_ligados.tocados(changed_paths(cwd), core)
    difs = kf_ligados.fora_de_sincronia(Path(cwd) / "scripts", core, nomes)
    if not difs:
        return ""
    return f"kaizen-flow fora de sincronia ({', '.join(difs)}): correr /kaizen-sync e repetir o fecho"


def write_commit(cwd, slug, subject, paths):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(cwd) / f"COMMIT_{stamp}.md"
    stage = "\n".join(f"git add {p}" for p in paths)
    out.write_text(
        f"## Mensagem\n\n```\n{subject}\n\nFecha o SP {slug} (gates verdes, sp-fechar.py).\n```\n\n"
        f"## Stage\n\n```\n{stage}\n```\n\n"
        f"## Fora do commit\n\nNada além do que o git status mostrava; rever antes de confirmar.\n",
        encoding="utf-8")
    return out


def worktree_hint(cwd, slug):
    """Se `cwd` é uma worktree (não o checkout principal), o passo que falta depois do commit."""
    def git(*a):
        r = kf_git.run(cwd, *a, run=subprocess.run)
        return r.stdout.strip() if r.returncode == 0 else None
    gd, common = git("rev-parse", "--path-format=absolute", "--git-dir"), git("rev-parse", "--path-format=absolute", "--git-common-dir")
    if not gd or not common or gd == common:
        return None
    return (f"WORKTREE: depois do commit: python -I scripts/sb-worktree.py merge {slug} && "
            f"python -I scripts/sb-worktree.py clean {slug}")


FILA_ESTADO = Path.home() / ".claude" / "sp-fila-estado.json"


def em_fila(slug, estado=None):
    """True se `slug` é uma sessão lançada pela fila (consta de `sessoes` no estado)."""
    try:
        return slug in json.loads(Path(estado or FILA_ESTADO).read_text(encoding="utf-8")).get("sessoes", {})
    except (OSError, ValueError, AttributeError):
        return False


def seguinte(root, slug, project=None, fila=False):
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
    if all(s.status == "Done" for s in irmaos):
        return (f"ÚLTIMO FILHO: fechar a mãe {kid.parent} numa worktree, nunca no checkout principal: "
                f"sb-worktree.py ensure {kid.parent} → sp-move.py {kid.parent} done → commit → sb-worktree.py merge {kid.parent} "
                f"(manual: AskUserQuestion «fechar?»; auto: fechar sozinho)")
    return f"SEGUINTE: nenhum filho elegível de {kid.parent} (os restantes dependem de SPs por fechar)"


def fechar(root, slug, project=None, nxt=False, msg=None, budget=True, commit=True, commit_dir=".", testes=True, sem_prova=None):
    """Corre o fecho. Devolve (rc, linhas)."""
    t_total = time.monotonic()
    sp = find_doing(root, slug, project)
    lines = []
    rc, text = passo("gates", run_gates, sp)
    lines.append(text)
    if rc:
        return rc, lines + [f"{slug}: gate vermelho, SP continua em Doing"]
    if testes and not sp_gates.parse_gates(sp.path.read_text(encoding="utf-8")):
        rc, text = passo("test-fast", run_fast)
        lines.append(text)
        if rc:
            return 1, lines + [f"{slug}: test-fast vermelho, SP continua em Doing"]
    faltas = avisos(sp.path.read_text(encoding="utf-8"))
    if faltas and not sem_prova:
        return 1, lines + faltas + [f"{slug}: sem prova/reflect, SP continua em Doing (registar, ou --sem-prova \"motivo\")"]
    if faltas:
        registar_dispensa(sp.path, sem_prova)
        lines += [f.replace("AVISO", "DISPENSADO") for f in faltas]
    if commit:
        bloqueio = kf_por_sincronizar(commit_dir)
        if bloqueio:
            return 1, lines + [bloqueio, f"{slug}: kaizen-flow por sincronizar, SP continua em Doing"]
    if budget:
        rc, text = passo("context-budget", run_budget)
        lines.append(text)
        if rc:
            return 1, lines + [f"{slug}: orçamento de contexto excedido, SP continua em Doing"]
    fila = em_fila(slug)
    if nxt and fila:
        return 1, lines + [f"{slug}: sessão da fila, --next não se aplica (o driver lança o seguinte)"]
    if nxt:
        lines.append(sp_move.advance(root, slug, sp.project))
    else:
        lines.append(sp_move.move(root, slug, "done", sp.project))
    prox = "" if nxt else seguinte(root, slug, sp.project, fila)
    if prox:
        lines.append(prox)
    if commit:
        paths = changed_paths(commit_dir)
        if paths:
            lines.append(f"COMMIT: {write_commit(commit_dir, slug, msg or f'vault: fecha {slug}', paths)}")
        else:
            lines.append("COMMIT: nada para stage (sem alterações ou fora de repo git)")
    hint = worktree_hint(commit_dir, slug)
    if hint:
        lines.append(hint)
    print(f"[sp-fechar] total {time.monotonic() - t_total:.1f}s", file=sys.stderr, flush=True)
    return 0, lines


def main(argv=None):
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
    try:
        rc, lines = fechar(args.root, args.slug, args.project, args.next, args.msg,
                           not args.sem_budget, not args.sem_commit, args.commit_dir,
                           not args.sem_testes, args.sem_prova)
    except (FecharError, sp_move.SpMoveError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    import kf_errlog
    sys.exit(kf_errlog.executar("sp-fechar", main))
