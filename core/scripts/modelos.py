"""Modelo/effort por papel (sp-autor, michi-exec, michi-leve): única fonte em .claude/modelos.json.

Uso: python -I scripts/modelos.py [--config F] list | get <papel> [--json|--cadeia] | michi <nivel> [--json] | args <papel>
                                  | set <papel> <modelo|alias> [--effort low|medium|high|xhigh|max]
                                  | sync [--check]
`sync` escreve model:/effort: no frontmatter dos ficheiros em "alvos" (por papel); `set` corre-o no fim.
rc: 0 ok; 1 sync --check com drift; 2 papel/effort inválido, config ou alvo em falta/ilegível
"""
import argparse
import json
import sys
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / ".claude" / "modelos.json"
EFFORTS = ("low", "medium", "high", "xhigh", "max")


class ModelosError(Exception):
    pass


def load(path=DEFAULT):
    try:
        data = json.loads(Path(path).read_bytes().decode("utf-8"))
    except FileNotFoundError:
        raise ModelosError(f"config não encontrada: {path}")
    except (ValueError, UnicodeDecodeError) as e:
        raise ModelosError(f"config inválida ({path}): {e}")
    if not isinstance(data.get("papeis"), dict):
        raise ModelosError(f"config sem 'papeis': {path}")
    return data


def papel(data, nome):
    p = data["papeis"].get(nome)
    if not isinstance(p, dict) or not p.get("model"):
        raise ModelosError(f"papel desconhecido: {nome} (há: {', '.join(data['papeis'])})")
    return p


MICHI_DEFAULT = {"simples": "michi-leve", "default": "michi-exec", "complexo": "michi-complexo"}


def cadeia(data, nome):
    """Modelo principal do papel seguido do `fallback` (ordem de tentativa)."""
    p = papel(data, nome)
    fb = p.get("fallback") or []
    return [p["model"], *[m for m in fb if m != p["model"]]]


def michi(data, nivel):
    """Resolve o nível do michi (simples|default|complexo) para {model, effort}; effort sempre low.
    Nível desconhecido ou vazio -> default; devolve (dict, aviso|None)."""
    mapa = {**MICHI_DEFAULT, **(data.get("michi_modelo") or {})}
    aviso = None
    if nivel not in mapa:
        aviso = f"aviso: nível michi '{nivel}' desconhecido ({', '.join(mapa)}); a usar default"
        nivel = "default"
    nome = mapa[nivel]
    if nome not in data["papeis"]:
        aviso = f"aviso: papel '{nome}' em falta em modelos.json; a usar michi-exec"
        nome = "michi-exec"
    return {"model": papel(data, nome)["model"], "effort": "low"}, aviso


def cli_args(nome, path=DEFAULT):
    """Lista de flags para `claude` (ex.: ['--model', 'claude-sonnet-5-5', '--effort', 'medium'])."""
    p = papel(load(path), nome)
    out = ["--model", p["model"]]
    if p.get("effort"):
        out += ["--effort", p["effort"]]
    return out


def resolve(data, modelo):
    """Alias -> ID; ID desconhecido devolve-se tal como veio, com aviso se não parecer um ID."""
    aliases = data.get("aliases", {})
    if modelo in aliases:
        return aliases[modelo], None
    if modelo.startswith("claude-"):
        return modelo, None
    return modelo, f"aviso: '{modelo}' não é alias ({', '.join(aliases)}) nem ID claude-*; gravado tal como está"


def save(path, data):
    raw = Path(path).read_bytes()
    eol = b"\r\n" if b"\r\n" in raw else b"\n"
    body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    Path(path).write_bytes(body.replace(b"\n", eol) + eol)


def _set_key(fm, key, value, eol):
    """Substitui ou acrescenta `key: value` (nível de topo) no bloco de frontmatter (bytes)."""
    linha = f"{key}: {value}".encode("utf-8")
    linhas = fm.split(eol)
    for i, l in enumerate(linhas):
        if l.startswith(key.encode() + b":"):
            linhas[i] = linha
            return eol.join(linhas)
    return eol.join(linhas + [linha])


