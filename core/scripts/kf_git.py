"""Helper único para chamadas git: lista de argumentos (sem shell), sem janela no Windows e cache opcional em processo.

A cache nunca cobre estado que o script altera: quem muda branch/index/HEAD chama `invalidar()`.
"""
import subprocess

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_CACHE = {}


def _executar(argv, **kw):
    kw.setdefault("creationflags", NO_WINDOW)
    return subprocess.run(argv, **kw)


def invalidar():
    """Esquece tudo o que foi memorizado (chamar depois de checkout, commit, add, merge...)."""
    _CACHE.clear()


def run(repo, *args, run=_executar, cache=False):
    """`git -C repo args...` com texto utf-8; `cache=True` memoriza o resultado até `invalidar()`."""
    argv = ["git", "-C", str(repo), *args]
    chave = tuple(argv)
    if cache and chave in _CACHE:
        return _CACHE[chave]
    r = run(argv, capture_output=True, text=True, encoding="utf-8")
    if cache:
        _CACHE[chave] = r
    return r


def branch_atual(repo, run=_executar):
    return run_(repo, "rev-parse", "--abbrev-ref", "HEAD", run=run).stdout.strip()


def ficheiros_alterados(repo, run=_executar):
    r = run_(repo, "status", "--porcelain", "-uall", run=run)
    return [linha[3:].strip() for linha in r.stdout.splitlines() if linha.strip()]


def ficheiros_em_head(diretorio, run=_executar, cache=False):
    """Nomes dos ficheiros do diretório que estão no HEAD (uma chamada por diretório). None: sem git ou fora de repo."""
    try:
        r = run_(diretorio, "ls-tree", "--name-only", "HEAD", "./", run=run, cache=cache)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return {n for n in r.stdout.splitlines() if n.strip()}


run_ = run


def atras_de(repo, ref="master", run=_executar):
    """Nº de commits de `ref` que o HEAD ainda não tem (0 se falhar)."""
    r = run(["git", "-C", str(repo), "rev-list", "--count", f"HEAD..{ref}"], capture_output=True, text=True, encoding="utf-8")
    try:
        return int(r.stdout.strip()) if r.returncode == 0 else 0
    except ValueError:
        return 0


def ficheiros_em(repo, ref="master", run=_executar):
    """Caminhos versionados em `ref` (vazio se falhar)."""
    r = run(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", ref], capture_output=True, text=True, encoding="utf-8")
    return r.stdout.splitlines() if r.returncode == 0 else []
