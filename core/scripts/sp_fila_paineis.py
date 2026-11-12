"""Sp-fila com painéis: um painel por SP elegível, com o modelo do SP, título no separador e teto global de 3.

Por SP: (verificação de master) → registo `pendente` → vaga (`reclamar_vaga`) → `sb-worktree ensure` →
`sp-move doing` na worktree → painel novo lá → título → `/michi --auto <slug> ...` → registo do painel.
Sem vaga o SP fica `pendente` e nada abre. Uma falha depois da vaga marca `falhou` (liberta a vaga), fecha
o painel se chegou a abrir e deixa a worktree intacta. Só stdlib.

Uso: módulo importado por sp_fila_execucao.py e sp-fila.py; sem execução direta
rc: n/a
"""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_painel_estado as pe  # noqa: E402
from painel_backend import enviar_prompt  # noqa: E402
from sp_fila_estado import REPO, SCRIPTS, run_hidden  # noqa: E402

try:
    import modelos  # noqa: E402
except ImportError:  # kaizen-flow sem modelos.py
    modelos = None

MODELOS = modelos.DEFAULT if modelos else None  # .claude/modelos.json; os testes trocam-no
_FM = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.S)
_MICHI_MODELO = re.compile(r"^michi_modelo:\s*(\S+)\s*$", re.M)


def nome_worktree(slug):
    """Nome curto da worktree, igual a `sb-worktree.name_of`: minúsculas, `-`, até 31 caracteres."""
    return re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")[:31].rstrip("-")


def nivel_sp(path):
    """`michi_modelo` do frontmatter do SP (simples|default|complexo); None se faltar o campo ou o ficheiro."""
    try:
        texto = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    m = _FM.search(texto)
    n = m and _MICHI_MODELO.search(m.group(1))
    return n.group(1) if n else None


def modelo_sp(path):
    """{model, effort} do nível michi do SP (`modelos.michi`; sem nível = default)."""
    if modelos is None:
        raise RuntimeError("modelos.py em falta: sem modelo para o painel")
    return modelos.michi(modelos.load(MODELOS), nivel_sp(path) or "default")[0]


def comando_painel(path):
    """Comando do painel: `claude --model <M> --effort <E>` com o modelo do SP."""
    m = modelo_sp(path)
    return ["claude", "--model", m["model"], "--effort", m["effort"]]


def prompt_painel(slug, worktree):
    """Prompt numa só linha (o Enter enviado ao painel submete-o): michi em modo auto na worktree, atalhos proibidos e `sp-estado` no fim."""
    return (f"/michi --auto {slug} (painel da fila /sp-fila) Worktree já criada: {worktree}; lê e escreve só lá. "
            "Nunca: `sp-fechar.py --sem-budget`, `--sem-testes` ou semelhantes, merge, `sb-worktree clean`, `/kaizen-sync`, "
            "abrir painéis ou `sp-handoff --launch`. Ao terminar ou parar, corre por último "
            f"`python -I scripts/sp-estado.py {slug} <estado> --msg '<resumo numa linha>'` "
            "com <estado> = done (SP em Done na worktree), pergunta (decisão do user em falta), bloqueado (gate ou erro) ou falhou.")


def titulo_livre(slug, existentes):
    """Título do separador: o slug; se já houver, `slug-2`, `slug-3`, ..."""
    usados = set(existentes)
    if slug not in usados:
        return slug
    n = 2
    while f"{slug}-{n}" in usados:
        n += 1
    return f"{slug}-{n}"


def garantir_fila(estado, root=None):
    """Fila de painéis do programa do estado (reusada se já existe) ou uma nova sem programa; devolve o fila-id."""
    programa = estado.get("programa")
    if programa:
        try:
            return pe.criar_fila(programa, root=root)
        except pe.ErroEstado as e:
            if "já existe" not in str(e):
                raise
            return pe.fila_id(programa)
    return pe.criar_fila(None, root=root)


def sp_move_na_worktree(root, worktree, alvo):
    """`sp-move doing` da cópia da worktree do filho, com cwd lá: o Doing nasce só na worktree (master e o ramo do orquestrador intactos).

    A raiz dos SPs é a mesma, relativa à worktree; fora do repo (testes) mantém-se `root`."""
    wt = Path(worktree)
    try:
        raiz = wt / Path(root).resolve().relative_to(REPO.resolve())
    except ValueError:
        raiz = Path(root)
    return [sys.executable, "-I", str(wt / "scripts" / "sp-move.py"), "--root", str(raiz), "--project", alvo.project, alvo.slug, "doing"]


def _sob_repo(path):
    try:
        Path(path).resolve().relative_to(REPO.resolve())
        return True
    except ValueError:
        return False


def _em_master(path, run):
    """True se o ficheiro do SP está commitado em master (o `ensure` parte de master: sem isto a worktree não o tem)."""
    p = Path(path)
    r = run(["git", "-C", str(p.parent), "ls-tree", "--name-only", "master", "--", p.name],
            capture_output=True, text=True, encoding="utf-8")
    return r.returncode == 0 and bool((r.stdout or "").strip())


def _ensure(slug, run):
    """Worktree do SP (`sb-worktree ensure`, última linha da saída); RuntimeError com o stderr se falhar."""
    r = run([sys.executable, "-I", str(SCRIPTS / "sb-worktree.py"), "ensure", slug], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"sb-worktree ensure {slug}: {(r.stderr or r.stdout or '').strip()}")
    linhas = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
    if not linhas:
        raise RuntimeError(f"sb-worktree ensure {slug}: sem caminho da worktree na saída")
    return linhas[-1]


def _titulos(backend):
    f = getattr(backend, "titulos", None)
    try:
        return list((f() if f else {}).values())
    except Exception:  # noqa: BLE001 — sem lista de títulos fica o slug
        return []


