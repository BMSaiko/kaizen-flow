#!/usr/bin/env python3
"""Corre os gates declarados no frontmatter de um SP, por ordem, e pára no primeiro vermelho.

Só lê o campo `gates:` do frontmatter (nunca o corpo do SP). Formato:
  gates:
    - cmd: python -I scripts/test_sp_list.py
      cwd: .          # opcional, defeito = diretório de trabalho atual
      timeout: 300    # opcional, segundos, defeito 300
RC 0 = todos verdes (ou SP sem gates); 1 = gate vermelho/timeout; 2 = gate inválido ou proibido (nada corre).

Uso:
  python -I scripts/sp-gates.py <caminho.md>
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_TIMEOUT = 300
FORBIDDEN = (
    (re.compile(r"(?<![\w-])--force(?![\w-])|\bgit\s+push\b.*\s-f\b"), "--force"),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "git reset --hard"),
    (re.compile(r"\bgit\s+clean\b.*\s-\w*f"), "git clean -f"),
    (re.compile(r"\bgit\s+add\s+(-A\b|--all\b|\.(\s|$))"), "git add -A/."),
    (re.compile(r"\.env(\.|\b)|\.(key|pem|p12|pfx)\b|\bid_rsa|\bsecrets?\.|\.secrets"), "leitura de segredos"),
)


def forbidden(cmd):
    """Devolve o nome da proibição em que `cmd` cai, ou None."""
    for rx, name in FORBIDDEN:
        if rx.search(cmd):
            return name
    return None


def _frontmatter_lines(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    out = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        out.append(line)
    return out


def parse_gates(text):
    gates, in_gates, current = [], False, None
    for line in _frontmatter_lines(text):
        if re.match(r"^gates:\s*$", line):
            in_gates = True
            continue
        if not in_gates:
            continue
        if line and not line[0].isspace():
            break
        m = re.match(r"^\s*-\s*cmd:\s*(.*?)\s*$", line)
        if m:
            current = {"cmd": m.group(1), "cwd": ".", "timeout": DEFAULT_TIMEOUT}
            gates.append(current)
            continue
        m = re.match(r"^\s+(cwd|timeout):\s*(.*?)\s*$", line)
        if m and current is not None:
            current[m.group(1)] = int(m.group(2)) if m.group(1) == "timeout" else m.group(2).strip("'\"")
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


def run(gates):
    """Corre por ordem; pára no primeiro rc≠0 ou timeout. Devolve os resultados corridos."""
    results = []
    for g in gates:
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
        if rc != 0:
            break
    return results


def summary(results):
    lines = []
    for r in results:
        flag = " TIMEOUT" if r["timeout"] else ""
        lines.append(f"- `{r['cmd']}` rc={r['rc']}{flag} ({r['secs']} s)")
        if r["tail"]:
            lines += [f"    {t}" for t in r["tail"].splitlines()]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Corre os gates do frontmatter de um SP")
    ap.add_argument("path")
    args = ap.parse_args(argv)
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
    results = run(gates)
    print(summary(results))
    return 0 if all(r["rc"] == 0 for r in results) and len(results) == len(gates) else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
