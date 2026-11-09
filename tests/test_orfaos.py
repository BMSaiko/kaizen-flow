"""Teste de órfãos (vive em tests/ porque o sync reconstrói core/ a partir do vault): todo o script CLI de `core/scripts` tem de ter um chamador.

Chamador = outro ficheiro do pacote (script, skill, adaptador, `bin/`, doc) que menciona o nome.
O catálogo `docs/commands.md`/`docs/agent-commands.md` e o `CHANGELOG.md` não contam (listam tudo).
Alias fino obsoleto (docstring com `OBSOLETO`) fica isento: existe só para quem usa o nome antigo.
"""
import re
from pathlib import Path

PACOTE = Path(__file__).resolve().parent.parent
SCRIPTS = PACOTE / "core" / "scripts"
CATALOGO = {"commands.md", "agent-commands.md", "CHANGELOG.md"}
SUFIXOS = {".py", ".md", ".js", ".json", ".toml", ".sh", ".ps1", ".lua", ".txt"}
RAIZES = ("core", "bin", "adapters", "docs", "usage")


def candidatos():
    """CLIs (nome com hífen ou `__main__`), sem testes, módulos auxiliares nem aliases obsoletos."""
    out = []
    for p in sorted(SCRIPTS.glob("*.py")):
        if p.name.startswith("test_") or p.name.startswith("_"):
            continue
        texto = p.read_text(encoding="utf-8")
        doc = texto.split('"""', 2)[1] if texto.count('"""') >= 2 else ""
        if "__main__" not in texto or "OBSOLETO" in doc:
            continue
        out.append(p)
    return out


def ficheiros():
    for raiz in RAIZES:
        base = PACOTE / raiz
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if f.is_file() and f.suffix in SUFIXOS and "__pycache__" not in f.parts and f.name not in CATALOGO:
                yield f
    for nome in ("README.md", "package.json"):
        if (PACOTE / nome).is_file():
            yield PACOTE / nome


def orfaos():
    textos = {f: f.read_text(encoding="utf-8", errors="ignore") for f in ficheiros()}
    res = []
    for p in candidatos():
        nome = p.stem
        pad = re.compile(r"(?<![\w-])" + re.escape(nome) + r"(?:\.py)?(?![\w-])")
        if not any(
            pad.search(t) for f, t in textos.items()
            if f != p and f.name not in (f"test_{nome.replace('-', '_')}.py",)
        ):
            res.append(p.name)
    return res


def test_nenhum_script_orfao():
    lista = orfaos()
    assert not lista, "scripts sem chamador (ligar a um gatilho ou remover): " + ", ".join(lista)