def _por_titulo(backend, pane, texto):
    f = getattr(backend, "titulo", None)
    if f:
        f(pane, texto)


def _lancar_um(alvo, fila, backend, run, sleep, verificar, root, estado_root):
    res = {"slug": alvo.slug, "estado": None, "modelo": None, "worktree": None, "titulo": None, "msg": None}
    if verificar and not _em_master(alvo.path, run):
        msg = f"commitar {alvo.path} em master antes de lançar (a worktree parte de master)"
        pe.registar(fila, alvo.slug, root=estado_root)
        pe.transitar(alvo.slug, "falhou", msg=msg, fila=fila, root=estado_root)
        return {**res, "estado": "falhou", "msg": msg}
    try:
        cmd = comando_painel(alvo.path)
    except Exception as e:  # noqa: BLE001 — config de modelos inválida: falha só este SP
        msg = f"sem modelo para {alvo.slug}: {e}"
        pe.registar(fila, alvo.slug, root=estado_root)
        pe.transitar(alvo.slug, "falhou", msg=msg, fila=fila, root=estado_root)
        return {**res, "estado": "falhou", "msg": msg}
    modelo = cmd[2]
    res["modelo"] = modelo
    pe.registar(fila, alvo.slug, root=estado_root, modelo=modelo)
    if not pe.reclamar_vaga(alvo.slug, fila=fila, root=estado_root, modelo=modelo):
        return {**res, "estado": "pendente", "msg": f"sem vaga: {pe.MAX_PARALELO} painéis ativos no total das filas"}
    pane = None
    try:
        wt = _ensure(alvo.slug, run)
        res["worktree"] = wt
        r = run(sp_move_na_worktree(root or alvo.path.parents[3], wt, alvo), capture_output=True, text=True, encoding="utf-8", cwd=wt)
        if r.returncode != 0:
            raise RuntimeError(f"sp-move {alvo.slug} doing: {(r.stderr or r.stdout or '').strip()}")
        pe.registar(fila, alvo.slug, root=estado_root, worktree=wt)
        texto = prompt_painel(alvo.slug, wt)
        interativo = getattr(backend, "interativo", True)
        pane = backend.abrir(cmd if interativo else cmd + [texto], wt)
        titulo = titulo_livre(alvo.slug, _titulos(backend))
        _por_titulo(backend, pane, titulo)
        res["titulo"] = titulo
        if interativo:
            enviar_prompt(backend, pane, texto, run, sleep)
        pe.registar(fila, alvo.slug, root=estado_root, pane=str(pane))
    except Exception as e:  # noqa: BLE001 — qualquer falha deste SP liberta a vaga e não pára os outros
        msg = f"erro a lançar {alvo.slug}: {e}"
        pe.transitar(alvo.slug, "falhou", msg=msg, fila=fila, root=estado_root)
        if pane is not None:
            try:
                backend.fechar(pane)
            except Exception:  # noqa: BLE001 — o registo já diz falhou
                pass
        return {**res, "estado": "falhou", "msg": msg}
    return {**res, "estado": "a-correr"}


def lancar(alvos, fila, backend, run=run_hidden, sleep=time.sleep, verificar_master=None, root=None, estado_root=None):
    """Lança um painel por alvo (obj com `slug`, `path`, `project`) na fila `fila`; devolve um resultado por alvo, sem `pane`.

    `verificar_master`: None = só para SPs dentro do repo. `root`: raiz dos SPs para o `sp-move` (defeito: a do próprio SP).
    `estado_root`: pasta do estado das filas (defeito: `SP_FILA_ROOT` ou `~/.claude/sp-fila`)."""
    out = []
    for alvo in alvos:
        verificar = _sob_repo(alvo.path) if verificar_master is None else verificar_master
        out.append(_lancar_um(alvo, fila, backend, run, sleep, verificar, root, estado_root))
    return out


def raiz_principal(repo=REPO):
    """Checkout principal de `repo`: numa worktree, `.git` é um ficheiro `gitdir: <principal>/.git/worktrees/<nome>`."""
    git = Path(repo) / ".git"
    if git.is_file():
        m = re.match(r"gitdir:\s*(.+)", git.read_text(encoding="utf-8").strip())
        if m:
            alvo = Path(m.group(1).strip())
            alvo = alvo if alvo.is_absolute() else (Path(repo) / alvo).resolve()
            if alvo.parent.name == "worktrees":
                return alvo.parent.parent.parent
    return Path(repo)


def worktree_prevista(slug, repo=REPO):
    """Caminho que `sb-worktree.py ensure` daria: `<pai do checkout principal>\\code-wt\\sb-<nome>`."""
    return str(raiz_principal(repo).parent / "code-wt" / f"sb-{nome_worktree(slug)}")


def plano_dry_run(alvos, maximo=None):
    """O que `lancar` faria, sem efeitos: [{slug, modelo, worktree}]; além de `maximo`, `{slug, pendente: True}`."""
    plano = []
    for i, alvo in enumerate(alvos):
        if maximo is not None and i >= maximo:
            plano.append({"slug": alvo.slug, "pendente": True})
            continue
        try:
            modelo = modelo_sp(alvo.path)["model"]
        except Exception as e:  # noqa: BLE001
            modelo = f"? ({e})"
        plano.append({"slug": alvo.slug, "modelo": modelo, "worktree": worktree_prevista(alvo.slug)})
    return plano


def render_dry_run(plano):
    """Uma linha por SP: `slug · modelo · worktree`, ou `slug · pendente (sem vaga)`."""
    return "\n".join(f"{p['slug']} · pendente (sem vaga)" if p.get("pendente") else f"{p['slug']} · {p['modelo']} · {p['worktree']}"
                     for p in plano)
