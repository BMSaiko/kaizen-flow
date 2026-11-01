#!/usr/bin/env python3
"""Corre os gates declarados no frontmatter de um SP, por ordem, e pára no primeiro vermelho.

Só lê o campo `gates:` do frontmatter (nunca o corpo do SP). Formato:
  gates:
    - cmd: python -I scripts/test_sp_list.py
      cwd: .          # opcional, defeito = diretório de trabalho atual
      timeout: 300    # opcional, segundos, defeito 300
      inputs: a/*.py, b.md   # opcional, globs (relativos a cwd): sem mudança desde a última corrida verde, o gate é saltado
RC 0 = todos verdes (ou SP sem gates); 1 = gate vermelho/timeout; 2 = gate inválido ou proibido (nada corre).

Uso:
  python -I scripts/sp-gates.py <caminho.md>          # incremental: salta gates verdes com inputs iguais
  python -I scripts/sp-gates.py <caminho.md> --full   # corre todos (o fecho, sp-fechar.py, usa sempre isto)
  python -I scripts/sp-gates.py --sugerir <repo>      # gates por tipo de repo (Node, Python, Tauri, vault), bloco `gates:` pronto
Ordem da fase 5: gates -> harden -> pentest -> review (michi/references/michi-gates.md).
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402

DEFAULT_TIMEOUT = 300
CACHE_PATH = Path(__file__).resolve().parent.parent / ".sp-gates-cache.json"
FORBIDDEN = (
    (re.compile(r"(?<![\w-])--force(?![\w-])|\bgit\s+push\b.*\s-f\b"), "--force"),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "git reset --hard"),
    (re.compile(r"\bgit\s+clean\b.*\s-\w*f"), "git clean -f"),
    (re.compile(r"\bgit\s+add\s+(-A\b|--all\b|\.(\s|$))"), "git add -A/."),
    (re.compile(r"\.env(\.|\b)|\.(key|pem|p12|pfx)\b|\bid_rsa|\bsecrets?\.|\.secrets"), "leitura de segredos"),
)


def detect_gates(repo):
    """Comandos de gate sugeridos para o tipo de repo em `repo` (lista de `cmd`, por ordem)."""
    r = Path(repo)
    if (r / "tools" / "vault-mcp").exists() and (r / "scripts" / "context-budget.py").exists():
        return ["python -I scripts/context-budget.py", "python -I scripts/test-fast.py"]
    cmds = []
    if (r / "src-tauri" / "Cargo.toml").exists():
        cmds.append("cargo check --manifest-path src-tauri/Cargo.toml")
    if (r / "package.json").exists():
        try:
            scripts = json.loads((r / "package.json").read_text(encoding="utf-8")).get("scripts", {})
        except (OSError, ValueError):
            scripts = {}
        cmds += [f"npm run {n}" for n in ("lint", "typecheck", "build") if n in scripts]
        if "test" in scripts:
            cmds.append("npm test")
    if (r / "pyproject.toml").exists() or (r / "pytest.ini").exists() or (r / "setup.cfg").exists():
        cmds.append("python -m pytest -q")
    return cmds


def suggestion(repo):
    """Bloco `gates:` de frontmatter para o repo, ou texto vazio se o tipo é desconhecido."""
    cmds = detect_gates(repo)
    if not cmds:
        return ""
    return "gates:\n" + "\n".join(f"  - cmd: {c}\n    timeout: 300" for c in cmds)


def forbidden(cmd):
    """Devolve o nome da proibição em que `cmd` cai, ou None."""
    for rx, name in FORBIDDEN:
        if rx.search(cmd):
            return name
    return None


def parse_gates(text):
    gates, in_gates, current = [], False, None
    for line in kaizen_engine.frontmatter_lines(text):
        if re.match(r"^gates:\s*$", line):
            in_gates = True
            continue
        if not in_gates:
            continue
        if line and not line[0].isspace():
            break
        m = re.match(r"^\s*-\s*cmd:\s*(.*?)\s*$", line)
        if m:
            current = {"cmd": m.group(1), "cwd": ".", "timeout": DEFAULT_TIMEOUT, "inputs": []}
            gates.append(current)
            continue
        m = re.match(r"^\s+(cwd|timeout|inputs):\s*(.*?)\s*$", line)
        if m and current is not None:
            if m.group(1) == "timeout":
                current["timeout"] = int(m.group(2))
            elif m.group(1) == "inputs":
                current["inputs"] = [x.strip().strip("'\"") for x in m.group(2).split(",") if x.strip()]
            else:
                current["cwd"] = m.group(2).strip("'\"")
    return gates


def problems(gates):
    found, seen = [], set()
    for i, g in enumerate(gates, 1):
        cmd = g["cmd"].strip()
        if not cmd:
            found.append(f"gate {i}: comando vazio")
            continue
        if cmd in seen:
            found.append(f"gate {i}: comando duplicado '{cmd}'")
        seen.add(cmd)
        bad = forbidden(cmd)
        if bad:
            found.append(f"gate {i}: comando proibido ({bad}): {cmd}")
    return found


def input_hash(g):
    """Hash do comando + conteúdo dos ficheiros que casam com `inputs`; None se não há inputs."""
    if not g.get("inputs"):
        return None
    base = Path(g["cwd"])
    h = hashlib.sha256(g["cmd"].encode("utf-8"))
    files = sorted({p for pat in g["inputs"] for p in base.glob(pat) if p.is_file()})
    for p in files:
        h.update(str(p.relative_to(base)).encode("utf-8"))
        h.update(p.read_bytes())
    return h.hexdigest()


def _load_cache(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run(gates, cache_path=None):
    """Corre por ordem; pára no primeiro rc≠0 ou timeout. Devolve os resultados corridos.

    Com `cache_path`, um gate com `inputs` cujo hash coincide com a última corrida verde é saltado
    (resultado com `cached`). Sem `cache_path` corre sempre tudo.
    """
    cache = _load_cache(cache_path) if cache_path else {}
    results = []
    for g in gates:
        digest = input_hash(g) if cache_path else None
        key = f"{Path(g['cwd']).resolve()}::{g['cmd']}"
        if digest and cache.get(key) == digest:
            results.append({"cmd": g["cmd"], "rc": 0, "timeout": False, "secs": 0, "tail": "", "cached": True})
            continue
        start = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.run(g["cmd"], shell=True, cwd=g["cwd"], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=g["timeout"])
            rc, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired as exc:
            rc, timed_out = 124, True
            out = (exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else exc.stdout) or ""
        results.append({"cmd": g["cmd"], "rc": rc, "timeout": timed_out,
                        "secs": round(time.monotonic() - start, 1),
                        "tail": "\n".join(out.strip().splitlines()[-10:])})
        if digest:
            if rc == 0:
                cache[key] = digest
            else:
                cache.pop(key, None)
        if rc != 0:
            break
    if cache_path:
        try:
            Path(cache_path).write_text(json.dumps(cache, indent=1), encoding="utf-8")
        except OSError:
            pass
    return results


def summary(results):
    lines = []
    for r in results:
        flag = " TIMEOUT" if r["timeout"] else ""
        when = "cache" if r.get("cached") else f"{r['secs']} s"
        lines.append(f"- `{r['cmd']}` rc={r['rc']}{flag} ({when})")
        if r["tail"]:
            lines += [f"    {t}" for t in r["tail"].splitlines()]
    return "\n".join(lines)


def table(results, total):
    """Tabela final `# | comando | RC | estado`; gates não corridos (após um vermelho) ficam «não correu»."""
    rows = ["| # | comando | RC | estado |", "|---|---|---|---|"]
    for i, r in enumerate(results, 1):
        state = "TIMEOUT" if r["timeout"] else ("cache" if r.get("cached") else ("verde" if r["rc"] == 0 else "VERMELHO"))
        rows.append(f"| {i} | `{r['cmd']}` | {r['rc']} | {state} |")
    rows += [f"| {i} | — | — | não correu |" for i in range(len(results) + 1, total + 1)]
    return "\n".join(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Corre os gates do frontmatter de um SP")
    ap.add_argument("path", nargs="?")
    ap.add_argument("--sugerir", metavar="REPO", help="imprime o bloco gates: sugerido para o tipo de repo")
    ap.add_argument("--full", action="store_true", help="ignora a cache: corre todos os gates")
    args = ap.parse_args(argv)
    if args.sugerir:
        block = suggestion(args.sugerir)
        print(block or "tipo de repo desconhecido: declarar os gates à mão", file=None if block else sys.stderr)
        return 0 if block else 1
    if not args.path:
        ap.error("falta o caminho do SP (ou --sugerir REPO)")
    try:
        text = Path(args.path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"{args.path}: erro de leitura ({exc.__class__.__name__})", file=sys.stderr)
        return 2
    gates = parse_gates(text)
    if not gates:
        print("sem gates declarados no SP")
        return 0
    bad = problems(gates)
    if bad:
        print("\n".join(bad), file=sys.stderr)
        return 2
    results = run(gates, cache_path=None if args.full else CACHE_PATH)
    print(summary(results))
    print(table(results, len(gates)))
    return 0 if all(r["rc"] == 0 for r in results) and len(results) == len(gates) else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
