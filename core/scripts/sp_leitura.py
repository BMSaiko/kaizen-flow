"""Leitura única de Super Prompts: frontmatter e secção por título, com o CRLF tratado num só sítio.

Substitui os regex e `split("---")` espalhados pelos scripts.

Uso: módulo importado (`import sp_leitura`); `frontmatter(texto)`, `campos(texto)`, `bloco(texto)`, `seccao(texto, titulo)`, `ler(caminho)`
rc: n/a
"""
import re
from pathlib import Path


def _lf(texto):
    return texto.replace("\r\n", "\n")


def bloco(texto):
    """Texto entre as cercas `---` do frontmatter ("" se não há frontmatter ou não fecha)."""
    m = re.match(r"---\n(.*?)\n---", _lf(texto), re.S)
    return m.group(1) if m else ""


def frontmatter(texto):
    """Campos do frontmatter como dict: sem comentários `# ...` nem aspas; sem frontmatter {}.

    Um frontmatter por fechar lê até ao fim do ficheiro (como o `kaizen_engine` sempre fez)."""
    linhas = texto.splitlines()
    if not linhas or linhas[0].strip() != "---":
        return {}
    fm = {}
    for linha in linhas[1:]:
        if linha.strip() == "---":
            break
        chave, sep, valor = linha.partition(":")
        if not sep or not chave.strip():
            continue
        fm[chave.strip()] = re.sub(r"\s+#.*$", "", valor.strip()).strip("'\"")
    return fm


def campos(texto):
    """Campos de topo do frontmatter, valor só com `strip` (aspas e comentários ficam); por fechar dá {}."""
    out = {}
    for linha in bloco(texto).splitlines():
        chave, sep, valor = linha.partition(":")
        if sep and not chave.startswith(" "):
            out[chave.strip()] = valor.strip()
    return out


def seccao(texto, titulo, *, maiusculas=True):
    """Corpo (sem `strip`) da primeira secção `## <titulo>...` até ao próximo `## `; "" se não existe.

    `titulo` casa por prefixo; `maiusculas=False` ignora a caixa."""
    flags = re.S | re.M | (0 if maiusculas else re.I)
    m = re.search(rf"^##\s+{re.escape(titulo)}[^\n]*\n(.*?)(?=^##\s|\Z)", texto, flags)
    return m.group(1) if m else ""


def ler(caminho):
    """`(frontmatter, texto)` do ficheiro `caminho` (UTF-8; o `read_text` já devolve o texto com LF)."""
    texto = Path(caminho).read_text(encoding="utf-8")
    return frontmatter(texto), texto
