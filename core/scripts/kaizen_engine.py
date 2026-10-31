"""Motor único do SP: frontmatter (parse/rewrite) e carregamento dos scripts com hífen.

Os scripts `sp-*` importam isto em vez de repetirem parsers e `importlib`.
"""
import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
    """Carrega `scripts/<name>.py` (nome com hífen incluído) uma só vez por processo."""
    key = name.replace("-", "_")
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


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
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fm = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if not sep or not key.strip():
            continue
        value = re.sub(r"\s+#.*$", "", value.strip()).strip("'\"")
        fm[key.strip()] = value
    return fm


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
