"""Índice de SPs: listagem e frontmatter com cache por processo (nunca em disco)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402

_LISTAS = {}
_FRONTMATTER = {}


def invalidar():
    """Esquece listagens e frontmatter; chamar depois de mover ou escrever um SP."""
    _LISTAS.clear()
    _FRONTMATTER.clear()


def _varrer(root):
    """([`*.md` ordenados], {pasta: mtime_ns}) sob `root`."""
    ficheiros, pastas = [], {}
    for pasta, subs, nomes in os.walk(root):
        pastas[pasta] = os.stat(pasta).st_mtime_ns
        ficheiros.extend(Path(pasta, n) for n in nomes if n.endswith(".md"))
    return sorted(ficheiros), pastas


def _fresca(pastas):
    try:
        return all(os.stat(p).st_mtime_ns == m for p, m in pastas.items())
    except OSError:
        return False


def listar(root):
    """Todos os `*.md` sob `root`, ordenados; a travessia repete-se só se alguma pasta mudou (mtime)."""
    chave = str(root)
    hit = _LISTAS.get(chave)
    if hit is None or not _fresca(hit[1]):
        hit = _LISTAS[chave] = _varrer(root)
    return list(hit[0])


def frontmatter(path):
    """Frontmatter de `path` (cópia); relido só se o ficheiro mudou (mtime/tamanho)."""
    path = Path(path)
    st = path.stat()
    sig = (st.st_mtime_ns, st.st_size)
    hit = _FRONTMATTER.get(str(path))
    if hit is None or hit[0] != sig:
        hit = (sig, kaizen_engine.parse_frontmatter(path.read_text(encoding="utf-8")))
        _FRONTMATTER[str(path)] = hit
    return dict(hit[1])