def render(raw, p):
    """Devolve o ficheiro com `model:`/`effort:` do papel no frontmatter; resto intacto."""
    eol = b"\r\n" if b"\r\n" in raw else b"\n"
    abre = b"---" + eol
    if not raw.startswith(abre):
        raise ModelosError("ficheiro sem frontmatter")
    fim = raw.find(eol + b"---", len(abre) - len(eol))
    if fim < 0:
        raise ModelosError("frontmatter sem fecho")
    fm = raw[len(abre):fim]
    fm = _set_key(fm, "model", p["model"], eol)
    if p.get("effort"):
        fm = _set_key(fm, "effort", p["effort"], eol)
    return abre + fm + raw[fim:]


def sync(path, check=False):
    """Aplica os papéis aos ficheiros em `alvos` (caminhos relativos à raiz do repo).
    Devolve a lista de ficheiros que diferiam (escritos, ou só listados com check)."""
    path = Path(path)
    data = load(path)
    root = path.resolve().parent.parent
    diff = []
    for nome, ficheiros in data.get("alvos", {}).items():
        p = papel(data, nome)
        for rel in ficheiros:
            f = root / rel
            try:
                raw = f.read_bytes()
            except FileNotFoundError:
                raise ModelosError(f"alvo não encontrado: {rel}")
            try:
                novo = render(raw, p)
            except ModelosError as e:
                raise ModelosError(f"{rel}: {e}")
            if novo != raw:
                diff.append(rel)
                if not check:
                    f.write_bytes(novo)
    return diff


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Modelo/effort por papel")
    ap.add_argument("--config", default=str(DEFAULT))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    g = sub.add_parser("get")
    g.add_argument("papel")
    g.add_argument("--json", action="store_true")
    g.add_argument("--cadeia", action="store_true")
    m = sub.add_parser("michi")
    m.add_argument("nivel", nargs="?", default="")
    m.add_argument("--json", action="store_true")
    a = sub.add_parser("args")
    a.add_argument("papel")
    s = sub.add_parser("set")
    s.add_argument("papel")
    s.add_argument("modelo")
    s.add_argument("--effort")
    y = sub.add_parser("sync")
    y.add_argument("--check", action="store_true")
    ns = ap.parse_args(argv)

    try:
        data = load(ns.config)
        if ns.cmd == "list":
            for nome, p in data["papeis"].items():
                print(f"{nome:<12} {p.get('model', ''):<22} {p.get('effort', '')}")
        elif ns.cmd == "get":
            p = papel(data, ns.papel)
            if ns.cadeia:
                print(chr(10).join(cadeia(data, ns.papel)))
            else:
                print(json.dumps(p) if ns.json else p["model"])
        elif ns.cmd == "michi":
            r, aviso = michi(data, ns.nivel)
            if aviso:
                print(aviso, file=sys.stderr)
            print(json.dumps(r) if ns.json else r["model"])
        elif ns.cmd == "args":
            print(" ".join(cli_args(ns.papel, ns.config)))
        elif ns.cmd == "set":
            p = papel(data, ns.papel)
            if ns.effort is not None and ns.effort not in EFFORTS:
                raise ModelosError(f"effort inválido: {ns.effort} (válidos: {'|'.join(EFFORTS)})")
            model, aviso = resolve(data, ns.modelo)
            if aviso:
                print(aviso, file=sys.stderr)
            p["model"] = model
            if ns.effort:
                p["effort"] = ns.effort
            save(ns.config, data)
            print(f"{ns.papel}: {model} / {p.get('effort', '')}")
            for rel in sync(ns.config):
                print(f"sync: {rel}")
        elif ns.cmd == "sync":
            diff = sync(ns.config, check=ns.check)
            for rel in diff:
                print(f"{'difere' if ns.check else 'sync'}: {rel}")
            if ns.check and diff:
                print("frontmatter diverge de modelos.json: correr `modelos.py sync`", file=sys.stderr)
                return 1
    except ModelosError as e:
        print(e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
