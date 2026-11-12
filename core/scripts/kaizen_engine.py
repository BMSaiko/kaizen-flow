"""Motor único do SP: frontmatter (parse/rewrite) e carregamento dos scripts com hífen.

Os scripts `sp-*` importam isto em vez de repetirem parsers e `importlib`.

Uso: módulo importado pelos scripts sp-* (`kaizen_engine.load(nome)`); sem execução direta
rc: n/a
"""
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sp_leitura  # noqa: E402
from sp_carregar import carregar  # noqa: E402


def load(name):
    """Carrega `scripts/<name>.py` (nome com hífen incluído) uma só vez por processo."""
    return carregar(HERE / f"{name}.py", name.replace("-", "_"))


def relocate(src, dst):
    """Move `src` para `dst` (cria a pasta): `git mv` se rastreado, senão `rename`."""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tracked = subprocess.run(
        ["git", "-C", str(src.parent), "ls-files", "--error-unmatch", src.name],
        capture_output=True,
    ).returncode == 0
    if tracked:
        subprocess.run(["git", "-C", str(src.parent), "mv", str(src), str(dst)], check=True, capture_output=True)
    else:
        src.rename(dst)


def frontmatter_lines(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    out = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        out.append(line)
    return out


def parse_frontmatter(text):
    return sp_leitura.frontmatter(text)


def parse_list(value):
    return [item.strip() for item in (value or "").strip("[]").split(",") if item.strip()]


def rewrite_fields(raw, fields, error):
    """Reescreve no frontmatter os campos de `fields` (todos têm de existir); `raw` e retorno são bytes.

    Falhas levantam `error(mensagem)`; o resto do ficheiro e o fim de linha ficam intactos.
    """
    lines = raw.decode("utf-8").splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise error("SP sem frontmatter")
    seen = set()
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            break
        name = lines[i].partition(":")[0]
        if name in fields and lines[i].startswith(f"{name}:"):
            eol = lines[i][len(lines[i].rstrip("\r\n")):]
            lines[i] = f"{name}: {fields[name]}{eol}"
            seen.add(name)
    else:
        raise error("frontmatter sem fecho")
    if seen != set(fields):
        raise error("frontmatter sem " + "/".join(fields))
    return "".join(lines).encode("utf-8")


def parse_permitir(value):
    """Allowlist `permitir:` (uma linha, comandos separados por `;`)."""
    return [c.strip() for c in (value or "").split(";") if c.strip()]


def precisa_perguntar(fm, acao):
    """True se `acao` ainda exige pergunta ao utilizador.

    `acao` = commit|push|pr (só `auto` dispensa) ou um comando (só dispensa se estiver em
    `permitir` e não for irreversível: o que `sp-gates.forbidden` apanha pergunta sempre).
    """
    if acao in ("commit", "push", "pr"):
        return fm.get(acao) != "auto"
    cmd = acao.strip()
    if load("sp-gates").forbidden(cmd):
        return True
    return cmd not in parse_permitir(fm.get("permitir"))
